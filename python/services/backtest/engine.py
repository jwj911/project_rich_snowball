"""Vector-friendly backtesting engine for simple futures strategies."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass(slots=True)
class BacktestConfig:
    symbol: str
    period: str = "1d"
    strategy_type: str = "ma_cross"
    short_window: int = 5
    long_window: int = 20
    initial_cash: float = 100_000.0
    quantity: int = 1
    multiplier: float = 1.0
    fee_rate: float = 0.0001
    direction: str = "long"


@dataclass(slots=True)
class BacktestTrade:
    entry_time: str
    exit_time: str
    direction: str
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    return_pct: float


@dataclass(slots=True)
class BacktestResult:
    config: BacktestConfig
    metrics: dict[str, float | int]
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    signals: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": {
                "symbol": self.config.symbol,
                "period": self.config.period,
                "strategy_type": self.config.strategy_type,
                "short_window": self.config.short_window,
                "long_window": self.config.long_window,
                "initial_cash": self.config.initial_cash,
                "quantity": self.config.quantity,
                "multiplier": self.config.multiplier,
                "fee_rate": self.config.fee_rate,
                "direction": self.config.direction,
            },
            "metrics": self.metrics,
            "trades": [asdict(trade) for trade in self.trades],
            "equity_curve": self.equity_curve,
            "signals": self.signals,
        }


def run_backtest(df: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
    """Run a single-position backtest.

    Signals are generated at close and executed at the next bar open to avoid
    look-ahead bias. This keeps the engine predictable for agent-generated
    strategy templates.
    """
    if len(df) < max(config.long_window + 2, 30):
        raise ValueError("K 线数据不足，无法完成回测")

    data = df.sort_values("time").reset_index(drop=True).copy()
    data["short_ma"] = data["close"].rolling(config.short_window, min_periods=config.short_window).mean()
    data["long_ma"] = data["close"].rolling(config.long_window, min_periods=config.long_window).mean()
    data["prev_short_ma"] = data["short_ma"].shift(1)
    data["prev_long_ma"] = data["long_ma"].shift(1)

    if config.strategy_type == "ma_cross":
        long_entry = (data["prev_short_ma"] <= data["prev_long_ma"]) & (data["short_ma"] > data["long_ma"])
        long_exit = (data["prev_short_ma"] >= data["prev_long_ma"]) & (data["short_ma"] < data["long_ma"])
    else:
        long_entry = data["short_ma"] > data["long_ma"]
        long_exit = data["short_ma"] < data["long_ma"]

    if config.direction == "short":
        entry_signal = long_exit
        exit_signal = long_entry
    else:
        entry_signal = long_entry
        exit_signal = long_exit

    cash = float(config.initial_cash)
    position_entry_price: float | None = None
    position_entry_time: str | None = None
    trades: list[BacktestTrade] = []
    equity_curve: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []

    for i in range(1, len(data)):
        row = data.iloc[i]
        signal_row = data.iloc[i - 1]
        execution_price = float(row["open"])
        current_close = float(row["close"])
        time_value = str(row["time"])

        if position_entry_price is None and bool(entry_signal.iloc[i - 1]):
            position_entry_price = execution_price
            position_entry_time = time_value
            signals.append({"time": time_value, "type": "entry", "price": execution_price})
        elif position_entry_price is not None and bool(exit_signal.iloc[i - 1]):
            gross = _position_pnl(
                config.direction,
                position_entry_price,
                execution_price,
                config.quantity,
                config.multiplier,
            )
            fee = (position_entry_price + execution_price) * config.quantity * config.multiplier * config.fee_rate
            pnl = gross - fee
            cash += pnl
            base = position_entry_price * config.quantity * config.multiplier
            trades.append(
                BacktestTrade(
                    entry_time=position_entry_time or time_value,
                    exit_time=time_value,
                    direction=config.direction,
                    entry_price=round(position_entry_price, 4),
                    exit_price=round(execution_price, 4),
                    quantity=config.quantity,
                    pnl=round(pnl, 4),
                    return_pct=round(pnl / base * 100, 4) if base else 0.0,
                )
            )
            signals.append({"time": time_value, "type": "exit", "price": execution_price})
            position_entry_price = None
            position_entry_time = None

        unrealized = 0.0
        if position_entry_price is not None:
            unrealized = _position_pnl(
                config.direction,
                position_entry_price,
                current_close,
                config.quantity,
                config.multiplier,
            )
        equity_curve.append({
            "time": time_value,
            "equity": round(cash + unrealized, 4),
            "close": current_close,
            "short_ma": _safe_round(signal_row.get("short_ma")),
            "long_ma": _safe_round(signal_row.get("long_ma")),
        })

    metrics = _calculate_metrics(equity_curve, trades, config.initial_cash)
    return BacktestResult(config=config, metrics=metrics, trades=trades, equity_curve=equity_curve, signals=signals)


def _position_pnl(direction: str, entry: float, exit_price: float, quantity: int, multiplier: float) -> float:
    if direction == "short":
        return (entry - exit_price) * quantity * multiplier
    return (exit_price - entry) * quantity * multiplier


def _calculate_metrics(
    equity_curve: list[dict[str, Any]],
    trades: list[BacktestTrade],
    initial_cash: float,
) -> dict[str, float | int]:
    if not equity_curve:
        return {
            "total_return_pct": 0.0,
            "annualized_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "sharpe": 0.0,
            "trade_count": 0,
            "score": 0,
        }

    equity = np.array([point["equity"] for point in equity_curve], dtype=float)
    total_return = (equity[-1] / initial_cash - 1) * 100
    returns = pd.Series(equity).pct_change().dropna()
    periods = max(len(equity), 1)
    annualized = ((equity[-1] / initial_cash) ** (252 / periods) - 1) * 100 if equity[-1] > 0 else -100.0
    rolling_peak = np.maximum.accumulate(equity)
    drawdown = (equity / rolling_peak - 1) * 100
    max_drawdown = abs(float(drawdown.min())) if len(drawdown) else 0.0
    wins = [trade.pnl for trade in trades if trade.pnl > 0]
    losses = [trade.pnl for trade in trades if trade.pnl < 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    profit_factor = sum(wins) / abs(sum(losses)) if losses else (float(len(wins)) if wins else 0.0)
    sharpe = (returns.mean() / (returns.std(ddof=0) + 1e-12)) * np.sqrt(252) if not returns.empty else 0.0
    score = _score_strategy(total_return, max_drawdown, win_rate, profit_factor, len(trades))

    return {
        "total_return_pct": round(float(total_return), 2),
        "annualized_return_pct": round(float(annualized), 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "win_rate_pct": round(float(win_rate), 2),
        "profit_factor": round(float(profit_factor), 2),
        "sharpe": round(float(sharpe), 2),
        "trade_count": len(trades),
        "score": score,
    }


def _score_strategy(
    total_return: float,
    max_drawdown: float,
    win_rate: float,
    profit_factor: float,
    trade_count: int,
) -> int:
    score = 50
    score += min(max(total_return, -30), 50) * 0.5
    score -= min(max_drawdown, 40) * 0.7
    score += (win_rate - 50) * 0.2
    score += min(profit_factor, 3) * 5
    if trade_count < 3:
        score -= 15
    return int(max(0, min(100, round(score))))


def _safe_round(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 4)
