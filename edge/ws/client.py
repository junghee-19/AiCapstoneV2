"""Persistent WebSocket client that lets the Spring server control the edge node."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional
from urllib.parse import urlencode

import websockets

from config.settings import settings
from runtime.inspection_control import auto_status
from ws.handlers import handle_server_message
from ws.protocol import make_event

logger = logging.getLogger(__name__)


def resolve_ws_url() -> str:
    if settings.EDGE_WS_URL:
        return settings.EDGE_WS_URL

    base = settings.SERVER_BASE_URL.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]
    else:
        base = "ws://" + base
    return f"{base}{settings.EDGE_WS_PATH}"


async def run_edge_ws_client(stop_event: Optional[asyncio.Event] = None) -> None:
    """Connect to the server and process control commands until cancelled."""
    if not settings.EDGE_WS_ENABLED:
        logger.info("[WS] EDGE_WS_ENABLED=false — 서버 WebSocket 연결 생략")
        return

    while stop_event is None or not stop_event.is_set():
        url = _url_with_device_id(resolve_ws_url())
        try:
            logger.info("[WS] 서버 연결 시도: %s", url)
            async with websockets.connect(
                url,
                ping_interval=settings.EDGE_WS_PING_INTERVAL_SEC,
                ping_timeout=settings.EDGE_WS_PING_TIMEOUT_SEC,
                close_timeout=3,
                max_size=1024 * 1024,
            ) as websocket:
                logger.info("[WS] 서버 연결 완료")
                await _send_json(
                    websocket,
                    make_event(
                        "edge.connected",
                        payload={"auto": auto_status()},
                        device_id=settings.EDGE_DEVICE_ID,
                    ),
                )

                async for raw in websocket:
                    response = await _handle_raw_message(raw)
                    await _send_json(websocket, response)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(
                "[WS] 연결 종료/실패: %s — %.1f초 후 재연결",
                e,
                settings.EDGE_WS_RECONNECT_DELAY_SEC,
            )
            try:
                await asyncio.wait_for(
                    stop_event.wait() if stop_event else asyncio.sleep(settings.EDGE_WS_RECONNECT_DELAY_SEC),
                    timeout=settings.EDGE_WS_RECONNECT_DELAY_SEC,
                )
            except asyncio.TimeoutError:
                pass


async def _handle_raw_message(raw: Any) -> dict[str, Any]:
    try:
        message = json.loads(raw)
        if not isinstance(message, dict):
            raise ValueError("WebSocket message must be a JSON object")
    except Exception as e:
        return make_event(
            "edge.command.error",
            ok=False,
            error=f"Invalid message: {e}",
            device_id=settings.EDGE_DEVICE_ID,
        )
    return await handle_server_message(message)


async def _send_json(websocket: Any, message: dict[str, Any]) -> None:
    await websocket.send(json.dumps(message, ensure_ascii=False))


def _url_with_device_id(url: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{urlencode({'deviceId': settings.EDGE_DEVICE_ID})}"

