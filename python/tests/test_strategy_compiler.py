"""StrategyCompilerAgent 测试。"""

from __future__ import annotations

import asyncio

import pytest

from models import AgentTaskDB, FutContractDB, KlineDataDB, RealtimeQuoteDB, VarietyDB
from services.agent.context import AgentContext
from services.agent.core import AgentStatus
from services.agent.executor import AgentExecutor
from services.agent.strategy_compiler_agent import StrategyCompilerAgent, StrategyDSL, StrategyValidator


def _create_user(db_session):
    from models import UserDB
    user = UserDB(
        username="strategy_compiler_user",
        email="strategy@example.com",
        password_hash="x",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_test_variety(db_session, symbol="RB", name="螺纹钢", exchange="SHFE"):
    existing = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if existing:
        return existing, db_session.query(FutContractDB).filter(FutContractDB.symbol == symbol).first()
    variety = VarietyDB(
        symbol=symbol,
        contract_code=symbol + "2501",
        name=name,
        exchange=exchange,
        category="黑色系",
        margin_rate=8.0,
        is_active=True,
    )
    db_session.add(variety)
    db_session.commit()
    db_session.refresh(variety)

    contract = FutContractDB(
        ts_code=symbol + "2501.SHF",
        symbol=symbol,
        name=name,
        exchange=exchange,
        fut_code=symbol,
        is_active=True,
    )
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(contract)

    quote = RealtimeQuoteDB(
        variety_id=variety.id,
        current_price=3500.0,
        change_percent=1.5,
        open_price=3450.0,
        high=3550.0,
        low=3440.0,
        volume=150000,
    )
    db_session.add(quote)
    db_session.commit()

    return variety, contract


class TestStrategyValidator:
    def test_valid_ma_cross_strategy(self):
        dsl = StrategyDSL(
            name="测试策略",
            description="测试",
            universe=["RB"],
            timeframe="1d",
            direction="long",
            entry={"conditions": [{"indicator": "sma5", "operator": "cross_above", "indicator2": "sma20"}], "logic": "and"},
            exit={"conditions": [{"indicator": "sma5", "operator": "cross_below", "indicator2": "sma20"}], "logic": "and"},
            risk={"position_size": {"type": "fixed_lots", "value": 1}, "stop_loss": {"type": "atr_multiple", "value": 2.0}, "take_profit": {"type": "risk_reward_ratio", "value": 2.0}},
        )
        errors = StrategyValidator.validate(dsl)
        assert errors == []

    def test_invalid_indicator(self):
        dsl = StrategyDSL(
            name="测试策略",
            description="测试",
            universe=["RB"],
            timeframe="1d",
            direction="long",
            entry={"conditions": [{"indicator": "invalid_indicator", "operator": "cross_above", "indicator2": "sma20"}], "logic": "and"},
            exit={"conditions": [], "logic": "and"},
            risk={},
        )
        errors = StrategyValidator.validate(dsl)
        assert any("不支持的指标" in e for e in errors)

    def test_invalid_operator(self):
        dsl = StrategyDSL(
            name="测试策略",
            description="测试",
            universe=["RB"],
            timeframe="1d",
            direction="long",
            entry={"conditions": [{"indicator": "sma5", "operator": "fly_to_moon"}], "logic": "and"},
            exit={"conditions": [], "logic": "and"},
            risk={},
        )
        errors = StrategyValidator.validate(dsl)
        assert any("不支持的操作符" in e for e in errors)

    def test_cross_without_indicator2(self):
        dsl = StrategyDSL(
            name="测试策略",
            description="测试",
            universe=["RB"],
            timeframe="1d",
            direction="long",
            entry={"conditions": [{"indicator": "sma5", "operator": "cross_above"}], "logic": "and"},
            exit={"conditions": [], "logic": "and"},
            risk={},
        )
        errors = StrategyValidator.validate(dsl)
        assert any("需要 indicator2" in e for e in errors)

    def test_invalid_timeframe(self):
        dsl = StrategyDSL(
            name="测试策略",
            description="测试",
            universe=["RB"],
            timeframe="invalid",
            direction="long",
            entry={"conditions": [], "logic": "and"},
            exit={"conditions": [], "logic": "and"},
            risk={},
        )
        errors = StrategyValidator.validate(dsl)
        assert any("不支持的周期" in e for e in errors)


class TestStrategyCompilerAgent:
    def test_ma_cross_strategy_compilation(self, db_session):
        user = _create_user(db_session)
        variety, contract = _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢5日上穿20日均线做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢5日上穿20日均线做多", task_id=task_id))

        task = db_session.get(AgentTaskDB, task_id)
        assert result.success is True
        assert task.status == "completed"
        assert result.data is not None
        assert "dsl" in result.data
        dsl = result.data["dsl"]
        assert dsl["universe"] == ["RB"]
        assert dsl["direction"] == "long"
        assert dsl["timeframe"] == "1d"
        assert len(dsl["entry"]["conditions"]) > 0
        assert dsl["entry"]["conditions"][0]["operator"] == "cross_above"

    def test_macd_strategy_compilation(self, db_session):
        user = _create_user(db_session)
        variety, contract = _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢MACD金叉做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢MACD金叉做多", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        assert dsl["entry"]["conditions"][0]["indicator"] == "macd_dif"
        assert dsl["entry"]["conditions"][0]["operator"] == "cross_above"
        assert dsl["entry"]["conditions"][0]["indicator2"] == "macd_dea"

    def test_rsi_strategy_compilation(self, db_session):
        user = _create_user(db_session)
        variety, contract = _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢RSI低于30做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢RSI低于30做多", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        assert dsl["entry"]["conditions"][0]["indicator"] == "rsi24"
        assert dsl["entry"]["conditions"][0]["operator"] == "less_than"
        assert dsl["entry"]["conditions"][0]["value"] == 30

    def test_bollinger_strategy_compilation(self, db_session):
        user = _create_user(db_session)
        variety, contract = _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢跌破布林带下轨做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢跌破布林带下轨做多", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        assert dsl["entry"]["conditions"][0]["indicator"] == "close"
        assert dsl["entry"]["conditions"][0]["operator"] == "cross_above"
        assert dsl["entry"]["conditions"][0]["indicator2"] == "boll_lower"

    def test_breakout_strategy_compilation(self, db_session):
        user = _create_user(db_session)
        variety, contract = _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢突破20日高点做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢突破20日高点做多", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        assert dsl["entry"]["conditions"][0]["indicator"] == "close"
        assert dsl["entry"]["conditions"][0]["operator"] == "cross_above"
        assert dsl["entry"]["conditions"][0]["indicator2"] == "high_20"

    def test_strategy_with_custom_risk(self, db_session):
        user = _create_user(db_session)
        variety, contract = _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢5日上穿20日均线做多，跌破3400止损，止盈3600")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢5日上穿20日均线做多，跌破3400止损，止盈3600", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        risk = dsl["risk"]
        assert risk["stop_loss"]["type"] == "fixed_price"
        assert risk["stop_loss"]["value"] == 3400.0
        assert risk["take_profit"]["type"] == "target_price"
        assert risk["take_profit"]["value"] == 3600.0

    def test_unknown_symbol_fails(self, db_session):
        user = _create_user(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "未知品种策略")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "未知品种 XXXX 策略", task_id=task_id))

        assert result.success is False
        assert "无法识别" in result.error_message

    def test_strategy_json_output(self, db_session):
        user = _create_user(db_session)
        variety, contract = _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢5日下穿20日均线做空")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢5日下穿20日均线做空", task_id=task_id))

        assert result.success is True
        assert "json" in result.data
        assert isinstance(result.data["json"], str)
        # 验证 JSON 可解析
        import json
        parsed = json.loads(result.data["json"])
        assert parsed["universe"] == ["RB"]
        assert parsed["direction"] == "short"


class TestSignalTemplates:
    """验证 quantative_tools signals 中的信号被抽象为可一键调用的策略模板。"""

    def test_kdj_oversold_strategy(self, db_session):
        user = _create_user(db_session)
        _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢 KDJ 超卖做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢 KDJ 超卖做多", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        assert dsl["entry"]["conditions"][0]["indicator"] == "kdj_k"
        assert dsl["entry"]["conditions"][0]["operator"] == "cross_above"
        assert dsl["entry"]["conditions"][0]["indicator2"] == "kdj_d"
        assert dsl["entry"]["conditions"][1]["indicator"] == "kdj_j"
        assert dsl["entry"]["conditions"][1]["operator"] == "less_than"

    def test_cci_mean_reversion_strategy(self, db_session):
        user = _create_user(db_session)
        _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢 CCI 低于 -100 做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢 CCI 低于 -100 做多", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        assert dsl["entry"]["conditions"][0]["indicator"].startswith("cci")
        assert dsl["entry"]["conditions"][0]["operator"] == "less_than"
        assert dsl["entry"]["conditions"][0]["value"] == -100

    def test_rsv_extreme_reversal_strategy(self, db_session):
        user = _create_user(db_session)
        _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢 RSV 小于 10 做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢 RSV 小于 10 做多", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        assert dsl["entry"]["conditions"][0]["indicator"] == "kdj_j"
        assert dsl["entry"]["conditions"][0]["operator"] == "less_than"
        assert dsl["entry"]["conditions"][0]["value"] == 10

    def test_ma_bias_strategy(self, db_session):
        user = _create_user(db_session)
        _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢均线偏离 2% 做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢均线偏离 2% 做多", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        assert dsl["entry"]["conditions"][0]["indicator"] == "close"
        assert dsl["entry"]["conditions"][0]["indicator2"] == "sma20"
        assert dsl["entry"]["conditions"][0]["operator"] == "greater_than"

    def test_bollinger_breakout_strategy(self, db_session):
        user = _create_user(db_session)
        _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢布林带突破上轨做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢布林带突破上轨做多", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        assert dsl["entry"]["conditions"][0]["indicator"] == "close"
        assert dsl["entry"]["conditions"][0]["operator"] == "cross_above"
        assert dsl["entry"]["conditions"][0]["indicator2"] == "boll_upper"

    def test_hl_breakout_strategy(self, db_session):
        user = _create_user(db_session)
        _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢突破昨日高点做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢突破昨日高点做多", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        assert dsl["entry"]["conditions"][0]["indicator"] == "close"
        assert dsl["entry"]["conditions"][0]["operator"] == "cross_above"
        assert dsl["entry"]["conditions"][0]["indicator2"] == "high_1"

    def test_hl_breakout_default_window(self, db_session):
        """未指定窗口时，高低点突破默认使用 20 周期。"""
        user = _create_user(db_session)
        _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢突破高点做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢突破高点做多", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        assert dsl["entry"]["conditions"][0]["indicator2"] == "high_20"

    def test_macd_short_default_direction(self, db_session):
        """MACD 未显式指定金叉/死叉时，空头默认死叉入、金叉出。"""
        user = _create_user(db_session)
        _create_test_variety(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢MACD做空")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢MACD做空", task_id=task_id))

        assert result.success is True
        dsl = result.data["dsl"]
        assert dsl["direction"] == "short"
        assert dsl["entry"]["conditions"][0]["operator"] == "cross_below"
        assert dsl["exit"]["conditions"][0]["operator"] == "cross_above"
