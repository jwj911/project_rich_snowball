"""Backtest orchestration service.

支持两种回测入口：
1. 传统 StrategyIntent（解析自自然语言）
2. StrategyDSL（编译自策略编译器）
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from models import FactorDefinitionDB, VarietyDB
from services.agent.data_tools import _get_kline_data, _get_variety_info
from services.agent.factor_engine.dsl import PanelData, evaluate_factor
from services.backtest.engine import BacktestConfig, _eval_conditions, run_backtest
from services.backtest.futures import (
    FuturesBacktestConfig,
    FuturesContractSpec,
    FuturesOrder,
    run_futures_backtest,
    signals_to_target_lots,
)
from services.backtest.parser import StrategyIntent
from services.cache import get_cached

logger = logging.getLogger(__name__)


def _backtest_cache_key(
    symbol: str,
    period: str,
    direction: str,
    entry_conditions: list[dict[str, Any]],
    exit_conditions: list[dict[str, Any]],
    limit: int,
    start_date: str = "",
    end_date: str = "",
    engine_mode: str = "legacy",
    initial_cash: float | None = None,
    quantity: int | None = None,
    risk: dict[str, Any] | None = None,
) -> str:
    """生成回测缓存 key。"""
    cond_str = json.dumps(
        {
            "entry": entry_conditions,
            "exit": exit_conditions,
            "limit": limit,
            "start_date": start_date,
            "end_date": end_date,
            "engine_mode": engine_mode,
            "initial_cash": initial_cash,
            "quantity": quantity,
            "risk": risk,
        },
        sort_keys=True,
    )
    cond_hash = hashlib.md5(cond_str.encode()).hexdigest()[:12]
    return f"backtest:v2:{symbol}:{period}:{direction}:{cond_hash}"


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
        "start": df["time"].iloc[0].isoformat()
        if hasattr(df["time"].iloc[0], "isoformat")
        else str(df["time"].iloc[0]),
        "end": df["time"].iloc[-1].isoformat()
        if hasattr(df["time"].iloc[-1], "isoformat")
        else str(df["time"].iloc[-1]),
        "bars": len(df),
    }
    return result


def _inject_factor_columns(
    db: Session,
    df: pd.DataFrame,
    symbol: str,
    entry_conditions: list[dict[str, Any]],
    exit_conditions: list[dict[str, Any]],
    custom_columns: dict[str, pd.Series] | None = None,
) -> pd.DataFrame:
    """预计算策略 DSL 中引用的自定义因子列并注入 DataFrame。

    indicator / indicator2 以 factor:<factor_id> 形式出现时，
    从 factor_definitions 读取 source_expression 并在单品种面板上求值。

    indicator / indicator2 以 factor_custom:<hash> 形式出现时，
    从 custom_columns 中直接取值注入。
    """
    # 收集需要注入的列
    custom_keys: set[str] = set()
    factor_ids: set[str] = set()
    for cond in entry_conditions + exit_conditions:
        for key in ("indicator", "indicator2"):
            val = cond.get(key)
            if isinstance(val, str):
                if val.startswith("factor_custom:"):
                    custom_keys.add(val)
                elif val.startswith("factor:"):
                    factor_ids.add(val[len("factor:") :].strip())

    if not factor_ids and not custom_keys:
        return df

    if "time" not in df.columns:
        return df

    df["time"] = pd.to_datetime(df["time"], format="mixed")
    df_indexed = df.set_index("time").copy()

    # 注入 custom_columns
    for ck in custom_keys:
        if custom_columns and ck in custom_columns:
            series = custom_columns[ck]
            if isinstance(series, pd.Series):
                df_indexed[ck] = series.reindex(df_indexed.index)

    # 注入 factor_definitions 因子
    for fid in factor_ids:
        factor = (
            db.query(FactorDefinitionDB)
            .filter(FactorDefinitionDB.factor_id == fid, FactorDefinitionDB.is_active.is_(True))
            .first()
        )
        if not factor:
            logger.warning("回测引用的因子不存在或已禁用：%s", fid)
            continue

        try:
            panel = PanelData(
                open=pd.DataFrame({symbol: df_indexed["open"]}),
                high=pd.DataFrame({symbol: df_indexed["high"]}),
                low=pd.DataFrame({symbol: df_indexed["low"]}),
                close=pd.DataFrame({symbol: df_indexed["close"]}),
                volume=pd.DataFrame({symbol: df_indexed["volume"]}),
            )
            result = evaluate_factor(factor.source_expression, panel)
            series = result[symbol]
            col_name = f"factor:{fid}"
            df_indexed[col_name] = series
        except Exception as exc:
            logger.warning("因子 %s 求值失败：%s", fid, exc)

    return df_indexed.reset_index()


def _run_futures_dsl_backtest(
    *,
    df: pd.DataFrame,
    symbol: str,
    period: str,
    direction: str,
    entry_conditions: list[dict[str, Any]],
    exit_conditions: list[dict[str, Any]],
    initial_cash: float,
    quantity: int,
    variety: VarietyDB | None,
) -> dict[str, Any]:
    """Run DSL signals through the futures broker simulator."""
    entry_signal = _eval_conditions(df, entry_conditions, logic="and")
    exit_signal = _eval_conditions(df, exit_conditions, logic="and")
    target_lots = signals_to_target_lots(entry_signal, exit_signal, direction=direction, quantity=quantity)

    multiplier = float(variety.multiplier) if variety and variety.multiplier else 1.0
    commission = float(variety.commission) if variety and variety.commission else 0.0001
    margin_rate = float(variety.margin_rate) if variety and variety.margin_rate else 0.1
    tick_size = float(variety.tick_size) if variety and variety.tick_size else 1.0

    contract = FuturesContractSpec(
        symbol=symbol,
        multiplier=multiplier,
        tick_size=tick_size,
        margin_rate=margin_rate,
        commission_rate=commission if commission < 0.05 else 0.0001,
    )
    futures_config = FuturesBacktestConfig(initial_cash=initial_cash)
    result = run_futures_backtest(df, target_lots, contract, futures_config).to_dict()
    result["config"] = {
        "symbol": symbol,
        "period": period,
        "strategy_type": "dsl",
        "engine_mode": "futures",
        "initial_cash": initial_cash,
        "quantity": quantity,
        "multiplier": multiplier,
        "fee_rate": contract.commission_rate,
        "direction": direction,
        "margin_rate": margin_rate,
        "tick_size": tick_size,
    }
    result["signals"] = _orders_to_signals(result.get("orders", []))
    return result


def _orders_to_signals(orders: list[dict[str, Any]] | list[FuturesOrder]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for order in orders:
        if isinstance(order, FuturesOrder):
            current = order.target_lots
            previous = order.previous_lots
            payload = {"time": order.time, "price": order.fill_price, "reason": order.reason}
        else:
            current = int(order.get("target_lots", 0))
            previous = int(order.get("previous_lots", 0))
            payload = {"time": order.get("time"), "price": order.get("fill_price"), "reason": order.get("reason")}

        if previous == 0 and current != 0:
            signals.append({**payload, "type": "entry"})
        elif previous != 0 and current == 0:
            signals.append({**payload, "type": "exit"})
        elif previous != 0 and current != 0 and (previous > 0) != (current > 0):
            signals.append({**payload, "type": "flip"})
        else:
            signals.append({**payload, "type": "rebalance"})
    return signals


def _data_window(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "start": df["time"].iloc[0].isoformat()
        if hasattr(df["time"].iloc[0], "isoformat")
        else str(df["time"].iloc[0]),
        "end": df["time"].iloc[-1].isoformat()
        if hasattr(df["time"].iloc[-1], "isoformat")
        else str(df["time"].iloc[-1]),
        "bars": len(df),
    }


def _run_dsl_backtest_inner(
    db: Session,
    symbol: str,
    period: str,
    direction: str,
    entry_conditions: list[dict[str, Any]],
    exit_conditions: list[dict[str, Any]],
    initial_cash: float,
    quantity: int,
    limit: int,
    custom_columns: dict[str, pd.Series] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    risk: dict[str, Any] | None = None,
    engine_mode: str = "legacy",
) -> dict[str, Any]:
    """无缓存版本的 DSL 回测执行（供 get_cached 调用）。"""
    variety_info = _get_variety_info(db, symbol)
    if not variety_info:
        raise ValueError(f"未找到品种 {symbol}")

    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    multiplier = float(variety.multiplier) if variety and variety.multiplier else 1.0
    commission = float(variety.commission) if variety and variety.commission else 0.0001

    klines = _get_kline_data(db, symbol, period=period, limit=limit, start_date=start_date, end_date=end_date)
    if len(klines) < 30:
        raise ValueError(f"{symbol} 可用 K 线不足，至少需要 30 根")

    df = pd.DataFrame(klines)
    df = _inject_factor_columns(db, df, symbol, entry_conditions, exit_conditions, custom_columns=custom_columns)
    df["time"] = pd.to_datetime(df["time"], format="mixed")

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

    if engine_mode == "futures":
        result = _run_futures_dsl_backtest(
            df=df,
            symbol=symbol,
            period=period,
            direction=direction,
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            initial_cash=initial_cash,
            quantity=quantity,
            variety=variety,
        )
        result["variety"] = variety_info
        result["data_window"] = _data_window(df)
        return result

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
        stop_loss=risk.get("stop_loss") if risk else None,
        take_profit=risk.get("take_profit") if risk else None,
    )
    result = run_backtest(df, config, entry_conditions=entry_conditions, exit_conditions=exit_conditions).to_dict()
    result["variety"] = variety_info
    result["data_window"] = _data_window(df)
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
    custom_columns: dict[str, pd.Series] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    risk: dict[str, Any] | None = None,
    engine_mode: str = "legacy",
) -> dict[str, Any]:
    """根据 DSL 条件执行回测（带 5 分钟 LRU 缓存）。

    Args:
        start_date: 可选，K 线起始日期（含），用于 OOS 验证。
        end_date: 可选，K 线结束日期（含），用于 OOS 验证。
    """
    start_str = start_date.isoformat() if start_date else ""
    end_str = end_date.isoformat() if end_date else ""
    cache_key = _backtest_cache_key(
        symbol,
        period,
        direction,
        entry_conditions,
        exit_conditions,
        limit,
        start_date=start_str,
        end_date=end_str,
        engine_mode=engine_mode,
        initial_cash=initial_cash,
        quantity=quantity,
        risk=risk,
    )
    result = get_cached(
        cache_key,
        lambda: _run_dsl_backtest_inner(
            db,
            symbol,
            period,
            direction,
            entry_conditions,
            exit_conditions,
            initial_cash,
            quantity,
            limit,
            custom_columns=custom_columns,
            start_date=start_date,
            end_date=end_date,
            risk=risk,
            engine_mode=engine_mode,
        ),
        ttl=300,  # 5 分钟缓存
    )
    logger.info(
        "dsl_backtest_complete",
        extra={
            "symbol": symbol,
            "period": period,
            "direction": direction,
            "engine_mode": engine_mode,
            "cache_key": cache_key,
            "bars": result.get("data_window", {}).get("bars"),
            "trade_count": result.get("metrics", {}).get("trade_count"),
            "score": result.get("metrics", {}).get("score"),
        },
    )
    return result
