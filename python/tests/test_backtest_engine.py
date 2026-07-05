"""Backtest engine unit tests.

Cover indicator computation (volume_sma, ATR channel), stop-loss/take-profit
execution, between operator, and scoring edge cases.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pandas as pd

from models import FutContractDB, KlineDataDB, RealtimeQuoteDB, VarietyDB
from services.agent.data_tools import _get_kline_data
from services.backtest.engine import _compute_indicator
from services.backtest.service import run_dsl_backtest


def _create_variety_and_contract(db_session, symbol="TE", name="测试品种"):
    existing = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if existing:
        contract = db_session.query(FutContractDB).filter(FutContractDB.symbol == symbol).first()
        if contract:
            return existing, contract
        contract = FutContractDB(
            ts_code=symbol + "2501.SHF",
            symbol=symbol,
            name=name,
            exchange="SHFE",
            fut_code=symbol,
            is_active=True,
        )
        db_session.add(contract)
        db_session.flush()
        return existing, contract

    variety = VarietyDB(
        symbol=symbol,
        contract_code=symbol + "2501",
        name=name,
        exchange="SHFE",
        category="黑色系",
        margin_rate=Decimal("0.10"),
        multiplier=Decimal("10"),
        tick_size=Decimal("1"),
        commission=Decimal("0.0001"),
        is_active=True,
    )
    db_session.add(variety)
    db_session.flush()

    contract = FutContractDB(
        ts_code=symbol + "2501.SHF",
        symbol=symbol,
        name=name,
        exchange="SHFE",
        fut_code=symbol,
        is_active=True,
    )
    db_session.add(contract)
    db_session.flush()

    quote = RealtimeQuoteDB(
        variety_id=variety.id,
        current_price=Decimal("3500"),
        change_percent=Decimal("0"),
    )
    db_session.add(quote)
    db_session.flush()

    return variety, contract


def _seed_klines(db_session, variety, contract, period="1d", rows=None):
    if rows is None:
        rows = []
    base_time = datetime(2024, 1, 1, 9, 0, 0)
    for i, row in enumerate(rows):
        k = KlineDataDB(
            variety_id=variety.id,
            contract_id=contract.id,
            period=period,
            trading_time=base_time + timedelta(days=i),
            open_price=Decimal(str(row["open"])),
            high_price=Decimal(str(row["high"])),
            low_price=Decimal(str(row["low"])),
            close_price=Decimal(str(row["close"])),
            volume=row.get("volume", 1000),
        )
        db_session.add(k)
    db_session.flush()
    return rows


def _baseline_rows(count=28):
    """Generate a stable price series to satisfy the minimum 30-bar requirement."""
    return [{"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000} for _ in range(count)]


def _always_true_entry():
    return [{"indicator": "close", "operator": "greater_than", "value": 0}]


def _never_exit():
    return [{"indicator": "close", "operator": "less_than", "value": 0}]


class TestIndicatorComputation:
    """Tests for _compute_indicator edge cases."""

    def test_volume_sma_indicator(self, db_session):
        variety, contract = _create_variety_and_contract(db_session)
        # 35 bars with identical volume so volume_sma20 equals volume.
        rows = _baseline_rows(35)
        _seed_klines(db_session, variety, contract, rows=rows)

        result = run_dsl_backtest(
            db_session,
            symbol=variety.symbol,
            period="1d",
            direction="long",
            entry_conditions=[
                {
                    "indicator": "volume",
                    "operator": "greater_than",
                    "indicator2": "volume_sma20",
                    "value": 1.5,
                    "transform": "multiply_value",
                }
            ],
            exit_conditions=_never_exit(),
            limit=50,
        )

        # volume == sma20, so volume > sma20 * 1.5 should never trigger.
        assert result["metrics"]["trade_count"] == 0

    def test_atr_channel_indicator(self, db_session):
        variety, contract = _create_variety_and_contract(db_session)
        # Create a small DataFrame and verify ATR channel values are computed.
        rows = _baseline_rows(30)
        rows.append({"open": 105, "high": 115, "low": 104, "close": 114, "volume": 5000})
        rows.append({"open": 114, "high": 116, "low": 113, "close": 115, "volume": 5000})
        _seed_klines(db_session, variety, contract, rows=rows)

        klines = _get_kline_data(db_session, variety.symbol, period="1d", limit=50)
        df = pd.DataFrame(klines)

        upper = _compute_indicator(df, "atr_upper_14_2")
        lower = _compute_indicator(df, "atr_lower_14_2")
        # ATR channel should be positive and upper > lower once ATR is available.
        valid_upper = upper.dropna()
        valid_lower = lower.dropna()
        assert len(valid_upper) > 0
        assert len(valid_lower) > 0
        assert (valid_upper > valid_lower).all()


class TestStopLossAndTakeProfit:
    """Tests for DSL risk stop_loss / take_profit execution."""

    def test_fixed_stop_loss_long(self, db_session):
        variety, contract = _create_variety_and_contract(db_session)
        rows = _baseline_rows(29)
        rows.append({"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000})
        rows.append({"open": 100.5, "high": 101, "low": 94, "close": 95, "volume": 1000})
        _seed_klines(db_session, variety, contract, rows=rows)

        result = run_dsl_backtest(
            db_session,
            symbol=variety.symbol,
            period="1d",
            direction="long",
            entry_conditions=_always_true_entry(),
            exit_conditions=_never_exit(),
            risk={
                "stop_loss": {"type": "fixed_price", "value": 95},
                "take_profit": {"type": "target_price", "value": 110},
            },
            limit=50,
        )

        assert result["metrics"]["trade_count"] == 1
        trade = result["trades"][0]
        assert trade["exit_price"] == 95.0
        assert trade.get("entry_price") == 100.0

    def test_fixed_take_profit_long(self, db_session):
        variety, contract = _create_variety_and_contract(db_session)
        rows = _baseline_rows(29)
        rows.append({"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000})
        rows.append({"open": 100.5, "high": 106, "low": 100, "close": 105, "volume": 1000})
        _seed_klines(db_session, variety, contract, rows=rows)

        result = run_dsl_backtest(
            db_session,
            symbol=variety.symbol,
            period="1d",
            direction="long",
            entry_conditions=_always_true_entry(),
            exit_conditions=_never_exit(),
            risk={
                "stop_loss": {"type": "fixed_price", "value": 90},
                "take_profit": {"type": "target_price", "value": 105},
            },
            limit=50,
        )

        assert result["metrics"]["trade_count"] == 1
        trade = result["trades"][0]
        assert trade["exit_price"] == 105.0


class TestBetweenOperator:
    """Tests for the between operator."""

    def test_between_condition(self, db_session):
        variety, contract = _create_variety_and_contract(db_session)
        rows = [{"open": 100, "high": 100, "low": 99, "close": 99, "volume": 1000} for _ in range(29)]
        rows.append({"open": 100, "high": 101, "low": 99, "close": 101, "volume": 1000})  # entry signal
        rows.append({"open": 101, "high": 102, "low": 100, "close": 102, "volume": 1000})  # exit signal
        rows.append({"open": 102, "high": 103, "low": 101, "close": 103, "volume": 1000})  # exit execution
        _seed_klines(db_session, variety, contract, rows=rows)

        result = run_dsl_backtest(
            db_session,
            symbol=variety.symbol,
            period="1d",
            direction="long",
            entry_conditions=[{"indicator": "close", "operator": "between", "value": [100, 102]}],
            exit_conditions=[{"indicator": "close", "operator": "greater_than", "value": 101}],
            limit=50,
        )

        assert result["metrics"]["trade_count"] >= 1


class TestScoringEdgeCases:
    """Tests for metrics calculation and scoring."""

    def test_negative_equity_annualized(self):
        """Annualized return should not crash when equity goes negative."""
        from services.backtest.engine import _calculate_metrics

        equity_curve = [
            {"time": "2024-01-01", "equity": 100000.0},
            {"time": "2024-01-02", "equity": -10000.0},
        ]
        metrics = _calculate_metrics(equity_curve, [], 100000.0)
        assert metrics["annualized_return_pct"] == -100.0

    def test_score_with_zero_win_rate(self):
        """Low win rate should not over-penalize the score."""
        from services.backtest.engine import _score_strategy

        score = _score_strategy(
            total_return=20, max_drawdown=10, win_rate=0, profit_factor=1.5, trade_count=10
        )
        # With the old formula this would be heavily penalized; ensure it stays reasonable.
        assert 20 <= score <= 80
