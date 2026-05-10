"""
라즈베리파이 터치스크린 UI 라우터.

구성:
    GET  /touch          → static/index.html 서빙
    GET  /touch/events   → Server-Sent Events 로 상태 푸시
                           (IDLE / BUSY / RESULT)

라이브 카메라 영상은 기존 라우터의
    GET /edge/camera/stream
을 그대로 사용한다.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse

from runtime.touchscreen_state import get_touchscreen_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/touch", tags=["Touchscreen"])

# edge/api/touchscreen.py → ../pi-touchscreen/  (정적 UI 는 별도 폴더로 분리)
_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "pi-touchscreen"


@router.get("/", summary="터치스크린 메인 HTML")
async def serve_index() -> FileResponse:
    """터치스크린 브라우저(키오스크)가 처음 열 페이지."""
    return FileResponse(str(_STATIC_DIR / "index.html"), media_type="text/html")


@router.post("/dismiss", summary="결과 화면 닫고 라이브 화면으로 복귀")
async def dismiss_result() -> dict:
    """터치스크린에서 RESULT 화면을 탭하면 호출 — IDLE 로 전환해 라이브 카메라 표시."""
    await get_touchscreen_state().set_idle()
    return {"ok": True, "status": "IDLE"}


@router.get("/events", summary="터치스크린 상태 SSE")
async def sse_events() -> StreamingResponse:
    """
    Server-Sent Events: 상태 변경(IDLE / BUSY / RESULT) 발생 시 즉시 푸시.

    클라이언트(브라우저)는 EventSource('/touch/events') 로 구독.
    각 이벤트는 JSON 한 줄로 직렬화되어 'data:' 프리픽스로 전송된다.
    """
    state = get_touchscreen_state()

    async def event_stream():
        try:
            async for message in state.subscribe():
                yield f"data: {message}\n\n"
        except asyncio.CancelledError:
            logger.debug("[터치스크린 SSE] 클라이언트 연결 종료")
            raise

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",   # nginx/proxy 버퍼링 방지
        "Connection": "keep-alive",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
