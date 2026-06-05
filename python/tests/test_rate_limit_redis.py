"""Phase 4: 登录限流 Redis 化 + 高成本 GET/SSE 限流测试。

覆盖点：
1. auth.py register/login 调用 check_rate_limit（带 action=auth:register/auth:login）
2. 内存路径和 Redis 路径均正确工作
3. 429 响应包含正确 Retry-After header
4. clear_rate_limit_store 能清空计数器
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

import middleware.rate_limit
from middleware.rate_limit import (
    _check_rate_limit_memory,
    _check_rate_limit_redis,
    check_rate_limit,
    clear_rate_limit_store,
)


class TestAuthRateLimitRedis:
    """Auth 限流使用 Redis（或内存降级）的集成测试。"""

    def test_register_rate_limit_memory_path(self, client: TestClient):
        """register 在内存路径下应正确限流（60s/10req）。"""
        clear_rate_limit_store()
        # 触发 10 次成功注册（使用不同用户名）
        for i in range(10):
            resp = client.post(
                "/api/auth/register",
                json={
                    "username": f"ratelimittest{i}",
                    "email": f"rl{i}@example.com",
                    "password": "Password123!",
                },
            )
            assert resp.status_code == 201, f"第 {i+1} 次注册应成功"

        # 第 11 次应被限流
        resp = client.post(
            "/api/auth/register",
            json={
                "username": "ratelimittest_overflow",
                "email": "rl_overflow@example.com",
                "password": "Password123!",
            },
        )
        assert resp.status_code == 429
        assert resp.headers.get("retry-after") == "60"
        data = resp.json()
        assert data.get("code") == "RATE_LIMITED"
        clear_rate_limit_store()

    def test_login_rate_limit_memory_path(self, client: TestClient):
        """login 在内存路径下应正确限流（60s/10req）。"""
        clear_rate_limit_store()
        # 先注册一个用户
        client.post(
            "/api/auth/register",
            json={
                "username": "loginrl",
                "email": "loginrl@example.com",
                "password": "Password123!",
            },
        )
        clear_rate_limit_store()  # 清空注册计数器，只测登录

        # 触发 10 次登录（成功也算入限流）
        for i in range(10):
            resp = client.post(
                "/api/auth/login",
                data={"username": "loginrl", "password": "Password123!"},
            )
            assert resp.status_code == 200, f"第 {i+1} 次登录应成功"

        # 第 11 次应被限流
        resp = client.post(
            "/api/auth/login",
            data={"username": "loginrl", "password": "Password123!"},
        )
        assert resp.status_code == 429
        assert resp.headers.get("retry-after") == "60"
        clear_rate_limit_store()

    def test_login_rate_limit_independent_of_register(self, client: TestClient):
        """login 和 register 的限流计数器应独立。"""
        clear_rate_limit_store()
        # 注册触满 10 次
        for i in range(10):
            resp = client.post(
                "/api/auth/register",
                json={
                    "username": f"indep{i}",
                    "email": f"indep{i}@example.com",
                    "password": "Password123!",
                },
            )
            assert resp.status_code == 201

        # register 已满，但 login 应不受影响（只要没登录过）
        # 先注册一个专门测试登录的用户
        resp = client.post(
            "/api/auth/register",
            json={
                "username": "indep_login",
                "email": "indep_login@example.com",
                "password": "Password123!",
            },
        )
        # 这次注册应被限流（因为 register 已经满了）
        assert resp.status_code == 429

        # 但 login 应该还能进行（不同 action key）
        # 由于 register 429 没有创建用户，用之前已注册的用户测试不了
        # 换一个思路：先清空，注册一个用户，再单独把 register 打满，验证 login 不受影响
        clear_rate_limit_store()
        client.post(
            "/api/auth/register",
            json={
                "username": "indep_login2",
                "email": "indep_login2@example.com",
                "password": "Password123!",
            },
        )
        # 单独把 register 打满（模拟不同 IP 或清空后再来）
        clear_rate_limit_store()
        for i in range(10):
            client.post(
                "/api/auth/register",
                json={
                    "username": f"fillreg{i}",
                    "email": f"fillreg{i}@example.com",
                    "password": "Password123!",
                },
            )
        # register 已满
        resp = client.post(
            "/api/auth/register",
            json={
                "username": "fillreg_overflow",
                "email": "fillreg_overflow@example.com",
                "password": "Password123!",
            },
        )
        assert resp.status_code == 429

        # login 应仍能进行（1 次）
        resp = client.post(
            "/api/auth/login",
            data={"username": "indep_login2", "password": "Password123!"},
        )
        assert resp.status_code == 200
        clear_rate_limit_store()

    def test_check_rate_limit_redis_with_custom_params(self):
        """check_rate_limit Redis 路径应正确传递 window_seconds/max_requests。"""
        mock_client = MagicMock()
        mock_pipe = MagicMock()
        mock_client.pipeline.return_value = mock_pipe
        mock_pipe.execute.return_value = [0, 1, 1, 4]

        with patch("middleware.rate_limit.is_redis_available", return_value=True), \
             patch("middleware.rate_limit.get_redis_client", return_value=mock_client):
            result = check_rate_limit("1.2.3.4", "test_action", window_seconds=30, max_requests=5)

        assert result is True
        # 验证 key 包含 action
        key_arg = mock_pipe.zremrangebyscore.call_args[0][0]
        assert "test_action" in key_arg

    def test_check_rate_limit_memory_cleanup(self):
        """内存限流清理函数应能正确删除过期 key。"""
        clear_rate_limit_store()
        from datetime import timedelta
        from middleware.rate_limit import _cleanup_stale_rate_limit_keys, _rate_limit_store, _rate_limit_lock
        # 插入一个已过期的 key
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=9999)
        with _rate_limit_lock:
            _rate_limit_store["expired_key:test"] = [old_ts]
            _rate_limit_store["fresh_key:test"] = [datetime.now(timezone.utc)]
        _cleanup_stale_rate_limit_keys()
        with _rate_limit_lock:
            assert "expired_key:test" not in _rate_limit_store
            assert "fresh_key:test" in _rate_limit_store
        clear_rate_limit_store()


class TestGetSSECostlyRateLimit:
    """高成本 GET/SSE 限流测试（预留，待 middleware 实现后启用）。"""

    @pytest.mark.skip(reason="高成本 GET 限流策略待 middleware 实现")
    def test_batch_get_rate_limit(self, client: TestClient):
        """GET /api/realtime/batch 应在高频请求时被限流。"""
        pass

    @pytest.mark.skip(reason="SSE 限流策略待 middleware 实现")
    def test_sse_stream_rate_limit(self, client: TestClient):
        """SSE 连接应在过量连接时被限流。"""
        pass
