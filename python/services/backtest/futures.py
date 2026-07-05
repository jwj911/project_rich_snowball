"""Futures-specific backtesting primitives.

This module is intentionally independent from the existing single-position
engine. It focuses on futures account semantics: signed lots, contract
multiplier, margin, slippage, commissions, position flips, and mark-to-market
equity.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from math import floor
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("time", "open", "high", "low", "close")


@dataclass(slots=True)
class FuturesContractSpec:
    """Contract-level settings used by the broker simulator."""

    symbol: str
    multiplier: float = 1.0
    tick_size: float = 1.0
    margin_rate: float = 0.1
    commission_rate: float = 0.0001
    commission_per_lot: float = 0.0
    slippage_ticks: float = 0.0


@dataclass(slots=True)
class FuturesBacktestConfig:
    """Execution and account settings for futures backtests."""

    initial_cash: float = 100_000.0
    signal_lag_bars: int = 1
    maintenance_margin_ratio: float = 0.75
    allow_short: bool = True
    clamp_to_margin: bool = True


@dataclass(slots=True)
class FuturesOrder:
    time: str
    previous_lots: int
    target_lots: int
    traded_lots: int
    fill_price: float
    fee: float
    reason: str = "rebalance"


@dataclass(slots=True)
class FuturesTrade:
    entry_time: str
    exit_time: str
    direction: str
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    fee: float
    return_pct: float
    reason: str = "signal"


@dataclass(slots=True)
class FuturesAccountSnapshot:
    time: str
    close: float
    cash: float
    equity: float
    margin: float
    available_cash: float
    position_lots: int
    avg_price: float | None
    realized_pnl: float
    unrealized_pnl: float
    fee: float


@dataclass(slots=True)
class FuturesBacktestResult:
    contract: FuturesContractSpec
    config: FuturesBacktestConfig
    metrics: dict[str, float | int]
    orders: list[FuturesOrder] = field(default_factory=list)
    trades: list[FuturesTrade] = field(default_factory=list)
    equity_curve: list[FuturesAccountSnapshot] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": asdict(self.contract),
            "config": asdict(self.config),
            "metrics": self.metrics,
            "orders": [asdict(order) for order in self.orders],
            "trades": [asdict(trade) for trade in self.trades],
            "equity_curve": [asdict(point) for point in self.equity_curve],
        }


@dataclass(slots=True)
class _PositionState:
    lots: int = 0
    avg_price: float = 0.0
    entry_time: str | None = None


def run_futures_backtest(
    df: pd.DataFrame,
    target_lots: Sequence[int | float] | pd.Series,
    contract: FuturesContractSpec,
    config: FuturesBacktestConfig | None = None,
) -> FuturesBacktestResult:
    """Run a futures backtest from signed target lots.

    Args:
        df: OHLCV bars. Required columns: time/open/high/low/close.
        target_lots: Desired signed lots per signal bar. Positive is long,
            negative is short, and zero is flat. The target generated at bar N
            is executed at bar N + signal_lag_bars using that bar's open.
        contract: Contract specification.
        config: Account and execution settings.
    """
    config = config or FuturesBacktestConfig()
    data = _prepare_bars(df)
    targets = _prepare_targets(target_lots, len(data))

    cash = float(config.initial_cash)
    position = _PositionState()
    orders: list[FuturesOrder] = []
    trades: list[FuturesTrade] = []
    curve: list[FuturesAccountSnapshot] = []
    total_realized_pnl = 0.0
    total_fee = 0.0

    for i, row in data.iterrows():
        time_value = str(row["time"])
        open_price = float(row["open"])
        close_price = float(row["close"])
        bar_fee = 0.0
        bar_realized = 0.0

        signal_idx = i - max(config.signal_lag_bars, 0)
        if signal_idx >= 0:
            desired_lots = int(targets.iloc[signal_idx])
            if desired_lots < 0 and not config.allow_short:
                desired_lots = 0
            desired_lots = _fit_target_to_margin(cash, position, desired_lots, open_price, contract, config)

            if desired_lots != position.lots:
                fill_price = _apply_slippage(open_price, desired_lots - position.lots, contract)
                outcome = _rebalance_position(
                    position=position,
                    target_lots=desired_lots,
                    fill_price=fill_price,
                    time_value=time_value,
                    contract=contract,
                )
                cash += outcome["realized_pnl"] - outcome["fee"]
                bar_fee += outcome["fee"]
                bar_realized += outcome["realized_pnl"]
                total_fee += outcome["fee"]
                total_realized_pnl += outcome["realized_pnl"]
                orders.append(
                    FuturesOrder(
                        time=time_value,
                        previous_lots=outcome["previous_lots"],
                        target_lots=desired_lots,
                        traded_lots=abs(desired_lots - outcome["previous_lots"]),
                        fill_price=round(fill_price, 6),
                        fee=round(outcome["fee"], 6),
                    )
                )
                trades.extend(outcome["trades"])

        unrealized = _unrealized_pnl(position, close_price, contract)
        margin = _required_margin(position.lots, close_price, contract)
        equity = cash + unrealized

        if position.lots and margin > 0 and equity <= margin * config.maintenance_margin_ratio:
            fill_price = _apply_slippage(close_price, -position.lots, contract)
            outcome = _rebalance_position(
                position=position,
                target_lots=0,
                fill_price=fill_price,
                time_value=time_value,
                contract=contract,
                reason="margin_call",
            )
            cash += outcome["realized_pnl"] - outcome["fee"]
            bar_fee += outcome["fee"]
            bar_realized += outcome["realized_pnl"]
            total_fee += outcome["fee"]
            total_realized_pnl += outcome["realized_pnl"]
            orders.append(
                FuturesOrder(
                    time=time_value,
                    previous_lots=outcome["previous_lots"],
                    target_lots=0,
                    traded_lots=abs(outcome["previous_lots"]),
                    fill_price=round(fill_price, 6),
                    fee=round(outcome["fee"], 6),
                    reason="margin_call",
                )
            )
            trades.extend(outcome["trades"])
            unrealized = 0.0
            margin = 0.0
            equity = cash

        curve.append(
            FuturesAccountSnapshot(
                time=time_value,
                close=round(close_price, 6),
                cash=round(cash, 6),
                equity=round(equity, 6),
                margin=round(margin, 6),
                available_cash=round(equity - margin, 6),
                position_lots=position.lots,
                avg_price=round(position.avg_price, 6) if position.lots else None,
                realized_pnl=round(bar_realized, 6),
                unrealized_pnl=round(unrealized, 6),
                fee=round(bar_fee, 6),
            )
        )

    metrics = _calculate_futures_metrics(curve, trades, total_fee, total_realized_pnl, config.initial_cash)
    return FuturesBacktestResult(
        contract=contract, config=config, metrics=metrics, orders=orders, trades=trades, equity_curve=curve
    )


def signals_to_target_lots(
    entry_signal: pd.Series | Sequence[bool],
    exit_signal: pd.Series | Sequence[bool],
    *,
    direction: str = "long",
    quantity: int = 1,
) -> pd.Series:
    """Convert entry/exit boolean signals to signed target lots."""
    entry = pd.Series(entry_signal).fillna(False).astype(bool)
    exit_ = pd.Series(exit_signal).fillna(False).astype(bool)
    if len(entry) != len(exit_):
        raise ValueError("entry_signal and exit_signal must have the same length")

    signed_quantity = -abs(int(quantity)) if direction == "short" else abs(int(quantity))
    current = 0
    targets: list[int] = []
    for enter, leave in zip(entry, exit_, strict=False):
        if current == 0 and enter:
            current = signed_quantity
        elif current != 0 and leave:
            current = 0
        targets.append(current)
    return pd.Series(targets, index=entry.index)


def _prepare_bars(df: pd.DataFrame) -> pd.DataFrame:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")
    if len(df) < 2:
        raise ValueError("at least two bars are required")
    data = df.loc[:, [*REQUIRED_COLUMNS]].copy()
    data["time"] = pd.to_datetime(data["time"], format="mixed")
    data.sort_values("time", inplace=True)
    data.reset_index(drop=True, inplace=True)
    for col in ("open", "high", "low", "close"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    if data[["open", "high", "low", "close"]].isna().any().any():
        raise ValueError("OHLC columns cannot contain NaN values")
    return data


def _prepare_targets(target_lots: Sequence[int | float] | pd.Series, length: int) -> pd.Series:
    targets = pd.Series(target_lots).fillna(0)
    if len(targets) != length:
        raise ValueError(f"target_lots length {len(targets)} does not match bar length {length}")
    return targets.astype(int).reset_index(drop=True)


def _fit_target_to_margin(
    cash: float,
    position: _PositionState,
    target_lots: int,
    price: float,
    contract: FuturesContractSpec,
    config: FuturesBacktestConfig,
) -> int:
    if not config.clamp_to_margin or contract.margin_rate <= 0:
        return target_lots
    equity = cash + _unrealized_pnl(position, price, contract)
    margin_per_lot = abs(price) * contract.multiplier * contract.margin_rate
    if margin_per_lot <= 0:
        return target_lots
    max_lots = max(0, floor(equity / margin_per_lot))
    if abs(target_lots) <= max_lots:
        return target_lots
    return int(np.sign(target_lots) * max_lots)


def _apply_slippage(price: float, delta_lots: int, contract: FuturesContractSpec) -> float:
    if delta_lots == 0 or contract.slippage_ticks == 0:
        return price
    direction = 1 if delta_lots > 0 else -1
    return price + direction * contract.slippage_ticks * contract.tick_size


def _rebalance_position(
    *,
    position: _PositionState,
    target_lots: int,
    fill_price: float,
    time_value: str,
    contract: FuturesContractSpec,
    reason: str = "signal",
) -> dict[str, Any]:
    previous_lots = position.lots
    delta_lots = target_lots - previous_lots
    traded_lots = abs(delta_lots)
    fee = _commission(fill_price, traded_lots, contract)
    realized_pnl = 0.0
    closed_trades: list[FuturesTrade] = []

    if previous_lots == 0:
        position.lots = target_lots
        position.avg_price = fill_price if target_lots else 0.0
        position.entry_time = time_value if target_lots else None
        return {"previous_lots": previous_lots, "realized_pnl": realized_pnl, "fee": fee, "trades": closed_trades}

    previous_sign = int(np.sign(previous_lots))
    target_sign = int(np.sign(target_lots))

    if target_lots == 0 or previous_sign != target_sign:
        closed_lots = abs(previous_lots)
        close_pnl = _closed_pnl(previous_lots, position.avg_price, fill_price, contract)
        close_fee = fee * (closed_lots / traded_lots) if traded_lots else 0.0
        closed_trades.append(
            _make_trade(position, time_value, fill_price, closed_lots, close_pnl, close_fee, contract, reason)
        )
        realized_pnl += close_pnl
        position.lots = 0
        position.avg_price = 0.0
        position.entry_time = None

        if target_lots != 0:
            position.lots = target_lots
            position.avg_price = fill_price
            position.entry_time = time_value
        return {"previous_lots": previous_lots, "realized_pnl": realized_pnl, "fee": fee, "trades": closed_trades}

    if abs(target_lots) < abs(previous_lots):
        closed_lots = abs(previous_lots) - abs(target_lots)
        signed_closed = previous_sign * closed_lots
        close_pnl = _closed_pnl(signed_closed, position.avg_price, fill_price, contract)
        close_fee = fee
        closed_trades.append(
            _make_trade(position, time_value, fill_price, closed_lots, close_pnl, close_fee, contract, reason)
        )
        realized_pnl += close_pnl
        position.lots = target_lots
        if target_lots == 0:
            position.avg_price = 0.0
            position.entry_time = None
        return {"previous_lots": previous_lots, "realized_pnl": realized_pnl, "fee": fee, "trades": closed_trades}

    if abs(target_lots) > abs(previous_lots):
        added_lots = abs(target_lots) - abs(previous_lots)
        current_abs = abs(previous_lots)
        position.avg_price = (position.avg_price * current_abs + fill_price * added_lots) / (current_abs + added_lots)
        position.lots = target_lots

    return {"previous_lots": previous_lots, "realized_pnl": realized_pnl, "fee": fee, "trades": closed_trades}


def _commission(price: float, lots: int, contract: FuturesContractSpec) -> float:
    turnover = abs(price) * abs(lots) * contract.multiplier
    return turnover * contract.commission_rate + abs(lots) * contract.commission_per_lot


def _closed_pnl(lots: int, entry_price: float, exit_price: float, contract: FuturesContractSpec) -> float:
    if lots < 0:
        return (entry_price - exit_price) * abs(lots) * contract.multiplier
    return (exit_price - entry_price) * abs(lots) * contract.multiplier


def _unrealized_pnl(position: _PositionState, price: float, contract: FuturesContractSpec) -> float:
    if position.lots == 0:
        return 0.0
    return _closed_pnl(position.lots, position.avg_price, price, contract)


def _required_margin(lots: int, price: float, contract: FuturesContractSpec) -> float:
    return abs(lots) * abs(price) * contract.multiplier * max(contract.margin_rate, 0.0)


def _make_trade(
    position: _PositionState,
    exit_time: str,
    exit_price: float,
    quantity: int,
    pnl: float,
    fee: float,
    contract: FuturesContractSpec,
    reason: str,
) -> FuturesTrade:
    base = abs(position.avg_price) * quantity * contract.multiplier
    direction = "short" if position.lots < 0 else "long"
    return FuturesTrade(
        entry_time=position.entry_time or exit_time,
        exit_time=exit_time,
        direction=direction,
        entry_price=round(position.avg_price, 6),
        exit_price=round(exit_price, 6),
        quantity=quantity,
        pnl=round(pnl - fee, 6),
        fee=round(fee, 6),
        return_pct=round((pnl - fee) / base * 100, 6) if base else 0.0,
        reason=reason,
    )


def _calculate_futures_metrics(
    curve: list[FuturesAccountSnapshot],
    trades: list[FuturesTrade],
    total_fee: float,
    total_realized_pnl: float,
    initial_cash: float,
) -> dict[str, float | int]:
    if not curve:
        return {
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe": 0.0,
            "trade_count": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "total_fee": 0.0,
            "total_realized_pnl": 0.0,
        }

    equity = np.array([point.equity for point in curve], dtype=float)
    returns = pd.Series(equity).pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    rolling_peak = np.maximum.accumulate(equity)
    drawdown = equity / np.where(rolling_peak == 0, np.nan, rolling_peak) - 1
    wins = [trade.pnl for trade in trades if trade.pnl > 0]
    losses = [trade.pnl for trade in trades if trade.pnl < 0]
    profit_factor = sum(wins) / abs(sum(losses)) if losses else (float(len(wins)) if wins else 0.0)
    sharpe = (returns.mean() / (returns.std(ddof=0) + 1e-12)) * np.sqrt(252) if not returns.empty else 0.0

    return {
        "total_return_pct": round((equity[-1] / initial_cash - 1) * 100, 4) if initial_cash else 0.0,
        "max_drawdown_pct": round(abs(float(np.nanmin(drawdown))) * 100, 4) if len(drawdown) else 0.0,
        "sharpe": round(float(sharpe), 4),
        "trade_count": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 4) if trades else 0.0,
        "profit_factor": round(float(profit_factor), 4),
        "total_fee": round(float(total_fee), 6),
        "total_realized_pnl": round(float(total_realized_pnl), 6),
        "final_equity": round(float(equity[-1]), 6),
    }
