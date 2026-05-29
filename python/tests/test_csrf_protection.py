"""CSRF 防护测试：验证写接口不接受 cookie-only 鉴权。

策略：POST/PUT/PATCH/DELETE 必须携带 Authorization header，不接受 access_token cookie
回退；GET/HEAD 保持兼容以支持 SSE 等场景。
"""

import pytest


@pytest.fixture(scope="function")
def csrf_user(client):
    """注册并登录，返回 (access_token, access_token_cookie)。"""
    client.post("/api/auth/register", json={
        "username": "csrf_tester",
        "email": "csrf@test.com",
        "password": "password123",
    })
    res = client.post("/api/auth/login", data={
        "username": "csrf_tester",
        "password": "password123",
    })
    assert res.status_code == 200
    data = res.json()
    access_token = data["access_token"]
    access_cookie = res.cookies.get("access_token")
    assert access_cookie, "access_token cookie should be set after login"
    return access_token, access_cookie


class TestWriteMethodsRequireHeader:
    """POST/PUT/PATCH/DELETE 必须携带 Authorization header，不接受 cookie 回退。"""

    def test_post_comment_without_header_returns_401(self, client, csrf_user):
        _, access_cookie = csrf_user
        res = client.post(
            "/api/comments",
            json={"content": "test", "variety_id": 1},
            cookies={"access_token": access_cookie},
        )
        assert res.status_code == 401

    def test_post_comment_with_header_succeeds(self, client, csrf_user):
        access_token, _ = csrf_user
        res = client.post(
            "/api/comments",
            json={"content": "test", "variety_id": 1},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        # 品种可能不存在返回 404，但不应因鉴权返回 401
        assert res.status_code != 401

    def test_post_watchlist_without_header_returns_401(self, client, csrf_user):
        _, access_cookie = csrf_user
        res = client.post(
            "/api/watchlists",
            json={"variety_id": 1},
            cookies={"access_token": access_cookie},
        )
        assert res.status_code == 401

    def test_post_price_level_without_header_returns_401(self, client, csrf_user):
        _, access_cookie = csrf_user
        res = client.post(
            "/api/price-levels",
            json={"variety_id": 1, "type": "support", "price": "100.00"},
            cookies={"access_token": access_cookie},
        )
        assert res.status_code == 401

    def test_put_price_level_without_header_returns_401(self, client, csrf_user):
        _, access_cookie = csrf_user
        res = client.put(
            "/api/price-levels/1",
            json={"price": "200.00"},
            cookies={"access_token": access_cookie},
        )
        assert res.status_code == 401

    def test_delete_price_level_without_header_returns_401(self, client, csrf_user):
        _, access_cookie = csrf_user
        res = client.delete(
            "/api/price-levels/1",
            cookies={"access_token": access_cookie},
        )
        assert res.status_code == 401

    def test_post_stream_token_without_header_returns_401(self, client, csrf_user):
        _, access_cookie = csrf_user
        res = client.post(
            "/api/realtime/stream-token",
            cookies={"access_token": access_cookie},
        )
        assert res.status_code == 401

    def test_logout_without_header_returns_401(self, client, csrf_user):
        _, access_cookie = csrf_user
        res = client.post(
            "/api/auth/logout",
            cookies={"access_token": access_cookie},
        )
        assert res.status_code == 401


class TestGetMethodsAcceptCookie:
    """GET/HEAD 仍然接受 cookie 鉴权（向后兼容，SSE 等场景）。"""

    def test_get_me_with_cookie_succeeds(self, client, csrf_user):
        _, access_cookie = csrf_user
        res = client.get(
            "/api/auth/me",
            cookies={"access_token": access_cookie},
        )
        assert res.status_code == 200
        assert res.json()["username"] == "csrf_tester"

    def test_get_realtime_batch_with_cookie_succeeds(self, client, csrf_user):
        _, access_cookie = csrf_user
        res = client.get(
            "/api/realtime/batch?symbols=AU",
            cookies={"access_token": access_cookie},
        )
        # 品种可能不存在返回 404，但不应因鉴权返回 401
        assert res.status_code != 401
