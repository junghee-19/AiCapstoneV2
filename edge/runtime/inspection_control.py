"""Inspection command controller shared by FastAPI routes and WebSocket handlers."""

import asyncio
import logging
from typing import Any, Optional

from models.schemas import InspectionPacket
from runtime.touchscreen_state import get_touchscreen_state

logger = logging.getLogger(__name__)

_auto_running: bool = False
_auto_interval: float = 5.0
_auto_task: Optional[asyncio.Task[None]] = None
_trigger_lock = asyncio.Lock()
_idle_revert_task: Optional[asyncio.Task[None]] = None
RESULT_DISPLAY_SECONDS: float = 6.0
AUTO_INSPECTION_ENABLED: bool = False


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
        "imageUrl": image_url,
        "inspectedAt": packet.inspected_at.isoformat() if packet.inspected_at else None,
    }


async def _notify_result(packet: InspectionPacket) -> None:
    state = get_touchscreen_state()
    payload = _packet_to_touchscreen_payload(packet)
    await state.set_result(
        result=payload["result"],
        defects=payload["defects"],
        image_url=payload["imageUrl"],
        inspected_at=payload["inspectedAt"],
    )

    # RESULT_DISPLAY_SECONDS 후 IDLE 로 자동 복귀
    global _idle_revert_task
    if _idle_revert_task and not _idle_revert_task.done():
        _idle_revert_task.cancel()
    _idle_revert_task = asyncio.create_task(_revert_to_idle_after(RESULT_DISPLAY_SECONDS))


async def _revert_to_idle_after(seconds: float) -> None:
    try:
        await asyncio.sleep(seconds)
        await get_touchscreen_state().set_idle()
    except asyncio.CancelledError:
        pass


def auto_status() -> dict[str, Any]:
    return {
        "enabled": AUTO_INSPECTION_ENABLED,
        "running": _auto_running,
        "interval_seconds": _auto_interval,
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


async def start_auto_inspection(interval: float = 5.0) -> dict[str, Any]:
    """Start the background auto-inspection loop if it is not already running."""
    global _auto_running, _auto_interval, _auto_task

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
    _auto_interval = float(interval)
    _auto_task = asyncio.create_task(_auto_inspect_loop(), name="edge-auto-inspection")
    logger.info("[검사제어] 자동 연속 검사 시작 — 간격: %.1f초", _auto_interval)
    return auto_status()


async def stop_auto_inspection() -> dict[str, Any]:
    """Stop the background auto-inspection loop."""
    global _auto_running, _auto_task

    _auto_running = False
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
    global _auto_running

    idle_poll_seconds = 0.5
    while _auto_running:
        try:
            from main import run_inspection_pipeline_when_pcb_present

            logger.info("[자동검사] PCB 감시 중...")
            async with _trigger_lock:
                performed = await asyncio.to_thread(run_inspection_pipeline_when_pcb_present)
            if performed:
                logger.info("[자동검사] 검사 완료 — 다음 감시까지 %.1f초 대기", _auto_interval)
                await asyncio.sleep(_auto_interval)
                continue
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("[자동검사] 파이프라인 오류: %s", e)

        if _auto_running:
            await asyncio.sleep(idle_poll_seconds)
