"""
缓存服务
========
支持 Redis（优先）和内存 LRU（降级）双模式。
Redis 不可用时自动降级到内存实现，确保应用始终可运行。
"""

import json
import logging
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Lock, RLock
from typing import Any
from weakref import WeakValueDictionary

from config import CACHE_MAX_SIZE
from services.metrics import cache_operations_total
from services.redis_client import get_redis_client, is_redis_available, mark_redis_unavailable

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 5
_MAX_SIZE = CACHE_MAX_SIZE

# 内存降级缓存
_cache: OrderedDict[str, Any] = OrderedDict()
_cache_time: dict[str, datetime] = {}
_lock = RLock()

# 缓存击穿防护：按 key 粒度加锁，保证同 key 并发 miss 时仅一个线程回源
_fetch_locks: WeakValueDictionary[str, RLock] = WeakValueDictionary()
_fetch_locks_lock = Lock()


def get_cached(key: str, db_fetch_func: Callable[[], Any], ttl: int = DEFAULT_TTL_SECONDS) -> Any:
    """获取缓存值。Redis 优先，不可用时降级到内存 LRU。"""
    if is_redis_available():
        return _get_cached_redis(key, db_fetch_func, ttl)
    return _get_cached_memory(key, db_fetch_func, ttl)


def _get_fetch_lock(key: str) -> RLock:
    """获取指定 key 的回源互斥锁（WeakValueDictionary 自动释放无引用的锁对象）。"""
    with _fetch_locks_lock:
        lock = _fetch_locks.get(key)
        if lock is None:
            lock = RLock()
            _fetch_locks[key] = lock
        return lock


def _get_cached_redis(key: str, db_fetch_func: Callable[[], Any], ttl: int) -> Any:
    """Redis 缓存实现（含缓存击穿防护）。"""
    client = get_redis_client()
    if client is None:
        # 极端情况：is_redis_available() 为真但 client 为 None
        return _get_cached_memory(key, db_fetch_func, ttl)

    try:
        val = client.get(key)
        if val is not None:
            cache_operations_total.labels(operation="get", result="hit").inc()
            try:
                return json.loads(val)
            except Exception:
                return val
        cache_operations_total.labels(operation="get", result="miss").inc()
    except Exception as exc:
        cache_operations_total.labels(operation="get", result="miss").inc()
        logger.warning("Redis get failed for key %s: %s", key, exc)
        mark_redis_unavailable()
        return _get_cached_memory(key, db_fetch_func, ttl)

    # 缓存击穿防护：同 key 仅一个线程执行 db_fetch_func
    lock = _get_fetch_lock(key)
    with lock:
        # 双重检查：其他线程可能已回源完成
        try:
            val = client.get(key)
            if val is not None:
                cache_operations_total.labels(operation="get", result="hit").inc()
                try:
                    return json.loads(val)
                except Exception:
                    return val
        except Exception as exc:
            logger.warning("Redis double-check get failed for key %s: %s", key, exc)
            mark_redis_unavailable()

        # 缓存未命中，执行 DB 查询
        data = db_fetch_func()

        try:
            client.setex(key, ttl, json.dumps(data, default=str))
            cache_operations_total.labels(operation="set", result="success").inc()
        except Exception as exc:
            logger.warning("Redis set failed for key %s: %s", key, exc)
            mark_redis_unavailable()

        return data


def _get_cached_memory(key: str, db_fetch_func: Callable[[], Any], ttl: int) -> Any:
    """内存 LRU 缓存实现（Redis 不可用时降级，含缓存击穿防护）。"""
    now = datetime.now(timezone.utc)
    with _lock:
        if key in _cache:
            if now - _cache_time[key] < timedelta(seconds=ttl):
                _cache.move_to_end(key)
                cache_operations_total.labels(operation="get", result="hit").inc()
                return _cache[key]
            else:
                _cache.pop(key, None)
                _cache_time.pop(key, None)
                cache_operations_total.labels(operation="get", result="expired").inc()
        else:
            cache_operations_total.labels(operation="get", result="miss").inc()

    # 缓存击穿防护：同 key 仅一个线程执行 db_fetch_func
    lock = _get_fetch_lock(key)
    with lock:
        # 双重检查
        with _lock:
            if key in _cache and now - _cache_time[key] < timedelta(seconds=ttl):
                _cache.move_to_end(key)
                cache_operations_total.labels(operation="get", result="hit").inc()
                return _cache[key]

        data = db_fetch_func()

        with _lock:
            while len(_cache) >= _MAX_SIZE:
                oldest_key = next(iter(_cache))
                _cache.pop(oldest_key, None)
                _cache_time.pop(oldest_key, None)

            _cache[key] = data
            _cache_time[key] = now
            _cache.move_to_end(key)
            cache_operations_total.labels(operation="set", result="success").inc()

        return data


def invalidate_cache(key: str | None = None):
    """清除缓存。Redis 优先，同时清理内存降级缓存。"""
    if is_redis_available():
        client = get_redis_client()
        if client:
            try:
                if key:
                    client.delete(key)
                else:
                    # Redis 慎用 flushdb，这里只清理带特定前缀的键
                    for k in client.scan_iter(match="futures:*"):
                        client.delete(k)
            except Exception as exc:
                logger.warning("Redis invalidate failed: %s", exc)
                mark_redis_unavailable()

    with _lock:
        if key:
            _cache.pop(key, None)
            _cache_time.pop(key, None)
        else:
            _cache.clear()
            _cache_time.clear()


def get_cache_stats() -> dict:
    """返回缓存统计。Redis 优先，不可用时返回内存统计。"""
    if is_redis_available():
        client = get_redis_client()
        if client:
            try:
                info = client.info("memory")
                return {
                    "backend": "redis",
                    "used_memory_human": info.get("used_memory_human", "unknown"),
                    "connected_clients": client.info("clients").get("connected_clients", 0),
                }
            except Exception as exc:
                logger.warning("Redis stats failed: %s", exc)
                mark_redis_unavailable()

    with _lock:
        return {
            "backend": "memory",
            "size": len(_cache),
            "max_size": _MAX_SIZE,
            "ttl_seconds": DEFAULT_TTL_SECONDS,
        }
