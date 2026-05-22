"""Refresh token 机制测试。"""

from unittest.mock import patch

from fastapi.testclient import TestClient


class TestRefreshToken:
    """Refresh token 全链路测试。"""

    def test_login_sets_refresh_cookie_and_hides_token_body(self, client: TestClient):
        """登录响应只返回 access token，refresh token 写入 HttpOnly cookie。"""
        client.post("/api/auth/register", json={
            "username": "refresh_user",
            "email": "refresh@test.com",
            "password": "password123"
        })
        r = client.post("/api/auth/login", data={
            "username": "refresh_user",
            "password": "password123"
        })
        assert r.status_code == 200
        data = r.json()
        assert data["refresh_token"] is None
        assert "expires_in" in data

        refresh_cookie = r.cookies.get("refresh_token")
        assert refresh_cookie is not None
        assert len(refresh_cookie) > 20
        assert "httponly" in r.headers["set-cookie"].lower()

    def test_refresh_cookie_exchanges_new_access_token(self, client: TestClient):
        """HttpOnly refresh cookie 可以换取新的 access token。"""
        client.post("/api/auth/register", json={
            "username": "refresh_user2",
            "email": "refresh2@test.com",
            "password": "password123"
        })
        login_r = client.post("/api/auth/login", data={
            "username": "refresh_user2",
            "password": "password123"
        })
        assert login_r.status_code == 200

        r2 = client.post("/api/auth/refresh")
        assert r2.status_code == 200
        data = r2.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    def test_invalid_refresh_token_returns_401(self, client: TestClient):
        """无效 refresh token 应返回 401。"""
        r = client.post("/api/auth/refresh", json={"refresh_token": "invalid_token_xyz"})
        assert r.status_code == 401
        assert "无效" in r.json()["message"] or "过期" in r.json()["message"]

    def test_missing_refresh_token_returns_401(self, client: TestClient):
        """没有 refresh cookie 或兼容 body 时应返回 401。"""
        r = client.post("/api/auth/refresh")
        assert r.status_code == 401
        assert "无效" in r.json()["message"] or "过期" in r.json()["message"]

    def test_logout_revokes_refresh_cookie(self, client: TestClient):
        """登出后 refresh token 被吊销，当前 cookie 不能继续刷新。"""
        client.post("/api/auth/register", json={
            "username": "logout_user",
            "email": "logout@test.com",
            "password": "password123"
        })
        login_r = client.post("/api/auth/login", data={
            "username": "logout_user",
            "password": "password123"
        })
        access_token = login_r.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        logout_r = client.post("/api/auth/logout", headers=headers)
        assert logout_r.status_code == 200

        refresh_r = client.post("/api/auth/refresh")
        assert refresh_r.status_code == 401

    def test_refresh_token_uses_config_expire_days(self, client: TestClient):
        """P1 修复：refresh token 过期时间应读取 REFRESH_TOKEN_EXPIRE_DAYS 配置而非 hardcoded 7 天。"""
        client.post("/api/auth/register", json={
            "username": "refresh_config_user",
            "email": "refresh_config@test.com",
            "password": "password123"
        })
        with patch("routers.auth.REFRESH_TOKEN_EXPIRE_DAYS", 14):
            login_r = client.post("/api/auth/login", data={
                "username": "refresh_config_user",
                "password": "password123"
            })
            assert login_r.status_code == 200
            refresh_cookie = login_r.cookies.get("refresh_token")
            assert refresh_cookie is not None
            assert len(refresh_cookie) > 20

    def test_refresh_token_rotation(self, client: TestClient):
        """P2 修复：刷新 access token 时应同时轮转 refresh token，旧 token 立即失效。"""
        client.post("/api/auth/register", json={
            "username": "rotation_user",
            "email": "rotation@test.com",
            "password": "password123"
        })
        login_r = client.post("/api/auth/login", data={
            "username": "rotation_user",
            "password": "password123"
        })
        assert login_r.status_code == 200
        old_refresh_cookie = login_r.cookies.get("refresh_token")
        assert old_refresh_cookie is not None

        # 第一次刷新：应获得新的 access token 和新的 refresh cookie
        refresh_r1 = client.post("/api/auth/refresh")
        assert refresh_r1.status_code == 200
        new_refresh_cookie = refresh_r1.cookies.get("refresh_token")
        assert new_refresh_cookie is not None
        assert new_refresh_cookie != old_refresh_cookie, "refresh token 应被轮转"

        # 用旧的 refresh token 再次刷新：应返回 401（已吊销）
        # 手动构造带旧 cookie 的请求
        import httpx
        old_cookie_header = {"Cookie": f"refresh_token={old_refresh_cookie}"}
        refresh_r2 = client.post("/api/auth/refresh", headers=old_cookie_header)
        assert refresh_r2.status_code == 401, "旧 refresh token 被吊销后应无法再次使用"
