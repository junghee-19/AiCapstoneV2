"""
시계열 결함 alarm — 인메모리 ring buffer

device_id 별 직전 N회 검사 결과를 보관하다가,
같은 결함 타입이 같은 위치(±tol px)에서 M회 이상 반복되면 alarm=True 를 반환한다.

엣지 프로세스 재시작 시 휘발 — 라인 운영 중 즉시 반응 용도.
영구 통계가 필요하면 Spring Boot 백엔드에서 별도 집계.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)


# device_id -> deque of inspection snapshots
# 각 snapshot은 ((defect_type, center_x, center_y), ...) 튜플 리스트
_history: dict[str, deque[list[tuple[str, float, float]]]] = {}
_lock = threading.Lock()


def _matches(
    a: tuple[str, float, float],
    b: tuple[str, float, float],
    tol: float,
) -> bool:
    """타입 일치 + 중심 거리 tol 이하면 동일 결함으로 간주."""
    if a[0] != b[0]:
        return False
    return math.hypot(a[1] - b[1], a[2] - b[2]) <= tol


def record_and_check(
    device_id: str,
    current_defects: list[tuple[str, float, float]],
) -> tuple[bool, Optional[str]]:
    """
    이번 검사 결과를 history에 추가하고 alarm 여부를 계산한다.

    Args:
        device_id: 엣지 디바이스 ID
        current_defects: 이번 검사에서 검출된 [(defect_type, center_x, center_y), ...]

    Returns:
        (alarm, reason) — reason은 alarm=True일 때만 사람이 읽는 사유 문자열.
    """
    if not settings.DEFECT_ALARM_ENABLED:
        return False, None

    n_window = settings.DEFECT_ALARM_WINDOW_N
    threshold = settings.DEFECT_ALARM_THRESHOLD_M
    tol = settings.DEFECT_ALARM_POSITION_TOL_PX

    with _lock:
        buf = _history.get(device_id)
        if buf is None or buf.maxlen != n_window:
            buf = deque(maxlen=n_window)
            _history[device_id] = buf

        # 이번 검사 직전까지의 history (M-1회 이상 매치되면 이번 회차 포함 alarm)
        prior_history = list(buf)
        buf.append(list(current_defects))

    if not current_defects or not prior_history:
        return False, None

    # 이번 결함 각각에 대해, 직전 검사들 중 매치된 횟수가 (threshold-1) 이상인지 확인
    for cur in current_defects:
        match_count = 1  # 이번 회차 자체 포함
        for past_snapshot in prior_history:
            if any(_matches(cur, past, tol) for past in past_snapshot):
                match_count += 1
        if match_count >= threshold:
            reason = (
                f"defect '{cur[0]}' near ({cur[1]:.1f},{cur[2]:.1f}) "
                f"appeared {match_count}/{len(prior_history) + 1} recent inspections "
                f"(threshold={threshold}, tol={tol:.0f}px)"
            )
            logger.warning("[ALARM] %s — %s", device_id, reason)
            return True, reason

    return False, None


def reset(device_id: Optional[str] = None) -> None:
    """테스트/운영자 요청 시 history 초기화."""
    with _lock:
        if device_id is None:
            _history.clear()
        else:
            _history.pop(device_id, None)
