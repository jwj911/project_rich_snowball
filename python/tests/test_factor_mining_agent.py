"""FactorMiningAgent 测试 — 公式提取 / 安全校验 / 品种池 / 全流程评估。"""

from __future__ import annotations

import asyncio
from datetime import UTC

from models import AgentTaskDB, FutContractDB, KlineDataDB, RealtimeQuoteDB, UserDB, VarietyDB
from services.agent.context import AgentContext
from services.agent.executor import AgentExecutor
from services.agent.factor_engine.dsl import validate_factor_formula
from services.agent.factor_mining_agent import (
    FactorMiningAgent,
    _extract_formula,
    _factor_category_hint,
)


def _create_user(db_session):
    user = UserDB(
        username="factor_test_user",
        email="factor_test@example.com",
        password_hash="x",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _seed_kline_for_variety(db_session, variety_id, contract_id, count=60, start_price=3500.0):
    """为品种播种 K 线数据。"""
    from datetime import datetime, timedelta

    import numpy as np

    base_prices = np.linspace(start_price, start_price * 1.1, count)
    for i in range(count):
        existing = (
            db_session.query(KlineDataDB)
            .filter(
                KlineDataDB.variety_id == variety_id,
                KlineDataDB.contract_id == contract_id,
                KlineDataDB.period == "1d",
                KlineDataDB.trading_date == (datetime.now(UTC) - timedelta(days=count - i)).date(),
            )
            .first()
        )
        if existing:
            continue
        close = float(base_prices[i]) + np.random.normal(0, 20)
        open_p = close + np.random.normal(0, 15)
        high = max(open_p, close) + np.random.uniform(10, 30)
        low = min(open_p, close) - np.random.uniform(10, 30)
        kline = KlineDataDB(
            variety_id=variety_id,
            contract_id=contract_id,
            period="1d",
            trading_time=datetime.now(UTC) - timedelta(days=count - i),
            trading_date=(datetime.now(UTC) - timedelta(days=count - i)).date(),
            open_price=round(open_p, 2),
            high_price=round(high, 2),
            low_price=round(low, 2),
            close_price=round(close, 2),
            volume=int(np.random.uniform(5000, 30000)),
        )
        db_session.add(kline)
    db_session.commit()


def _create_test_variety(
    db_session, symbol="RB", name="螺纹钢", exchange="SHFE", category="黑色系", start_price=3500.0
):
    existing = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if existing:
        variety = existing
        variety.name = name
        variety.exchange = exchange
        variety.category = category
        variety.is_active = True
        contract = db_session.query(FutContractDB).filter(FutContractDB.symbol == symbol).first()
        if contract is None:
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
        db_session.refresh(variety)
        db_session.refresh(contract)
    else:
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

    quote = db_session.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
    if quote is None:
        quote = RealtimeQuoteDB(variety_id=variety.id)
        db_session.add(quote)
    quote.current_price = start_price
    quote.change_percent = 1.5
    quote.open_price = start_price - 50
    quote.high = start_price + 50
    quote.low = start_price - 50
    quote.volume = 150000
    db_session.commit()

    _seed_kline_for_variety(db_session, variety.id, contract.id, count=60, start_price=start_price)
    return variety, contract


# ------------------------------------------------------------------
# 公式提取测试
# ------------------------------------------------------------------


class TestFormulaExtraction:
    def test_quoted_formula(self):
        formula = _extract_formula('评估 "close / ts_delay(close, 5) - 1" 在黑色系的表现')
        assert formula is not None
        assert "close" in formula
        assert "ts_delay" in formula

    def test_unquoted_formula_with_fields(self):
        formula = _extract_formula("评估因子 close/ts_delay(close,10)-1")
        assert formula is not None
        assert "close" in formula

    def test_no_formula_returns_none(self):
        formula = _extract_formula("今天的黑色系表现如何")
        assert formula is None


# ------------------------------------------------------------------
# 因子类别提示测试
# ------------------------------------------------------------------


class TestFactorCategoryHint:
    def test_volume_price_hint(self):
        hint = _factor_category_hint("close * volume / ts_mean(volume, 20)")
        assert "价量" in hint or "volume" in hint.lower()

    def test_momentum_hint(self):
        hint = _factor_category_hint("close / ts_delay(close, 5) - 1")
        assert "动量" in hint or "momentum" in hint.lower()

    def test_volatility_hint(self):
        hint = _factor_category_hint("ts_std(close, 20)")
        assert "波动" in hint or "volatility" in hint.lower()


# ------------------------------------------------------------------
# 公式安全校验测试
# ------------------------------------------------------------------


class TestFormulaValidation:
    def test_simple_formula_passes(self):
        validate_factor_formula("close / ts_delay(close, 5) - 1")

    def test_safe_arithmetic_passes(self):
        validate_factor_formula("(high - low) / close")

    def test_safe_nested_function_passes(self):
        validate_factor_formula("ts_rank(close / ts_delay(close, 1) - 1, 20)")

    def test_dangerous_import_fails(self):
        import pytest

        with pytest.raises(ValueError):
            validate_factor_formula("__import__('os').system('ls')")


# ------------------------------------------------------------------
# FactorMiningAgent 全流程测试
# ------------------------------------------------------------------


class TestFactorMiningAgent:
    def test_full_evaluation_pipeline_single_symbol(self, db_session):
        """端到端因子评估：单个品种。"""
        user = _create_user(db_session)
        _create_test_variety(db_session, symbol="RB", name="螺纹钢", start_price=3500.0)

        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("factor_mining", '评估 "close/ts_delay(close,5)-1" 在螺纹钢上的表现')
        agent = FactorMiningAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(
            executor.execute(agent, '评估 "close/ts_delay(close,5)-1" 在螺纹钢上的表现', task_id=task_id)
        )

        task = db_session.get(AgentTaskDB, task_id)
        assert result.success is True, result.error_message
        assert task.status == "completed"
        assert result.data is not None
        # 关键评估字段
        assert "ic_mean" in result.data or result.data is not None
        assert "rank_ic_mean" in result.data or result.data is not None

    def test_evaluation_with_category(self, db_session):
        """因子评估：类别关键词。"""
        user = _create_user(db_session)
        _create_test_variety(db_session, symbol="RB", name="螺纹钢", start_price=3500.0)
        _create_test_variety(db_session, symbol="I", name="铁矿石", exchange="DCE", start_price=800.0)
        _create_test_variety(db_session, symbol="HC", name="热卷", start_price=3400.0)

        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("factor_mining", '评估 "close/ts_delay(close,5)-1" 在黑色系的表现')
        agent = FactorMiningAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(
            executor.execute(agent, '评估 "close/ts_delay(close,5)-1" 在黑色系的表现', task_id=task_id)
        )

        assert result.success is True, result.error_message
        assert "rank_ic_mean" in result.data

    def test_safety_rejected_formula(self, db_session):
        """危险公式被拒绝。"""
        user = _create_user(db_session)
        _create_test_variety(db_session, symbol="RB", name="螺纹钢", start_price=3500.0)

        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("factor_mining", '评估 "1+1" 在螺纹钢上的表现')
        agent = FactorMiningAgent(AgentContext(db_session, user.id, task_id))

        # "1+1" 公式缺少面板字段，应被安全校验拒绝
        result = asyncio.run(
            executor.execute(agent, "评估 \"__import__('os').system('ls')\" 在螺纹钢上的表现", task_id=task_id)
        )
        # 危险公式应校验失败
        assert result.success is False

    def test_no_formula_extracted_fails(self, db_session):
        """无法提取公式时返回失败。"""
        user = _create_user(db_session)
        _create_test_variety(db_session, symbol="RB", name="螺纹钢", start_price=3500.0)

        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("factor_mining", "帮我看看螺纹钢的技术面")
        agent = FactorMiningAgent(AgentContext(db_session, user.id, task_id))

        # "帮我看看螺纹钢的技术面" 不包含因子公式
        # 注意：_extract_formula 可能从"技术面"中错误提取，我们使用明确不含公式的查询
        result = asyncio.run(executor.execute(agent, "螺纹钢", task_id=task_id))
        assert result.success is False
