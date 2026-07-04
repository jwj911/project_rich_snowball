"""Backtest orchestration service."""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from models import VarietyDB
from services.agent.data_tools import _get_kline_data, _get_variety_info
from services.backtest.engine import BacktestConfig, run_backtest
from services.backtest.parser import StrategyIntent


def run_strategy_backtest(db: Session, intent: StrategyIntent) -> dict[str, Any]:
    """Load market data and run a parsed strategy backtest."""
    variety_info = _get_variety_info(db, intent.symbol)
    if not variety_info:
        raise ValueError(f"未找到品种 {intent.symbol}")

    variety = db.query(VarietyDB).filter(VarietyDB.symbol == intent.symbol).first()
    multiplier = float(variety.multiplier) if variety and variety.multiplier else 1.0
    commission = float(variety.commission) if variety and variety.commission else 0.0001

    klines = _get_kline_data(db, intent.symbol, period=intent.period, limit=intent.limit)
    if len(klines) < max(intent.long_window + 2, 30):
        raise ValueError(f"{intent.symbol} 可用 K 线不足，至少需要 {max(intent.long_window + 2, 30)} 根")

    df = pd.DataFrame(klines)
    df["time"] = pd.to_datetime(df["time"], format="mixed")

    config = BacktestConfig(
        symbol=intent.symbol,
        period=intent.period,
        strategy_type=intent.strategy_type,
        short_window=intent.short_window,
        long_window=intent.long_window,
        initial_cash=intent.initial_cash,
        quantity=intent.quantity,
        multiplier=multiplier,
        fee_rate=commission if commission < 0.05 else 0.0001,
        direction=intent.direction,
    )
    result = run_backtest(df, config).to_dict()
    result["variety"] = variety_info
    result["data_window"] = {
        "start": klines[0]["time"],
        "end": klines[-1]["time"],
        "bars": len(klines),
    }
    return result
