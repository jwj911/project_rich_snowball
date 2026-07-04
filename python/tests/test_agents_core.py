"""Agent 基座测试。"""

from __future__ import annotations

import asyncio
from typing import Any

from models import AgentTaskDB, FutContractDB, KlineDataDB, RealtimeQuoteDB, UserDB, VarietyDB
from services.agent.context import AgentContext
from services.agent.core import Agent, AgentResult, AgentStatus
from services.agent.executor import AgentExecutor
from services.agent.tech_analysis_agent import TechAnalysisAgent
from services.agent.risk_management_agent import RiskManagementAgent
from services.agent.tools import Tool, ToolDefinition, ToolParameter, ToolRegistry
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta


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


# ------------------------------------------------------------------
# TechAnalysisAgent 测试
# ------------------------------------------------------------------

def _create_test_variety(db_session, symbol="RB", name="螺纹钢", exchange="SHFE", margin_rate=8.0):
    """创建测试品种及关联数据。"""
    variety = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if variety is None:
        variety = VarietyDB(
            symbol=symbol,
            contract_code=symbol + "2501",
            name=name,
            exchange=exchange,
            category="黑色系",
            margin_rate=margin_rate,
            is_active=True,
        )
        db_session.add(variety)
    else:
        variety.name = name
        variety.exchange = exchange
        variety.category = "黑色系"
        variety.margin_rate = margin_rate
        variety.is_active = True
    db_session.commit()
    db_session.refresh(variety)

    # 创建关联合约
    ts_code = symbol + "2501.SHF"
    contract = db_session.query(FutContractDB).filter(FutContractDB.ts_code == ts_code).first()
    if contract is None:
        contract = FutContractDB(
            ts_code=ts_code,
            symbol=symbol,
            name=name,
            exchange="SHFE",
            fut_code=symbol,
            is_active=True,
        )
        db_session.add(contract)
    else:
        contract.symbol = symbol
        contract.name = name
        contract.exchange = "SHFE"
        contract.fut_code = symbol
        contract.is_active = True
    db_session.commit()
    db_session.refresh(contract)

    # 创建实时行情
    quote = db_session.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
    if quote is None:
        quote = RealtimeQuoteDB(variety_id=variety.id)
        db_session.add(quote)
    quote.current_price = 3500.0
    quote.change_percent = 1.5
    quote.open_price = 3450.0
    quote.high = 3550.0
    quote.low = 3440.0
    quote.volume = 150000
    db_session.commit()

    # 创建 K 线数据（50 根，上升趋势）
    base_prices = np.linspace(3300, 3600, 50)
    for i in range(50):
        close = base_prices[i] + np.random.normal(0, 20)
        open_p = close + np.random.normal(0, 15)
        high = max(open_p, close) + np.random.uniform(10, 30)
        low = min(open_p, close) - np.random.uniform(10, 30)
        kline = KlineDataDB(
            variety_id=variety.id,
            contract_id=contract.id,
            period="1d",
            trading_time=datetime.now(timezone.utc) - timedelta(days=50-i),
            trading_date=(datetime.now(timezone.utc) - timedelta(days=50-i)).date(),
            open_price=round(open_p, 2),
            high_price=round(high, 2),
            low_price=round(low, 2),
            close_price=round(close, 2),
            volume=int(np.random.uniform(10000, 50000)),
        )
        db_session.add(kline)
    db_session.commit()

    return variety, contract


def test_tech_analysis_agent_completes_with_report(db_session):
    user = _create_user(db_session)
    variety, contract = _create_test_variety(db_session, symbol="RB", name="螺纹钢")
    executor = AgentExecutor(db_session, user.id)
    task_id = executor.create_task("tech_analysis", "分析螺纹钢日线")
    agent = TechAnalysisAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(executor.execute(agent, "分析螺纹钢日线", task_id=task_id))

    task = db_session.get(AgentTaskDB, task_id)
    assert result.success is True
    assert task.status == "completed"
    assert result.data is not None
    assert "score" in result.data
    assert "rating" in result.data
    assert 0 <= result.data["score"] <= 100
    assert result.data["rating"] in ["偏强", "中性偏强", "中性", "中性偏弱", "偏弱"]
    assert "indicators" in result.data
    assert "rsi24" in result.data["indicators"] or result.data["indicators"].get("rsi24") is not None


def test_tech_analysis_agent_returns_failed_for_unknown_symbol(db_session):
    user = _create_user(db_session)
    executor = AgentExecutor(db_session, user.id)
    task_id = executor.create_task("tech_analysis", "分析未知品种")
    agent = TechAnalysisAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(executor.execute(agent, "分析 XXXX 走势", task_id=task_id))

    task = db_session.get(AgentTaskDB, task_id)
    assert result.success is False
    assert task.status == "failed"
    assert "无法从查询中识别" in task.error_message or "未找到" in task.error_message


# ------------------------------------------------------------------
# RiskManagementAgent 测试
# ------------------------------------------------------------------

def test_risk_management_agent_completes_with_plan(db_session):
    user = _create_user(db_session)
    variety, contract = _create_test_variety(db_session, symbol="AU", name="黄金", margin_rate=10.0)
    executor = AgentExecutor(db_session, user.id)
    task_id = executor.create_task("risk_management", "黄金做多风控方案")
    agent = RiskManagementAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(executor.execute(agent, "黄金做多风控方案", task_id=task_id))

    task = db_session.get(AgentTaskDB, task_id)
    assert result.success is True
    assert task.status == "completed"
    assert result.data is not None
    assert "position" in result.data
    assert "stop_loss" in result.data
    assert "take_profit" in result.data
    assert result.data["direction"] == "long"
    assert result.data["entry_price"] > 0


def test_risk_management_agent_returns_failed_for_unknown_symbol(db_session):
    user = _create_user(db_session)
    executor = AgentExecutor(db_session, user.id)
    task_id = executor.create_task("risk_management", "做空未知品种")
    agent = RiskManagementAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(executor.execute(agent, "做空 XXXX 风控", task_id=task_id))

    task = db_session.get(AgentTaskDB, task_id)
    assert result.success is False
    assert task.status == "failed"
    assert "无法识别" in task.error_message or "未找到" in task.error_message


def test_data_agent_fallback_without_llm_returns_result(client, auth_headers, monkeypatch, seed_varieties):
    import config

    monkeypatch.setattr(config, "OPENAI_API_KEY", "")

    resp = client.post(
        "/api/agents/tasks",
        json={"agent_type": "data", "query": "螺纹钢最新价格是多少"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "螺纹钢" in data["result"]["answer"]
    assert data["result"]["data"].get("symbol") == "RB"


def test_data_agent_fallback_sorts_top_gainers(client, auth_headers, monkeypatch, seed_varieties, db_session):
    import config
    from models import RealtimeQuoteDB, VarietyDB
    from decimal import Decimal

    monkeypatch.setattr(config, "OPENAI_API_KEY", "")

    for symbol, change in [("CU", Decimal("5.0")), ("AL", Decimal("2.0")), ("ZN", Decimal("3.0"))]:
        v = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        if v:
            quote = db_session.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == v.id).first()
            if quote is None:
                quote = RealtimeQuoteDB(variety_id=v.id)
                db_session.add(quote)
            quote.current_price = 1000.0
            quote.change_percent = change
            quote.volume = int(float(change) * 10000)
            db_session.commit()

    resp = client.post(
        "/api/agents/tasks",
        json={"agent_type": "data", "query": "有色金属涨幅前 3"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "铜" in data["result"]["answer"]


def test_agent_status_endpoint_returns_task_summary(client, auth_headers):
    resp = client.get("/api/agents/status", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tasks"] >= 0
    assert "llm_configured" in data
    assert any(item["agent_type"] == "data" for item in data["capabilities"])


def test_agent_permission_heartbeat_returns_current_permissions(client, auth_headers):
    resp = client.get("/api/agents/permission-heartbeat", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert data["can_create_tasks"] is True
    assert data["can_view_own_tasks"] is True
    assert "data" in data["allowed_agent_types"] or "tech_analysis" in data["allowed_agent_types"]
