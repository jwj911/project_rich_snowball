"""交易观点/日记路由测试
======================
验证 /api/opinions 的 CRUD、权限和状态流转行为。
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-opinions")
os.environ["ENABLE_SCHEDULER"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import OpinionDB, UserDB, VarietyDB


class TestOpinionsAuth:
    def test_list_requires_auth(self, client):
        """未登录访问观点列表应返回 401。"""
        r = client.get("/api/opinions")
        assert r.status_code == 401

    def test_me_requires_auth(self, client):
        """未登录访问我的观点应返回 401。"""
        r = client.get("/api/opinions/me")
        assert r.status_code == 401

    def test_create_requires_auth(self, client):
        """未登录创建观点应返回 401。"""
        r = client.post("/api/opinions", json={"variety_id": 1, "type": "long", "reason": "看涨"})
        assert r.status_code == 401

    def test_update_requires_auth(self, client):
        """未登录更新观点应返回 401。"""
        r = client.put("/api/opinions/1", json={"reason": "更新"})
        assert r.status_code == 401

    def test_delete_requires_auth(self, client):
        """未登录删除观点应返回 401。"""
        r = client.delete("/api/opinions/1")
        assert r.status_code == 401


class TestOpinionsCRUD:
    def test_create_opinion_success(self, client, auth_headers, db_session):
        """成功创建交易观点。"""
        variety = db_session.query(VarietyDB).first()
        assert variety is not None

        r = client.post(
            "/api/opinions",
            json={
                "variety_id": variety.id,
                "type": "long",
                "reason": "螺纹钢需求回暖，看好后市",
                "target_price": "4500.00",
                "stop_loss": "4100.00",
            },
            headers=auth_headers,
        )
        assert r.status_code == 201
        data = r.json()
        assert data["variety_id"] == variety.id
        assert data["type"] == "long"
        assert data["reason"] == "螺纹钢需求回暖，看好后市"
        assert data["target_price"] == "4500.0000"
        assert data["stop_loss"] == "4100.0000"
        assert data["status"] == "open"
        assert data["variety_symbol"] == variety.symbol
        assert data["variety_name"] == variety.name

    def test_create_opinion_variety_not_found(self, client, auth_headers):
        """品种不存在应返回 404。"""
        r = client.post(
            "/api/opinions",
            json={"variety_id": 99999, "type": "long", "reason": "test"},
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_create_opinion_invalid_type(self, client, auth_headers, db_session):
        """非法 type 应返回 422。"""
        variety = db_session.query(VarietyDB).first()
        r = client.post(
            "/api/opinions",
            json={"variety_id": variety.id, "type": "invalid", "reason": "test"},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_list_opinions(self, client, auth_headers, db_session):
        """观点列表应返回所有用户的观点。"""
        variety = db_session.query(VarietyDB).first()
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()
        db_session.add(OpinionDB(user_id=user.id, variety_id=variety.id, type="long", reason="A"))
        db_session.commit()

        r = client.get("/api/opinions", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert data[0]["reason"] == "A"

    def test_list_opinions_filter_by_variety(self, client, auth_headers, db_session):
        """按品种筛选应生效。"""
        v1 = db_session.query(VarietyDB).first()
        v2 = db_session.query(VarietyDB).offset(1).first()
        if v2 is None:
            # 如果只有一个品种，跳过此测试的核心断言
            return
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()
        db_session.add(OpinionDB(user_id=user.id, variety_id=v1.id, type="long", reason="V1"))
        db_session.add(OpinionDB(user_id=user.id, variety_id=v2.id, type="short", reason="V2"))
        db_session.commit()

        r = client.get(f"/api/opinions?variety_id={v1.id}", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert all(o["variety_id"] == v1.id for o in data)

    def test_list_opinions_filter_by_status(self, client, auth_headers, db_session):
        """按状态筛选应生效。"""
        variety = db_session.query(VarietyDB).first()
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()
        db_session.add(OpinionDB(user_id=user.id, variety_id=variety.id, type="long", reason="Open", status="open"))
        db_session.add(OpinionDB(user_id=user.id, variety_id=variety.id, type="short", reason="Closed", status="closed_profit"))
        db_session.commit()

        r = client.get("/api/opinions?status=closed_profit", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["status"] == "closed_profit"

    def test_me_returns_only_own(self, client, auth_headers, db_session):
        """我的观点只返回自己的。"""
        from models import UserDB
        variety = db_session.query(VarietyDB).first()
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()
        # 创建另一个用户
        other = UserDB(username="other_user", email="other@test.com", password_hash="x")
        db_session.add(other)
        db_session.flush()
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()
        db_session.add(OpinionDB(user_id=user.id, variety_id=variety.id, type="long", reason="Mine"))
        db_session.add(OpinionDB(user_id=other.id, variety_id=variety.id, type="short", reason="Other"))
        db_session.commit()

        r = client.get("/api/opinions/me", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["reason"] == "Mine"

    def test_get_single_opinion(self, client, auth_headers, db_session):
        """获取单条观点详情。"""
        variety = db_session.query(VarietyDB).first()
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()
        op = OpinionDB(user_id=user.id, variety_id=variety.id, type="long", reason="Detail")
        db_session.add(op)
        db_session.commit()

        r = client.get(f"/api/opinions/{op.id}", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == op.id
        assert data["reason"] == "Detail"

    def test_get_single_not_found(self, client, auth_headers):
        """获取不存在的观点应返回 404。"""
        r = client.get("/api/opinions/99999", headers=auth_headers)
        assert r.status_code == 404


class TestOpinionsUpdate:
    def test_update_opinion_success(self, client, auth_headers, db_session):
        """成功更新观点。"""
        variety = db_session.query(VarietyDB).first()
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()
        op = OpinionDB(user_id=user.id, variety_id=variety.id, type="long", reason="Old")
        db_session.add(op)
        db_session.commit()

        r = client.put(
            f"/api/opinions/{op.id}",
            json={"reason": "New reason", "target_price": "5000.00"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["reason"] == "New reason"
        assert data["target_price"] == "5000.0000"
        assert data["status"] == "open"

    def test_close_opinion_sets_closed_at(self, client, auth_headers, db_session):
        """关闭观点时自动记录 closed_at。"""
        variety = db_session.query(VarietyDB).first()
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()
        op = OpinionDB(user_id=user.id, variety_id=variety.id, type="long", reason="To close", status="open")
        db_session.add(op)
        db_session.commit()
        assert op.closed_at is None

        r = client.put(
            f"/api/opinions/{op.id}",
            json={"status": "closed_profit", "actual_outcome": "profit"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "closed_profit"
        assert data["actual_outcome"] == "profit"
        assert data["closed_at"] is not None

    def test_update_not_owner_returns_403(self, client, auth_headers, db_session):
        """非 owner 更新应返回 403。"""
        from models import UserDB
        variety = db_session.query(VarietyDB).first()
        other = UserDB(username="other_user2", email="other2@test.com", password_hash="x")
        db_session.add(other)
        db_session.flush()
        op = OpinionDB(user_id=other.id, variety_id=variety.id, type="long", reason="Other")
        db_session.add(op)
        db_session.commit()

        r = client.put(
            f"/api/opinions/{op.id}",
            json={"reason": "Hacked"},
            headers=auth_headers,
        )
        assert r.status_code == 403

    def test_update_not_found(self, client, auth_headers):
        """更新不存在的观点应返回 404。"""
        r = client.put("/api/opinions/99999", json={"reason": "x"}, headers=auth_headers)
        assert r.status_code == 404


class TestOpinionsDelete:
    def test_delete_opinion_success(self, client, auth_headers, db_session):
        """成功删除观点。"""
        variety = db_session.query(VarietyDB).first()
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()
        op = OpinionDB(user_id=user.id, variety_id=variety.id, type="long", reason="Delete me")
        db_session.add(op)
        db_session.commit()

        r = client.delete(f"/api/opinions/{op.id}", headers=auth_headers)
        assert r.status_code == 204
        assert db_session.get(OpinionDB, op.id) is None

    def test_delete_not_owner_returns_403(self, client, auth_headers, db_session):
        """非 owner 删除应返回 403。"""
        from models import UserDB
        variety = db_session.query(VarietyDB).first()
        other = UserDB(username="other_user3", email="other3@test.com", password_hash="x")
        db_session.add(other)
        db_session.flush()
        op = OpinionDB(user_id=other.id, variety_id=variety.id, type="long", reason="Other")
        db_session.add(op)
        db_session.commit()

        r = client.delete(f"/api/opinions/{op.id}", headers=auth_headers)
        assert r.status_code == 403

    def test_delete_not_found(self, client, auth_headers):
        """删除不存在的观点应返回 404。"""
        r = client.delete("/api/opinions/99999", headers=auth_headers)
        assert r.status_code == 404


class TestOpinionsXSS:
    def test_create_opinion_reason_xss_escaped(self, client, auth_headers, db_session):
        """reason 中的 <script> 标签应被 HTML escape。"""
        from html import escape

        variety = db_session.query(VarietyDB).first()
        assert variety is not None

        malicious_reason = "<script>alert('xss')</script>"
        r = client.post(
            "/api/opinions",
            json={"variety_id": variety.id, "type": "long", "reason": malicious_reason},
            headers=auth_headers,
        )
        assert r.status_code == 201
        data = r.json()
        assert data["reason"] == escape(malicious_reason)

    def test_update_opinion_reason_xss_escaped(self, client, auth_headers, db_session):
        """更新 reason 时 XSS 也应被清洗。"""
        from html import escape

        variety = db_session.query(VarietyDB).first()
        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()
        op = OpinionDB(user_id=user.id, variety_id=variety.id, type="long", reason="Original")
        db_session.add(op)
        db_session.commit()

        malicious_reason = "<img src=x onerror=alert(1)>"
        r = client.put(
            f"/api/opinions/{op.id}",
            json={"reason": malicious_reason},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["reason"] == escape(malicious_reason)
