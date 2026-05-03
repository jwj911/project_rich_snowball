from datetime import datetime, timedelta
from typing import Any, Optional, Callable

_cache = {}
_cache_time = {}
DEFAULT_TTL_SECONDS = 5


def get_cached(key: str, db_fetch_func: Callable[[], Any], ttl: int = DEFAULT_TTL_SECONDS) -> Any:
    now = datetime.now()
    if key in _cache:
        if now - _cache_time[key] < timedelta(seconds=ttl):
            return _cache[key]
    data = db_fetch_func()
    _cache[key] = data
    _cache_time[key] = now
    return data


def invalidate_cache(key: Optional[str] = None):
    if key:
        _cache.pop(key, None)
        _cache_time.pop(key, None)
    else:
        _cache.clear()
        _cache_time.clear()
