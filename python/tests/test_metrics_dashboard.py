"""业务指标面板路由测试
======================
验证 /metrics/dashboard 系列接口的结构、权限和聚合正确性。
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-metrics-dashboard")
os.environ["ENABLE_SCHEDULER"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import UTC, datetime, timedelta

from models import CommentDB, DataIngestionRunDB, PriceLevelDB, UserDB, WatchlistDB


class TestMetricsDashboardAuth:
    def test_dashboard_requires_auth(self, client):
        """未登录访问 /metrics/dashboard 应返回 401。"""
        r = client.get("/metrics/dashboard")
        assert r.status_code == 401

    def test_activity_requires_auth(self, client):
        """未登录访问 /metrics/dashboard/activity 应返回 401。"""
        r = client.get("/metrics/dashboard/activity")
        assert r.status_code == 401

    def test_collection_requires_auth(self, client):
        """未登录访问 /metrics/dashboard/collection 应返回 401。"""
        r = client.get("/metrics/dashboard/collection")
        assert r.status_code == 401

    def test_dashboard_forbids_normal_user(self, client, auth_headers):
        """普通登录用户访问 /metrics/dashboard 应返回 403。"""
        r = client.get("/metrics/dashboard", headers=auth_headers)
        assert r.status_code == 403

    def test_activity_forbids_normal_user(self, client, auth_headers):
        """普通登录用户访问 /metrics/dashboard/activity 应返回 403。"""
        r = client.get("/metrics/dashboard/activity", headers=auth_headers)
        assert r.status_code == 403

    def test_collection_forbids_normal_user(self, client, auth_headers):
        """普通登录用户访问 /metrics/dashboard/collection 应返回 403。"""
        r = client.get("/metrics/dashboard/collection", headers=auth_headers)
        assert r.status_code == 403

    def test_dashboard_allows_admin(self, client, admin_headers):
        """admin 用户访问 /metrics/dashboard 应返回 200。"""
        r = client.get("/metrics/dashboard", headers=admin_headers)
        assert r.status_code == 200

    def test_activity_allows_admin(self, client, admin_headers):
        """admin 用户访问 /metrics/dashboard/activity 应返回 200。"""
        r = client.get("/metrics/dashboard/activity", headers=admin_headers)
        assert r.status_code == 200

    def test_collection_allows_admin(self, client, admin_headers):
        """admin 用户访问 /metrics/dashboard/collection 应返回 200。"""
        r = client.get("/metrics/dashboard/collection", headers=admin_headers)
        assert r.status_code == 200


class TestMetricsDashboardOverview:
    def test_dashboard_structure(self, client, admin_headers, seed_varieties, db_session):
        """dashboard 接口应返回预期的结构。"""
        r = client.get("/metrics/dashboard", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "users" in data
        assert "comments" in data
        assert "engagement" in data
        assert "market" in data
        assert "timestamp" in data

    def test_dashboard_counts_with_data(self, client, admin_headers, seed_varieties, db_session):
        """有数据时 dashboard 计数应正确。"""
        # 创建评论
        user = db_session.query(UserDB).filter(UserDB.role == "admin").first()
        comment = CommentDB(variety_id=1, user_id=user.id, content="test")
        db_session.add(comment)
        # 创建价位标注
        pl = PriceLevelDB(user_id=user.id, variety_id=seed_varieties[0].id, type="support", price=100)
        db_session.add(pl)
        # 创建自选
        wl = WatchlistDB(user_id=user.id, variety_id=seed_varieties[1].id)
        db_session.add(wl)
        db_session.commit()

        r = client.get("/metrics/dashboard", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["comments"]["total"] >= 1
        assert data["engagement"]["price_levels"] >= 1
        assert data["engagement"]["watchlists"] >= 1
        assert data["market"]["total_varieties"] == len(seed_varieties)


class TestMetricsDashboardActivity:
    def test_activity_returns_7_days(self, client, admin_headers):
        """activity 接口应返回最近 7 天数据。"""
        r = client.get("/metrics/dashboard/activity", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "new_users" in data
        assert "comments" in data
        assert len(data["new_users"]) == 7
        assert len(data["comments"]) == 7
        # 每个元素应有 date 和 count
        for item in data["new_users"]:
            assert "date" in item
            assert "count" in item

    def test_activity_counts_with_data(self, client, admin_headers, seed_varieties, db_session):
        """有今日数据时 activity 计数应正确。"""
        user = db_session.query(UserDB).filter(UserDB.role == "admin").first()
        comment = CommentDB(variety_id=1, user_id=user.id, content="today")
        db_session.add(comment)
        db_session.commit()

        r = client.get("/metrics/dashboard/activity", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        today = datetime.now(UTC).date().isoformat()
        comment_today = next((d for d in data["comments"] if d["date"] == today), None)
        assert comment_today is not None
        assert comment_today["count"] >= 1


class TestMetricsDashboardCollection:
    def test_collection_structure_empty(self, client, admin_headers):
        """无采集数据时 collection 接口应返回合理默认值。"""
        r = client.get("/metrics/dashboard/collection", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "last_24h" in data
        assert "recent_runs" in data
        assert "circuit_breakers" in data
        assert "timestamp" in data
        assert data["last_24h"]["total"] == 0
        assert data["last_24h"]["success_rate"] is None

    def test_collection_with_run(self, client, admin_headers, db_session):
        """有采集数据时 collection 应正确聚合。"""
        run = DataIngestionRunDB(
            job_name="test_job",
            source="mock",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            duration_ms=1500,
            status="success",
            success_count=10,
            failed_count=0,
        )
        db_session.add(run)
        db_session.commit()

        r = client.get("/metrics/dashboard/collection", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["last_24h"]["total"] == 1
        assert data["last_24h"]["success"] == 1
        assert data["last_24h"]["success_rate"] == 1.0
        assert data["last_24h"]["avg_duration_ms"] == 1500
        assert len(data["recent_runs"]) == 1
        assert data["recent_runs"][0]["job_name"] == "test_job"
