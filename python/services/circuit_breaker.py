"""数据源熔断保护（Redis 优先 + 内存降级）。

连续失败超过阈值后暂停该源一段时间，避免打爆外部 API。
- Redis 可用时：状态持久化到 Redis，支持多 worker/多实例共享
- Redis 不可用时：自动降级到内存实现，保证单机可用性
"""

import logging
import time
from threading import Lock

from services.redis_client import get_redis_client, is_redis_available, mark_redis_unavailable

logger = logging.getLogger(__name__)

CIRCUIT_THRESHOLD = 5
CIRCUIT_COOLDOWN_SECONDS = 600
_REDIS_KEY_PREFIX = "futures:circuit"

# ---- 内存降级存储 ----
_FAILURE_COUNTS: dict[str, int] = {}
_LAST_FAILURE_TIME: dict[str, float] = {}
_LOCK = Lock()


def _redis_key(source: str) -> str:
    return f"{_REDIS_KEY_PREFIX}:{source}"


def _redis_get_state(source: str) -> tuple[int, float] | None:
    """从 Redis 读取熔断状态，返回 (failure_count, last_failure_time)。"""
    if not is_redis_available():
        return None
    client = get_redis_client()
    if client is None:
        return None
    try:
        key = _redis_key(source)
        data = client.hgetall(key)
        if not data:
            return 0, 0.0
        if not isinstance(data, dict):
            return 0, 0.0
        count = int(data.get("count", 0))
        last = float(data.get("last", 0.0))
        return count, last
    except Exception as e:
        logger.warning("Redis circuit read failed: %s", e)
        mark_redis_unavailable()
        return None


def _redis_set_state(source: str, count: int, last: float) -> None:
    """写入熔断状态到 Redis，并设置 TTL。"""
    if not is_redis_available():
        return
    client = get_redis_client()
    if client is None:
        return
    try:
        key = _redis_key(source)
        pipe = client.pipeline()
        pipe.hset(key, mapping={"count": count, "last": last})
        pipe.expire(key, CIRCUIT_COOLDOWN_SECONDS + 60)
        pipe.execute()
    except Exception as e:
        logger.warning("Redis circuit write failed: %s", e)
        mark_redis_unavailable()


def _memory_get_state(source: str) -> tuple[int, float]:
    # 调用方需持有 _LOCK
    return _FAILURE_COUNTS.get(source, 0), _LAST_FAILURE_TIME.get(source, 0.0)


def _memory_set_state(source: str, count: int, last: float) -> None:
    # 调用方需持有 _LOCK
    _FAILURE_COUNTS[source] = count
    _LAST_FAILURE_TIME[source] = last


def _get_state(source: str) -> tuple[int, float]:
    redis_state = _redis_get_state(source)
    if redis_state is not None:
        return redis_state
    return _memory_get_state(source)


def _set_state(source: str, count: int, last: float) -> None:
    _redis_set_state(source, count, last)
    _memory_set_state(source, count, last)


def is_circuit_open(source: str) -> bool:
    """检查某数据源的熔断器是否已打开。"""
    count, last = _get_state(source)
    if count >= CIRCUIT_THRESHOLD:
        if time.time() - last < CIRCUIT_COOLDOWN_SECONDS:
            return True
        # 冷却结束，重置计数
        _set_state(source, 0, 0.0)
    return False


def record_failure(source: str) -> None:
    """记录一次采集失败。"""
    count, last = _get_state(source)
    count += 1
    last = time.time()
    _set_state(source, count, last)


def record_success(source: str) -> None:
    """记录一次采集成功，重置失败计数。"""
    _set_state(source, 0, 0.0)


def get_circuit_status(source: str | None = None) -> dict:
    """返回熔断器状态。source 为 None 时返回所有源（基于内存视图）。"""
    with _LOCK:
        if source:
            return _status_for_source(source)
        return {src: _status_for_source(src) for src in _FAILURE_COUNTS}


def _status_for_source(src: str) -> dict:
    count, last = _get_state(src)
    now = time.time()
    open_state = count >= CIRCUIT_THRESHOLD and (now - last) < CIRCUIT_COOLDOWN_SECONDS
    return {
        "source": src,
        "failure_count": count,
        "is_open": open_state,
        "threshold": CIRCUIT_THRESHOLD,
        "cooldown_seconds": CIRCUIT_COOLDOWN_SECONDS,
        "last_failure_ago_seconds": int(now - last) if last > 0 else None,
    }
