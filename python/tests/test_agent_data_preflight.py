"""Agent 数据前置检查测试。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from models import FutContractDB, KlineDataDB, UserDB, VarietyDB
from services.agent.analysis_pipeline_agent import AnalysisPipelineAgent
from services.agent.backtest_agent import BacktestAgent
from services.agent.context import AgentContext
from services.agent.executor import AgentExecutor
from services.agent.factor_mining_agent import FactorMiningAgent


def _create_user(db_session, username: str = "preflight_user") -> UserDB:
    user = UserDB(username=username, email=f"{username}@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_variety_with_contract(db_session, symbol: str = "ZZ") -> tuple[VarietyDB, FutContractDB]:
    variety = VarietyDB(
        symbol=symbol,
        contract_code=f"{symbol}2501",
        name=f"{symbol}测试品种",
        exchange="SHFE",
        category="黑色系",
        is_active=True,
    )
    db_session.add(variety)
    db_session.flush()
    contract = FutContractDB(
        ts_code=f"{symbol}2501.SHF",
        symbol=symbol,
        fut_code=symbol,
        name=variety.name,
        exchange="SHFE",
        is_active=True,
    )
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(variety)
    db_session.refresh(contract)
    return variety, contract


def _add_daily_klines(
    db_session,
    variety: VarietyDB,
    contract: FutContractDB,
    count: int,
    high_price: float = 3520.0,
) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for offset in range(count):
        trading_time = base + timedelta(days=offset)
        db_session.add(
            KlineDataDB(
                variety_id=variety.id,
                contract_id=contract.id,
                period="1d",
                trading_time=trading_time,
                trading_date=trading_time.date(),
                open_price=3500.0,
                high_price=high_price,
                low_price=3480.0,
                close_price=3510.0,
                volume=10000,
            )
        )
    db_session.commit()


def test_backtest_agent_blocks_bad_kline_before_engine(db_session):
    user = _create_user(db_session, "backtest_preflight")
    _create_variety_with_contract(db_session, "ZZ")
    executor = AgentExecutor(db_session, user.id)
    task_id = executor.create_task("backtest", "ZZ 5日上穿20日均线回测")
    agent = BacktestAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(executor.execute(agent, "ZZ 5日上穿20日均线回测", task_id=task_id))

    assert result.success is False
    assert "已停止回测" in (result.error_message or "")
    assert result.data["data_preflight"]["status"] == "bad"
    assert result.data["data_preflight"]["quality"]["issues"][0]["code"] == "KLINE_NO_DATA"


def test_factor_mining_agent_reports_missing_panel_field_before_evaluation(db_session):
    user = _create_user(db_session, "factor_preflight")
    variety, contract = _create_variety_with_contract(db_session, "ZF")
    _add_daily_klines(db_session, variety, contract, 35)
    executor = AgentExecutor(db_session, user.id)
    task_id = executor.create_task("factor_mining", '评估 "amount / volume" 在 ZF 上的表现')
    agent = FactorMiningAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(executor.execute(agent, '评估 "amount / volume" 在 ZF 上的表现', task_id=task_id))

    assert result.success is False
    assert "尚未提供的字段" in (result.error_message or "")
    assert result.data["data_preflight"]["missing_fields"] == ["amount"]


def test_analysis_pipeline_degrades_on_bad_kline(db_session):
    user = _create_user(db_session, "pipeline_preflight")
    _create_variety_with_contract(db_session, "ZP")
    executor = AgentExecutor(db_session, user.id)
    task_id = executor.create_task("analysis_pipeline", "帮我完整分析 ZP")
    agent = AnalysisPipelineAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(executor.execute(agent, "帮我完整分析 ZP", task_id=task_id))

    # 数据质量 bad 时应降级为数据现状报告，而不是直接失败
    assert result.success is True
    assert result.data["data_quality"]["status"] == "bad"
    assert "数据现状报告" in result.answer
