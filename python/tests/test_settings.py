"""用户偏好设置路由测试
======================
验证 /api/settings 的查询、更新、默认值和隔离性。
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-settings")
os.environ["ENABLE_SCHEDULER"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from models import UserPreferenceDB


class TestSettingsAuth:
    def test_get_settings_requires_auth(self, client):
        """未登录访问 /api/settings 应返回 401。"""
        r = client.get("/api/settings")
        assert r.status_code == 401

    def test_put_settings_requires_auth(self, client):
        """未登录更新 /api/settings 应返回 401。"""
        r = client.put("/api/settings", json={"theme": "light"})
        assert r.status_code == 401


class TestSettingsDefaults:
    def test_new_user_has_default_settings(self, client, auth_headers, db_session):
        """新注册用户应自动拥有默认偏好设置。"""
        r = client.get("/api/settings", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["theme"] == "dark"
        assert data["polling_interval_seconds"] == 30
        assert data["notifications_enabled"] is True
        assert data["language"] == "zh-CN"

    def test_settings_user_isolation(self, client, db_session):
        """用户 A 的设置不应影响用户 B。"""
        # 注册用户 A
        client.post("/api/auth/register", json={
            "username": "user_a",
            "email": "a@test.com",
            "password": "password123"
        })
        r = client.post("/api/auth/login", data={
            "username": "user_a",
            "password": "password123"
        })
        token_a = r.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # 注册用户 B
        client.post("/api/auth/register", json={
            "username": "user_b",
            "email": "b@test.com",
            "password": "password123"
        })
        r = client.post("/api/auth/login", data={
            "username": "user_b",
            "password": "password123"
        })
        token_b = r.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # A 更新主题为 light
        r = client.put("/api/settings", json={"theme": "light"}, headers=headers_a)
        assert r.status_code == 200

        # B 的主题仍应为 dark
        r = client.get("/api/settings", headers=headers_b)
        assert r.status_code == 200
        assert r.json()["theme"] == "dark"


class TestSettingsUpdate:
    def test_update_theme(self, client, auth_headers):
        """更新主题应生效。"""
        r = client.put("/api/settings", json={"theme": "light"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["theme"] == "light"

        r = client.get("/api/settings", headers=auth_headers)
        assert r.json()["theme"] == "light"

    def test_update_polling_interval(self, client, auth_headers):
        """更新轮询间隔应生效。"""
        r = client.put("/api/settings", json={"polling_interval_seconds": 60}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["polling_interval_seconds"] == 60

    def test_update_notifications(self, client, auth_headers):
        """更新通知开关应生效。"""
        r = client.put("/api/settings", json={"notifications_enabled": False}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["notifications_enabled"] is False

    def test_update_language(self, client, auth_headers):
        """更新语言应生效。"""
        r = client.put("/api/settings", json={"language": "en-US"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["language"] == "en-US"

    def test_partial_update(self, client, auth_headers):
        """Patch 语义：只更新提供的字段，其他不变。"""
        # 先更新 theme
        client.put("/api/settings", json={"theme": "light"}, headers=auth_headers)
        # 再只更新 language
        r = client.put("/api/settings", json={"language": "en-US"}, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["theme"] == "light"  # 未变更
        assert data["language"] == "en-US"
        assert data["polling_interval_seconds"] == 30  # 默认值未变

    def test_invalid_theme_rejected(self, client, auth_headers):
        """非法主题值应被校验拒绝。"""
        r = client.put("/api/settings", json={"theme": "invalid"}, headers=auth_headers)
        assert r.status_code == 422

    def test_polling_interval_out_of_range(self, client, auth_headers):
        """轮询间隔超出范围应被校验拒绝。"""
        r = client.put("/api/settings", json={"polling_interval_seconds": 1}, headers=auth_headers)
        assert r.status_code == 422

        r = client.put("/api/settings", json={"polling_interval_seconds": 4000}, headers=auth_headers)
        assert r.status_code == 422


class TestSettingsDbState:
    def test_preference_record_created_on_register(self, client, db_session):
        """注册后数据库中应存在对应的偏好记录。"""
        client.post("/api/auth/register", json={
            "username": "db_test_user",
            "email": "db@test.com",
            "password": "password123"
        })
        from models import UserDB
        user = db_session.query(UserDB).filter(UserDB.username == "db_test_user").first()
        pref = db_session.query(UserPreferenceDB).filter(UserPreferenceDB.user_id == user.id).first()
        assert pref is not None
        assert pref.theme == "dark"
