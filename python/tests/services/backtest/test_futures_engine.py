"""Futures broker simulator tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from services.backtest.futures import (
    FuturesBacktestConfig,
    FuturesContractSpec,
    run_futures_backtest,
    signals_to_target_lots,
)


def _bars(prices: list[float]) -> pd.DataFrame:
    start = datetime(2026, 1, 1, 9, 0, 0)
    rows = []
    for i, price in enumerate(prices):
        rows.append(
            {
                "time": start + timedelta(days=i),
                "open": price,
                "high": price + 2,
                "low": price - 2,
                "close": price + 1,
            }
        )
    return pd.DataFrame(rows)


def test_long_trade_uses_multiplier_and_next_bar_open_execution():
    df = _bars([100, 101, 105, 110, 111])
    targets = [1, 1, 0, 0, 0]
    contract = FuturesContractSpec(symbol="RB", multiplier=10, margin_rate=0.1, commission_rate=0)

    result = run_futures_backtest(df, targets, contract)

    assert len(result.orders) == 2
    assert result.orders[0].fill_price == 101
    assert result.orders[1].fill_price == 110
    assert result.trades[0].pnl == 90
    assert result.metrics["final_equity"] == 100090


def test_short_trade_can_profit_when_price_falls():
    df = _bars([100, 99, 94, 90, 89])
    targets = [-2, -2, 0, 0, 0]
    contract = FuturesContractSpec(symbol="CU", multiplier=5, margin_rate=0.1, commission_rate=0)

    result = run_futures_backtest(df, targets, contract)

    assert result.trades[0].direction == "short"
    assert result.trades[0].pnl == 90
    assert result.metrics["win_rate_pct"] == 100


def test_target_lots_are_clamped_by_margin_capacity():
    df = _bars([100, 101, 102])
    targets = [100, 100, 100]
    contract = FuturesContractSpec(symbol="AU", multiplier=100, margin_rate=0.2, commission_rate=0)
    config = FuturesBacktestConfig(initial_cash=10_000)

    result = run_futures_backtest(df, targets, contract, config)

    assert result.orders[0].target_lots == 4
    assert result.equity_curve[0].position_lots == 0
    assert result.equity_curve[1].position_lots == 4


def test_slippage_moves_fill_against_order_direction():
    df = _bars([100, 100, 105, 105])
    targets = [1, 0, 0, 0]
    contract = FuturesContractSpec(symbol="IF", multiplier=1, tick_size=0.2, slippage_ticks=2, commission_rate=0)

    result = run_futures_backtest(df, targets, contract)

    assert result.orders[0].fill_price == 100.4
    assert result.orders[1].fill_price == 104.6
    assert result.trades[0].pnl == 4.2


def test_signals_to_target_lots_builds_signed_position_series():
    targets = signals_to_target_lots(
        entry_signal=[False, True, False, False, True],
        exit_signal=[False, False, False, True, False],
        direction="short",
        quantity=3,
    )

    assert targets.tolist() == [0, -3, -3, 0, -3]
