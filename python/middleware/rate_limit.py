"""
全局限流中间件
==============
基于 Redis 滑动窗口（优先）或内存滑动窗口（降级）的全局限流，覆盖所有写入端点。
支持 X-Forwarded-For / X-Real-IP 获取真实客户端 IP。

- GET/HEAD/OPTIONS 不限流
- 健康检查、指标、文档端点不限流
- 429 响应携带 Retry-After 头

注意：内存降级模式下多实例部署不共享限流状态。
"""

import ipaddress
from datetime import UTC, datetime, timedelta
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse

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

# 不限流的方法
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
    """判断当前请求是否在白名单中。"""
    if request.method in _EXCLUDED_METHODS:
        return True
    path = request.url.path
    return any(path.startswith(excluded) for excluded in _EXCLUDED_PATHS)


# ---- Redis 实现 ----
def _check_rate_limit_redis(client_ip: str, method: str, path: str) -> bool:
    """Redis 滑动窗口限流。"""
    client = get_redis_client()
    if client is None:
        return _check_rate_limit_memory(client_ip, method, path)

    key = f"futures:ratelimit:{client_ip}:{method}:{path}"
    now = datetime.now(UTC)
    window_start = (now - timedelta(seconds=_WINDOW_SECONDS)).timestamp()

    try:
        pipe = client.pipeline()
        # 清理过期记录
        pipe.zremrangebyscore(key, 0, window_start)
        # 添加当前请求
        pipe.zadd(key, {now.isoformat(): now.timestamp()})
        # 设置 key 过期时间
        pipe.expire(key, _WINDOW_SECONDS)
        # 获取当前窗口内计数
        pipe.zcard(key)
        _, _, _, count = pipe.execute()
        # count 已包含当前请求，因此用 < 而非 <=
        return count < _MAX_REQUESTS_PER_WINDOW
    except (OSError, ConnectionError, TimeoutError):
        return _check_rate_limit_memory(client_ip, method, path)


# ---- 内存降级实现 ----
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


def _check_rate_limit_memory(client_ip: str, method: str, path: str) -> bool:
    """内存滑动窗口限流（Redis 不可用时降级）。"""
    now = datetime.now(UTC)
    window_start = now - timedelta(seconds=_WINDOW_SECONDS)
    key = f"{client_ip}:{method}:{path}"

    with _rate_limit_lock:
        entries = _rate_limit_store.get(key, [])
        entries = [ts for ts in entries if ts > window_start]
        if len(entries) >= _MAX_REQUESTS_PER_WINDOW:
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


async def rate_limit_middleware(request: Request, call_next):
    """FastAPI HTTP 中间件：全局写入端点限流。"""
    if _is_excluded(request):
        return await call_next(request)

    client_ip = _get_client_ip(request)
    method = request.method
    path = request.url.path

    if is_redis_available():
        allowed = _check_rate_limit_redis(client_ip, method, path)
    else:
        allowed = _check_rate_limit_memory(client_ip, method, path)

    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "code": "RATE_LIMITED",
                "message": f"请求过于频繁，请 {_RETRY_AFTER_SECONDS} 秒后再试",
                "retry_after": _RETRY_AFTER_SECONDS,
            },
            headers={"Retry-After": str(_RETRY_AFTER_SECONDS)},
        )

    return await call_next(request)
