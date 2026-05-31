"""
工作区 API 测试：watchlists / price-levels / workspace / comments price_level_id
"""
import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-workspace-local-development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from main import app
from models import SessionLocal, VarietyDB, WatchlistDB, PriceLevelDB, CommentDB


@pytest.fixture(scope="class")
def db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="class")
def client(db):
    from fastapi.testclient import TestClient
    from dependencies import get_db
    from routers.auth import clear_rate_limit_store

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    clear_rate_limit_store()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture(scope="class")
def auth_client(client, db):
    # 清理可能存在的旧用户及其关联数据（兼容外键开启/关闭两种情况）
    from models import UserDB, WatchlistDB, PriceLevelDB, CommentDB, RefreshTokenDB
    old = db.query(UserDB).filter(UserDB.username == "workspace_user").first()
    if old:
        # 显式清理关联数据，避免外键关闭时留下孤儿数据
        from models import UserPreferenceDB
        db.query(WatchlistDB).filter(WatchlistDB.user_id == old.id).delete(synchronize_session=False)
        db.query(PriceLevelDB).filter(PriceLevelDB.user_id == old.id).delete(synchronize_session=False)
        db.query(CommentDB).filter(CommentDB.user_id == old.id).delete(synchronize_session=False)
        db.query(RefreshTokenDB).filter(RefreshTokenDB.user_id == old.id).delete(synchronize_session=False)
        db.query(UserPreferenceDB).filter(UserPreferenceDB.user_id == old.id).delete(synchronize_session=False)
        db.delete(old)
        db.commit()

    r = client.post("/api/auth/register", json={
        "username": "workspace_user",
        "email": "ws@example.com",
        "password": "password123"
    })
    assert r.status_code == 201, f"注册失败: {r.text}"

    r = client.post("/api/auth/login", data={
        "username": "workspace_user",
        "password": "password123"
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    # 获取当前用户 ID
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    user_id = r.json()["id"]
    client._user_id = user_id
    return client


class TestWatchlists:
    def test_create_watchlist(self, auth_client):
        r = auth_client.post("/api/watchlists", json={"variety_id": 1, "notes": "关注黄金"})
        assert r.status_code == 201
        data = r.json()
        assert data["variety_id"] == 1
        assert data["notes"] == "关注黄金"

    def test_create_watchlist_duplicate(self, auth_client):
        r = auth_client.post("/api/watchlists", json={"variety_id": 1})
        assert r.status_code == 409

    def test_list_watchlists(self, auth_client):
        r = auth_client.get("/api/watchlists")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert data[0]["variety_symbol"] == "AU"

    def test_delete_watchlist(self, auth_client, db):
        uid = auth_client._user_id
        w = db.query(WatchlistDB).filter(WatchlistDB.user_id == uid).first()
        assert w is not None
        r = auth_client.delete(f"/api/watchlists/{w.id}")
        assert r.status_code == 200
        r = auth_client.get("/api/watchlists")
        assert len(r.json()) == 0


class TestPriceLevels:
    def test_create_price_level(self, auth_client):
        r = auth_client.post("/api/price-levels", json={
            "variety_id": 1,
            "type": "support",
            "price": 450.0,
            "note": "强支撑"
        })
        assert r.status_code == 201
        data = r.json()
        assert data["type"] == "support"
        assert float(data["price"]) == 450.0

    def test_create_price_level_duplicate(self, auth_client):
        auth_client.post("/api/price-levels", json={
            "variety_id": 1, "type": "support", "price": 450.0, "note": "已有"
        })
        r = auth_client.post("/api/price-levels", json={
            "variety_id": 1, "type": "support", "price": 450.0
        })
        assert r.status_code == 409

    def test_list_price_levels(self, auth_client):
        auth_client.post("/api/price-levels", json={
            "variety_id": 1, "type": "support", "price": 450.0, "note": "列表测试"
        })
        r = auth_client.get("/api/price-levels")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1

    def test_update_price_level(self, auth_client, db):
        uid = auth_client._user_id
        pl = PriceLevelDB(user_id=uid, variety_id=1, type="support", price=500.0, scope="continuous")
        db.add(pl)
        db.commit()
        db.refresh(pl)
        r = auth_client.put(f"/api/price-levels/{pl.id}", json={"price": 460.0, "note": "更新"})
        assert r.status_code == 200
        assert float(r.json()["price"]) == 460.0

    def test_delete_price_level(self, auth_client, db):
        uid = auth_client._user_id
        pl = PriceLevelDB(user_id=uid, variety_id=1, type="support", price=500.0, scope="continuous")
        db.add(pl)
        db.commit()
        db.refresh(pl)
        r = auth_client.delete(f"/api/price-levels/{pl.id}")
        assert r.status_code == 200


class TestCommentsPriceLevel:
    def test_create_comment_with_price_level(self, auth_client, db):
        uid = auth_client._user_id
        pl = PriceLevelDB(user_id=uid, variety_id=1, type="support", price=400.0)
        db.add(pl)
        db.commit()
        db.refresh(pl)

        r = auth_client.post("/api/comments", json={
            "variety_id": 1,
            "content": "测试评论关联价位",
            "price_level_id": pl.id
        })
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["price_level_id"] == pl.id

    def test_create_comment_with_invalid_price_level(self, auth_client, db):
        r = auth_client.post("/api/comments", json={
            "variety_id": 1,
            "content": "测试",
            "price_level_id": 99999
        })
        assert r.status_code == 404


class TestWorkspace:
    def test_get_workspace(self, auth_client, db):
        uid = auth_client._user_id
        # 先创建一些数据
        w = WatchlistDB(user_id=uid, variety_id=1)
        db.add(w)
        pl = PriceLevelDB(user_id=uid, variety_id=1, type="resistance", price=500.0)
        db.add(pl)
        c = CommentDB(variety_id=1, user_id=uid, content="工作区测试")
        db.add(c)
        db.commit()

        r = auth_client.get("/api/workspace/me")
        assert r.status_code == 200
        data = r.json()
        assert "watchlists" in data
        assert "price_levels" in data
        assert "recent_comments" in data
        assert len(data["watchlists"]) >= 1
        assert len(data["price_levels"]) >= 1
        assert len(data["recent_comments"]) >= 1
