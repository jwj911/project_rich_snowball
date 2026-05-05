from datetime import datetime, timedelta
from typing import Any, Optional, Callable
from threading import RLock
from collections import OrderedDict

DEFAULT_TTL_SECONDS = 5
_MAX_SIZE = 256

_cache: OrderedDict[str, Any] = OrderedDict()
_cache_time: dict[str, datetime] = {}
_lock = RLock()


def get_cached(key: str, db_fetch_func: Callable[[], Any], ttl: int = DEFAULT_TTL_SECONDS) -> Any:
    now = datetime.now()
    with _lock:
        if key in _cache:
            if now - _cache_time[key] < timedelta(seconds=ttl):
                # LRU: 移动到末尾（最近使用）
                _cache.move_to_end(key)
                return _cache[key]
            else:
                # TTL 过期，清理
                _cache.pop(key, None)
                _cache_time.pop(key, None)

    # 锁外执行 DB 查询，避免长时间持有锁
    data = db_fetch_func()

    with _lock:
        # 容量检查：淘汰最久未使用
        while len(_cache) >= _MAX_SIZE:
            oldest_key = next(iter(_cache))
            _cache.pop(oldest_key, None)
            _cache_time.pop(oldest_key, None)

        _cache[key] = data
        _cache_time[key] = now
        _cache.move_to_end(key)

    return data


def invalidate_cache(key: Optional[str] = None):
    with _lock:
        if key:
            _cache.pop(key, None)
            _cache_time.pop(key, None)
        else:
            _cache.clear()
            _cache_time.clear()


def get_cache_stats() -> dict:
    with _lock:
        return {
            "size": len(_cache),
            "max_size": _MAX_SIZE,
            "ttl_seconds": DEFAULT_TTL_SECONDS,
        }
