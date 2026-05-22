"""
SSE 实时行情推送测试
========================
验证 /api/realtime/stream 端点行为。
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-realtime-sse")
os.environ.setdefault("SSE_TEST_MODE", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from models import RealtimeQuoteDB


@pytest.fixture
def seed_user():
    """创建一个测试用户并返回（使用 SessionLocal 确保 _sse_realtime_generator 可见）。"""
    from models import UserDB, SessionLocal
    from utils import hash_password
    db = SessionLocal()
    try:
        db.query(UserDB).filter(UserDB.username == "sse_tester").delete(synchronize_session=False)
        user = UserDB(username="sse_tester", email="sse@test.com", password_hash=hash_password("password123"))
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


@pytest.fixture
def seed_realtime_quotes(db_session, seed_varieties):
    """为前 2 个品种写入实时行情数据（如 lifespan 已初始化则先清理）。"""
    from models import RealtimeQuoteDB
    variety_ids = [v.id for v in seed_varieties[:2]]
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
    ]
    for q in quotes:
        db_session.add(q)
    db_session.commit()
    return quotes


class TestRealtimeSse:
    def _login_and_create_stream_token(self, client):
        r = client.post("/api/auth/login", data={"username": "sse_tester", "password": "password123"})
        assert r.status_code == 200
        access_token = r.json()["access_token"]

        r = client.post("/api/realtime/stream-token", headers={"Authorization": f"Bearer {access_token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["expires_in"] <= 60
        assert len(body["stream_token"]) > 10
        return body["stream_token"]

    def test_stream_returns_sse_content_type(self, client, seed_user, seed_varieties, seed_realtime_quotes):
        """SSE 端点应返回 text/event-stream Content-Type。"""
        token = self._login_and_create_stream_token(client)

        r = client.get(f"/api/realtime/stream?symbols=AU&symbols=AG&token={token}")
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")

    def test_stream_includes_quotes_data(self, client, seed_user, seed_varieties, seed_realtime_quotes):
        """SSE 响应体中应包含行情数据的 data: 行。"""
        token = self._login_and_create_stream_token(client)

        r = client.get(f"/api/realtime/stream?symbols=AU&symbols=AG&token={token}")
        assert r.status_code == 200
        body = r.text
        assert "data:" in body
        assert "AU" in body
        assert "AG" in body

    def test_stream_requires_token(self, client, seed_user, seed_varieties, seed_realtime_quotes):
        """缺少 token 时应返回 401。"""
        r = client.get("/api/realtime/stream?symbols=AU")
        assert r.status_code == 401

    def test_stream_invalid_token(self, client, seed_user, seed_varieties, seed_realtime_quotes):
        """无效 token 时应在端点入口处拒绝，返回 401，避免建立 SSE 连接消耗资源。"""
        r = client.get("/api/realtime/stream?symbols=AU&token=invalid-token")
        assert r.status_code == 401
