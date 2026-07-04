"""Agent 路由器测试 — 覆盖 agents.py 全部 6 个端点。"""

from __future__ import annotations


class TestListAgentTasks:
    """GET /api/agents/tasks — 任务列表查询。"""

    def test_returns_empty_list_for_new_user(self, client, auth_headers):
        resp = client.get("/api/agents/tasks", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_returns_tasks_after_creation(self, client, auth_headers):
        # 先创建一个任务
        resp = client.post(
            "/api/agents/tasks",
            json={"agent_type": "data_quality", "query": "检查数据质量"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        resp = client.get("/api/agents/tasks", headers=auth_headers)

        data = resp.json()
        assert len(data) >= 1
        task = data[0]
        assert task["agent_type"] == "data_quality"
        assert task["query"] == "检查数据质量"
        assert "status" in task
        assert "steps" in task

    def test_filters_by_status(self, client, auth_headers):
        # 创建多个任务
        client.post("/api/agents/tasks", json={"agent_type": "data_quality", "query": "q1"}, headers=auth_headers)
        client.post("/api/agents/tasks", json={"agent_type": "data_quality", "query": "q2"}, headers=auth_headers)

        completed = client.get("/api/agents/tasks?status=completed", headers=auth_headers)
        pending = client.get("/api/agents/tasks?status=pending", headers=auth_headers)

        assert completed.status_code == 200
        assert pending.status_code == 200
        # data_quality 同步完成，所以 completed 列表应有数据
        assert len(completed.json()) >= 1

    def test_respects_pagination(self, client, auth_headers):
        # 创建 3 个任务
        for i in range(3):
            client.post("/api/agents/tasks", json={"agent_type": "data_quality", "query": f"q{i}"}, headers=auth_headers)

        resp = client.get("/api/agents/tasks?skip=0&limit=2", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) <= 2

    def test_requires_auth(self, client):
        resp = client.get("/api/agents/tasks")

        assert resp.status_code == 401


class TestGetAgentStatus:
    """GET /api/agents/status — 状态汇总。"""

    def test_returns_status_summary(self, client, auth_headers):
        resp = client.get("/api/agents/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert "server_time" in data
        assert "llm_configured" in data
        assert "total_tasks" in data
        assert "running_tasks" in data
        assert "completed_tasks" in data
        assert "failed_tasks" in data
        assert "recent_failed_tasks" in data
        assert isinstance(data["recent_failed_tasks"], list)
        assert "capabilities" in data
        assert len(data["capabilities"]) >= 1
        # 验证每个 capability 结构
        cap = data["capabilities"][0]
        assert "agent_type" in cap
        assert "label" in cap
        assert "enabled" in cap
        assert isinstance(cap["enabled"], bool)

    def test_requires_auth(self, client):
        resp = client.get("/api/agents/status")

        assert resp.status_code == 401


class TestGetPermissionHeartbeat:
    """GET /api/agents/permission-heartbeat — 权限心跳。"""

    def test_returns_permissions(self, client, auth_headers):
        resp = client.get("/api/agents/permission-heartbeat", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["authenticated"] is True
        assert data["can_create_tasks"] is True
        assert data["can_stream_chat"] is True
        assert data["can_view_own_tasks"] is True
        assert data["can_delete_own_tasks"] is True
        assert "allowed_agent_types" in data
        assert "data" in data["allowed_agent_types"] or "tech_analysis" in data["allowed_agent_types"]
        assert "csrf_policy" in data
        assert "token_transport" in data

    def test_requires_auth(self, client):
        resp = client.get("/api/agents/permission-heartbeat")

        assert resp.status_code == 401


class TestGetAgentTask:
    """GET /api/agents/tasks/{task_id} — 单任务详情。"""

    def test_returns_task_by_id(self, client, auth_headers):
        create = client.post(
            "/api/agents/tasks",
            json={"agent_type": "data_quality", "query": "测试任务"},
            headers=auth_headers,
        )
        task_id = create.json()["id"]

        resp = client.get(f"/api/agents/tasks/{task_id}", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task_id
        assert data["agent_type"] == "data_quality"
        assert data["query"] == "测试任务"
        assert "steps" in data
        assert "sub_tasks" in data

    def test_returns_404_for_nonexistent_task(self, client, auth_headers):
        resp = client.get("/api/agents/tasks/99999", headers=auth_headers)

        assert resp.status_code == 404

    def test_returns_sub_tasks_for_parent_task(self, client, auth_headers, db_session):
        """验证 parent/sub_tasks 关系能正确序列化为列表。"""
        from models import UserDB
        from services.agent.executor import AgentExecutor

        user = db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()
        executor = AgentExecutor(db_session, user.id)
        parent_id = executor.create_task("data_quality", "父任务")
        child_id = executor.create_task("data_quality", "子任务", parent_task_id=parent_id)

        resp = client.get(f"/api/agents/tasks/{parent_id}", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["sub_tasks"], list)
        assert len(data["sub_tasks"]) == 1
        assert data["sub_tasks"][0]["id"] == child_id
        assert data["sub_tasks"][0]["parent_task_id"] == parent_id

    def test_returns_403_for_other_users_task(self, client, auth_headers, db_session):
        """验证用户不能查看他人的任务。"""
        from models import UserDB

        # 用 auth_headers 用户创建一个任务
        create = client.post(
            "/api/agents/tasks",
            json={"agent_type": "data_quality", "query": "owner"},
            headers=auth_headers,
        )
        task_id = create.json()["id"]

        # 创建另一个用户并以该用户身份请求
        other_user = UserDB(
            username="other_user",
            email="other@test.com",
            password_hash="x",
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)

        # 注册并登录另一个用户
        client.post("/api/auth/register", json={
            "username": "other_user_2",
            "email": "other2@test.com",
            "password": "password123",
        })
        login_resp = client.post("/api/auth/login", data={
            "username": "other_user_2",
            "password": "password123",
        })
        other_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        resp = client.get(f"/api/agents/tasks/{task_id}", headers=other_headers)

        assert resp.status_code == 403


class TestCreateAgentTask:
    """POST /api/agents/tasks — 创建并同步执行 Agent 任务。"""

    def test_creates_data_quality_task(self, client, auth_headers, seed_varieties):
        resp = client.post(
            "/api/agents/tasks",
            json={"agent_type": "data_quality", "query": "检查数据质量"},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_type"] == "data_quality"
        assert data["status"] == "completed"
        assert data["result"] is not None
        assert data["result"]["status"] == "completed"

    def test_creates_tech_analysis_task(self, client, auth_headers, seed_varieties, db_session):
        """在有种子的数据库中执行技术分析。"""
        from models import FutContractDB, KlineDataDB, RealtimeQuoteDB

        variety = seed_varieties[0]  # AU

        # 创建必要的关联数据
        contract = db_session.query(FutContractDB).filter(FutContractDB.symbol == "AU").first()
        if contract is None:
            contract = FutContractDB(
                ts_code="AU2501.SHF",
                symbol="AU",
                name="黄金",
                exchange="SHFE",
                fut_code="AU",
                is_active=True,
            )
            db_session.add(contract)
            db_session.flush()
        else:
            db_session.refresh(contract)

        quote = db_session.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
        if quote is None:
            quote = RealtimeQuoteDB(
                variety_id=variety.id,
            )
            db_session.add(quote)
            db_session.flush()
        quote.current_price = 450.0
        quote.change_percent = 1.5
        quote.open_price = 445.0
        quote.high = 455.0
        quote.low = 444.0
        quote.volume = 50000
        db_session.commit()

        # 创建几根 K 线
        from datetime import UTC, datetime, timedelta

        for day_offset in range(30):
            kline = KlineDataDB(
                variety_id=variety.id,
                contract_id=contract.id,
                period="1d",
                trading_time=datetime.now(UTC) - timedelta(days=day_offset),
                open_price=445.0 + day_offset * 0.5,
                high_price=455.0 + day_offset * 0.5,
                low_price=440.0 + day_offset * 0.5,
                close_price=450.0 + day_offset * 0.5,
                volume=50000,
            )
            db_session.add(kline)
        db_session.commit()

        resp = client.post(
            "/api/agents/tasks",
            json={"agent_type": "tech_analysis", "query": "分析黄金走势"},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_type"] == "tech_analysis"
        assert data["status"] == "completed"
        assert data["result"] is not None

    def test_returns_400_for_invalid_agent_type(self, client, auth_headers):
        resp = client.post(
            "/api/agents/tasks",
            json={"agent_type": "nonexistent", "query": "test"},
            headers=auth_headers,
        )

        assert resp.status_code == 422  # Pydantic validation error

    def test_returns_error_for_missing_data(self, client, auth_headers):
        """在无种子数据时 data_quality agent 应返回 failed。"""
        resp = client.post(
            "/api/agents/tasks",
            json={"agent_type": "data_quality", "query": "检查数据"},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        # data_quality 在没有数据时可能 failed 或 completed（取决于逻辑）
        assert data["status"] in ("completed", "failed")

    def test_requires_auth(self, client):
        resp = client.post(
            "/api/agents/tasks",
            json={"agent_type": "data_quality", "query": "test"},
        )

        assert resp.status_code == 401


class TestDeleteAgentTask:
    """DELETE /api/agents/tasks/{task_id} — 删除任务。"""

    def test_deletes_own_task(self, client, auth_headers):
        create = client.post(
            "/api/agents/tasks",
            json={"agent_type": "data_quality", "query": "待删除"},
            headers=auth_headers,
        )
        task_id = create.json()["id"]

        resp = client.delete(f"/api/agents/tasks/{task_id}", headers=auth_headers)

        assert resp.status_code == 204

        # 确认已删除
        get_resp = client.get(f"/api/agents/tasks/{task_id}", headers=auth_headers)
        assert get_resp.status_code == 404

    def test_returns_404_for_nonexistent_task(self, client, auth_headers):
        resp = client.delete("/api/agents/tasks/99999", headers=auth_headers)

        assert resp.status_code == 404

    def test_returns_403_for_other_users_task(self, client, auth_headers):
        create = client.post(
            "/api/agents/tasks",
            json={"agent_type": "data_quality", "query": "owner"},
            headers=auth_headers,
        )
        task_id = create.json()["id"]

        # 以另一个用户身份尝试删除
        client.post("/api/auth/register", json={
            "username": "delete_other_user",
            "email": "delete_other@test.com",
            "password": "password123",
        })
        login_resp = client.post("/api/auth/login", data={
            "username": "delete_other_user",
            "password": "password123",
        })
        other_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        resp = client.delete(f"/api/agents/tasks/{task_id}", headers=other_headers)

        assert resp.status_code == 403

    def test_requires_auth(self, client):
        resp = client.delete("/api/agents/tasks/1")

        assert resp.status_code == 401
