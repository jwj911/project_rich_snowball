"""
自选 Watchlist API 测试
======================
验证：CRUD、越权、重复添加

运行方式：
    cd python
    pytest tests/test_watchlists.py -v
"""

import os
import sys
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from main import app
from fastapi.testclient import TestClient
from routers.auth import clear_rate_limit_store

client = TestClient(app)


def _register_and_login():
    clear_rate_limit_store()
    username = f"wl_test_{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": "password123"
    })
    r = client.post("/api/auth/login", data={
        "username": username,
        "password": "password123"
    })
    return r.json()["access_token"]


def test_create_watchlist():
    """登录用户应能添加自选"""
    token = _register_and_login()
    r = client.post("/api/watchlists", json={
        "variety_id": 1,
        "notes": "关注黄金"
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["variety_id"] == 1
    assert data["notes"] == "关注黄金"


def test_create_watchlist_duplicate():
    """重复添加同一品种应返回 409"""
    token = _register_and_login()
    client.post("/api/watchlists", json={
        "variety_id": 1,
        "notes": "第一次"
    }, headers={"Authorization": f"Bearer {token}"})
    r = client.post("/api/watchlists", json={
        "variety_id": 1,
        "notes": "第二次"
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 409


def test_list_watchlists():
    """应返回当前用户的自选列表"""
    token = _register_and_login()
    client.post("/api/watchlists", json={
        "variety_id": 1,
        "notes": ""
    }, headers={"Authorization": f"Bearer {token}"})
    r = client.get("/api/watchlists", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_update_watchlist():
    """用户应能更新自己的自选备注"""
    token = _register_and_login()
    r = client.post("/api/watchlists", json={
        "variety_id": 1,
        "notes": "旧备注"
    }, headers={"Authorization": f"Bearer {token}"})
    wid = r.json()["id"]

    r = client.put(f"/api/watchlists/{wid}", json={
        "notes": "新备注",
        "is_notified": True
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["notes"] == "新备注"
    assert r.json()["is_notified"] is True


def test_delete_watchlist():
    """用户应能删除自己的自选"""
    token = _register_and_login()
    r = client.post("/api/watchlists", json={
        "variety_id": 1,
        "notes": ""
    }, headers={"Authorization": f"Bearer {token}"})
    wid = r.json()["id"]

    r = client.delete(f"/api/watchlists/{wid}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    r = client.get("/api/watchlists", headers={"Authorization": f"Bearer {token}"})
    assert len(r.json()) == 0


def test_cross_user_watchlist_forbidden():
    """用户 A 不应能操作用户 B 的自选"""
    token_a = _register_and_login()
    r = client.post("/api/watchlists", json={
        "variety_id": 1,
        "notes": "A 的"
    }, headers={"Authorization": f"Bearer {token_a}"})
    wid = r.json()["id"]

    token_b = _register_and_login()
    r = client.put(f"/api/watchlists/{wid}", json={
        "notes": "B 篡改"
    }, headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 403

    r = client.delete(f"/api/watchlists/{wid}", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 403


def test_unauthorized_watchlist():
    """未登录访问应返回 401"""
    client.cookies.clear()
    r = client.get("/api/watchlists")
    assert r.status_code == 401
