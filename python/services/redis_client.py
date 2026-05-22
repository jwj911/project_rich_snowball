"""
Redis 客户端管理
================
提供统一的 Redis 连接获取与异常降级逻辑。
当 Redis 不可用时，自动降级到内存实现（缓存/限流），确保应用始终可运行。

环境变量：
    REDIS_URL=redis://:password@localhost:6379/0
    若未设置或连接失败，则 is_redis_available() 返回 False，调用方应 fallback 到内存实现。
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None
_redis_available: bool | None = None
_redis_last_check: float = 0
_redis_check_interval: int = 60  # 秒


def _create_redis_client() -> redis.Redis | None:
    """尝试创建 Redis 客户端。"""
    try:
        import redis
    except ImportError:
        logger.warning("redis package not installed")
        return None

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None

    try:
        client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        logger.info("Redis connected: %s", redis_url.split("@")[-1])
        return client
    except Exception as e:
        logger.warning("Redis connection failed (%s), fallback to in-memory", e)
        return None


def get_redis_client() -> redis.Redis | None:
    """获取 Redis 客户端（单例，延迟初始化）。"""
    global _redis_client, _redis_available
    if _redis_available is None:
        _redis_client = _create_redis_client()
        _redis_available = _redis_client is not None
    return _redis_client


def is_redis_available() -> bool:
    """检查 Redis 是否可用。断开后会按 _redis_check_interval 间隔自动重试。"""
    global _redis_available, _redis_client, _redis_last_check
    if _redis_available is None:
        get_redis_client()
        return bool(_redis_available)
    if not _redis_available:
        now = time.time()
        if now - _redis_last_check > _redis_check_interval:
            _redis_last_check = now
            _redis_client = _create_redis_client()
            _redis_available = _redis_client is not None
            if _redis_available:
                logger.info("Redis reconnected successfully")
    return bool(_redis_available)


def mark_redis_unavailable() -> None:
    """标记 Redis 为不可用，触发降级到内存实现。

    当运行中检测到 Redis 操作失败时调用，避免后续请求持续尝试已断开的连接。
    is_redis_available() 会按 _redis_check_interval 间隔自动重试恢复。
    """
    global _redis_available, _redis_client, _redis_last_check
    if _redis_available:
        logger.warning("Redis marked unavailable due to runtime error")
    _redis_available = False
    _redis_client = None
    _redis_last_check = time.time()


def close_redis_client() -> None:
    """关闭 Redis 连接（应用退出时调用）。"""
    global _redis_client, _redis_available
    if _redis_client:
        with contextlib.suppress(Exception):
            _redis_client.close()
        _redis_client = None
    _redis_available = None
