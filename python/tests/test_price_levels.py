"""
价位标注 Price Level API 测试
==============================
验证：CRUD、越权、重复价位、品种不存在

运行方式：
    cd python
    pytest tests/test_price_levels.py -v
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
    username = f"pl_test_{uuid.uuid4().hex[:8]}"
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


def test_create_price_level():
    """登录用户应能添加支撑/阻力位"""
    token = _register_and_login()
    r = client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "support",
        "price": "550.50",
        "note": "强支撑"
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["type"] == "support"
    assert data["price"] == "550.5000"
    assert data["note"] == "强支撑"


def test_create_price_level_duplicate():
    """同一用户同一品种同一类型同一价格应返回 409"""
    token = _register_and_login()
    client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "resistance",
        "price": "600.00",
        "note": ""
    }, headers={"Authorization": f"Bearer {token}"})
    r = client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "resistance",
        "price": "600.00",
        "note": "重复"
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 409


def test_list_price_levels():
    """应支持按品种和类型过滤"""
    token = _register_and_login()
    client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "support",
        "price": "100.00",
        "note": ""
    }, headers={"Authorization": f"Bearer {token}"})
    client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "resistance",
        "price": "200.00",
        "note": ""
    }, headers={"Authorization": f"Bearer {token}"})

    r = client.get("/api/price-levels?type=support", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["type"] == "support"


def test_update_price_level():
    """用户应能更新自己的价位标注"""
    token = _register_and_login()
    r = client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "support",
        "price": "300.00",
        "note": "旧"
    }, headers={"Authorization": f"Bearer {token}"})
    plid = r.json()["id"]

    r = client.put(f"/api/price-levels/{plid}", json={
        "price": "310.00",
        "note": "新"
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["price"] == "310.0000"
    assert r.json()["note"] == "新"


def test_update_price_level_duplicate():
    """更新 price 后与已有记录重复应返回 409"""
    token = _register_and_login()
    client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "support",
        "price": "300.00",
        "note": "第一条"
    }, headers={"Authorization": f"Bearer {token}"})
    r = client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "support",
        "price": "310.00",
        "note": "第二条"
    }, headers={"Authorization": f"Bearer {token}"})
    plid = r.json()["id"]

    r = client.put(f"/api/price-levels/{plid}", json={
        "price": "300.00"
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 409


def test_delete_price_level():
    """用户应能删除自己的价位标注"""
    token = _register_and_login()
    r = client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "support",
        "price": "400.00",
        "note": ""
    }, headers={"Authorization": f"Bearer {token}"})
    plid = r.json()["id"]

    r = client.delete(f"/api/price-levels/{plid}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    r = client.get("/api/price-levels", headers={"Authorization": f"Bearer {token}"})
    assert len(r.json()) == 0


def test_cross_user_price_level_forbidden():
    """用户 A 不应能操作用户 B 的价位标注"""
    token_a = _register_and_login()
    r = client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "support",
        "price": "500.00",
        "note": ""
    }, headers={"Authorization": f"Bearer {token_a}"})
    plid = r.json()["id"]

    token_b = _register_and_login()
    r = client.put(f"/api/price-levels/{plid}", json={
        "note": "篡改"
    }, headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 403

    r = client.delete(f"/api/price-levels/{plid}", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 403


def test_unauthorized_price_level():
    """未登录访问应返回 401"""
    r = client.get("/api/price-levels")
    assert r.status_code == 401


def test_create_price_levels_batch():
    """批量导入价位标注应成功，重复记录应跳过"""
    token = _register_and_login()

    # 先创建一条已有记录
    client.post("/api/price-levels", json={
        "variety_id": 1,
        "type": "support",
        "price": "100.00",
        "note": "已有"
    }, headers={"Authorization": f"Bearer {token}"})

    r = client.post("/api/price-levels/batch", json={
        "items": [
            {"variety_id": 1, "type": "support", "price": "100.00", "note": "重复"},
            {"variety_id": 1, "type": "support", "price": "200.00", "note": "新增支撑"},
            {"variety_id": 1, "type": "resistance", "price": "300.00", "note": "新增阻力"},
            {"variety_id": 99999, "type": "support", "price": "400.00", "note": "品种不存在"},
        ]
    }, headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200
    data = r.json()
    assert data["created_count"] == 2
    assert data["failed_count"] == 2
    assert len(data["success"]) == 2
    assert len(data["failed"]) == 2

    # 验证失败原因
    failed_reasons = {f["reason"] for f in data["failed"]}
    assert "该价位标注已存在" in failed_reasons
    assert "品种不存在" in failed_reasons

    # 验证最终列表
    r = client.get("/api/price-levels", headers={"Authorization": f"Bearer {token}"})
    levels = r.json()
    assert len(levels) == 3  # 100(已有) + 200 + 300
