"""
per-defect 크롭 보존 모듈

YOLO Stage2 결과 각 결함 박스를 작은 JPG로 잘라 captures/defects/ 아래에 저장한다.
원본 프레임(stage2 입력 이미지) 좌표계 기준의 bbox만 받는다.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config.settings import settings

logger = logging.getLogger(__name__)

_EDGE_ROOT = Path(__file__).resolve().parent.parent
DEFECT_CROPS_DIR = _EDGE_ROOT / "captures" / "defects"


def _safe_token(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", text)[:40] or "x"


def save_defect_crop(
    source_image: np.ndarray,
    bbox_x: float,
    bbox_y: float,
    bbox_w: float,
    bbox_h: float,
    *,
    run_id: str,
    index: int,
    defect_type: str,
    padding: int = settings.DEFECT_CROP_PADDING_PX,
) -> Optional[str]:
    """
    bbox 영역을 padding 만큼 여유 두고 잘라 저장. 반환값은 captures/ 기준 상대 경로
    (예: "defects/20260508_..._0_TRACE_OPEN.jpg") — 정적 서빙 URL은 /captures/<반환값>.
    실패 시 None.
    """
    if source_image is None or source_image.size == 0:
        return None

    h, w = source_image.shape[:2]
    x1 = max(0, int(bbox_x) - padding)
    y1 = max(0, int(bbox_y) - padding)
    x2 = min(w, int(bbox_x + bbox_w) + padding)
    y2 = min(h, int(bbox_y + bbox_h) + padding)
    if x2 <= x1 or y2 <= y1:
        return None

    crop = source_image[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    DEFECT_CROPS_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{run_id}_{index}_{_safe_token(defect_type)}.jpg"
    out_path = DEFECT_CROPS_DIR / fname
    ok = cv2.imwrite(str(out_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        logger.warning("[defect_crop] 저장 실패: %s", out_path)
        return None
    logger.info("[defect_crop] 저장: %s (%dx%d)", out_path.name, crop.shape[1], crop.shape[0])
    return f"defects/{fname}"
