"""
可观测性指标测试
================
验证 Prometheus 指标定义、中间件记录、业务路由埋点。
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-metrics-local-development")
os.environ["ENABLE_SCHEDULER"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from services.metrics import (
    auth_operations_total,
    cache_operations_total,
    comment_operations_total,
    data_collection_runs_total,
    external_api_duration_seconds,
    http_exceptions_total,
    http_requests_total,
    price_level_operations_total,
    watchlist_operations_total,
)


@pytest.fixture(autouse=True)
def _reset_metrics():
    """每个测试前重置所有 Counter 状态，避免跨测试累积干扰断言。"""
    for metric in [
        auth_operations_total,
        comment_operations_total,
        price_level_operations_total,
        watchlist_operations_total,
        data_collection_runs_total,
        http_exceptions_total,
        http_requests_total,
        cache_operations_total,
    ]:
        # 将 Counter 的所有 label 组合清零
        for samples in metric.collect():
            for sample in samples.samples:
                if sample.name.endswith("_total"):
                    metric.labels(**sample.labels)._value.set(0.0)
    yield


class TestMetricsEndpoint:
    def test_metrics_returns_prometheus_text(self, client, monkeypatch):
        """/metrics 端点应返回 Prometheus 格式的指标文本。"""
        monkeypatch.setattr("main._is_trusted_proxy", lambda h: True)
        r = client.get("/metrics")
        assert r.status_code == 200
        body = r.text
        assert "http_requests_total" in body
        assert "http_request_duration_seconds" in body
        assert "auth_operations_total" in body
        assert "comment_operations_total" in body
        assert "price_level_operations_total" in body
        assert "watchlist_operations_total" in body
        assert "external_api_duration_seconds" in body
        assert "http_exceptions_total" in body

    def test_metrics_forbidden_from_untrusted_ip(self, client):
        """非信任 IP 访问 /metrics 应返回 403。"""
        # TestClient 默认 client.host 为 "testclient"
        r = client.get("/metrics")
        assert r.status_code == 403


class TestAuthMetrics:
    def test_login_success_increments_auth_metric(self, client):
        """登录成功后 auth_operations_total{operation=login,result=success} 应增加。"""
        client.post("/api/auth/register", json={
            "username": "metrics_tester",
            "email": "metrics@test.com",
            "password": "password123"
        })
        before = _get_counter_value(auth_operations_total, operation="login", result="success")
        client.post("/api/auth/login", data={"username": "metrics_tester", "password": "password123"})
        after = _get_counter_value(auth_operations_total, operation="login", result="success")
        assert after == before + 1

    def test_login_failure_increments_auth_metric(self, client):
        """登录失败后 auth_operations_total{operation=login,result=failure} 应增加。"""
        before = _get_counter_value(auth_operations_total, operation="login", result="failure")
        client.post("/api/auth/login", data={"username": "nonexistent", "password": "wrong"})
        after = _get_counter_value(auth_operations_total, operation="login", result="failure")
        assert after == before + 1

    def test_register_failure_increments_auth_metric(self, client):
        """注册冲突后 auth_operations_total{operation=register,result=failure} 应增加。"""
        client.post("/api/auth/register", json={
            "username": "metrics_dup",
            "email": "dup@test.com",
            "password": "password123"
        })
        before = _get_counter_value(auth_operations_total, operation="register", result="failure")
        client.post("/api/auth/register", json={
            "username": "metrics_dup",
            "email": "dup2@test.com",
            "password": "password123"
        })
        after = _get_counter_value(auth_operations_total, operation="register", result="failure")
        assert after == before + 1


class TestHttpRequestMetrics:
    def test_request_increments_http_requests_total(self, client, auth_headers):
        """任意请求后 http_requests_total 应增加。"""
        before = _get_counter_value(http_requests_total, method="GET", endpoint="/api/products", status_code="200")
        client.get("/api/products", headers=auth_headers)
        after = _get_counter_value(http_requests_total, method="GET", endpoint="/api/products", status_code="200")
        assert after == before + 1

    def test_404_increments_http_requests_total(self, client):
        """404 请求也应记录到 http_requests_total。"""
        before = _get_counter_value(http_requests_total, method="GET", endpoint="/api/nonexistent", status_code="404")
        client.get("/api/nonexistent")
        after = _get_counter_value(http_requests_total, method="GET", endpoint="/api/nonexistent", status_code="404")
        assert after == before + 1


class TestBusinessMetrics:
    def test_comment_create_increments_metric(self, client, auth_headers, seed_varieties):
        """创建评论后 comment_operations_total{action=create,result=success} 应增加。"""
        product_id = seed_varieties[0].id
        before = _get_counter_value(comment_operations_total, action="create", result="success")
        client.post("/api/comments", json={
            "product_id": product_id,
            "content": "metrics test comment"
        }, headers=auth_headers)
        after = _get_counter_value(comment_operations_total, action="create", result="success")
        assert after == before + 1

    def test_price_level_create_increments_metric(self, client, auth_headers, seed_varieties):
        """创建价位标注后 price_level_operations_total{action=create,result=success} 应增加。"""
        variety_id = seed_varieties[0].id
        before = _get_counter_value(price_level_operations_total, action="create", result="success")
        client.post("/api/price-levels", json={
            "variety_id": variety_id,
            "type": "support",
            "price": 100.0,
            "note": "metrics test"
        }, headers=auth_headers)
        after = _get_counter_value(price_level_operations_total, action="create", result="success")
        assert after == before + 1

    def test_watchlist_create_increments_metric(self, client, auth_headers, seed_varieties):
        """创建自选后 watchlist_operations_total{action=create,result=success} 应增加。"""
        variety_id = seed_varieties[0].id
        before = _get_counter_value(watchlist_operations_total, action="create", result="success")
        client.post("/api/watchlists", json={
            "variety_id": variety_id,
            "notes": "metrics test"
        }, headers=auth_headers)
        after = _get_counter_value(watchlist_operations_total, action="create", result="success")
        assert after == before + 1


def _get_counter_value(counter, **labels):
    """从 Prometheus Counter 中读取指定 label 组合的当前值。"""
    try:
        return counter.labels(**labels)._value.get()
    except Exception:
        return 0.0
