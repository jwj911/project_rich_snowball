"""
工作区聚合 Workspace API 测试
=============================
验证：/api/workspace/me 返回当前用户的研究数据聚合

运行方式：
    cd python
    pytest tests/test_workspace.py -v
"""

import os
import sys
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from fastapi.testclient import TestClient
from routers.auth import clear_rate_limit_store

client = TestClient(app)


def _register_and_login():
    clear_rate_limit_store()
    username = f"ws_test_{uuid.uuid4().hex[:8]}"
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


def test_workspace_me_empty():
    """新用户的工作区应返回空列表"""
    token = _register_and_login()
    r = client.get("/api/workspace/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["price_levels"] == []
    assert data["watchlists"] == []
    assert data["recent_comments"] == []


def test_workspace_me_with_data():
    """添加数据后工作区应能聚合展示"""
    token = _register_and_login()

    # 添加价位标注
    client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "support",
        "price": "100.00",
        "note": "测试支撑"
    }, headers={"Authorization": f"Bearer {token}"})

    # 添加自选
    client.post("/api/watchlists", json={
        "variety_id": 1,
        "notes": "测试自选"
    }, headers={"Authorization": f"Bearer {token}"})

    # 添加评论（需要先有 product）
    client.post("/api/comments", json={
        "product_id": 1,
        "content": "测试评论"
    }, headers={"Authorization": f"Bearer {token}"})

    r = client.get("/api/workspace/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["price_levels"]) == 1
    assert len(data["watchlists"]) == 1
    assert len(data["recent_comments"]) == 1
    assert data["price_levels"][0]["note"] == "测试支撑"
    assert data["watchlists"][0]["notes"] == "测试自选"
    assert data["recent_comments"][0]["content"] == "测试评论"


def test_workspace_me_isolation():
    """用户 A 不应看到用户 B 的数据"""
    token_a = _register_and_login()
    client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "support",
        "price": "100.00",
        "note": "A 的"
    }, headers={"Authorization": f"Bearer {token_a}"})

    token_b = _register_and_login()
    r = client.get("/api/workspace/me", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200
    data = r.json()
    assert data["price_levels"] == []
    assert data["watchlists"] == []
    assert data["recent_comments"] == []


def test_workspace_unauthorized():
    """未登录访问应返回 401"""
    client.cookies.clear()
    r = client.get("/api/workspace/me")
    assert r.status_code == 401
