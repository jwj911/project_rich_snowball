"""Agent 流式执行测试。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from models import AgentTaskDB, FutContractDB, KlineDataDB, RealtimeQuoteDB, UserDB, VarietyDB
from services.agent.analysis_pipeline_agent import AnalysisPipelineAgent
from services.agent.backtest_agent import BacktestAgent
from services.agent.context import AgentContext
from services.agent.core import AgentEventType, AgentResult, AgentStatus
from services.agent.data_quality_agent import DataQualityAgent
from services.agent.executor import AgentExecutor
from services.agent.factor_mining_agent import FactorMiningAgent
from services.agent.risk_management_agent import RiskManagementAgent
from services.agent.strategy_compiler_agent import StrategyCompilerAgent
from services.agent.tech_analysis_agent import TechAnalysisAgent
import numpy as np
from datetime import datetime, timezone, timedelta


def _create_user(db_session) -> UserDB:
    user = UserDB(
        username="agent_stream_user",
        email="agent-stream@example.com",
        password_hash="x",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_test_variety(
    db_session,
    symbol: str = "RB",
    name: str = "螺纹钢",
    exchange: str = "SHFE",
    multiplier: float = 10.0,
    tick_size: float = 1.0,
) -> VarietyDB:
    variety = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if variety is None:
        variety = VarietyDB(
            symbol=symbol,
            contract_code=symbol + "2501",
            name=name,
            exchange=exchange,
            category="黑色系",
            margin_rate=8.0,
            multiplier=multiplier,
            tick_size=tick_size,
            is_active=True,
        )
        db_session.add(variety)
    else:
        variety.name = name
        variety.exchange = exchange
        variety.category = "黑色系"
        variety.margin_rate = 8.0
        variety.multiplier = multiplier
        variety.tick_size = tick_size
        variety.is_active = True
    db_session.commit()
    db_session.refresh(variety)

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
            trading_time=datetime.now(timezone.utc) - timedelta(days=50 - i),
            trading_date=(datetime.now(timezone.utc) - timedelta(days=50 - i)).date(),
            open_price=round(open_p, 2),
            high_price=round(high, 2),
            low_price=round(low, 2),
            close_price=round(close, 2),
            volume=int(np.random.uniform(10000, 50000)),
        )
        db_session.add(kline)
    db_session.commit()

    return variety


async def _collect_stream(agent, query: str) -> list[dict[str, Any]]:
    """收集 Agent run_stream 产生的所有事件。"""
    events: list[dict[str, Any]] = []
    async for event in agent.run_stream(query):
        events.append(event)
    return events


@pytest.mark.parametrize(
    "agent_cls,query",
    [
        (TechAnalysisAgent, "分析螺纹钢日线"),
        (RiskManagementAgent, "螺纹钢做多风控方案"),
        (BacktestAgent, "螺纹钢 5 日上穿 20 日均线回测"),
        (StrategyCompilerAgent, "螺纹钢 5 日上穿 20 日均线做多策略"),
        (DataQualityAgent, "检查螺纹钢日线数据质量"),
    ],
)
def test_agent_run_stream_yields_events(db_session, agent_cls, query):
    user = _create_user(db_session)
    variety = _create_test_variety(db_session)
    task_id = AgentExecutor(db_session, user.id).create_task(agent_cls.name, query)
    agent = agent_cls(AgentContext(db_session, user.id, task_id))

    events = asyncio.run(_collect_stream(agent, query))

    event_types = [e["event_type"] for e in events]
    # run_stream 直接调用时不一定包含 start/done（由 executor 在 SSE 中补充）
    assert "result" in event_types or "error" in event_types
    # 至少有一个中间步骤或进度事件
    assert any(t in event_types for t in ("thought", "action", "observation", "progress"))
    assert events[-1]["event_type"] in ("result", "error")


def test_tech_analysis_stream_steps_in_real_time(db_session):
    """验证 TechAnalysisAgent 的流式事件按分析阶段逐步产生。"""
    user = _create_user(db_session)
    variety = _create_test_variety(db_session)
    task_id = AgentExecutor(db_session, user.id).create_task("tech_analysis", "分析螺纹钢日线")
    agent = TechAnalysisAgent(AgentContext(db_session, user.id, task_id))

    events = asyncio.run(_collect_stream(agent, "分析螺纹钢日线"))

    event_types = [e["event_type"] for e in events]
    assert "progress" in event_types
    assert "thought" in event_types
    assert "result" in event_types


def test_strategy_compiler_macd_volume_transform(db_session):
    """验证 MACD+成交量策略生成 volume > volume_sma * mult 的转换条件。"""
    user = _create_user(db_session)
    variety = _create_test_variety(db_session)
    task_id = AgentExecutor(db_session, user.id).create_task("strategy_compiler", "螺纹钢 MACD 金叉放量 1.5 倍做多策略")
    agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(agent.run("螺纹钢 MACD 金叉放量 1.5 倍做多策略"))

    assert result.success
    dsl = result.data["dsl"]
    entry = dsl["entry"]["conditions"]
    volume_cond = next((c for c in entry if c.get("indicator") == "volume"), None)
    assert volume_cond is not None
    assert volume_cond.get("indicator2") == "volume_sma20"
    assert volume_cond.get("value") == 1.5
    assert volume_cond.get("transform") == "multiply_value"


def test_risk_management_uses_variety_multiplier_and_tick_size(db_session):
    """验证风控 Agent 使用品种真实合约乘数和最小变动价位。"""
    user = _create_user(db_session)
    variety = _create_test_variety(db_session, symbol="CU", multiplier=5.0, tick_size=10.0)
    task_id = AgentExecutor(db_session, user.id).create_task("risk_management", "铜 CU 做多风控方案")
    agent = RiskManagementAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(agent.run("铜 CU 做多风控方案"))

    assert result.success
    # 止损价应为 tick_size 的整数倍
    stop_loss_price = result.data["stop_loss"]["stop_loss_price"]
    assert stop_loss_price % 10.0 == pytest.approx(0.0)


def test_analysis_pipeline_degrades_on_bad_data(db_session, monkeypatch):
    """验证完整分析在数据质量 bad 时降级为数据现状报告。"""
    user = _create_user(db_session)
    variety = _create_test_variety(db_session, symbol="AL", name="铝")
    # 删除 K 线数据使 preflight 为 bad
    db_session.query(KlineDataDB).filter(KlineDataDB.variety_id == variety.id).delete()
    db_session.commit()

    task_id = AgentExecutor(db_session, user.id).create_task("analysis_pipeline", "完整分析铝 AL")
    agent = AnalysisPipelineAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(agent.run("完整分析铝 AL"))

    assert result.success
    assert result.data["data_quality"]["status"] == "bad"
    assert "数据现状报告" in result.answer


def test_analysis_pipeline_full_run_on_good_data(db_session):
    """验证完整分析在数据质量良好时返回完整报告。"""
    user = _create_user(db_session)
    variety = _create_test_variety(db_session, symbol="ZN", name="锌")
    task_id = AgentExecutor(db_session, user.id).create_task("analysis_pipeline", "完整分析锌 ZN")
    agent = AnalysisPipelineAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(agent.run("完整分析锌 ZN"))

    assert result.success
    assert result.data["data_quality"]["status"] in ("good", "warning")
    assert "完整分析报告" in result.answer
    assert result.data["risk"]["position"] is not None
