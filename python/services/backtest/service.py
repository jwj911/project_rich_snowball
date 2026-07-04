"""Backtest orchestration service.

支持两种回测入口：
1. 传统 StrategyIntent（解析自自然语言）
2. StrategyDSL（编译自策略编译器）
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from models import VarietyDB
from services.agent.data_tools import _get_kline_data, _get_variety_info
from services.backtest.engine import BacktestConfig, run_backtest
from services.backtest.parser import StrategyIntent


def _prepare_dataframe(db: Session, intent: StrategyIntent) -> tuple[pd.DataFrame, dict[str, Any], VarietyDB | None]:
    """加载 K 线数据并返回 DataFrame + 品种信息。"""
    variety_info = _get_variety_info(db, intent.symbol)
    if not variety_info:
        raise ValueError(f"未找到品种 {intent.symbol}")

    variety = db.query(VarietyDB).filter(VarietyDB.symbol == intent.symbol).first()

    klines = _get_kline_data(db, intent.symbol, period=intent.period, limit=intent.limit)
    if len(klines) < max(intent.long_window + 2, 30):
        raise ValueError(f"{intent.symbol} 可用 K 线不足，至少需要 {max(intent.long_window + 2, 30)} 根")

    df = pd.DataFrame(klines)
    df["time"] = pd.to_datetime(df["time"], format="mixed")
    return df, variety_info, variety


def run_strategy_backtest(db: Session, intent: StrategyIntent) -> dict[str, Any]:
    """Load market data and run a parsed strategy backtest."""
    df, variety_info, variety = _prepare_dataframe(db, intent)

    multiplier = float(variety.multiplier) if variety and variety.multiplier else 1.0
    commission = float(variety.commission) if variety and variety.commission else 0.0001

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
        "start": df["time"].iloc[0].isoformat() if hasattr(df["time"].iloc[0], "isoformat") else str(df["time"].iloc[0]),
        "end": df["time"].iloc[-1].isoformat() if hasattr(df["time"].iloc[-1], "isoformat") else str(df["time"].iloc[-1]),
        "bars": len(df),
    }
    return result


def run_dsl_backtest(
    db: Session,
    symbol: str,
    period: str,
    direction: str,
    entry_conditions: list[dict[str, Any]],
    exit_conditions: list[dict[str, Any]],
    initial_cash: float = 100_000.0,
    quantity: int = 1,
    limit: int = 500,
) -> dict[str, Any]:
    """根据 DSL 条件执行回测。"""
    variety_info = _get_variety_info(db, symbol)
    if not variety_info:
        raise ValueError(f"未找到品种 {symbol}")

    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    multiplier = float(variety.multiplier) if variety and variety.multiplier else 1.0
    commission = float(variety.commission) if variety and variety.commission else 0.0001

    klines = _get_kline_data(db, symbol, period=period, limit=limit)
    if len(klines) < 30:
        raise ValueError(f"{symbol} 可用 K 线不足，至少需要 30 根")

    df = pd.DataFrame(klines)
    df["time"] = pd.to_datetime(df["time"], format="mixed")

    # 从 entry conditions 推断窗口
    short_window = 5
    long_window = 20
    for cond in entry_conditions:
        ind = cond.get("indicator", "")
        ind2 = cond.get("indicator2", "")
        import re
        m1 = re.search(r"(\d+)", ind)
        m2 = re.search(r"(\d+)", ind2)
        if m1 and m2:
            v1 = int(m1.group(1))
            v2 = int(m2.group(1))
            short_window = min(v1, v2)
            long_window = max(v1, v2)
            break

    config = BacktestConfig(
        symbol=symbol,
        period=period,
        strategy_type="dsl",
        short_window=short_window,
        long_window=long_window,
        initial_cash=initial_cash,
        quantity=quantity,
        multiplier=multiplier,
        fee_rate=commission if commission < 0.05 else 0.0001,
        direction=direction,
    )
    result = run_backtest(df, config, entry_conditions=entry_conditions, exit_conditions=exit_conditions).to_dict()
    result["variety"] = variety_info
    result["data_window"] = {
        "start": df["time"].iloc[0].isoformat() if hasattr(df["time"].iloc[0], "isoformat") else str(df["time"].iloc[0]),
        "end": df["time"].iloc[-1].isoformat() if hasattr(df["time"].iloc[-1], "isoformat") else str(df["time"].iloc[-1]),
        "bars": len(df),
    }
    return result
