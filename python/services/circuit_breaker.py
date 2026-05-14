"""数据源熔断保护（内存实现）。

连续失败超过阈值后暂停该源一段时间，避免打爆外部 API。
Phase 5 可替换为 Redis 持久化实现。
"""
import time
import threading
from typing import Optional

_FAILURE_COUNTS: dict[str, int] = {}
_LAST_FAILURE_TIME: dict[str, float] = {}
_LOCK = threading.Lock()

CIRCUIT_THRESHOLD = 5
CIRCUIT_COOLDOWN_SECONDS = 600


def is_circuit_open(source: str) -> bool:
    """检查某数据源的熔断器是否已打开。"""
    with _LOCK:
        if _FAILURE_COUNTS.get(source, 0) >= CIRCUIT_THRESHOLD:
            if time.time() - _LAST_FAILURE_TIME.get(source, 0) < CIRCUIT_COOLDOWN_SECONDS:
                return True
            # 冷却结束，重置计数
            _FAILURE_COUNTS[source] = 0
        return False


def record_failure(source: str) -> None:
    """记录一次采集失败。"""
    with _LOCK:
        _FAILURE_COUNTS[source] = _FAILURE_COUNTS.get(source, 0) + 1
        _LAST_FAILURE_TIME[source] = time.time()


def record_success(source: str) -> None:
    """记录一次采集成功，重置失败计数。"""
    with _LOCK:
        if source in _FAILURE_COUNTS:
            _FAILURE_COUNTS[source] = 0


def get_circuit_status(source: Optional[str] = None) -> dict:
    """返回熔断器状态。source 为 None 时返回所有源。"""
    with _LOCK:
        if source:
            return _status_for_source(source)
        return {
            src: _status_for_source(src)
            for src in _FAILURE_COUNTS
        }


def _status_for_source(src: str) -> dict:
    count = _FAILURE_COUNTS.get(src, 0)
    last = _LAST_FAILURE_TIME.get(src, 0)
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
