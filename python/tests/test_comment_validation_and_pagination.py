"""
评论校验和分页测试
==================
验证：空白内容拦截、分页参数边界
"""

import uuid


def test_blank_comment_rejected(client):
    """空白评论应返回 422"""
    username = f"comment_test_{uuid.uuid4().hex[:8]}"
    r = client.post("/api/auth/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": "password123"
    })
    assert r.status_code == 201, r.text

    r = client.post("/api/auth/login", data={
        "username": username,
        "password": "password123"
    })
    token = r.json()["access_token"]

    r = client.post("/api/comments", json={
        "variety_id": 1,
        "content": "   "
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422
    assert "评论内容不能为空" in r.text


def test_comment_pagination(client, auth_headers):
    """评论列表应支持 skip/limit 分页"""
    r = client.get("/api/comments/me?skip=0&limit=5", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) <= 5


def test_comment_pagination_limit_too_high(client, auth_headers):
    """limit 超过 1000 应返回 422"""
    r = client.get("/api/comments/me?limit=1001", headers=auth_headers)
    assert r.status_code == 422


def test_product_comment_pagination(client, auth_headers):
    """品种详情评论应支持分页参数"""
    r = client.get("/api/varieties/AU/detail?comment_skip=0&comment_limit=5", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "comments" in data
    assert len(data["comments"]) <= 5
