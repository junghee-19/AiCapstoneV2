"""Inspection command controller shared by FastAPI routes and WebSocket handlers."""

import asyncio
import logging
import time
from typing import Any, Optional

from config.settings import settings
from models.schemas import InspectionPacket
from runtime.touchscreen_state import get_touchscreen_state

logger = logging.getLogger(__name__)

_auto_running: bool = False
_auto_interval: float = 5.0
_auto_task: Optional[asyncio.Task[None]] = None
_auto_waiting_for_exit: bool = False
_auto_cooldown_until: float = 0.0
_auto_capture_candidate_since: Optional[float] = None
_trigger_lock = asyncio.Lock()
AUTO_INSPECTION_ENABLED: bool = settings.AUTO_INSPECTION_ENABLED


def _packet_to_touchscreen_payload(packet: InspectionPacket) -> dict[str, Any]:
    """InspectionPacket 을 터치스크린 SSE 용 페이로드로 변환."""
    defects = [
        {
            "defectType": d.defect_type,
            "confidence": d.confidence,
            "bboxX": d.bbox_x,
            "bboxY": d.bbox_y,
            "bboxWidth": d.bbox_width,
            "bboxHeight": d.bbox_height,
        }
        for d in (packet.defects or [])
    ]
    fiducials: list[dict[str, Any]] = []
    if packet.fiducial1_x is not None and packet.fiducial1_y is not None:
        fiducials.append({
            "label": "F1",
            "x": packet.fiducial1_x,
            "y": packet.fiducial1_y,
            "confidence": packet.fiducial1_confidence,
        })
    if packet.fiducial2_x is not None and packet.fiducial2_y is not None:
        fiducials.append({
            "label": "F2",
            "x": packet.fiducial2_x,
            "y": packet.fiducial2_y,
            "confidence": packet.fiducial2_confidence,
        })
    image_url = None
    if packet.image_path:
        # /captures/xxx.jpg 형태로 마운트되어 있음 (edge/main.py 의 StaticFiles)
        from pathlib import Path
        try:
            name = Path(packet.image_path).name
            image_url = f"/captures/{name}"
        except Exception:
            image_url = None
    return {
        "result": packet.result.value if hasattr(packet.result, "value") else str(packet.result),
        "defects": defects,
        "fiducials": fiducials,
        "thresholds": {
            "fiducialConfidence": settings.effective_fiducial_confidence(),
            "defectConfidence": settings.effective_defect_confidence(),
        },
        "imageUrl": image_url,
        "inspectedAt": packet.inspected_at.isoformat() if packet.inspected_at else None,
    }


async def _notify_result(packet: InspectionPacket) -> None:
    """결과 페이로드를 터치스크린 상태에 반영. 다음 검사(BUSY)가 시작될 때까지 RESULT 유지."""
    state = get_touchscreen_state()
    payload = _packet_to_touchscreen_payload(packet)
    await state.set_result(
        result=payload["result"],
        defects=payload["defects"],
        image_url=payload["imageUrl"],
        inspected_at=payload["inspectedAt"],
        fiducials=payload["fiducials"],
        thresholds=payload["thresholds"],
    )


def auto_status() -> dict[str, Any]:
    cooldown_remaining = max(0.0, _auto_cooldown_until - time.monotonic())
    hold_remaining = 0.0
    if _auto_capture_candidate_since is not None:
        held_for = time.monotonic() - _auto_capture_candidate_since
        hold_remaining = max(0.0, settings.AUTO_CAPTURE_HOLD_SEC - held_for)
    return {
        "enabled": AUTO_INSPECTION_ENABLED,
        "running": _auto_running,
        "interval_seconds": _auto_interval,
        "waiting_for_pcb_exit": _auto_waiting_for_exit,
        "cooldown_remaining_seconds": round(cooldown_remaining, 1),
        "capture_hold_seconds": settings.AUTO_CAPTURE_HOLD_SEC,
        "capture_hold_remaining_seconds": round(hold_remaining, 1),
        "capture_candidate_active": _auto_capture_candidate_since is not None,
        "result_display_seconds": settings.AUTO_RESULT_DISPLAY_SEC,
    }


async def trigger_inspection_once(stage2_source_mode: Optional[str] = None) -> InspectionPacket:
    """Run one inspection and return its packet."""
    state = get_touchscreen_state()
    async with _trigger_lock:
        logger.info("[검사제어] 수동 검사 실행")
        await state.set_busy()
        try:
            import main as main_mod
        except ImportError as e:
            await state.set_idle()
            raise RuntimeError("검사 파이프라인을 로드할 수 없습니다.") from e

        if getattr(main_mod, "camera", None) is None:
            await state.set_idle()
            raise RuntimeError(
                "카메라가 초기화되지 않아 실제 검사를 실행할 수 없습니다. "
                "개발 환경에서는 /edge/inspect/dummy 또는 저장 이미지 검사를 사용하고, "
                "운영 환경에서는 컨테이너에 카메라 장치가 연결되어 있는지 확인하세요."
            )

        stage1_detector = (
            getattr(main_mod, "fiducial_detector", None)
            if getattr(main_mod.settings, "USE_SEPARATE_MODELS", False)
            else getattr(main_mod, "detector", None)
        )
        if stage1_detector is None:
            await state.set_idle()
            raise RuntimeError("Stage 1 YOLO 탐지기가 로드되지 않아 검사를 실행할 수 없습니다.")

        try:
            packet = await main_mod.run_inspection_pipeline(
                stage2_source_mode=stage2_source_mode,
                force_camera=True,
            )
        except Exception:
            await state.set_idle()
            raise

        if packet is None:
            await state.set_idle()
            raise RuntimeError("검사 실행 중 오류가 발생했습니다.")

        await _notify_result(packet)
        return packet


async def trigger_file_inspection(
    path: str,
    stage2_source_mode: Optional[str] = None,
) -> Optional[InspectionPacket]:
    """파일 기반 검사를 실행하고 터치스크린 상태도 함께 갱신한다."""
    state = get_touchscreen_state()
    async with _trigger_lock:
        logger.info("[검사제어] 파일 검사 실행: %s", path)
        await state.set_busy()
        try:
            from main import run_inspection_pipeline_from_source_file
        except ImportError as e:
            await state.set_idle()
            raise RuntimeError("검사 파이프라인을 로드할 수 없습니다.") from e

        try:
            packet = await run_inspection_pipeline_from_source_file(path, stage2_source_mode)
        except Exception:
            await state.set_idle()
            raise

        if packet is None:
            await state.set_idle()
            return None

        await _notify_result(packet)
        return packet


async def start_auto_inspection(interval: float = 5.0) -> dict[str, Any]:
    """Start the background auto-inspection loop if it is not already running."""
    global _auto_running, _auto_interval, _auto_task
    global _auto_waiting_for_exit, _auto_cooldown_until, _auto_capture_candidate_since

    if not AUTO_INSPECTION_ENABLED:
        task = _auto_task
        _auto_running = False
        _auto_task = None
        if task is not None and not task.done():
            task.cancel()
        logger.info("[검사제어] 자동 연속 검사는 임시 비활성화 상태입니다.")
        return auto_status()

    if interval <= 0:
        raise ValueError("interval must be greater than 0")

    if _auto_running:
        return auto_status()

    _auto_running = True
    _auto_waiting_for_exit = False
    _auto_cooldown_until = 0.0
    _auto_capture_candidate_since = None
    _auto_interval = float(interval)
    _auto_task = asyncio.create_task(_auto_inspect_loop(), name="edge-auto-inspection")
    logger.info("[검사제어] 자동 연속 검사 시작 — 간격: %.1f초", _auto_interval)
    return auto_status()


async def stop_auto_inspection() -> dict[str, Any]:
    """Stop the background auto-inspection loop."""
    global _auto_running, _auto_task
    global _auto_waiting_for_exit, _auto_cooldown_until, _auto_capture_candidate_since

    _auto_running = False
    _auto_waiting_for_exit = False
    _auto_cooldown_until = 0.0
    _auto_capture_candidate_since = None
    task = _auto_task
    _auto_task = None
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("[검사제어] 자동 연속 검사 중지")
    return auto_status()


async def _auto_inspect_loop() -> None:
    """Watch for PCB presence and run inspections repeatedly."""
    global _auto_running, _auto_waiting_for_exit, _auto_cooldown_until, _auto_capture_candidate_since

    idle_poll_seconds = settings.AUTO_INSPECTION_IDLE_POLL_SEC
    while _auto_running:
        try:
            from main import is_pcb_in_capture_area, run_inspection_pipeline_when_pcb_present

            cooldown_remaining = _auto_cooldown_until - time.monotonic()
            if cooldown_remaining > 0:
                _auto_capture_candidate_since = None
                await asyncio.sleep(min(idle_poll_seconds, cooldown_remaining))
                continue

            if _auto_waiting_for_exit:
                _auto_capture_candidate_since = None
                present, reason = await asyncio.to_thread(is_pcb_in_capture_area)
                if present:
                    logger.debug("[자동검사] 이전 PCB 배출 대기 중 — %s", reason)
                    await asyncio.sleep(idle_poll_seconds)
                    continue
                _auto_waiting_for_exit = False
                logger.info("[자동검사] PCB 배출 확인 — 다음 PCB 감시 재개")

            logger.info("[자동검사] PCB 감시 중...")
            present, reason = await asyncio.to_thread(is_pcb_in_capture_area)
            if not present:
                if _auto_capture_candidate_since is not None:
                    logger.info("[자동검사] 촬영 대기 조건 해제 — %s", reason)
                _auto_capture_candidate_since = None
                logger.debug("[자동검사] PCB 촬영 대기 — %s", reason)
                await asyncio.sleep(idle_poll_seconds)
                continue

            now = time.monotonic()
            if _auto_capture_candidate_since is None:
                _auto_capture_candidate_since = now
                logger.info("[자동검사] PCB 위치 확인 — %.1f초 유지 후 촬영", settings.AUTO_CAPTURE_HOLD_SEC)

            held_for = now - _auto_capture_candidate_since
            hold_remaining = settings.AUTO_CAPTURE_HOLD_SEC - held_for
            if hold_remaining > 0:
                logger.debug("[자동검사] 촬영 전 대기 중 — 남은 %.1f초 (%s)", hold_remaining, reason)
                await asyncio.sleep(min(idle_poll_seconds, hold_remaining))
                continue

            state = get_touchscreen_state()
            await state.set_busy("PCB 감지됨 — 자동 검사 중...")
            async with _trigger_lock:
                packet = await asyncio.to_thread(run_inspection_pipeline_when_pcb_present)
            if packet is not None:
                _auto_capture_candidate_since = None
                await _notify_result(packet)
                _auto_waiting_for_exit = True
                _auto_cooldown_until = (
                    time.monotonic()
                    + settings.AUTO_RESULT_DISPLAY_SEC
                    + settings.AUTO_CAPTURE_COOLDOWN_SEC
                )
                logger.info("[자동검사] 검사 완료 — 다음 감시까지 %.1f초 대기", _auto_interval)
                await asyncio.sleep(_auto_interval)
                continue
            _auto_capture_candidate_since = None
            await state.set_idle()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("[자동검사] 파이프라인 오류: %s", e)

        if _auto_running:
            await asyncio.sleep(idle_poll_seconds)
