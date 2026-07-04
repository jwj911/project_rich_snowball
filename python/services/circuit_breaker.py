"""数据源熔断保护（Redis 优先 + 内存降级）。

连续失败超过阈值或最近窗口失败率超过阈值后，暂停该源一段时间，避免打爆外部 API。
- Redis 可用时：状态持久化到 Redis，支持多 worker/多实例共享
- Redis 不可用时：自动降级到内存实现，保证单机可用性

熔断条件（满足任一即打开）：
1. 连续失败次数 >= CIRCUIT_THRESHOLD
2. 最近 CIRCUIT_RATE_WINDOW 次尝试中，失败次数 / 总尝试次数 >= CIRCUIT_FAILURE_THRESHOLD
"""

from __future__ import annotations

import logging
import os
import time
from threading import Lock

from services.redis_client import get_redis_client, is_redis_available, mark_redis_unavailable

logger = logging.getLogger(__name__)

CIRCUIT_THRESHOLD = int(os.getenv("CIRCUIT_THRESHOLD", "5"))
CIRCUIT_COOLDOWN_SECONDS = int(os.getenv("CIRCUIT_COOLDOWN_SECONDS", "600"))
CIRCUIT_FAILURE_THRESHOLD = float(os.getenv("CIRCUIT_FAILURE_THRESHOLD", "0.5"))
CIRCUIT_RATE_WINDOW = int(os.getenv("CIRCUIT_RATE_WINDOW", "10"))
_REDIS_KEY_PREFIX = "futures:circuit"

# ---- 内存降级存储 ----
_FAILURE_COUNTS: dict[str, int] = {}
_LAST_FAILURE_TIME: dict[str, float] = {}
_RECENT_RESULTS: dict[str, list[int]] = {}  # 1=失败, 0=成功，长度 <= CIRCUIT_RATE_WINDOW
_LOCK = Lock()


def _redis_key(source: str) -> str:
    return f"{_REDIS_KEY_PREFIX}:{source}"


def _redis_get_state(source: str) -> dict | None:
    """从 Redis 读取熔断状态。"""
    if not is_redis_available():
        return None
    client = get_redis_client()
    if client is None:
        return None
    try:
        key = _redis_key(source)
        data = client.hgetall(key)
        if not data:
            return {"failure_count": 0, "last_failure_at": 0.0, "recent_results": ""}
        if not isinstance(data, dict):
            return {"failure_count": 0, "last_failure_at": 0.0, "recent_results": ""}
        return {
            "failure_count": int(data.get("failure_count", 0)),
            "last_failure_at": float(data.get("last_failure_at", 0.0)),
            "recent_results": data.get("recent_results", ""),
        }
    except Exception as e:
        logger.warning("Redis circuit read failed: %s", e)
        mark_redis_unavailable()
        return None


def _redis_set_state(source: str, failure_count: int, last: float, results: list[int]) -> None:
    """写入熔断状态到 Redis，并设置 TTL。"""
    if not is_redis_available():
        return
    client = get_redis_client()
    if client is None:
        return
    try:
        key = _redis_key(source)
        pipe = client.pipeline()
        pipe.hset(
            key,
            mapping={
                "failure_count": failure_count,
                "last_failure_at": last,
                "recent_results": ",".join(str(r) for r in results),
            },
        )
        pipe.expire(key, CIRCUIT_COOLDOWN_SECONDS + 60)
        pipe.execute()
    except Exception as e:
        logger.warning("Redis circuit write failed: %s", e)
        mark_redis_unavailable()


def _memory_get_state(source: str) -> tuple[int, float, list[int]]:
    # 调用方需持有 _LOCK
    return (
        _FAILURE_COUNTS.get(source, 0),
        _LAST_FAILURE_TIME.get(source, 0.0),
        _RECENT_RESULTS.get(source, []).copy(),
    )


def _memory_set_state(source: str, failure_count: int, last: float, results: list[int]) -> None:
    # 调用方需持有 _LOCK
    _FAILURE_COUNTS[source] = failure_count
    _LAST_FAILURE_TIME[source] = last
    _RECENT_RESULTS[source] = results.copy()


def _get_state(source: str) -> tuple[int, float, list[int]]:
    redis_state = _redis_get_state(source)
    if redis_state is not None:
        failure_count = int(redis_state.get("failure_count", 0))
        last = float(redis_state.get("last_failure_at", 0.0))
        results_str = redis_state.get("recent_results", "")
        results = [int(x) for x in results_str.split(",") if x] if results_str else []
        return failure_count, last, results
    return _memory_get_state(source)


def _set_state(source: str, failure_count: int, last: float, results: list[int]) -> None:
    _redis_set_state(source, failure_count, last, results)
    with _LOCK:
        _memory_set_state(source, failure_count, last, results)


def _reset_state(source: str) -> None:
    _set_state(source, 0, 0.0, [])


def _push_result(results: list[int], is_failure: bool) -> list[int]:
    """将最新结果推入滑动窗口。"""
    results = results[-(CIRCUIT_RATE_WINDOW - 1) :] if len(results) >= CIRCUIT_RATE_WINDOW else results
    results.append(1 if is_failure else 0)
    return results


def is_circuit_open(source: str) -> bool:
    """检查某数据源的熔断器是否已打开。"""
    failure_count, last, results = _get_state(source)
    now = time.time()

    # 冷却期内连续失败达到阈值
    if failure_count >= CIRCUIT_THRESHOLD:
        if now - last < CIRCUIT_COOLDOWN_SECONDS:
            return True
        # 冷却结束，重置计数
        _reset_state(source)

    # 最近窗口失败率达到阈值
    if len(results) >= CIRCUIT_RATE_WINDOW:
        failure_rate = sum(results) / len(results)
        if failure_rate >= CIRCUIT_FAILURE_THRESHOLD:
            # 进入失败率熔断冷却期
            _set_state(source, failure_count, now, results)
            return True

    return False


def record_failure(source: str) -> None:
    """记录一次采集失败。"""
    failure_count, last, results = _get_state(source)
    failure_count += 1
    last = time.time()
    results = _push_result(results, is_failure=True)
    _set_state(source, failure_count, last, results)


def record_success(source: str) -> None:
    """记录一次采集成功，重置连续失败计数并清空失败率窗口。"""
    _set_state(source, 0, 0.0, [])


def get_circuit_status(source: str | None = None) -> dict:
    """返回熔断器状态。source 为 None 时返回所有源（基于内存视图）。"""
    with _LOCK:
        if source:
            return _status_for_source(source)
        return {src: _status_for_source(src) for src in _FAILURE_COUNTS}


def _status_for_source(src: str) -> dict:
    failure_count, last, results = _get_state(src)
    now = time.time()
    consecutive_open = failure_count >= CIRCUIT_THRESHOLD and (now - last) < CIRCUIT_COOLDOWN_SECONDS
    rate_open = len(results) >= CIRCUIT_RATE_WINDOW and (sum(results) / len(results)) >= CIRCUIT_FAILURE_THRESHOLD
    return {
        "source": src,
        "failure_count": failure_count,
        "recent_results": results.copy(),
        "is_open": consecutive_open or rate_open,
        "threshold": CIRCUIT_THRESHOLD,
        "failure_rate_threshold": CIRCUIT_FAILURE_THRESHOLD,
        "rate_window": CIRCUIT_RATE_WINDOW,
        "cooldown_seconds": CIRCUIT_COOLDOWN_SECONDS,
        "last_failure_ago_seconds": int(now - last) if last > 0 else None,
    }
