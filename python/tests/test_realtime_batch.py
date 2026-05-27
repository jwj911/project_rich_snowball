"""
批量实时行情 API 测试
========================
验证 /api/realtime/batch 端点行为。
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-realtime-batch-local-development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from models import RealtimeQuoteDB


@pytest.fixture
def batch_auth_headers(client):
    """注册并登录测试用户，返回包含 Bearer token 的请求头。"""
    client.post("/api/auth/register", json={
        "username": "batch_tester",
        "email": "batch@test.com",
        "password": "password123"
    })
    r = client.post("/api/auth/login", data={
        "username": "batch_tester",
        "password": "password123"
    })
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seed_realtime_quotes(db_session, seed_varieties):
    """为前 3 个品种写入实时行情数据（如 lifespan 已初始化则先清理）。"""
    from models import RealtimeQuoteDB
    variety_ids = [v.id for v in seed_varieties[:3]]
    db_session.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id.in_(variety_ids)).delete(synchronize_session=False)

    quotes = [
        RealtimeQuoteDB(
            variety_id=seed_varieties[0].id,
            current_price=450.5,
            change_percent=1.2,
            open_price=445.0,
            high=452.0,
            low=444.0,
            volume=15000,
        ),
        RealtimeQuoteDB(
            variety_id=seed_varieties[1].id,
            current_price=6800.0,
            change_percent=-0.5,
            open_price=6850.0,
            high=6860.0,
            low=6780.0,
            volume=8000,
        ),
        RealtimeQuoteDB(
            variety_id=seed_varieties[2].id,
            current_price=72000.0,
            change_percent=0.8,
            open_price=71500.0,
            high=72500.0,
            low=71400.0,
            volume=5000,
        ),
    ]
    for q in quotes:
        db_session.add(q)
    db_session.commit()
    return quotes


class TestRealtimeBatch:
    def test_batch_returns_multiple_quotes(self, client, batch_auth_headers, seed_varieties, seed_realtime_quotes):
        """批量查询多个存在行情的品种应返回全部数据。"""
        r = client.get("/api/realtime/batch?symbols=AU&symbols=AG&symbols=CU", headers=batch_auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "quotes" in data
        assert "not_found" in data
        assert len(data["quotes"]) == 3
        symbols = {q["symbol"] for q in data["quotes"]}
        assert symbols == {"AU", "AG", "CU"}
        assert data["not_found"] == []

    def test_batch_partial_not_found(self, client, batch_auth_headers, seed_varieties, seed_realtime_quotes):
        """部分品种无行情时应返回已找到数据 + not_found 列表。"""
        r = client.get("/api/realtime/batch?symbols=AU&symbols=UNKNOWN", headers=batch_auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data["quotes"]) == 1
        assert data["quotes"][0]["symbol"] == "AU"
        assert data["not_found"] == ["UNKNOWN"]

    def test_batch_all_not_found(self, client, batch_auth_headers, seed_varieties, seed_realtime_quotes):
        """全部品种都不存在时应返回空 quotes + 全部 not_found。"""
        r = client.get("/api/realtime/batch?symbols=FAKE1&symbols=FAKE2", headers=batch_auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["quotes"] == []
        assert data["not_found"] == ["FAKE1", "FAKE2"]

    def test_batch_empty_symbols(self, client, batch_auth_headers):
        """空 symbols 列表应返回空结果。"""
        r = client.get("/api/realtime/batch", headers=batch_auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["quotes"] == []
        assert data["not_found"] == []

    def test_batch_single_symbol_equivalent(self, client, batch_auth_headers, seed_varieties, seed_realtime_quotes):
        """批量查询单个品种应与单品种接口返回一致。"""
        batch_r = client.get("/api/realtime/batch?symbols=AU", headers=batch_auth_headers)
        single_r = client.get("/api/realtime/AU", headers=batch_auth_headers)
        assert batch_r.status_code == 200
        assert single_r.status_code == 200

        batch_data = batch_r.json()
        single_data = single_r.json()

        assert len(batch_data["quotes"]) == 1
        assert batch_data["quotes"][0]["symbol"] == single_data["symbol"]
        assert batch_data["quotes"][0]["current_price"] == single_data["current_price"]
        assert batch_data["quotes"][0]["change_percent"] == single_data["change_percent"]
