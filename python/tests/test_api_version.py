"""API 版本治理中间件测试。

验证 ``/api/v1/*`` 路径被正确映射到 ``/api/*``，且不影响非 ``/api`` 路径。
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-api-version")
os.environ["ENABLE_SCHEDULER"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import NewsSourceDB


class TestApiVersionMiddleware:
    def test_v1_alias_returns_same_as_legacy(self, client, auth_headers, db_session):
        """/api/v1/news/sources 与 /api/news/sources 应返回相同结果。"""
        db_session.add(NewsSourceDB(name="内置", url="http://builtin/rss", is_enabled=True, is_builtin=True))
        db_session.commit()

        legacy = client.get("/api/news/sources", headers=auth_headers)
        v1 = client.get("/api/v1/news/sources", headers=auth_headers)

        assert legacy.status_code == 200
        assert v1.status_code == 200
        assert legacy.json() == v1.json()

    def test_v1_alias_requires_auth_same_as_legacy(self, client):
        """/api/v1 路径的鉴权行为与 /api 一致。"""
        legacy = client.get("/api/news/sources")
        v1 = client.get("/api/v1/news/sources")

        assert legacy.status_code == 401
        assert v1.status_code == 401

    def test_non_api_path_not_rewritten(self, client):
        """非 /api 路径不会被中间件重写，/health 保持原样。"""
        r = client.get("/health")
        assert r.status_code == 200

    def test_v1_root_without_trailing_slash_404(self, client):
        """/api/v1（无尾部斜杠）不匹配重写规则，返回 404。"""
        r = client.get("/api/v1")
        assert r.status_code == 404

    def test_legacy_path_still_works(self, client, auth_headers, db_session):
        """现有 /api 路径继续兼容。"""
        db_session.add(NewsSourceDB(name="内置", url="http://builtin/rss", is_enabled=True, is_builtin=True))
        db_session.commit()

        r = client.get("/api/news/sources", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) == 1
