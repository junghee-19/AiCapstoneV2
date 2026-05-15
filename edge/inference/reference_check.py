"""
정상 샘플 기준 부품 누락 검증 (위치 기반 Position Check).

흐름:
  1. 정상 샘플 한 장을 등록 → fiducial 2개 + 모든 부품 박스를 JSON 으로 저장
  2. 검사 시:
     - 현재 fiducial 2개 와 레퍼런스 fiducial 2개로 similarity transform 계산
     - 레퍼런스의 각 부품 위치를 현재 이미지 좌표로 변환
     - 변환된 위치 ± tolerance 안에 같은 클래스 검출이 있으면 OK
     - 없으면 MISSING 합성 결함으로 추가하고 FAIL 강제

좌표계가 fiducial 기준으로 정규화되므로 기판이 회전·이동·확대돼도 작동.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Optional

from models.schemas import AlignmentResult, BoundingBox, DefectPayload, DetectionItem, InspectionPacket

logger = logging.getLogger(__name__)


def _bbox_to_dict(bbox: BoundingBox) -> dict:
    return {"x": bbox.x, "y": bbox.y, "width": bbox.width, "height": bbox.height}


def save_reference(
    profile_path: Path,
    *,
    device_id: str,
    image_path: Optional[str],
    alignment: AlignmentResult,
    detections: list[DetectionItem],
) -> dict:
    """현재 검사 결과를 정상 샘플 레퍼런스로 저장."""
    if alignment.fiducial1 is None or alignment.fiducial2 is None:
        raise ValueError("fiducial 2개 모두 검출된 상태에서만 레퍼런스로 등록할 수 있습니다.")

    components = []
    for d in detections:
        if "fiducial" in d.defect_type.lower():
            continue  # fiducial 자체는 reference fiducial 로 따로 보관
        components.append({
            "class": d.defect_type,
            "confidence": d.confidence,
            "bbox": _bbox_to_dict(d.bbox),
        })

    payload = {
        "device_id": device_id,
        "image_path": image_path,
        "fiducial1": {
            "x": alignment.fiducial1.center_x,
            "y": alignment.fiducial1.center_y,
        },
        "fiducial2": {
            "x": alignment.fiducial2.center_x,
            "y": alignment.fiducial2.center_y,
        },
        "components": components,
    }

    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "[레퍼런스] 저장 완료 — %s (fiducial 2개, components %d개)",
        profile_path,
        len(components),
    )
    return payload


def load_reference(profile_path: Path) -> Optional[dict]:
    """저장된 레퍼런스 로드. 파일 없으면 None."""
    if not profile_path.exists():
        return None
    try:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("[레퍼런스] 로드 실패: %s", e)
        return None


def _similarity_transform(
    ref_f1: tuple[float, float],
    ref_f2: tuple[float, float],
    cur_f1: tuple[float, float],
    cur_f2: tuple[float, float],
):
    """
    레퍼런스 좌표 (x, y) 를 현재 이미지 좌표로 변환하는 함수를 반환.

    F1_ref→F1_cur, F2_ref→F2_cur 매핑을 만족하는 similarity
    (translation + rotation + scale) 변환을 닫힌 형태로 계산한다.
    """
    rx1, ry1 = ref_f1
    rx2, ry2 = ref_f2
    cx1, cy1 = cur_f1
    cx2, cy2 = cur_f2

    ref_dx, ref_dy = rx2 - rx1, ry2 - ry1
    cur_dx, cur_dy = cx2 - cx1, cy2 - cy1
    ref_len = math.hypot(ref_dx, ref_dy)
    cur_len = math.hypot(cur_dx, cur_dy)
    if ref_len < 1e-6 or cur_len < 1e-6:
        # 두 fiducial 이 거의 겹친 비정상 — identity 폴백
        return lambda x, y: (x, y)

    scale = cur_len / ref_len
    ref_angle = math.atan2(ref_dy, ref_dx)
    cur_angle = math.atan2(cur_dy, cur_dx)
    delta_angle = cur_angle - ref_angle
    cos_a = math.cos(delta_angle)
    sin_a = math.sin(delta_angle)

    def transform(x: float, y: float) -> tuple[float, float]:
        # 1) 레퍼런스 F1 원점으로 이동
        ox = x - rx1
        oy = y - ry1
        # 2) 회전 + 스케일
        nx = scale * (cos_a * ox - sin_a * oy)
        ny = scale * (sin_a * ox + cos_a * oy)
        # 3) 현재 F1 원점으로 이동
        return nx + cx1, ny + cy1

    return transform


def check_missing_components(
    reference: dict,
    *,
    current_alignment: AlignmentResult,
    current_detections: list[DetectionItem],
    tolerance_px: float,
) -> list[DefectPayload]:
    """
    레퍼런스 부품 위치를 현재 이미지로 투영하고, 매칭되는 검출이 없으면 MISSING 으로 반환.

    Args:
        reference: load_reference() 결과
        current_alignment: 현재 검사의 정렬 정보 (fiducial 2개 필요)
        current_detections: 현재 Stage 2 검출 (fiducial 제외)
        tolerance_px: 매칭 허용 반경 (변환된 좌표 기준)

    Returns:
        MISSING DefectPayload 목록 (없으면 빈 리스트)
    """
    if current_alignment.fiducial1 is None or current_alignment.fiducial2 is None:
        logger.warning("[레퍼런스] 현재 fiducial 부족 — 위치 검증 건너뜀")
        return []

    ref_f1 = (reference["fiducial1"]["x"], reference["fiducial1"]["y"])
    ref_f2 = (reference["fiducial2"]["x"], reference["fiducial2"]["y"])
    cur_f1 = (current_alignment.fiducial1.center_x, current_alignment.fiducial1.center_y)
    cur_f2 = (current_alignment.fiducial2.center_x, current_alignment.fiducial2.center_y)

    transform = _similarity_transform(ref_f1, ref_f2, cur_f1, cur_f2)

    # ── 디버그 — 변환 + 매칭 후보 풀 출력 ────────────────────────────────
    logger.info(
        "[위치검증][debug] ref_F1=%s ref_F2=%s cur_F1=%s cur_F2=%s",
        ref_f1, ref_f2, cur_f1, cur_f2,
    )
    tx, ty = transform(0.0, 0.0)
    tx1, ty1 = transform(100.0, 0.0)
    logger.info(
        "[위치검증][debug] transform 검증: (0,0)→(%.1f,%.1f), (100,0)→(%.1f,%.1f)",
        tx, ty, tx1, ty1,
    )

    # 같은 클래스의 검출만 매칭 후보 — 클래스별로 묶어두면 빠름
    by_class: dict[str, list[DetectionItem]] = {}
    for d in current_detections:
        cls = d.defect_type.lower()
        if "fiducial" in cls:
            continue
        by_class.setdefault(cls, []).append(d)

    logger.info(
        "[위치검증][debug] current detections by class: %s",
        {k: [(round(d.center_x, 1), round(d.center_y, 1)) for d in v] for k, v in by_class.items()},
    )
    ref_classes: dict[str, int] = {}
    for c in reference.get("components", []):
        cls = str(c["class"]).lower()
        ref_classes[cls] = ref_classes.get(cls, 0) + 1
    logger.info("[위치검증][debug] reference class counts: %s", ref_classes)

    # 클래스별로 따로 — 같은 idx 값이 클래스 간에 충돌하지 않도록 격리
    used_by_class: dict[str, set[int]] = {}
    missing: list[DefectPayload] = []

    for ref_comp in reference.get("components", []):
        cls = str(ref_comp["class"]).lower()
        bbox = ref_comp.get("bbox", {})
        rx = float(bbox.get("x", 0.0)) + float(bbox.get("width", 0.0)) / 2.0
        ry = float(bbox.get("y", 0.0)) + float(bbox.get("height", 0.0)) / 2.0
        ex_x, ex_y = transform(rx, ry)

        candidates = by_class.get(cls, [])
        used = used_by_class.setdefault(cls, set())
        best_idx = -1
        best_dist = float("inf")
        for idx, d in enumerate(candidates):
            if idx in used:
                continue
            dist = math.hypot(d.center_x - ex_x, d.center_y - ex_y)
            if dist < best_dist:
                best_dist = dist
                best_idx = idx

        if best_idx >= 0 and best_dist <= tolerance_px:
            used.add(best_idx)
            continue

        # 매칭 실패 → MISSING 으로 기록
        logger.warning(
            "[레퍼런스] 누락 감지: class=%s, 예상위치=(%.0f,%.0f), 최근접거리=%.1fpx (허용=%.1fpx)",
            cls, ex_x, ex_y, best_dist, tolerance_px,
        )
        size_w = max(20.0, float(bbox.get("width", 30.0)))
        size_h = max(20.0, float(bbox.get("height", 30.0)))
        missing.append(DefectPayload(
            defect_type=f"MISSING:{cls}:expected_at=({ex_x:.0f},{ex_y:.0f}),nearest={best_dist:.1f}px",
            confidence=1.0,
            bbox_x=max(0.0, ex_x - size_w / 2.0),
            bbox_y=max(0.0, ex_y - size_h / 2.0),
            bbox_width=size_w,
            bbox_height=size_h,
        ))

    return missing


def packet_components_for_save(packet: InspectionPacket) -> list[DetectionItem]:
    """InspectionPacket.defects → DetectionItem 리스트 (레퍼런스 저장용 변환).

    MISSING 합성 결함과 fiducial 은 제외.
    """
    items: list[DetectionItem] = []
    for d in packet.defects:
        if d.defect_type.startswith("MISSING:"):
            continue
        if "fiducial" in d.defect_type.lower():
            continue
        items.append(DetectionItem(
            defect_type=d.defect_type,
            confidence=d.confidence,
            bbox=BoundingBox(
                x=d.bbox_x, y=d.bbox_y,
                width=d.bbox_width, height=d.bbox_height,
            ),
        ))
    return items
