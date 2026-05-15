"""
PatchCore Anomaly Detection — Pi 추론 (TorchScript CPU).

학습: Colab GPU 로 사전 학습 (notebooks/anomaly_patchcore_train.ipynb)
추론: Pi 의 PyTorch CPU 로 백본 forward + cdist

입력: BGR numpy 이미지 (H, W, 3) — OpenCV 형식
출력: anomaly score + heatmap + 결함 박스 리스트
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _load_torch():
    """torch import — 일반적으로 컨테이너에 깔려있음."""
    try:
        import torch  # noqa: F401
        return torch
    except ImportError:
        logger.warning("[PatchCore] torch 미설치 — Anomaly Detection 비활성화")
        return None


class PatchCoreDetector:
    """PatchCore 추론기. 한 번 로드하면 모듈 캐시처럼 재사용."""

    def __init__(
        self,
        model_path: str | Path,
        coreset_path: str | Path,
        meta_path: str | Path,
        score_threshold: Optional[float] = None,
    ):
        self.model_path = Path(model_path)
        self.coreset_path = Path(coreset_path)
        self.meta_path = Path(meta_path)
        self._score_threshold_override = score_threshold

        self._torch = None
        self._model = None
        self._coreset = None             # torch.Tensor (CPU)
        self._meta: dict = {}

    @property
    def loaded(self) -> bool:
        return self._model is not None and self._coreset is not None

    def load(self) -> bool:
        """TorchScript 백본 + coreset + meta 로드. 실패하면 False."""
        torch = _load_torch()
        if torch is None:
            return False

        for p in (self.model_path, self.coreset_path, self.meta_path):
            if not p.exists():
                logger.warning("[PatchCore] 파일 없음 — 비활성화: %s", p)
                return False

        try:
            self._torch = torch
            self._model = torch.jit.load(str(self.model_path), map_location="cpu").eval()
            coreset_np = np.load(str(self.coreset_path)).astype(np.float32)
            self._coreset = torch.from_numpy(coreset_np)
            self._meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("[PatchCore] 로드 실패: %s", e)
            self._model = None
            self._coreset = None
            return False

        logger.info(
            "[PatchCore] 로드 완료 — TorchScript %s, coreset %s, threshold=%.2f",
            self.model_path.name,
            tuple(self._coreset.shape),
            self.threshold,
        )
        return True

    # ── 메타데이터 ────────────────────────────────────────────────────────────

    @property
    def image_size(self) -> int:
        return int(self._meta.get("image_size", 256))

    @property
    def patch_grid(self) -> int:
        return int(self._meta.get("patch_grid", 32))

    @property
    def normalize_mean(self) -> np.ndarray:
        return np.array(self._meta.get("normalize_mean", [0.485, 0.456, 0.406]),
                        dtype=np.float32)

    @property
    def normalize_std(self) -> np.ndarray:
        return np.array(self._meta.get("normalize_std", [0.229, 0.224, 0.225]),
                        dtype=np.float32)

    @property
    def threshold(self) -> float:
        if self._score_threshold_override is not None:
            return float(self._score_threshold_override)
        return float(self._meta.get("threshold_mean_plus_3sigma", 5.0))

    # ── 추론 ──────────────────────────────────────────────────────────────────

    def _preprocess(self, bgr: np.ndarray):
        """BGR uint8 → torch.Tensor [1, 3, H, W] (CPU, normalized)."""
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (self.image_size, self.image_size), interpolation=cv2.INTER_LINEAR)
        x = rgb.astype(np.float32) / 255.0
        x = (x - self.normalize_mean) / self.normalize_std
        x = x.transpose(2, 0, 1)              # HWC → CHW
        return self._torch.from_numpy(x).unsqueeze(0).contiguous()    # (1, 3, H, W)

    def infer(self, bgr: np.ndarray) -> dict:
        """
        한 장 추론.

        Returns:
            {
                "score": float, "heatmap": np.ndarray (G, G),
                "is_anomaly": bool, "threshold": float, "elapsed_ms": int,
                "boxes": list[(x, y, w, h, score)]
            }
        """
        if not self.loaded:
            return {"score": 0.0, "heatmap": None, "is_anomaly": False,
                    "threshold": self.threshold, "elapsed_ms": 0, "boxes": []}

        torch = self._torch
        start = time.perf_counter()
        h0, w0 = bgr.shape[:2]
        x = self._preprocess(bgr)

        with torch.no_grad():
            features = self._model(x)                   # (1, C, G, G)

        _, c, gh, gw = features.shape

        # (G*G, C) 로 펴기 — cdist 입력 형태
        feat = features.reshape(c, gh * gw).T.contiguous()

        # 가장 가까운 정상 패치까지 거리 (torch.cdist)
        dists = torch.cdist(feat, self._coreset)        # (G*G, M)
        min_dists, _ = dists.min(dim=1)                  # (G*G,)
        heatmap = min_dists.reshape(gh, gw).numpy()

        # ── score 정의: 상위 K 패치 평균 (단일 max 보다 견고) ─────────────
        # 손상이 작은 영역에 집중되면 max 만으론 다른 PCB 와 헷갈림.
        # 상위 1% (최소 5개) 평균은 손상 영역 평균 anomaly 잘 반영.
        flat = heatmap.flatten()
        top_k = max(5, flat.size // 100)
        top_vals = np.sort(flat)[::-1][:top_k]
        score = float(top_vals.mean())

        is_anomaly = score > self.threshold

        boxes = self._extract_boxes(heatmap, w0, h0, threshold=self.threshold) if is_anomaly else []

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        # 진단 로그 — heatmap 분포 / 상위 패치 좌표
        flat = heatmap.flatten()
        sorted_idx = np.argsort(flat)[::-1][:5]
        top5 = [(int(i // gw), int(i % gw), float(flat[i])) for i in sorted_idx]
        logger.info(
            "[PatchCore] 추론: score=%.2f (threshold=%.2f) → %s, %dms | "
            "heatmap: mean=%.2f, std=%.2f, top5(y,x,score)=%s",
            score, self.threshold,
            "ANOMALY" if is_anomaly else "OK",
            elapsed_ms,
            float(heatmap.mean()), float(heatmap.std()),
            top5,
        )

        return {
            "score": score,
            "heatmap": heatmap,
            "is_anomaly": is_anomaly,
            "threshold": self.threshold,
            "elapsed_ms": elapsed_ms,
            "boxes": boxes,
        }

    def _extract_boxes(
        self,
        heatmap: np.ndarray,
        orig_w: int,
        orig_h: int,
        threshold: float,
    ) -> list[tuple[float, float, float, float, float]]:
        """heatmap 의 anomalous 영역을 원본 이미지 좌표 박스 리스트로."""
        mask = (heatmap > threshold).astype(np.uint8)
        if mask.sum() == 0:
            return []

        num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        boxes = []
        gh, gw = heatmap.shape
        scale_x = orig_w / gw
        scale_y = orig_h / gh

        for label_id in range(1, num):
            x, y, w, h, area = stats[label_id]
            region = heatmap[y:y + h, x:x + w]
            region_score = float(region.max())
            bx = x * scale_x
            by = y * scale_y
            bw = w * scale_x
            bh = h * scale_y
            boxes.append((bx, by, bw, bh, region_score))
        return boxes


def get_detector(
    model_path: str | Path,
    coreset_path: str | Path,
    meta_path: str | Path,
    score_threshold: Optional[float] = None,
) -> Optional[PatchCoreDetector]:
    """전역 캐시된 detector 반환. 로드 실패 시 None."""
    detector = PatchCoreDetector(model_path, coreset_path, meta_path, score_threshold)
    if not detector.load():
        return None
    return detector
