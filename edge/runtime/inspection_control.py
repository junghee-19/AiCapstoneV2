"""Inspection command controller shared by FastAPI routes and WebSocket handlers."""

import asyncio
import logging
from typing import Any, Optional

from models.schemas import InspectionPacket

logger = logging.getLogger(__name__)

_auto_running: bool = False
_auto_interval: float = 5.0
_auto_task: Optional[asyncio.Task[None]] = None
_trigger_lock = asyncio.Lock()


def auto_status() -> dict[str, Any]:
    return {
        "running": _auto_running,
        "interval_seconds": _auto_interval,
    }


async def trigger_inspection_once(stage2_source_mode: Optional[str] = None) -> InspectionPacket:
    """Run one inspection and return its packet."""
    async with _trigger_lock:
        logger.info("[검사제어] 수동 검사 실행")
        try:
            from main import run_inspection_pipeline
        except ImportError as e:
            raise RuntimeError("검사 파이프라인을 로드할 수 없습니다.") from e

        packet = await run_inspection_pipeline(stage2_source_mode=stage2_source_mode)
        if packet is None:
            raise RuntimeError("검사 실행 중 오류가 발생했습니다.")
        return packet


async def start_auto_inspection(interval: float = 5.0) -> dict[str, Any]:
    """Start the background auto-inspection loop if it is not already running."""
    global _auto_running, _auto_interval, _auto_task

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
