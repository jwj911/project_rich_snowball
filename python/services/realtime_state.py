"""
实时行情数据状态
================
维护本地及 Redis 共享的更新时间标记，供 SSE 推送端点判断数据是否有更新。

原理：
- scheduler 每次完成 realtime_quotes 刷新后，调用 mark_realtime_updated()
- worker 先更新本地时间，再尽力把同一时间写入 Redis
- SSE 生成器使用本地与共享标记中的较新值，并在 Redis 降级时每 60 秒强制刷新
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock

from services.redis_client import get_redis_client, is_redis_available, mark_redis_unavailable

logger = logging.getLogger(__name__)

REALTIME_UPDATE_MARKER_KEY = "futures:realtime:update_time"
FALLBACK_FORCE_REFRESH_SECONDS = 60
_MIN_UPDATE_TIME = datetime.min.replace(tzinfo=UTC)

_last_update_time = _MIN_UPDATE_TIME
_state_lock = Lock()
_health_lock = Lock()
_shared_marker_degraded = False


@dataclass(frozen=True)
class RealtimeUpdateState:
    """供 SSE 消费的实时行情更新状态。"""

    last_update_time: datetime
    shared_available: bool
    force_refresh: bool


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _record_shared_health(available: bool, reason: str | None = None) -> None:
    """只在状态切换时记录不含连接信息的共享标记健康日志。"""
    global _shared_marker_degraded
    with _health_lock:
        if available:
            if _shared_marker_degraded:
                logger.info("realtime_update_marker_redis_recovered")
            _shared_marker_degraded = False
            return
        if not _shared_marker_degraded:
            logger.warning(
                "realtime_update_marker_degraded reason=%s fallback_refresh_seconds=%d",
                reason,
                FALLBACK_FORCE_REFRESH_SECONDS,
            )
        _shared_marker_degraded = True


def _serialize_update_time(update_time: datetime) -> str:
    return update_time.astimezone(UTC).isoformat()


def _parse_update_time(raw_value: object) -> datetime:
    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("ascii")
    if not isinstance(raw_value, str):
        raise ValueError("update marker must be a string")
    update_time = datetime.fromisoformat(raw_value)
    if update_time.tzinfo is None:
        raise ValueError("update marker must include a timezone")
    return update_time.astimezone(UTC)


def _write_shared_update_time(update_time: datetime) -> None:
    try:
        if not is_redis_available():
            _record_shared_health(False, "redis_unavailable")
            return
        client = get_redis_client()
        if client is None:
            _record_shared_health(False, "redis_unavailable")
            return
        client.set(REALTIME_UPDATE_MARKER_KEY, _serialize_update_time(update_time))
    except Exception:
        mark_redis_unavailable()
        _record_shared_health(False, "redis_write_failed")
        return
    _record_shared_health(True)


def _read_shared_update_time() -> tuple[datetime | None, bool]:
    try:
        if not is_redis_available():
            _record_shared_health(False, "redis_unavailable")
            return None, False
        client = get_redis_client()
        if client is None:
            _record_shared_health(False, "redis_unavailable")
            return None, False
        raw_value = client.get(REALTIME_UPDATE_MARKER_KEY)
    except Exception:
        mark_redis_unavailable()
        _record_shared_health(False, "redis_read_failed")
        return None, False

    if raw_value is None:
        _record_shared_health(True)
        return None, True
    try:
        update_time = _parse_update_time(raw_value)
    except (UnicodeError, ValueError):
        _record_shared_health(False, "invalid_shared_marker")
        return None, False
    _record_shared_health(True)
    return update_time, True


def mark_realtime_updated() -> None:
    """在成功刷新后更新本地标记，并尽力发布 Redis 共享标记。"""
    global _last_update_time
    update_time = _utc_now()
    with _state_lock:
        _last_update_time = max(_last_update_time, update_time)
        effective_update_time = _last_update_time
    _write_shared_update_time(effective_update_time)


def get_realtime_update_state(seconds_since_refresh: float | None = None) -> RealtimeUpdateState:
    """读取本地/共享较新标记，并计算 Redis 降级时的有界强刷状态。"""
    with _state_lock:
        local_update_time = _last_update_time
    shared_update_time, shared_available = _read_shared_update_time()
    effective_update_time = max(local_update_time, shared_update_time or _MIN_UPDATE_TIME)
    force_refresh = (
        not shared_available
        and seconds_since_refresh is not None
        and seconds_since_refresh >= FALLBACK_FORCE_REFRESH_SECONDS
    )
    return RealtimeUpdateState(
        last_update_time=effective_update_time,
        shared_available=shared_available,
        force_refresh=force_refresh,
    )


def get_last_update_time() -> datetime:
    """获取本地与 Redis 共享标记中的较新更新时间。"""
    return get_realtime_update_state().last_update_time
