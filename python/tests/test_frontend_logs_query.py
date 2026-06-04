"""前端监控日志查询端点测试
==============================
验证 GET /api/log/frontend 的权限、筛选和分页行为。
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-frontend-logs-query")
os.environ["ENABLE_SCHEDULER"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import UTC, datetime, timedelta

from models import FrontendLogDB


class TestFrontendLogsQueryAuth:
    def test_query_requires_auth(self, client):
        """未登录访问日志查询应返回 401。"""
        r = client.get("/api/log/frontend")
        assert r.status_code == 401

    def test_normal_user_can_only_see_own_logs(self, client, auth_headers, db_session):
        """普通用户只能查看与自己 user_id 关联的日志。"""
        from models import UserDB
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()

        # 创建一条属于该用户的日志
        db_session.add(FrontendLogDB(user_id=user.id, log_type="exception", level="error", payload_json='{}'))
        # 创建一条匿名日志
        db_session.add(FrontendLogDB(user_id=None, log_type="exception", level="error", payload_json='{}'))
        db_session.commit()

        r = client.get("/api/log/frontend", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["user_id"] == user.id

    def test_admin_can_see_all_logs(self, client, admin_headers, db_session):
        """admin 用户可以查看全部日志。"""
        # 创建匿名日志
        db_session.add(FrontendLogDB(user_id=None, log_type="exception", level="error", payload_json='{}'))
        # 创建 admin 自己的日志
        from models import UserDB
        admin = db_session.query(UserDB).filter(UserDB.username == "admin_tester").first()
        db_session.add(FrontendLogDB(user_id=admin.id, log_type="web-vitals", level="info", payload_json='{}'))
        db_session.commit()

        r = client.get("/api/log/frontend", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2


class TestFrontendLogsQueryFilters:
    def test_filter_by_type(self, client, auth_headers, db_session):
        """按 type 筛选应生效。"""
        from models import UserDB
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()

        db_session.add(FrontendLogDB(user_id=user.id, log_type="exception", level="error", payload_json='{}'))
        db_session.add(FrontendLogDB(user_id=user.id, log_type="web-vitals", level="info", payload_json='{}'))
        db_session.commit()

        r = client.get("/api/log/frontend?type=exception", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["type"] == "exception"

    def test_filter_by_level(self, client, auth_headers, db_session):
        """按 level 筛选应生效。"""
        from models import UserDB
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()

        db_session.add(FrontendLogDB(user_id=user.id, log_type="exception", level="error", payload_json='{}'))
        db_session.add(FrontendLogDB(user_id=user.id, log_type="exception", level="warning", payload_json='{}'))
        db_session.commit()

        r = client.get("/api/log/frontend?level=error", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["level"] == "error"

    def test_filter_by_time_range(self, client, auth_headers, db_session):
        """按时间范围筛选应生效。"""
        from models import UserDB
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()

        now = datetime.now(UTC)
        old = now - timedelta(hours=2)
        recent = now - timedelta(minutes=5)

        db_session.add(FrontendLogDB(user_id=user.id, log_type="exception", level="error", payload_json='{}', created_at=old))
        db_session.add(FrontendLogDB(user_id=user.id, log_type="exception", level="error", payload_json='{}', created_at=recent))
        db_session.commit()

        start = (now - timedelta(hours=1)).isoformat()
        r = client.get(f"/api/log/frontend?start_time={start}", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1

    def test_combined_filters(self, client, auth_headers, db_session):
        """组合筛选应生效。"""
        from models import UserDB
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()

        db_session.add(FrontendLogDB(user_id=user.id, log_type="exception", level="error", payload_json='{}'))
        db_session.add(FrontendLogDB(user_id=user.id, log_type="exception", level="warning", payload_json='{}'))
        db_session.add(FrontendLogDB(user_id=user.id, log_type="web-vitals", level="error", payload_json='{}'))
        db_session.commit()

        r = client.get("/api/log/frontend?type=exception&level=error", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1


class TestFrontendLogsQueryPagination:
    def test_pagination_skip_limit(self, client, auth_headers, db_session):
        """分页 skip/limit 应生效。"""
        from models import UserDB
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()

        for i in range(5):
            db_session.add(FrontendLogDB(user_id=user.id, log_type="exception", level="error", payload_json=f'{{"i":{i}}}'))
        db_session.commit()

        r = client.get("/api/log/frontend?skip=0&limit=2", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) == 2
        assert r.headers["X-Total-Count"] == "5"

        r = client.get("/api/log/frontend?skip=2&limit=2", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_pagination_empty_result(self, client, auth_headers):
        """无日志时返回空列表。"""
        r = client.get("/api/log/frontend", headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == []
        assert r.headers["X-Total-Count"] == "0"


class TestFrontendLogsQueryPayload:
    def test_payload_json_parsed(self, client, auth_headers, db_session):
        """响应中的 payload 应从 JSON 字符串解析为 dict。"""
        from models import UserDB
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()

        db_session.add(FrontendLogDB(
            user_id=user.id,
            log_type="exception",
            level="error",
            payload_json='{"error":"TypeError","message":"fail"}'
        ))
        db_session.commit()

        r = client.get("/api/log/frontend", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data[0]["payload"] == {"error": "TypeError", "message": "fail"}

    def test_post_with_token_resolves_user_id(self, client, auth_headers, db_session):
        """携带有效 token 时，user_id 应从 token 解析，忽略客户端传入值。"""
        from models import UserDB
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()

        payload = {
            "type": "exception",
            "payload": {"error": "Test"},
            "level": "error",
            "user_id": 99999,  # 伪造值，应被忽略
        }
        r = client.post("/api/log/frontend", json=payload, headers=auth_headers)
        assert r.status_code == 202

        r = client.get("/api/log/frontend", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["user_id"] == user.id
