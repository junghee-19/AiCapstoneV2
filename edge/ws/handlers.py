"""Command handlers for server-originated WebSocket control messages."""

from __future__ import annotations

import logging
from typing import Any

from config.settings import settings
from runtime.inspection_control import (
    auto_status,
    start_auto_inspection,
    stop_auto_inspection,
    trigger_inspection_once,
)
from ws.protocol import make_event, packet_summary

logger = logging.getLogger(__name__)


def _normalize_stage2_mode(payload: dict[str, Any]) -> str:
    stage2_source = payload.get("stage2Source", payload.get("stage2_source"))
    mode = (stage2_source or settings.STAGE2_SOURCE_MODE).strip().lower()
    if mode == "deskew":
        mode = "aligned"
    if mode not in {"raw", "aligned"}:
        raise ValueError("stage2Source must be 'raw' or 'aligned'")
    return mode


async def handle_server_message(message: dict[str, Any]) -> dict[str, Any]:
    command = str(message.get("type") or message.get("command") or "").strip()
    request_id = message.get("requestId") or message.get("request_id")
    payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}

    try:
        if command in {"inspect.trigger", "inspect/trigger", "/inspect/trigger"}:
            packet = await trigger_inspection_once(_normalize_stage2_mode(payload))
            return make_event(
                "inspect.trigger.result",
                request_id=request_id,
                payload=packet_summary(packet),
                device_id=settings.EDGE_DEVICE_ID,
            )

        if command in {"inspect.auto.start", "inspect/auto/start", "/inspect/auto/start"}:
            interval = float(payload.get("interval", payload.get("intervalSeconds", 5.0)))
            status = await start_auto_inspection(interval)
            return make_event(
                "inspect.auto.status",
                request_id=request_id,
                payload=status,
                device_id=settings.EDGE_DEVICE_ID,
            )

        if command in {"inspect.auto.stop", "inspect/auto/stop", "/inspect/auto/stop"}:
            status = await stop_auto_inspection()
            return make_event(
                "inspect.auto.status",
                request_id=request_id,
                payload=status,
                device_id=settings.EDGE_DEVICE_ID,
            )

        if command in {"inspect.auto.status", "inspect/auto/status", "/inspect/auto/status"}:
            return make_event(
                "inspect.auto.status",
                request_id=request_id,
                payload=auto_status(),
                device_id=settings.EDGE_DEVICE_ID,
            )

        return make_event(
            "edge.command.error",
            request_id=request_id,
            ok=False,
            error=f"Unsupported command: {command or '<empty>'}",
            device_id=settings.EDGE_DEVICE_ID,
        )
    except Exception as e:
        logger.exception("[WS] 명령 처리 실패: %s", command)
        return make_event(
            "edge.command.error",
            request_id=request_id,
            ok=False,
            error=str(e),
            device_id=settings.EDGE_DEVICE_ID,
        )

