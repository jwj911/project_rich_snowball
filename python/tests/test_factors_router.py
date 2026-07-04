"""因子管理路由测试。

覆盖因子 CRUD 全部接口：列表、创建、详情、更新、软删除，
以及权限边界（owner/非owner/管理员/系统内置因子）和公式校验。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from models import FactorDefinitionDB, UserDB
from utils import hash_password

# ------------------------------------------------------------------
# 测试辅助函数
# ------------------------------------------------------------------

def _get_auth_user(db_session) -> UserDB | None:
    """获取 auth_headers 注册的用户。"""
    return db_session.query(UserDB).filter_by(username="integration_tester").first()


def _unique_factor_id(prefix: str = "factor") -> str:
    """生成唯一因子标识符，避免 UNIQUE 约束冲突。"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _create_builtin_factor(
    db_session,
    factor_id: str | None = None,
    name: str = "内置测试因子",
    category: str = "测试分类",
    q_score: str | Decimal | None = "0.9000",
    source: str = "wanfactor",
) -> FactorDefinitionDB:
    """创建系统内置因子（is_builtin=True, user_id=None）。"""
    factor = FactorDefinitionDB(
        user_id=None,
        is_builtin=True,
        package_id="manual",
        factor_id=factor_id or _unique_factor_id("builtin"),
        name=name,
        source=source,
        category=category,
        q_score=Decimal(q_score) if q_score is not None else None,
        source_expression="close / open",
        conversion_status="pending",
        is_active=True,
    )
    db_session.add(factor)
    db_session.flush()
    db_session.refresh(factor)
    return factor


def _create_user_factor(
    db_session,
    user_id: int,
    factor_id: str | None = None,
    name: str = "用户测试因子",
    category: str = "用户分类",
    source_expression: str = "close - open",
    source: str = "user",
) -> FactorDefinitionDB:
    """创建用户自定义因子（is_builtin=False, user_id=指定值）。"""
    factor = FactorDefinitionDB(
        user_id=user_id,
        is_builtin=False,
        package_id=f"user_{user_id}",
        factor_id=factor_id or _unique_factor_id("user"),
        name=name,
        source=source,
        category=category,
        source_expression=source_expression,
        conversion_status="pending",
        is_active=True,
    )
    db_session.add(factor)
    db_session.flush()
    db_session.refresh(factor)
    return factor


class TestFactorList:
    """GET /api/factors — 因子列表测试。"""

    def test_list_factors_empty(self, client, auth_headers):
        """空库时返回空列表。"""
        resp = client.get("/api/factors", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    def test_list_factors_returns_active_only(self, client, auth_headers, db_session):
        """默认只返回 is_active=True 的因子。"""
        user = _get_auth_user(db_session)
        _create_user_factor(db_session, user.id, name="活跃因子")
        deleted = _create_user_factor(db_session, user.id, name="已删除因子")
        deleted.is_active = False
        db_session.flush()

        resp = client.get("/api/factors", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        names = {f["name"] for f in data}
        assert "活跃因子" in names
        assert "已删除因子" not in names

    def test_list_factors_pagination(self, client, auth_headers, db_session):
        """分页参数 skip/limit 生效。"""
        user = _get_auth_user(db_session)
        for i in range(5):
            _create_user_factor(db_session, user.id, factor_id=f"f_{i}", name=f"因子{i}")

        resp = client.get("/api/factors?skip=0&limit=2", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        resp = client.get("/api/factors?skip=2&limit=2", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        resp = client.get("/api/factors?skip=4&limit=2", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    def test_list_factors_search_by_q(self, client, auth_headers, db_session):
        """q 参数支持名称和 factor_id 模糊搜索。"""
        user = _get_auth_user(db_session)
        _create_user_factor(db_session, user.id, factor_id="alpha_001", name="Alpha因子")
        _create_user_factor(db_session, user.id, factor_id="beta_002", name="Beta因子")

        resp = client.get("/api/factors?q=Alpha", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Alpha因子"

        resp = client.get("/api/factors?q=alpha_001", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["factor_id"] == "alpha_001"

    def test_list_factors_filter_by_category(self, client, auth_headers, db_session):
        """category 参数精确匹配。"""
        user = _get_auth_user(db_session)
        _create_user_factor(db_session, user.id, name="动量因子", category="momentum")
        _create_user_factor(db_session, user.id, name="价值因子", category="value")

        resp = client.get("/api/factors?category=momentum", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "动量因子"

    def test_list_factors_filter_by_source(self, client, auth_headers, db_session):
        """source 参数精确匹配。"""
        user = _get_auth_user(db_session)
        _create_user_factor(db_session, user.id, name="用户因子A", source="user")
        _create_builtin_factor(db_session, name="内置因子B", source="wanfactor")

        resp = client.get("/api/factors?source=wanfactor", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "内置因子B"

    def test_list_factors_filter_by_is_builtin(self, client, auth_headers, db_session):
        """is_builtin 参数布尔筛选。"""
        user = _get_auth_user(db_session)
        _create_user_factor(db_session, user.id, name="用户因子")
        _create_builtin_factor(db_session, name="内置因子")

        resp = client.get("/api/factors?is_builtin=true", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(f["is_builtin"] for f in data)
        assert any(f["name"] == "内置因子" for f in data)

        resp = client.get("/api/factors?is_builtin=false", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(not f["is_builtin"] for f in data)
        assert any(f["name"] == "用户因子" for f in data)

    def test_list_factors_sorted_by_q_score_desc(self, client, auth_headers, db_session):
        """默认按 q_score 降序排列。"""
        _get_auth_user(db_session)
        _create_builtin_factor(db_session, name="高Q因子", q_score="0.9500")
        _create_builtin_factor(db_session, name="低Q因子", q_score="0.8000")
        _create_builtin_factor(db_session, name="中Q因子", q_score="0.9000")

        resp = client.get("/api/factors", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        q_scores = [f["q_score"] for f in data if f["q_score"] is not None]
        assert q_scores == sorted(q_scores, reverse=True)

    def test_list_factors_requires_auth(self, client):
        """未登录返回 401。"""
        resp = client.get("/api/factors")
        assert resp.status_code == 401


class TestFactorCreate:
    """POST /api/factors — 创建自定义因子测试。"""

    def test_create_factor_success(self, client, auth_headers, db_session):
        """合法公式创建成功。"""
        resp = client.post(
            "/api/factors",
            json={
                "name": "我的自定义因子",
                "category": "momentum",
                "source_expression": "close / open",
                "fields_json": '["open", "close"]',
                "metadata_json": '{"description": "测试因子"}',
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "我的自定义因子"
        assert data["category"] == "momentum"
        assert data["source_expression"] == "close / open"
        assert data["is_builtin"] is False
        assert data["is_active"] is True
        assert data["user_id"] is not None
        assert data["package_id"].startswith("user_")
        assert data["conversion_status"] == "pending"
        assert data["factor_id"] is not None

    def test_create_factor_without_optional_fields(self, client, auth_headers):
        """可选字段（fields_json, metadata_json）可为空。"""
        resp = client.post(
            "/api/factors",
            json={
                "name": "简单因子",
                "category": "value",
                "source_expression": "close - open",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "简单因子"
        assert data["fields_json"] is None
        assert data["metadata_json"] is None

    def test_create_factor_invalid_formula(self, client, auth_headers):
        """非法公式返回 400 + VALIDATION_ERROR。"""
        resp = client.post(
            "/api/factors",
            json={
                "name": "非法因子",
                "category": "test",
                "source_expression": "import os; os.system('rm -rf /')",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == "VALIDATION_ERROR"
        assert "因子公式校验失败" in data["message"]

    def test_create_factor_empty_formula(self, client, auth_headers):
        """空公式触发 Pydantic 字段校验，返回 422。"""
        resp = client.post(
            "/api/factors",
            json={
                "name": "空公式因子",
                "category": "test",
                "source_expression": "",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_factor_requires_auth(self, client):
        """未登录返回 401。"""
        resp = client.post(
            "/api/factors",
            json={
                "name": "测试",
                "category": "test",
                "source_expression": "close + open",
            },
        )
        assert resp.status_code == 401


class TestFactorDetail:
    """GET /api/factors/{id} — 因子详情测试。"""

    def test_get_factor_success(self, client, auth_headers, db_session):
        """获取存在的因子详情。"""
        user = _get_auth_user(db_session)
        factor = _create_user_factor(db_session, user.id, name="详情因子")

        resp = client.get(f"/api/factors/{factor.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == factor.id
        assert data["name"] == "详情因子"
        assert data["source_expression"] == "close - open"

    def test_get_factor_not_found(self, client, auth_headers):
        """不存在的因子返回 404。"""
        resp = client.get("/api/factors/999999", headers=auth_headers)
        assert resp.status_code == 404
        data = resp.json()
        assert data["code"] == "NOT_FOUND"

    def test_get_factor_deleted_returns_404(self, client, auth_headers, db_session):
        """已软删除的因子返回 404。"""
        user = _get_auth_user(db_session)
        factor = _create_user_factor(db_session, user.id, name="已删除")
        factor.is_active = False
        db_session.flush()

        resp = client.get(f"/api/factors/{factor.id}", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_factor_requires_auth(self, client):
        """未登录返回 401。"""
        resp = client.get("/api/factors/1")
        assert resp.status_code == 401


class TestFactorUpdate:
    """PATCH /api/factors/{id} — 更新因子测试。"""

    def test_update_factor_owner_success(self, client, auth_headers, db_session):
        """Owner 成功更新自己创建的因子。"""
        user = _get_auth_user(db_session)
        factor = _create_user_factor(db_session, user.id, name="原始名称")

        resp = client.patch(
            f"/api/factors/{factor.id}",
            json={"name": "新名称", "category": "新分类"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "新名称"
        assert data["category"] == "新分类"
        # 未修改字段保持原值
        assert data["source_expression"] == "close - open"

    def test_update_factor_admin_can_modify(self, client, admin_headers, db_session):
        """管理员可以修改任意用户因子。"""
        # 创建一个普通用户及其因子
        normal_user = UserDB(
            username="normal_factor_user",
            email="normal@example.com",
            password_hash=hash_password("password123"),
        )
        db_session.add(normal_user)
        db_session.flush()
        db_session.refresh(normal_user)
        factor = _create_user_factor(db_session, normal_user.id, name="普通用户因子")

        resp = client.patch(
            f"/api/factors/{factor.id}",
            json={"name": "管理员修改"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "管理员修改"

    def test_update_factor_rejects_non_owner(self, client, auth_headers, db_session):
        """非 owner 非管理员修改用户因子返回 403。"""
        other_user = UserDB(
            username="factor_other",
            email="factor_other@test.com",
            password_hash=hash_password("password123"),
        )
        db_session.add(other_user)
        db_session.flush()
        db_session.refresh(other_user)
        factor = _create_user_factor(db_session, other_user.id, name="别人的因子")

        resp = client.patch(
            f"/api/factors/{factor.id}",
            json={"name": "试图修改"},
            headers=auth_headers,
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["code"] == "FORBIDDEN"

    def test_update_builtin_factor_rejected(self, client, auth_headers, db_session):
        """系统内置因子不可修改。"""
        factor = _create_builtin_factor(db_session, name="系统内置因子")

        resp = client.patch(
            f"/api/factors/{factor.id}",
            json={"name": "试图修改"},
            headers=auth_headers,
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["code"] == "FORBIDDEN"
        assert "系统内置因子" in data["message"]

    def test_update_factor_source_expression_revalidates(self, client, auth_headers, db_session):
        """修改 source_expression 时重新校验公式。"""
        user = _get_auth_user(db_session)
        factor = _create_user_factor(db_session, user.id, source_expression="close / open")

        # 合法公式更新
        resp = client.patch(
            f"/api/factors/{factor.id}",
            json={"source_expression": "close + open"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_expression"] == "close + open"

        # 非法公式更新
        resp = client.patch(
            f"/api/factors/{factor.id}",
            json={"source_expression": "__import__('os').system('ls')"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == "VALIDATION_ERROR"

    def test_update_factor_not_found(self, client, auth_headers):
        """更新不存在的因子返回 404。"""
        resp = client.patch(
            "/api/factors/999999",
            json={"name": "不存在"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_update_factor_requires_auth(self, client):
        """未登录返回 401。"""
        resp = client.patch("/api/factors/1", json={"name": "测试"})
        assert resp.status_code == 401


class TestFactorDelete:
    """DELETE /api/factors/{id} — 软删除因子测试。"""

    def test_delete_factor_owner_success(self, client, auth_headers, db_session):
        """Owner 成功软删除自己的因子。"""
        user = _get_auth_user(db_session)
        factor = _create_user_factor(db_session, user.id, name="待删除")

        resp = client.delete(f"/api/factors/{factor.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "因子已删除"

        # 验证数据库中已软删除
        db_session.refresh(factor)
        assert factor.is_active is False

    def test_delete_factor_admin_can_delete(self, client, admin_headers, db_session):
        """管理员可以删除任意用户因子。"""
        normal_user = UserDB(
            username="normal_delete_user",
            email="normal_del@example.com",
            password_hash=hash_password("password123"),
        )
        db_session.add(normal_user)
        db_session.flush()
        db_session.refresh(normal_user)
        factor = _create_user_factor(db_session, normal_user.id, name="管理员删除")

        resp = client.delete(f"/api/factors/{factor.id}", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "因子已删除"

    def test_delete_factor_rejects_non_owner(self, client, auth_headers, db_session):
        """非 owner 非管理员删除用户因子返回 403。"""
        other_user = UserDB(
            username="factor_delete_other",
            email="factor_delete_other@test.com",
            password_hash=hash_password("password123"),
        )
        db_session.add(other_user)
        db_session.flush()
        db_session.refresh(other_user)
        factor = _create_user_factor(db_session, other_user.id, name="别人的因子")

        resp = client.delete(f"/api/factors/{factor.id}", headers=auth_headers)
        assert resp.status_code == 403
        data = resp.json()
        assert data["code"] == "FORBIDDEN"

    def test_delete_builtin_factor_rejected(self, client, auth_headers, db_session):
        """系统内置因子不可删除。"""
        factor = _create_builtin_factor(db_session, name="系统内置待删")

        resp = client.delete(f"/api/factors/{factor.id}", headers=auth_headers)
        assert resp.status_code == 403
        data = resp.json()
        assert data["code"] == "FORBIDDEN"
        assert "系统内置因子" in data["message"]

    def test_delete_factor_not_found(self, client, auth_headers):
        """删除不存在的因子返回 404。"""
        resp = client.delete("/api/factors/999999", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_factor_requires_auth(self, client):
        """未登录返回 401。"""
        resp = client.delete("/api/factors/1")
        assert resp.status_code == 401
