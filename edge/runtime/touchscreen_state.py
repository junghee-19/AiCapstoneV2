"""
터치스크린 UI 상태 브로드캐스터.

검사 파이프라인이 상태를 변경하면 모든 SSE 구독자(터치 브라우저)에게
실시간으로 푸시한다. 동시 접속자 다수에 안전하도록 asyncio.Queue 기반 fan-out.

상태 종류:
    IDLE    — 라이브 카메라 화면
    BUSY    — 검사 중 (스피너)
    RESULT  — 결과 화면 (PASS / FAIL + 결함 박스)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)


class TouchscreenState:
    """SSE pub/sub 허브. 단일 인스턴스(_instance)를 모듈 전역에서 사용."""

    def __init__(self) -> None:
        self._status: str = "IDLE"
        self._snapshot: dict[str, Any] = {"status": "IDLE"}
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._lock = asyncio.Lock()

    @property
    def status(self) -> str:
        return self._status

    def snapshot(self) -> dict[str, Any]:
        """SSE 첫 연결 시 즉시 푸시할 현재 상태."""
        return dict(self._snapshot)

    async def set_idle(self) -> None:
        await self._update({"status": "IDLE"})

    async def set_busy(self, message: str = "검사 중...") -> None:
        await self._update({"status": "BUSY", "message": message})

    async def set_result(
        self,
        result: str,
        defects: list[dict[str, Any]],
        image_url: Optional[str] = None,
        inspected_at: Optional[str] = None,
    ) -> None:
        """검사 완료 — 결과 화면으로 전환."""
        await self._update(
            {
                "status": "RESULT",
                "result": result,             # "PASS" | "FAIL" | "SKIPPED"
                "defects": defects,           # [{defectType, bboxX, bboxY, bboxWidth, bboxHeight}, ...]
                "imageUrl": image_url,        # 검사한 이미지 정적 경로 (예: /captures/xxx.jpg)
                "inspectedAt": inspected_at,
            }
        )

    async def _update(self, payload: dict[str, Any]) -> None:
        self._status = payload.get("status", self._status)
        self._snapshot = payload
        await self._broadcast(payload)

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload, ensure_ascii=False)
        async with self._lock:
            dead: list[asyncio.Queue[str]] = []
            for queue in self._subscribers:
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    dead.append(queue)
            for queue in dead:
                self._subscribers.discard(queue)
        logger.debug("[터치스크린] 상태 브로드캐스트: %s (구독자 %d)", payload.get("status"), len(self._subscribers))

    async def subscribe(self) -> AsyncIterator[str]:
        """SSE 한 클라이언트의 메시지 스트림. 구독자에서 빠지면 자동 해제."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=16)
        async with self._lock:
            self._subscribers.add(queue)

        # 첫 연결에 현재 상태 즉시 전달
        try:
            queue.put_nowait(json.dumps(self._snapshot, ensure_ascii=False))
        except asyncio.QueueFull:
            pass

        try:
            while True:
                message = await queue.get()
                yield message
        finally:
            async with self._lock:
                self._subscribers.discard(queue)


# 모듈 전역 싱글턴
_instance = TouchscreenState()


def get_touchscreen_state() -> TouchscreenState:
    return _instance
