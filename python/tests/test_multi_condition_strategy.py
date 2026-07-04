"""多条件 AND/OR 策略编译 + 多品种 universe 测试。

覆盖 GAP-02 (多条件) 和 GAP-01a (多品种解析)。
"""

from __future__ import annotations

import asyncio

from models import AgentTaskDB, FutContractDB, RealtimeQuoteDB, VarietyDB
from services.agent.context import AgentContext
from services.agent.core import AgentStatus
from services.agent.executor import AgentExecutor
from services.agent.strategy_compiler_agent import (
    StrategyCompilerAgent,
    StrategyDSL,
    StrategyParser,
    StrategyValidator,
)


def _create_user(db_session):
    from models import UserDB

    user = UserDB(
        username="multi_test_user",
        email="multi_test@example.com",
        password_hash="x",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_variety(db_session, symbol, name, exchange="SHFE", category="黑色系"):
    existing = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if existing:
        return existing, db_session.query(FutContractDB).filter(FutContractDB.symbol == symbol).first()

    variety = VarietyDB(
        symbol=symbol,
        contract_code=symbol + "2501",
        name=name,
        exchange=exchange,
        category=category,
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


# ------------------------------------------------------------------
# Multi-condition AND tests
# ------------------------------------------------------------------

class TestMultiConditionAnd:
    """Test AND-combined conditions (且/并且/同时)."""

    def test_ma_cross_with_rsi_filter(self, db_session):
        """MACD 金叉 且 RSI 低于 40 — two conditions combined with AND."""
        user = _create_user(db_session)
        _create_variety(db_session, "RB", "螺纹钢")
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢5日上穿20日均线且RSI低于40做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢5日上穿20日均线且RSI低于40做多", task_id=task_id))

        assert result.success is True, result.error_message
        dsl = result.data["dsl"]
        assert dsl["universe"] == ["RB"]
        assert dsl["direction"] == "long"
        assert dsl["entry"]["logic"] == "and"
        assert len(dsl["entry"]["conditions"]) >= 2

        conditions = dsl["entry"]["conditions"]
        # First condition is MA cross
        ma_cond = conditions[0]
        assert ma_cond["indicator"] == "sma5"
        assert ma_cond["operator"] == "cross_above"
        # Second condition is RSI < 40
        rsi_cond = conditions[1]
        assert rsi_cond["indicator"] == "rsi24"
        assert rsi_cond["operator"] == "less_than"
        assert rsi_cond["value"] == 40

    def test_macd_with_volume_confirmation(self, db_session):
        """MACD 金叉 且 成交量放大 — AND with volume."""
        user = _create_user(db_session)
        _create_variety(db_session, "RB", "螺纹钢")
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢MACD金叉且成交量放大做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢MACD金叉且成交量放大做多", task_id=task_id))

        assert result.success is True, result.error_message
        dsl = result.data["dsl"]
        assert dsl["entry"]["logic"] == "and"
        assert len(dsl["entry"]["conditions"]) >= 2

        has_volume = any(c.get("indicator") == "volume" for c in dsl["entry"]["conditions"])
        assert has_volume, "Should include volume condition"

    def test_ma_cross_with_price_above_ma_filter(self, db_session):
        """均线交叉 且 价格在20日均线上方."""
        user = _create_user(db_session)
        _create_variety(db_session, "RB", "螺纹钢")
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢5日上穿20日均线且价格在20日均线上方做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢5日上穿20日均线且价格在20日均线上方做多", task_id=task_id))

        assert result.success is True, result.error_message
        dsl = result.data["dsl"]
        assert dsl["entry"]["logic"] == "and"
        assert len(dsl["entry"]["conditions"]) >= 2

        has_price_above = any(
            c.get("indicator") == "close" and c.get("operator") == "above" and c.get("indicator2") == "sma20"
            for c in dsl["entry"]["conditions"]
        )
        assert has_price_above, "Should include price above MA condition"

    def test_ma_cross_with_adx_filter(self, db_session):
        """均线交叉 且 ADX高于25."""
        user = _create_user(db_session)
        _create_variety(db_session, "RB", "螺纹钢")
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢5日上穿20日均线且ADX高于25做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢5日上穿20日均线且ADX高于25做多", task_id=task_id))

        assert result.success is True, result.error_message
        dsl = result.data["dsl"]
        assert dsl["entry"]["logic"] == "and"
        assert len(dsl["entry"]["conditions"]) >= 2

        has_adx = any(
            c.get("indicator") == "adx" and c.get("operator") == "greater_than" and c.get("value") == 25
            for c in dsl["entry"]["conditions"]
        )
        assert has_adx, "Should include ADX > 25 condition"


# ------------------------------------------------------------------
# Multi-condition OR tests
# ------------------------------------------------------------------

class TestMultiConditionOr:
    """Test OR-combined conditions (或/或者)."""

    def test_rsi_or_bollinger_entry(self, db_session):
        """RSI 超卖 或 布林带下轨 — OR logic."""
        user = _create_user(db_session)
        _create_variety(db_session, "RB", "螺纹钢")
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢RSI低于30或者布林带下轨做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢RSI低于30或者布林带下轨做多", task_id=task_id))

        assert result.success is True, result.error_message
        dsl = result.data["dsl"]
        assert dsl["entry"]["logic"] == "or"
        assert len(dsl["entry"]["conditions"]) >= 2

    def test_breakout_or_ma_cross(self, db_session):
        """突破高点 或 均线金叉."""
        user = _create_user(db_session)
        _create_variety(db_session, "RB", "螺纹钢")
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢突破20日高点或5日上穿20日均线做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢突破20日高点或5日上穿20日均线做多", task_id=task_id))

        assert result.success is True, result.error_message
        dsl = result.data["dsl"]
        assert dsl["entry"]["logic"] == "or"
        assert len(dsl["entry"]["conditions"]) >= 2


# ------------------------------------------------------------------
# Multi-symbol universe tests (GAP-01a)
# ------------------------------------------------------------------

class TestMultiSymbolUniverse:
    """Test multi-symbol universe resolution."""

    def test_comma_separated_symbols(self, db_session):
        """螺纹钢, 热卷 — two symbols."""
        user = _create_user(db_session)
        _create_variety(db_session, "RB", "螺纹钢")
        _create_variety(db_session, "HC", "热卷")
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢,热卷 5日上穿20日均线做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢,热卷 5日上穿20日均线做多", task_id=task_id))

        assert result.success is True, result.error_message
        dsl = result.data["dsl"]
        assert sorted(dsl["universe"]) == sorted(["RB", "HC"])
        assert dsl["entry"]["conditions"][0]["indicator"] == "sma5"

    def test_chinese_connector_symbols(self, db_session):
        """螺纹钢和热卷以及铁矿石 — three symbols with 和/以及."""
        user = _create_user(db_session)
        _create_variety(db_session, "RB", "螺纹钢")
        _create_variety(db_session, "HC", "热卷")
        _create_variety(db_session, "I", "铁矿石", exchange="DCE", category="黑色系")
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢和热卷以及铁矿石MACD金叉做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢和热卷以及铁矿石MACD金叉做多", task_id=task_id))

        assert result.success is True, result.error_message
        dsl = result.data["dsl"]
        assert sorted(dsl["universe"]) == sorted(["RB", "HC", "I"])

    def test_dunhao_separated_symbols(self, db_session):
        """螺纹钢、热卷、铁矿石 — three symbols with 顿号."""
        user = _create_user(db_session)
        _create_variety(db_session, "RB", "螺纹钢")
        _create_variety(db_session, "HC", "热卷")
        _create_variety(db_session, "I", "铁矿石", exchange="DCE")
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢、热卷、铁矿石RSI低于30做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢、热卷、铁矿石RSI低于30做多", task_id=task_id))

        assert result.success is True, result.error_message
        dsl = result.data["dsl"]
        assert sorted(dsl["universe"]) == sorted(["RB", "HC", "I"])

    def test_english_comma_separated(self, db_session):
        """RB, HC, I — uppercase codes comma separated."""
        user = _create_user(db_session)
        _create_variety(db_session, "RB", "螺纹钢")
        _create_variety(db_session, "HC", "热卷")
        _create_variety(db_session, "I", "铁矿石", exchange="DCE")
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "RB,HC,I MACD金叉做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "RB,HC,I MACD金叉做多", task_id=task_id))

        assert result.success is True, result.error_message
        dsl = result.data["dsl"]
        assert sorted(dsl["universe"]) == sorted(["RB", "HC", "I"])

    def test_single_symbol_still_works(self, db_session):
        """Single symbol — regression test."""
        user = _create_user(db_session)
        _create_variety(db_session, "RB", "螺纹钢")
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("strategy_compiler", "螺纹钢5日上穿20日均线做多")
        agent = StrategyCompilerAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "螺纹钢5日上穿20日均线做多", task_id=task_id))

        assert result.success is True, result.error_message
        dsl = result.data["dsl"]
        assert dsl["universe"] == ["RB"]


# ------------------------------------------------------------------
# Validation edge cases
# ------------------------------------------------------------------

class TestMultiConditionValidation:
    """Test validator for multi-condition DSL."""

    def test_valid_multi_condition_and_passes(self):
        dsl = StrategyDSL(
            name="测试",
            description="测试",
            universe=["RB"],
            timeframe="1d",
            direction="long",
            entry={
                "conditions": [
                    {"indicator": "sma5", "operator": "cross_above", "indicator2": "sma20"},
                    {"indicator": "rsi24", "operator": "less_than", "value": 40},
                ],
                "logic": "and",
            },
            exit={
                "conditions": [{"indicator": "sma5", "operator": "cross_below", "indicator2": "sma20"}],
                "logic": "and",
            },
            risk={"position_size": {"type": "fixed_lots", "value": 1}},
        )
        errors = StrategyValidator.validate(dsl)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_valid_multi_condition_or_passes(self):
        dsl = StrategyDSL(
            name="测试",
            description="测试",
            universe=["RB"],
            timeframe="1d",
            direction="long",
            entry={
                "conditions": [
                    {"indicator": "rsi24", "operator": "less_than", "value": 30},
                    {"indicator": "close", "operator": "cross_above", "indicator2": "boll_lower"},
                ],
                "logic": "or",
            },
            exit={
                "conditions": [{"indicator": "rsi24", "operator": "greater_than", "value": 70}],
                "logic": "and",
            },
            risk={},
        )
        errors = StrategyValidator.validate(dsl)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_invalid_condition_in_chain_fails(self):
        dsl = StrategyDSL(
            name="测试",
            description="测试",
            universe=["RB"],
            timeframe="1d",
            direction="long",
            entry={
                "conditions": [
                    {"indicator": "sma5", "operator": "cross_above", "indicator2": "sma20"},
                    {"indicator": "bogus", "operator": "greater_than", "value": 0},
                ],
                "logic": "and",
            },
            exit={"conditions": [], "logic": "and"},
            risk={},
        )
        errors = StrategyValidator.validate(dsl)
        assert any("不支持的指标" in e for e in errors)

    def test_cross_without_indicator2_in_chain_fails(self):
        dsl = StrategyDSL(
            name="测试",
            description="测试",
            universe=["RB"],
            timeframe="1d",
            direction="long",
            entry={
                "conditions": [
                    {"indicator": "sma5", "operator": "cross_above"},
                    {"indicator": "rsi24", "operator": "less_than", "value": 30},
                ],
                "logic": "and",
            },
            exit={"conditions": [], "logic": "and"},
            risk={},
        )
        errors = StrategyValidator.validate(dsl)
        assert any("需要 indicator2" in e for e in errors)
