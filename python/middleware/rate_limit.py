"""
全局限流中间件
==============
基于 Redis 滑动窗口（优先）或内存滑动窗口（降级）的全局限流，覆盖所有写入端点。
支持 X-Forwarded-For / X-Real-IP 获取真实客户端 IP。

- GET/HEAD/OPTIONS 默认不限流（可通过 check_rate_limit 单独限制）
- 健康检查、指标、文档端点不限流
- 429 响应携带 Retry-After 头

注意：内存降级模式下多实例部署不共享限流状态。
"""

import ipaddress
from datetime import UTC, datetime, timedelta
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse

from errors import ErrorCode

from config import RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS
from services.redis_client import get_redis_client, is_redis_available

# 配置
_WINDOW_SECONDS = RATE_LIMIT_WINDOW_SECONDS
_MAX_REQUESTS_PER_WINDOW = RATE_LIMIT_MAX_REQUESTS
_RETRY_AFTER_SECONDS = RATE_LIMIT_WINDOW_SECONDS

# 不限流的路径前缀
_EXCLUDED_PATHS = {
    "/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
}

# 中间件层面不限流的方法
_EXCLUDED_METHODS = {"GET", "HEAD", "OPTIONS"}

# ---- 内存降级实现 ----
_rate_limit_store: dict[str, list[datetime]] = {}
_rate_limit_lock = Lock()


def _is_trusted_proxy(host: str) -> bool:
    """判断 host 是否为受信代理（内网段 / localhost / IPv6 loopback）。

    支持 IPv4-mapped IPv6（如 ::ffff:127.0.0.1）和 IPv6 zone index。
    """
    if not host:
        return False
    # IPv4 显式信任列表
    if host in ("127.0.0.1", "localhost"):
        return True
    if host.startswith("10.") or host.startswith("192.168."):
        return True
    if any(host.startswith(f"172.{i}.") for i in range(16, 32)):
        return True
    # IPv6 判断（含 IPv4-mapped IPv6，如 ::ffff:127.0.0.1）
    try:
        ip = ipaddress.ip_address(host.split("%")[0])  # 去掉 zone index
        return ip.is_loopback or ip.is_private
    except ValueError:
        return False


def _get_client_ip(request: Request) -> str:
    """获取真实客户端 IP。

    仅在请求直接来自受信代理时才读取 X-Forwarded-For / X-Real-IP，
    防止客户端伪造转发头绕过限流。
    """
    client_host = request.client.host if request.client else ""

    if _is_trusted_proxy(client_host):
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
    return client_host or "unknown"


def _is_excluded(request: Request) -> bool:
    """判断当前请求是否在中间件白名单中。"""
    if request.method in _EXCLUDED_METHODS:
        return True
    path = request.url.path
    return any(path.startswith(excluded) for excluded in _EXCLUDED_PATHS)


def _cleanup_stale_rate_limit_keys():
    """清理内存限流存储中已完全过期的 key，防止字典无限增长。"""
    now = datetime.now(UTC)
    window_start = now - timedelta(seconds=_WINDOW_SECONDS)
    with _rate_limit_lock:
        stale_keys = [
            key for key, entries in _rate_limit_store.items()
            if not entries or all(ts <= window_start for ts in entries)
        ]
        for key in stale_keys:
            _rate_limit_store.pop(key, None)


def _check_rate_limit_redis(
    client_ip: str,
    action: str,
    window_seconds: int,
    max_requests: int,
) -> bool:
    """Redis 滑动窗口限流。"""
    client = get_redis_client()
    if client is None:
        return _check_rate_limit_memory(client_ip, action, window_seconds, max_requests)

    key = f"futures:ratelimit:{client_ip}:{action}"
    now = datetime.now(UTC)
    window_start = (now - timedelta(seconds=window_seconds)).timestamp()

    try:
        pipe = client.pipeline()
        # 清理过期记录
        pipe.zremrangebyscore(key, 0, window_start)
        # 添加当前请求
        pipe.zadd(key, {now.isoformat(): now.timestamp()})
        # 设置 key 过期时间
        pipe.expire(key, window_seconds)
        # 获取当前窗口内计数
        pipe.zcard(key)
        _, _, _, count = pipe.execute()
        # count 已包含当前请求，因此用 < 而非 <=
        return count < max_requests
    except (OSError, ConnectionError, TimeoutError):
        return _check_rate_limit_memory(client_ip, action, window_seconds, max_requests)


def _check_rate_limit_memory(
    client_ip: str,
    action: str,
    window_seconds: int,
    max_requests: int,
) -> bool:
    """内存滑动窗口限流（Redis 不可用时降级）。"""
    now = datetime.now(UTC)
    window_start = now - timedelta(seconds=window_seconds)
    key = f"{client_ip}:{action}"

    with _rate_limit_lock:
        entries = _rate_limit_store.get(key, [])
        entries = [ts for ts in entries if ts > window_start]
        if len(entries) >= max_requests:
            if entries:
                _rate_limit_store[key] = entries
            else:
                _rate_limit_store.pop(key, None)
            return False
        entries.append(now)
        if entries:
            _rate_limit_store[key] = entries
        else:
            _rate_limit_store.pop(key, None)
        # 定期清理全局过期 key（每 1000 个不同 key 触发一次）
        if len(_rate_limit_store) > 1000:
            _cleanup_stale_rate_limit_keys()
        return True


def check_rate_limit(
    client_ip: str,
    action: str,
    window_seconds: int = _WINDOW_SECONDS,
    max_requests: int = _MAX_REQUESTS_PER_WINDOW,
) -> bool:
    """通用限流检查，支持自定义窗口和阈值。

    优先使用 Redis，不可用时降级到内存。

    Args:
        client_ip: 客户端 IP
        action: 限流动作标识（如 "auth:login", "api:batch"）
        window_seconds: 滑动窗口大小（秒）
        max_requests: 窗口内最大请求数

    Returns:
        True 表示允许通过，False 表示已限流
    """
    if is_redis_available():
        return _check_rate_limit_redis(client_ip, action, window_seconds, max_requests)
    return _check_rate_limit_memory(client_ip, action, window_seconds, max_requests)


def clear_rate_limit_store():
    """清空限流计数器，供测试使用。"""
    with _rate_limit_lock:
        _rate_limit_store.clear()
    if is_redis_available():
        client = get_redis_client()
        if client:
            try:
                for k in client.scan_iter(match="futures:ratelimit:*"):
                    client.delete(k)
            except (OSError, ConnectionError):
                pass


# 高成本 GET/HEAD 端点独立限流配置（path -> (window_seconds, max_requests, action_name)）
_GET_COSTLY_ENDPOINTS: dict[str, tuple[int, int, str]] = {
    "/api/realtime/batch": (60, 100, "get:realtime:batch"),
    "/api/realtime/stream": (60, 30, "get:realtime:stream"),
}


async def rate_limit_middleware(request: Request, call_next):
    """FastAPI HTTP 中间件：全局写入端点限流 + 高成本 GET 端点限流。"""
    path = request.url.path
    method = request.method

    # 白名单排除（含常规 GET/HEAD/OPTIONS）
    if _is_excluded(request):
        # 但高成本 GET 端点仍需限流
        if method not in _EXCLUDED_METHODS or path not in _GET_COSTLY_ENDPOINTS:
            return await call_next(request)

    client_ip = _get_client_ip(request)

    # 高成本 GET 端点使用独立限流参数
    if method in ("GET", "HEAD") and path in _GET_COSTLY_ENDPOINTS:
        window_seconds, max_requests, action = _GET_COSTLY_ENDPOINTS[path]
    else:
        window_seconds = _WINDOW_SECONDS
        max_requests = _MAX_REQUESTS_PER_WINDOW
        action = f"{method}:{path}"

    allowed = check_rate_limit(
        client_ip,
        action,
        window_seconds=window_seconds,
        max_requests=max_requests,
    )

    if not allowed:
        retry_after = window_seconds
        return JSONResponse(
            status_code=429,
            content={
                "code": ErrorCode.RATE_LIMITED.value,
                "message": f"请求过于频繁，请 {retry_after} 秒后再试",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    return await call_next(request)
