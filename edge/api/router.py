"""
FastAPI 로컬 API 라우터

라즈베리파이 자체에서 서빙하는 로컬 REST API 엔드포인트.
같은 네트워크의 다른 기기(운영자 PC, 모니터링 툴 등)가
엣지 디바이스의 상태를 조회하거나 수동 검사를 트리거할 때 사용한다.

Base URL: http://<라즈베리파이_IP>:8000
"""

import asyncio
import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from api.sender import create_dummy_packet, ServerSender
from config.settings import settings
from runtime.inspection_control import (
    auto_status,
    start_auto_inspection,
    stop_auto_inspection,
    trigger_file_inspection,
    trigger_inspection_once,
)

logger = logging.getLogger(__name__)

# APIRouter: main.py의 FastAPI 앱에 include_router()로 등록한다.
router = APIRouter(prefix="/edge", tags=["Edge Device"])

_preview_lock = threading.Lock()
_last_preview_jpeg: Optional[bytes] = None
_last_guide_detection_at: float = 0.0
_last_guide_state: dict[str, Any] = {
    "fiducials": [],
    "alignment": None,
    "gate_ok": False,
    "gate_reason": "waiting",
}


def _normalize_stage2_mode(stage2_source: Optional[str]) -> str:
    mode = (stage2_source or settings.STAGE2_SOURCE_MODE).strip().lower()
    if mode == "deskew":
        mode = "aligned"
    if mode not in {"raw", "aligned"}:
        raise HTTPException(status_code=400, detail="stage2Source must be 'raw' or 'aligned'")
    return mode

def _refresh_capture_guide_state(frame: np.ndarray) -> dict[str, Any]:
    """오버레이용 피듀셜 상태를 낮은 빈도로 갱신한다."""
    global _last_guide_detection_at, _last_guide_state

    now = time.perf_counter()
    if now - _last_guide_detection_at < settings.TOUCH_GUIDE_DETECTION_INTERVAL_SEC:
        return _last_guide_state

    _last_guide_detection_at = now
    try:
        import main as main_mod
        from inference.alignment import compute_alignment

        stage1 = getattr(main_mod, "_stage1_detector")()
        if stage1 is None:
            _last_guide_state = {
                "fiducials": [],
                "alignment": None,
                "gate_ok": False,
                "gate_reason": "stage1-not-ready",
            }
            return _last_guide_state

        fiducials, _ = stage1.detect_fiducials(frame)
        alignment = compute_alignment(fiducials)
        gate_ok, gate_reason = getattr(main_mod, "_pcb_capture_gate")(frame, alignment)
        _last_guide_state = {
            "fiducials": fiducials,
            "alignment": alignment,
            "gate_ok": gate_ok,
            "gate_reason": gate_reason,
        }
    except Exception as e:
        logger.debug("[프리뷰 가이드] 피듀셜 상태 갱신 실패: %s", e)
        _last_guide_state = {
            "fiducials": [],
            "alignment": None,
            "gate_ok": False,
            "gate_reason": "guide-error",
        }
    return _last_guide_state


def _draw_detection_overlay(frame: np.ndarray, fiducials: list[Any], alignment: Any, gate_ok: bool = False, gate_reason: str = "") -> np.ndarray:
    """실시간 스트림 프레임에 촬영 영역/피듀셜 인식 가이드를 그린다."""
    annotated = frame.copy()
    h, w = annotated.shape[:2]

    cx = int(w * settings.PCB_CAPTURE_CENTER_X_RATIO)
    cy = int(h * settings.PCB_CAPTURE_CENTER_Y_RATIO)
    guide_half_w = int(w * settings.PCB_GUIDE_BOX_WIDTH_RATIO / 2.0)
    guide_half_h = int(h * settings.PCB_GUIDE_BOX_HEIGHT_RATIO / 2.0)
    guide_x1 = max(0, cx - guide_half_w)
    guide_y1 = max(0, cy - guide_half_h)
    guide_x2 = min(w - 1, cx + guide_half_w)
    guide_y2 = min(h - 1, cy + guide_half_h)
    pass_x1 = max(0, int(cx - (w * settings.PCB_CAPTURE_TOLERANCE_X_RATIO)))
    pass_y1 = max(0, int(cy - (h * settings.PCB_CAPTURE_TOLERANCE_Y_RATIO)))
    pass_x2 = min(w - 1, int(cx + (w * settings.PCB_CAPTURE_TOLERANCE_X_RATIO)))
    pass_y2 = min(h - 1, int(cy + (h * settings.PCB_CAPTURE_TOLERANCE_Y_RATIO)))
    guide_color = (70, 210, 110) if gate_ok else (150, 150, 150)
    guide_fill = annotated.copy()
    cv2.rectangle(guide_fill, (guide_x1, guide_y1), (guide_x2, guide_y2), guide_color, -1)
    cv2.addWeighted(guide_fill, 0.12 if gate_ok else 0.08, annotated, 0.88 if gate_ok else 0.92, 0, annotated)
    cv2.rectangle(annotated, (guide_x1, guide_y1), (guide_x2, guide_y2), guide_color, 4)
    cv2.rectangle(annotated, (pass_x1, pass_y1), (pass_x2, pass_y2), guide_color, 1)
    cv2.line(annotated, (cx - 22, cy), (cx + 22, cy), guide_color, 2)
    cv2.line(annotated, (cx, cy - 22), (cx, cy + 22), guide_color, 2)

    status_text = "READY TO CAPTURE" if gate_ok else "ALIGN PCB IN BOX"
    cv2.putText(
        annotated,
        status_text,
        (guide_x1, max(34, guide_y1 - 14)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        guide_color,
        3,
        cv2.LINE_AA,
    )
    if gate_reason:
        cv2.putText(
            annotated,
            gate_reason,
            (guide_x1, min(h - 18, guide_y2 + 34)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            guide_color,
            2,
            cv2.LINE_AA,
        )

    for idx, item in enumerate(fiducials[:2], start=1):
        x = int(item.bbox.x)
        y = int(item.bbox.y)
        w = int(item.bbox.width)
        h = int(item.bbox.height)
        fx = int(item.center_x)
        fy = int(item.center_y)
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 220, 255), 3)
        cv2.drawMarker(
            annotated,
            (fx, fy),
            (0, 220, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=30,
            thickness=2,
        )
        cv2.putText(
            annotated,
            f"F{idx} {item.confidence:.2f}",
            (x, max(24, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 220, 255),
            2,
            cv2.LINE_AA,
        )

    if alignment is not None and alignment.fiducial1 is not None and alignment.fiducial2 is not None:
        f1 = alignment.fiducial1
        f2 = alignment.fiducial2
        p1 = (int(f1.center_x), int(f1.center_y))
        p2 = (int(f2.center_x), int(f2.center_y))
        mid = (int((p1[0] + p2[0]) / 2), int((p1[1] + p2[1]) / 2))
        cv2.line(annotated, p1, p2, guide_color, 2)
        cv2.circle(annotated, mid, 9, guide_color, -1)
        cv2.putText(
            annotated,
            f"MID {mid[0]}, {mid[1]}",
            (mid[0] + 14, max(28, mid[1] - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            guide_color,
            2,
            cv2.LINE_AA,
        )
    else:
        cv2.putText(
            annotated,
            "Searching PCB...",
            (28, 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 170, 255),
            2,
            cv2.LINE_AA,
        )

    return annotated


# ── 상태 조회 ─────────────────────────────────────────────────────────────────

@router.get("/health", summary="헬스체크")
async def health_check() -> dict[str, Any]:
    """
    엣지 디바이스 서버 가동 여부를 확인하는 헬스체크 엔드포인트.

    모니터링 시스템이나 운영자가 라즈베리파이 FastAPI 서버가
    정상 동작 중인지 확인할 때 사용한다.

    Returns:
        status: "ok"
        timestamp: 현재 서버 시각 (ISO 8601)
        environment: 현재 실행 환경 (production / development)
    """
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "device_id": "RPI5-LINE-A",
        "environment": settings.ENVIRONMENT,
        "server_url": settings.SERVER_BASE_URL,
    }


@router.get("/status", summary="카메라/모델 상태 조회")
async def get_status() -> dict[str, Any]:
    """
    카메라 설정, YOLO 모델 경로, GPIO 핀 설정 등
    현재 엣지 디바이스의 구성 정보를 반환한다.
    """
    from inference.yolo_detector import resolve_edge_weights_path

    wu = resolve_edge_weights_path(settings.YOLO_WEIGHTS_PATH)
    fiducial_wu = resolve_edge_weights_path(settings.effective_fiducial_weights_path())
    defect_wu = resolve_edge_weights_path(settings.effective_defect_weights_path())
    weights_loaded = wu.exists()
    yolo_block = {
        "use_separate_models": settings.USE_SEPARATE_MODELS,
        "weights_path": str(wu),
        "weights_loaded": weights_loaded,
        "fiducial_weights_path": str(fiducial_wu),
        "fiducial_weights_loaded": fiducial_wu.exists(),
        "defect_weights_path": str(defect_wu),
        "defect_weights_loaded": defect_wu.exists(),
        "confidence_threshold": settings.YOLO_CONFIDENCE_THRESHOLD,
        "fiducial_confidence": settings.effective_fiducial_confidence(),
        "defect_confidence": settings.effective_defect_confidence(),
    }

    return {
        "camera": {
            "device_index": settings.CAMERA_DEVICE_INDEX,
            "resolution": f"{settings.CAMERA_WIDTH}x{settings.CAMERA_HEIGHT}",
        },
        "yolo": yolo_block,
        "server": {
            "base_url": settings.SERVER_BASE_URL,
        },
        "pipeline": {
            "stage2_source_mode": settings.STAGE2_SOURCE_MODE,
            "auto_inspection_enabled": settings.AUTO_INSPECTION_ENABLED,
            "auto_inspection_idle_poll_sec": settings.AUTO_INSPECTION_IDLE_POLL_SEC,
            "auto_result_display_sec": settings.AUTO_RESULT_DISPLAY_SEC,
            "auto_capture_cooldown_sec": settings.AUTO_CAPTURE_COOLDOWN_SEC,
            "auto_capture_hold_sec": settings.AUTO_CAPTURE_HOLD_SEC,
            "pcb_capture_min_fiducials": settings.PCB_CAPTURE_MIN_FIDUCIALS,
            "pcb_capture_center": {
                "x_ratio": settings.PCB_CAPTURE_CENTER_X_RATIO,
                "y_ratio": settings.PCB_CAPTURE_CENTER_Y_RATIO,
            },
            "pcb_capture_tolerance": {
                "x_ratio": settings.PCB_CAPTURE_TOLERANCE_X_RATIO,
                "y_ratio": settings.PCB_CAPTURE_TOLERANCE_Y_RATIO,
            },
            "pcb_capture_expected_span_ratio": settings.PCB_CAPTURE_EXPECTED_SPAN_RATIO,
            "pcb_capture_expected_angle_deg": settings.PCB_CAPTURE_EXPECTED_ANGLE_DEG,
            "pcb_guide_box": {
                "width_ratio": settings.PCB_GUIDE_BOX_WIDTH_RATIO,
                "height_ratio": settings.PCB_GUIDE_BOX_HEIGHT_RATIO,
            },
        },
    }


@router.get("/camera/preview.jpg", summary="카메라 프리뷰 단일 프레임(JPEG)")
async def camera_preview_frame() -> Response:
    """
    라즈베리파이 카메라 현재 프레임을 JPEG로 반환한다.
    프론트 대시보드에서 주기적으로 호출해 실시간 미리보기를 구성할 때 사용한다.
    """
    try:
        import main as main_mod

        cam = getattr(main_mod, "camera", None)
        if cam is None:
            raise HTTPException(status_code=503, detail="카메라가 초기화되지 않았습니다.")

        # 프리뷰와 검사 파이프라인이 동시에 카메라를 읽을 수 있어 직렬화한다.
        with _preview_lock:
            frame = cam.capture()
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
            if not ok:
                raise HTTPException(status_code=500, detail="카메라 프레임 인코딩 실패")

            global _last_preview_jpeg
            _last_preview_jpeg = encoded.tobytes()

        return Response(
            content=_last_preview_jpeg,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
    except HTTPException:
        raise
    except Exception as e:
        # 프레임 일시 실패 시 마지막 정상 프레임을 반환해 화면 정지를 줄인다.
        if _last_preview_jpeg is not None:
            logger.warning("[프리뷰] 캡처 실패 — 마지막 정상 프레임으로 대체: %s", e)
            return Response(
                content=_last_preview_jpeg,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "X-Preview-Stale": "1",
                },
            )
        raise HTTPException(status_code=500, detail=f"카메라 프리뷰 실패: {e}") from e


@router.get("/camera/stream.mjpg", summary="카메라 MJPEG 스트리밍")
async def camera_preview_stream() -> StreamingResponse:
    """
    대시보드용 실시간 카메라 스트리밍.
    브라우저 <img> 태그에서 multipart/x-mixed-replace(MJPEG)로 재생한다.
    """
    try:
        import main as main_mod
        cam = getattr(main_mod, "camera", None)
        if cam is None:
            raise HTTPException(status_code=503, detail="카메라가 초기화되지 않았습니다.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"카메라 스트림 초기화 실패: {e}") from e

    boundary = b"frame"

    def _gen():
        global _last_preview_jpeg
        while True:
            try:
                with _preview_lock:
                    frame = cam.capture(flush=False)
                    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                    if ok:
                        _last_preview_jpeg = encoded.tobytes()
            except Exception as e:
                logger.debug("[프리뷰 스트림] 캡처 실패: %s", e)

            if _last_preview_jpeg is None:
                time.sleep(0.05)
                continue

            chunk = (
                b"--" + boundary + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-store\r\n\r\n" +
                _last_preview_jpeg +
                b"\r\n"
            )
            yield chunk
            time.sleep(0.10)  # 약 10fps

    return StreamingResponse(
        _gen(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


# ── 수동 검사 트리거 ──────────────────────────────────────────────────────────

@router.post("/inspect/trigger", summary="수동 검사 실행")
async def trigger_inspection() -> dict[str, str]:
    """
    운영자가 HTTP 요청으로 즉시 검사를 한 번 실행하도록 트리거한다.

    실제 검사 파이프라인은 main.py의 run_inspection_pipeline()을 직접 호출하며,
    요청은 검사 완료 시점에 응답한다.

    Returns:
        검사 완료 메시지 (상세 결과는 서버 DB에서 확인)
    """
    logger.info("[라우터] 수동 검사 실행 요청 수신")

    try:
        packet = await trigger_inspection_once()
        return {"message": f"PCB가 중앙에서 5초간 안정된 뒤 검사 완료되었습니다. 결과: {packet.result.value}"}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.get("/camera/stream", summary="라즈베리 카메라 MJPEG 스트림")
async def stream_camera() -> StreamingResponse:
    """
    브라우저에서 <img src> 로 바로 볼 수 있는 MJPEG 스트림.

    현재 파이프라인은 단발 검사 중심이므로 이 스트림은 "실시간 카메라 프리뷰" 역할을 하며,
    수동 검사와 같은 카메라 장치를 공유한다.
    """
    try:
        import main as main_mod

        cam = getattr(main_mod, "camera", None)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"카메라 상태 확인 실패: {e}") from e

    if cam is None:
        raise HTTPException(status_code=503, detail="카메라가 초기화되지 않았습니다.")

    async def frame_generator():
        frame_interval_sec = 0.07

        while True:
            try:
                frame = cam.capture(flush=False)
                if settings.TOUCH_GUIDE_OVERLAY_ENABLED:
                    guide_state = _refresh_capture_guide_state(frame)
                    frame = _draw_detection_overlay(
                        frame,
                        guide_state.get("fiducials") or [],
                        guide_state.get("alignment"),
                        bool(guide_state.get("gate_ok")),
                        str(guide_state.get("gate_reason") or ""),
                    )

                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ok:
                    await asyncio.sleep(0.1)
                    continue

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + encoded.tobytes()
                    + b"\r\n"
                )
                await asyncio.sleep(frame_interval_sec)
            except Exception as e:
                logger.warning("[카메라 스트림] 프레임 전송 실패: %s", e)
                await asyncio.sleep(0.3)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


_EDGE_ROOT = Path(__file__).resolve().parent.parent
_CAPTURES_DIR = _EDGE_ROOT / "captures"
_IMAGE_SUFFIX = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class InspectFromFileBody(BaseModel):
    """저장된 이미지로 검사 — edge/captures 기준 상대 경로."""

    path: str = Field(
        ...,
        min_length=1,
        description='예: 20260404_120000_xxx.jpg 또는 subdir/foo.jpg',
    )


class CameraFocusBody(BaseModel):
    auto: bool = Field(default=False, description="true면 오토포커스")
    value: int = Field(default=30, ge=0, le=255, description="수동 초점 값 (0~255)")


@router.get("/camera/focus", summary="카메라 초점 상태 조회")
async def get_camera_focus() -> dict[str, Any]:
    try:
        import main as main_mod

        cam = getattr(main_mod, "camera", None)
        if cam is None:
            raise HTTPException(status_code=503, detail="카메라가 초기화되지 않았습니다.")
        with _preview_lock:
            state = cam.get_focus_state()
        return {"camera_focus": state}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"초점 상태 조회 실패: {e}") from e


@router.post("/camera/focus", summary="카메라 초점 실시간 설정")
async def set_camera_focus(body: CameraFocusBody) -> dict[str, Any]:
    try:
        import main as main_mod

        cam = getattr(main_mod, "camera", None)
        if cam is None:
            raise HTTPException(status_code=503, detail="카메라가 초기화되지 않았습니다.")
        with _preview_lock:
            state = cam.set_focus_runtime(auto=body.auto, value=body.value)
        return {"message": "카메라 초점을 적용했습니다.", "camera_focus": state}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"초점 설정 실패: {e}") from e


@router.post("/inspect/upload", summary="이미지 업로드 후 검사 (캡처 생략)")
async def inspect_from_uploaded_file(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(..., description="검사할 이미지 파일 (.jpg/.jpeg/.png/.bmp/.webp)"),
    stage2Source: Optional[str] = None,
) -> dict[str, str]:
    """
    브라우저에서 업로드한 이미지를 edge/captures 에 저장한 뒤 동일 검사 파이프라인을 실행한다.
    라즈베리파이·웹캠이 없는 팀원의 로컬 테스트 경로로 사용한다.
    """
    filename = image.filename or "upload.jpg"
    suffix = Path(filename).suffix.lower()
    if suffix not in _IMAGE_SUFFIX:
        raise HTTPException(status_code=400, detail="지원하지 않는 이미지 형식입니다.")

    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="업로드된 파일이 비어 있습니다.")

    # 원본 파일명의 특수문자를 제거해 안전한 저장 파일명을 만든다.
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).stem)[:40] or "upload"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    save_name = f"{ts}_{stem}{suffix}"
    _CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    save_path = _CAPTURES_DIR / save_name
    save_path.write_bytes(raw)

    if cv2.imread(str(save_path)) is None:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="이미지를 디코딩할 수 없습니다.")

    try:
        import main as main_mod

        det = getattr(main_mod, "detector", None)
        if det is None:
            raise HTTPException(status_code=503, detail="YOLO 모델이 로드되지 않았습니다.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"모델 상태 확인 실패: {e}") from e

    mode = _normalize_stage2_mode(stage2Source)
    background_tasks.add_task(trigger_file_inspection, save_name, mode)
    return {
        "message": f"업로드 이미지 검사를 시작했습니다: {save_name} (stage2={mode})",
    }


@router.post("/inspect/from-file", summary="저장 이미지 파일로 검사 (캡처 생략)")
async def inspect_from_file(
    body: InspectFromFileBody,
    background_tasks: BackgroundTasks,
    stage2Source: Optional[str] = None,
) -> dict[str, str]:
    """
    카메라 대신 edge/captures 아래 파일로 동일 검사 파이프라인을 실행한다.
    결과는 Spring Boot DB로 전송된다.
    """
    from inference.model_compare import resolve_safe_inspection_source_image

    try:
        src = resolve_safe_inspection_source_image(body.path.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if cv2.imread(str(src)) is None:
        raise HTTPException(status_code=400, detail="이미지를 디코딩할 수 없습니다.")

    try:
        import main as main_mod

        det = getattr(main_mod, "detector", None)
        if det is None:
            raise HTTPException(status_code=503, detail="YOLO 모델이 로드되지 않았습니다.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"모델 상태 확인 실패: {e}") from e

    mode = _normalize_stage2_mode(stage2Source)
    background_tasks.add_task(trigger_file_inspection, body.path.strip(), mode)
    return {
        "message": f"파일 검사를 시작했습니다: {body.path.strip()} (stage2={mode})",
    }


# ── 정상 샘플 위치 검증 (Position Check) ────────────────────────────────────

class ReferenceFromFileBody(BaseModel):
    """edge/captures 아래 정상 샘플 이미지로 레퍼런스 등록."""

    path: str = Field(..., min_length=1, description="captures/ 기준 상대 경로")


def _resolve_reference_path() -> Path:
    """settings.REFERENCE_PROFILE_PATH 를 edge/ 기준 절대 경로로 변환."""
    from main import _EDGE_DIR
    p = Path(settings.REFERENCE_PROFILE_PATH)
    if p.is_absolute():
        return p
    return (_EDGE_DIR / p).resolve()


@router.post("/reference/from-file", summary="정상 샘플로 위치 검증 레퍼런스 등록")
async def register_reference_from_file(body: ReferenceFromFileBody) -> dict[str, Any]:
    """지정된 정상 PCB 이미지로 검사 1회 실행 → fiducial + 부품 좌표를 레퍼런스 JSON 으로 저장."""
    from inference.model_compare import resolve_safe_inspection_source_image
    from inference.reference_check import save_reference, packet_components_for_save
    from models.schemas import AlignmentResult, BoundingBox, DetectionItem

    try:
        src = resolve_safe_inspection_source_image(body.path.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if cv2.imread(str(src)) is None:
        raise HTTPException(status_code=400, detail="이미지를 디코딩할 수 없습니다.")

    try:
        import main as main_mod
        if getattr(main_mod, "detector", None) is None:
            raise HTTPException(status_code=503, detail="YOLO 모델이 로드되지 않았습니다.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"모델 상태 확인 실패: {e}") from e

    # 검사 파이프라인 실행해 packet 받음
    from main import run_inspection_pipeline_from_source_file
    packet = await run_inspection_pipeline_from_source_file(body.path.strip(), None)
    if packet is None:
        raise HTTPException(status_code=500, detail="검사 실행 실패 — 레퍼런스 등록 불가.")

    # AlignmentResult 재구성 (packet 에는 좌표만 있어서)
    f1_item = None
    f2_item = None
    if packet.fiducial1_x is not None and packet.fiducial1_y is not None:
        f1_item = DetectionItem(
            defect_type="fiducial",
            confidence=packet.fiducial1_confidence or 1.0,
            bbox=BoundingBox(
                x=max(0.0, packet.fiducial1_x - 5.0),
                y=max(0.0, packet.fiducial1_y - 5.0),
                width=10.0, height=10.0,
            ),
        )
    if packet.fiducial2_x is not None and packet.fiducial2_y is not None:
        f2_item = DetectionItem(
            defect_type="fiducial",
            confidence=packet.fiducial2_confidence or 1.0,
            bbox=BoundingBox(
                x=max(0.0, packet.fiducial2_x - 5.0),
                y=max(0.0, packet.fiducial2_y - 5.0),
                width=10.0, height=10.0,
            ),
        )
    if f1_item is None or f2_item is None:
        raise HTTPException(status_code=400, detail="fiducial 2개가 모두 검출돼야 레퍼런스 등록 가능합니다.")

    alignment = AlignmentResult(
        is_aligned=True,
        fiducial1=f1_item,
        fiducial2=f2_item,
        angle_error_deg=packet.angle_error_deg or 0.0,
    )

    profile_path = _resolve_reference_path()
    try:
        saved = save_reference(
            profile_path,
            device_id=packet.device_id,
            image_path=packet.image_path,
            alignment=alignment,
            detections=packet_components_for_save(packet),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "message": "레퍼런스 등록 완료",
        "profile_path": str(profile_path),
        "device_id": saved["device_id"],
        "fiducial1": saved["fiducial1"],
        "fiducial2": saved["fiducial2"],
        "components_count": len(saved["components"]),
    }


@router.get("/reference", summary="현재 등록된 레퍼런스 프로파일 조회")
async def get_reference() -> dict[str, Any]:
    from inference.reference_check import load_reference

    profile_path = _resolve_reference_path()
    ref = load_reference(profile_path)
    if ref is None:
        raise HTTPException(status_code=404, detail="등록된 레퍼런스가 없습니다.")
    return {"profile_path": str(profile_path), "reference": ref}


@router.delete("/reference", summary="등록된 레퍼런스 삭제")
async def delete_reference() -> dict[str, Any]:
    profile_path = _resolve_reference_path()
    if profile_path.exists():
        profile_path.unlink()
        return {"message": "레퍼런스 삭제 완료", "profile_path": str(profile_path)}
    raise HTTPException(status_code=404, detail="삭제할 레퍼런스가 없습니다.")


@router.post("/inspect/dummy", summary="더미 데이터 전송 테스트")
async def send_dummy_inspection() -> dict[str, Any]:
    """
    더미(Dummy) 검사 결과 패킷을 생성하여 Spring Boot 서버로 전송한다.

    카메라나 YOLO 모델 없이 서버 연동을 빠르게 검증할 때 사용.
    Step 3의 핵심 테스트 엔드포인트.

    Returns:
        서버 응답 데이터 또는 오류 메시지
    """
    logger.info("[라우터] 더미 전송 테스트 시작")

    # 더미 패킷 생성
    packet = create_dummy_packet(device_id="RPI5-LINE-A")
    logger.info("[라우터] 더미 패킷 — 결과: %s, 결함 수: %d",
                packet.result.value, len(packet.defects))

    # 서버로 전송
    sender = ServerSender()
    response = sender.send(packet)
    sender.close()

    if response is None:
        raise HTTPException(
            status_code=502,
            detail=f"Spring Boot 서버({settings.SERVER_BASE_URL})에 전송 실패. "
                   "서버가 실행 중인지 확인하세요."
        )

    return {
        "message": "더미 전송 성공",
        "sent_packet": packet.to_server_json(),
        "server_response": response,
    }


# ── 시연용 엔드포인트 ─────────────────────────────────────────────────────────

@router.post("/inspect/demo/fail", summary="[시연용] FAIL 결과 강제 전송")
async def demo_force_fail() -> dict[str, Any]:
    """
    시연용: FAIL 결과를 무조건 생성하여 서버로 전송합니다.
    모델 학습 전에도 FAIL 알람·대시보드 표시를 시연할 때 사용합니다.

    GPIO 알람(빨간 LED + 부저)도 함께 동작합니다.
    """
    logger.info("[시연] FAIL 강제 전송 요청")

    packet = create_dummy_packet(device_id="RPI5-LINE-A", force_fail=True)

    sender = ServerSender()
    response = sender.send(packet)
    sender.close()

    if response is None:
        raise HTTPException(status_code=502, detail="서버 전송 실패")

    return {
        "message": "🔴 FAIL 시연 전송 완료 — 빨간 LED + 부저 동작",
        "result": "FAIL",
        "defects": [d.defect_type for d in packet.defects],
        "server_response": response,
    }


@router.post("/inspect/demo/pass", summary="[시연용] PASS 결과 강제 전송")
async def demo_force_pass() -> dict[str, Any]:
    """
    시연용: PASS 결과를 무조건 생성하여 서버로 전송합니다.
    정상 → 결함 → 정상 복구 흐름을 시연할 때 사용합니다.

    GPIO 알람(초록 LED)도 함께 동작합니다.
    """
    logger.info("[시연] PASS 강제 전송 요청")

    packet = create_dummy_packet(device_id="RPI5-LINE-A", force_pass=True)

    sender = ServerSender()
    response = sender.send(packet)
    sender.close()

    if response is None:
        raise HTTPException(status_code=502, detail="서버 전송 실패")

    return {
        "message": "🟢 PASS 시연 전송 완료 — 초록 LED 동작",
        "result": "PASS",
        "server_response": response,
    }


@router.post("/inspect/auto/start", summary="[시연용] 자동 연속 검사 시작")
async def auto_inspect_start(
    interval: float = 5.0,
    background_tasks: BackgroundTasks = None,
) -> dict[str, str]:
    """
    시연용: 일정 간격으로 자동 반복 검사를 시작합니다.
    기판을 올려놓으면 자동으로 검사 → 결과 전송이 반복됩니다.

    Args:
        interval: 검사 간격 (초, 기본값 5초)
    """
    before = auto_status()
    try:
        status = await start_auto_inspection(interval)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not status.get("enabled", True):
        return {"message": "자동 검사는 현재 임시 비활성화 상태입니다. 수동 검사만 사용할 수 있습니다."}
    if before["running"]:
        return {"message": f"자동 검사가 이미 실행 중입니다. (간격: {status['interval_seconds']}초)"}
    return {"message": f"✅ 자동 검사 시작 (간격: {interval}초) — /edge/inspect/auto/stop 으로 중지"}


@router.post("/inspect/auto/stop", summary="[시연용] 자동 연속 검사 중지")
async def auto_inspect_stop() -> dict[str, str]:
    """자동 반복 검사를 중지합니다."""
    logger.info("[시연] 자동 연속 검사 중지 요청")
    await stop_auto_inspection()
    return {"message": "⏹ 자동 검사 중지됨"}


@router.get("/inspect/auto/status", summary="자동 검사 실행 상태 조회")
async def auto_inspect_status() -> dict[str, Any]:
    """자동 검사 실행 여부와 설정된 간격을 반환합니다."""
    return auto_status()
