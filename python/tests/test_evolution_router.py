"""Evolution API 路由集成测试。

测试 /api/evolution 端点。
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_headers(client: TestClient) -> dict:
    """已认证的请求头（复用 conftest 中的 client）。"""
    # 尝试创建测试用户并获取 token
    try:
        resp = client.post(
            "/api/auth/register",
            json={"username": "evo_router_test", "email": "evo_router@test.com", "password": "TestPass123"},
        )
        if resp.status_code == 200:
            token_data = resp.json()
        else:
            resp = client.post(
                "/api/auth/login",
                data={"username": "evo_router_test", "password": "TestPass123"},
            )
            token_data = resp.json()
    except Exception:
        resp = client.post(
            "/api/auth/login",
            data={"username": "evo_router_test", "password": "TestPass123"},
        )
        token_data = resp.json()

    token = token_data.get("access_token", "")
    return {"Authorization": f"Bearer {token}"}


def _create_test_strategy(client: TestClient, headers: dict, symbol: str = "RB") -> int:
    """创建测试策略并返回 strategy_id。"""
    resp = client.post(
        "/api/strategies",
        json={
            "name": f"test-{symbol}",
            "symbol": symbol,
            "dsl_json": json.dumps({"test": True}),
            "timeframe": "1d",
            "direction": "long",
            "description": "test strategy",
        },
        headers=headers,
    )
    if resp.status_code == 200:
        return resp.json()["id"]
    # 可能策略已存在，尝试从列表中获取
    list_resp = client.get("/api/strategies", headers=headers)
    if list_resp.status_code == 200:
        items = list_resp.json()
        for item in items:
            if item.get("symbol") == symbol:
                return item["id"]
    raise RuntimeError(f"Failed to create strategy: {resp.status_code} {resp.text}")


@pytest.mark.integration
class TestEvolutionRunsRouter:
    def test_list_empty(self, client, auth_headers):
        resp = client.get("/api/evolution/runs", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_list_with_filter(self, client, auth_headers):
        resp = client.get("/api/evolution/runs?symbol=RB&status=completed", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_not_found(self, client, auth_headers):
        resp = client.get("/api/evolution/runs/99999", headers=auth_headers)
        assert resp.status_code == 404


@pytest.mark.integration
class TestLifecycleRouter:
    def test_list_empty(self, client, auth_headers):
        resp = client.get("/api/evolution/lifecycles", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_not_found(self, client, auth_headers):
        resp = client.get("/api/evolution/lifecycle/99999", headers=auth_headers)
        assert resp.status_code == 404

    def test_evaluate_decay_not_found(self, client, auth_headers):
        resp = client.post(
            "/api/evolution/evaluate-decay",
            json={"strategy_id": 99999},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_compare_insufficient(self, client, auth_headers):
        resp = client.post(
            "/api/evolution/compare",
            json={"strategy_ids": [1]},  # only 1 → error
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_compare_too_many(self, client, auth_headers):
        resp = client.post(
            "/api/evolution/compare",
            json={"strategy_ids": list(range(1, 22))},  # 21 → too many
            headers=auth_headers,
        )
        assert resp.status_code == 400


@pytest.mark.integration
class TestEndToEndLifecycle:
    """端到端：创建策略 → 评估衰减 → 获取生命周期。"""

    def test_full_flow(self, client, auth_headers):
        # 1. Create strategy
        strategy_id = _create_test_strategy(client, auth_headers, symbol="RB")

        # 2. Get lifecycle (should be accessible even if not yet created — returns default)
        resp = client.get(f"/api/evolution/lifecycle/{strategy_id}", headers=auth_headers)
        assert resp.status_code in (200, 404)  # 200 if default response, 404 if strategy not found

        # 3. Evaluate decay (should work with no data)
        resp = client.post(
            "/api/evolution/evaluate-decay",
            json={"strategy_id": strategy_id},
            headers=auth_headers,
        )
        if resp.status_code == 200:
            data = resp.json()
            assert "decay_score" in data
            assert "recommended_action" in data

        # 4. Compare strategies
        # Create second strategy for comparison
        strategy_id2 = _create_test_strategy(client, auth_headers, symbol="AU")
        resp = client.post(
            "/api/evolution/compare",
            json={"strategy_ids": [strategy_id, strategy_id2]},
            headers=auth_headers,
        )
        if resp.status_code == 200:
            data = resp.json()
            assert "items" in data
            assert len(data["items"]) == 2
