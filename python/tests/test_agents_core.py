"""Agent 基座测试。"""

from __future__ import annotations

import asyncio
from typing import Any

from models import AgentTaskDB, UserDB
from services.agent.context import AgentContext
from services.agent.core import Agent, AgentResult, AgentStatus
from services.agent.executor import AgentExecutor
from services.agent.tools import Tool, ToolDefinition, ToolParameter, ToolRegistry


class _SuccessAgent(Agent):
    name = "success"

    async def run(self, query: str) -> AgentResult:
        self._add_step("thought", f"收到：{query}")
        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer="ok",
            data={"query": query},
            steps=self.get_steps(),
        )


class _FailedAgent(Agent):
    name = "failed"

    async def run(self, query: str) -> AgentResult:
        self._add_step("error", "模拟失败")
        return AgentResult(
            status=AgentStatus.FAILED,
            error_message="模拟失败",
            steps=self.get_steps(),
        )


class _EchoTool(Tool):
    name = "echo_symbol"
    description = "回显品种代码"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(name="symbol", type="string", description="品种代码", required=True),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        return {"user_id": context.user_id, "symbol": kwargs["symbol"].upper()}


def _create_user(db_session) -> UserDB:
    user = UserDB(
        username="agent_core_user",
        email="agent-core@example.com",
        password_hash="x",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_executor_persists_completed_status_and_steps(db_session):
    user = _create_user(db_session)
    executor = AgentExecutor(db_session, user.id)
    task_id = executor.create_task("test", "hello")
    agent = _SuccessAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(executor.execute(agent, "hello", task_id=task_id))

    task = db_session.get(AgentTaskDB, task_id)
    assert result.success is True
    assert task.status == "completed"
    assert task.result_json is not None
    assert len(task.steps) == 1
    assert task.steps[0].role == "thought"


def test_executor_persists_failed_result_as_failed(db_session):
    user = _create_user(db_session)
    executor = AgentExecutor(db_session, user.id)
    task_id = executor.create_task("test", "fail")
    agent = _FailedAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(executor.execute(agent, "fail", task_id=task_id))

    task = db_session.get(AgentTaskDB, task_id)
    assert result.success is False
    assert task.status == "failed"
    assert task.error_message == "模拟失败"
    assert len(task.steps) == 1
    assert task.steps[0].role == "error"


def test_tool_registry_executes_registered_tool(db_session):
    user = _create_user(db_session)
    registry = ToolRegistry()
    registry.register(_EchoTool())

    result = asyncio.run(
        registry.execute(
            "echo_symbol",
            AgentContext(db_session, user.id),
            {"symbol": "au"},
        )
    )

    assert result == {"user_id": user.id, "symbol": "AU"}


def test_data_agent_without_llm_config_marks_task_failed(client, auth_headers, monkeypatch):
    import config

    monkeypatch.setattr(config, "OPENAI_API_KEY", "")

    resp = client.post(
        "/api/agents/tasks",
        json={"agent_type": "data", "query": "黄金最新价格是多少"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert "OPENAI_API_KEY" in data["error_message"]
