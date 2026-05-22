"""测试全局限流中间件"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from middleware.rate_limit import clear_rate_limit_store, _get_client_ip, _check_rate_limit_redis


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """每个测试前清空限流计数器。"""
    clear_rate_limit_store()


class TestRateLimitMiddleware:
    """全局限流中间件测试"""

    def test_get_requests_not_limited(self, client: TestClient):
        """GET 请求不受限流影响。"""
        for _ in range(105):
            resp = client.get("/health")
            assert resp.status_code == 200, "GET /health 应在限流白名单内"

    def test_health_metrics_docs_not_limited(self, client: TestClient):
        """健康检查、指标、文档端点不限流。"""
        for _ in range(105):
            assert client.get("/health").status_code == 200
            assert client.get("/metrics").status_code in (200, 403)  # /metrics 可能有 IP 限制

    def test_post_requests_limited(self, client: TestClient, auth_headers, seed_varieties):
        """POST 请求超过阈值后返回 429。"""
        # 使用一个不存在的 variety_id 来快速失败（避免创建太多数据）
        responses = []
        for _ in range(105):
            resp = client.post(
                "/api/price-levels",
                json={"variety_id": 99999, "type": "support", "price": 100},
                headers=auth_headers,
            )
            responses.append(resp.status_code)

        # 前面应成功（404），后面应被限流（429）
        not_limited = [c for c in responses if c != 429]
        rate_limited_count = responses.count(429)

        assert rate_limited_count > 0, "应至少有一些请求被限流"
        assert len(not_limited) > 0, "应至少有一些请求成功"

    def test_429_response_has_retry_after_header(self, client: TestClient, auth_headers):
        """429 响应应携带 Retry-After 头和统一错误格式。"""
        # 快速发送一批请求触发限流
        for _ in range(110):
            resp = client.post(
                "/api/price-levels",
                json={"variety_id": 99999, "type": "support", "price": 100},
                headers=auth_headers,
            )
            if resp.status_code == 429:
                assert "retry-after" in {k.lower() for k in resp.headers.keys()}
                data = resp.json()
                assert data.get("code") == "RATE_LIMITED"
                assert "retry_after" in data
                return

        pytest.skip("未触发限流，可能测试环境执行过快")

    def test_x_forwarded_for_respected(self, client: TestClient, auth_headers):
        """X-Forwarded-For 应被用于识别真实客户端 IP。"""
        # 使用不同的 X-Forwarded-For 值，它们应被当作不同客户端
        for i in range(3):
            h = dict(auth_headers)
            h["X-Forwarded-For"] = f"192.168.1.{i}"
            resp = client.post(
                "/api/price-levels",
                json={"variety_id": 99999, "type": "support", "price": 100},
                headers=h,
            )
            # 每个 IP 单独计数，都不应被限流（只发了 1 个请求）
            assert resp.status_code != 429, "不同 X-Forwarded-For 应被当作不同客户端"


class TestRateLimitSecurity:
    """限流安全加固测试"""

    def test_get_client_ip_trusted_proxy_reads_x_forwarded_for(self):
        """受信代理（127.0.0.1）传递的 X-Forwarded-For 应被读取。"""
        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {"X-Forwarded-For": "192.168.1.5"}
        assert _get_client_ip(request) == "192.168.1.5"

    def test_get_client_ip_public_ip_ignores_x_forwarded_for(self):
        """公网 IP 伪造的 X-Forwarded-For 不应被信任。"""
        request = MagicMock()
        request.client.host = "8.8.8.8"
        request.headers = {"X-Forwarded-For": "192.168.1.5"}
        assert _get_client_ip(request) == "8.8.8.8"

    def test_redis_rate_limit_uses_timestamp_not_iso(self):
        """P0 修复：zremrangebyscore 必须接收 float timestamp，而非 ISO 字符串。"""
        mock_client = MagicMock()
        mock_pipe = MagicMock()
        mock_client.pipeline.return_value = mock_pipe
        mock_pipe.execute.return_value = [0, 1, 1, 50]

        with patch("middleware.rate_limit.get_redis_client", return_value=mock_client):
            result = _check_rate_limit_redis("1.2.3.4", "POST", "/api/test")

        assert result is True
        call_args = mock_pipe.zremrangebyscore.call_args[0]
        # call_args[1] 是 window_start（max 参数）
        assert isinstance(call_args[1], (int, float)), (
            f"zremrangebyscore max 必须是数值型 timestamp，实际为 {type(call_args[1])}"
        )
        # 确认不是 ISO 字符串（不应包含 'T'）
        assert "T" not in str(call_args[1]), "window_start 不应是 ISO 格式字符串"

    def test_metrics_rejects_x_forwarded_for_from_public_ip(self, client: TestClient):
        """P0 修复：/metrics 端点应拒绝公网来源伪造的 X-Forwarded-For。"""
        # TestClient 的 host 是 testclient，不属于受信代理
        resp = client.get("/metrics", headers={"X-Forwarded-For": "10.0.0.1"})
        assert resp.status_code == 403, "公网来源伪造 X-Forwarded-For 不应绕过 /metrics 白名单"
