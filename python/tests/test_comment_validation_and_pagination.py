"""
评论校验和分页测试
==================
验证：空白内容拦截、分页参数边界

运行方式：
    cd python
    pytest tests/test_comment_validation_and_pagination.py -v
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_blank_comment_rejected():
    """空白评论应返回 422"""
    import uuid
    username = f"comment_test_{uuid.uuid4().hex[:8]}"
    # 先注册登录
    r = client.post("/api/auth/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": "password123"
    })
    assert r.status_code == 200, r.text

    r = client.post("/api/auth/login", data={
        "username": username,
        "password": "password123"
    })
    token = r.json()["access_token"]

    # 空白内容
    r = client.post("/api/comments", json={
        "product_id": 1,
        "content": "   "
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422
    assert "评论内容不能为空" in r.text


def test_comment_pagination():
    """评论列表应支持 skip/limit 分页"""
    r = client.get("/api/comments/user/trader001?skip=0&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) <= 5


def test_comment_pagination_limit_too_high():
    """limit 超过 1000 应返回 422"""
    r = client.get("/api/comments/user/trader001?limit=1001")
    assert r.status_code == 422


def test_product_comment_pagination():
    """商品详情评论应支持分页参数"""
    r = client.get("/api/products/1?comment_skip=0&comment_limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "comments" in data
    assert len(data["comments"]) <= 5
