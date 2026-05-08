"""Small helpers for edge WebSocket control messages."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def make_event(
    event_type: str,
    *,
    request_id: Optional[str] = None,
    ok: bool = True,
    payload: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
    device_id: str = "RPI5-LINE-A",
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": event_type,
        "ok": ok,
        "deviceId": device_id,
        "timestamp": datetime.now().isoformat(),
    }
    if request_id is not None:
        data["requestId"] = request_id
    if payload is not None:
        data["payload"] = payload
    if error is not None:
        data["error"] = error
    return data


def packet_summary(packet: Any) -> dict[str, Any]:
    return {
        "result": packet.result.value,
        "totalTimeMs": packet.total_time_ms,
        "inferenceTimeMs": packet.inference_time_ms,
        "imagePath": packet.image_path,
        "defectCount": len(packet.defects),
        "inspectedAt": packet.inspected_at.isoformat(),
    }

