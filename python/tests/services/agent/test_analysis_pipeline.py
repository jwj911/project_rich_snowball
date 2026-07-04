"""AnalysisPipelineAgent 测试。

验证多 Agent 串联时子任务创建、状态传递、汇总报告结构。
"""

from __future__ import annotations

import asyncio
from datetime import timezone, timedelta, datetime

import numpy as np
import pytest

from models import AgentTaskDB, FutContractDB, KlineDataDB, RealtimeQuoteDB, UserDB, VarietyDB
from services.agent.context import AgentContext
from services.agent.core import AgentResult, AgentStatus
from services.agent.data_agent import DataAgent
from services.agent.executor import AgentExecutor
from services.agent.analysis_pipeline_agent import AnalysisPipelineAgent


async def _mock_data_agent_run(self, query: str) -> AgentResult:
    """模拟 DataAgent 返回品种行情，避免测试依赖 LLM。"""
    return AgentResult(
        status=AgentStatus.COMPLETED,
        answer="螺纹钢最新价 3500.0，涨跌幅 1.5%",
        data={
            "current_price": 3500.0,
            "change_percent": 1.5,
            "name": "螺纹钢",
            "exchange": "SHFE",
            "symbol": "RB",
        },
        steps=[],
    )


@pytest.fixture
def _seed_pipeline_data(db_session, monkeypatch):
    """创建分析流水线所需的完整测试数据。"""
    monkeypatch.setattr(DataAgent, "run", _mock_data_agent_run)

    user = UserDB(username="pipeline_user", email="pipeline@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    symbol = "RB"
    variety = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if variety is None:
        variety = VarietyDB(
            symbol=symbol,
            contract_code=symbol + "2501",
            name="螺纹钢",
            exchange="SHFE",
            category="黑色系",
            margin_rate=8.0,
            is_active=True,
        )
        db_session.add(variety)
    else:
        variety.name = "螺纹钢"
        variety.exchange = "SHFE"
        variety.category = "黑色系"
        variety.is_active = True
    db_session.commit()
    db_session.refresh(variety)

    contract = FutContractDB(
        ts_code=symbol + "2501.SHF",
        symbol=symbol,
        name="螺纹钢",
        exchange="SHFE",
        fut_code=symbol,
        is_active=True,
    )
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(contract)

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

    base_prices = np.linspace(3300, 3600, 60)
    for i in range(60):
        close = base_prices[i] + np.random.normal(0, 20)
        open_p = close + np.random.normal(0, 15)
        high = max(open_p, close) + np.random.uniform(10, 30)
        low = min(open_p, close) - np.random.uniform(10, 30)
        kline = KlineDataDB(
            variety_id=variety.id,
            contract_id=contract.id,
            period="1d",
            trading_time=datetime.now(timezone.utc) - timedelta(days=60 - i),
            trading_date=(datetime.now(timezone.utc) - timedelta(days=60 - i)).date(),
            open_price=round(open_p, 2),
            high_price=round(high, 2),
            low_price=round(low, 2),
            close_price=round(close, 2),
            volume=int(np.random.uniform(10000, 50000)),
        )
        db_session.add(kline)
    db_session.commit()

    return user


class TestAnalysisPipeline:
    def test_pipeline_creates_sub_tasks(self, db_session, _seed_pipeline_data):
        user = _seed_pipeline_data
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("analysis_pipeline", "帮我完整分析螺纹钢")
        agent = AnalysisPipelineAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "帮我完整分析螺纹钢", task_id=task_id))

        assert result.success is True
        parent = db_session.get(AgentTaskDB, task_id)
        assert parent.status == "completed"
        sub_tasks = db_session.query(AgentTaskDB).filter(AgentTaskDB.parent_task_id == task_id).all()
        assert len(sub_tasks) == 3
        sub_types = {t.agent_type for t in sub_tasks}
        assert sub_types == {"data", "tech_analysis", "risk_management"}

    def test_sub_tasks_status_propagation(self, db_session, _seed_pipeline_data):
        user = _seed_pipeline_data
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("analysis_pipeline", "帮我完整分析螺纹钢")
        agent = AnalysisPipelineAgent(AgentContext(db_session, user.id, task_id))

        asyncio.run(executor.execute(agent, "帮我完整分析螺纹钢", task_id=task_id))

        sub_tasks = db_session.query(AgentTaskDB).filter(AgentTaskDB.parent_task_id == task_id).all()
        for sub in sub_tasks:
            assert sub.status == "completed"
            assert sub.result_json is not None

    def test_pipeline_report_structure(self, db_session, _seed_pipeline_data):
        user = _seed_pipeline_data
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("analysis_pipeline", "帮我完整分析螺纹钢")
        agent = AnalysisPipelineAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "帮我完整分析螺纹钢", task_id=task_id))

        data = result.data
        assert data is not None
        assert data["symbol"] == "RB"
        assert "data" in data
        assert "technical" in data
        assert "risk" in data
        assert "sub_task_results" in data
        assert data["technical"].get("score") is not None
        assert data["risk"].get("position") is not None

    def test_pipeline_fails_for_unknown_symbol(self, db_session):
        user = UserDB(username="pipeline_fail_user", email="pipeline-fail@example.com", password_hash="x")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("analysis_pipeline", "帮我完整分析 XXXX")
        agent = AnalysisPipelineAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "帮我完整分析 XXXX", task_id=task_id))

        assert result.success is False
        task = db_session.get(AgentTaskDB, task_id)
        assert task.status == "failed"
        assert "无法" in task.error_message
