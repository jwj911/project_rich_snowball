"""Vector-friendly backtesting engine for simple futures strategies."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


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


def run_backtest(
    df: pd.DataFrame,
    config: BacktestConfig,
    entry_conditions: list[dict[str, Any]] | None = None,
    exit_conditions: list[dict[str, Any]] | None = None,
) -> BacktestResult:
    """Run a single-position backtest.

    Supports both legacy strategy_type (ma_cross) and generic DSL conditions.
    Signals are generated at close and executed at the next bar open.
    """
    required_bars = max(config.long_window + 2, 30) if config.strategy_type == "ma_cross" else 30
    if len(df) < required_bars:
        raise ValueError(f"K 线数据不足，无法完成回测，至少需要 {required_bars} 根")

    data = df.sort_values("time").reset_index(drop=True).copy()

    # 计算信号
    if entry_conditions and exit_conditions:
        entry_signal = _eval_conditions(data, entry_conditions, logic="and")
        exit_signal = _eval_conditions(data, exit_conditions, logic="and")
    else:
        # Legacy MA cross logic
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

        entry_signal = long_exit if config.direction == "short" else long_entry
        exit_signal = long_entry if config.direction == "short" else long_exit

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
        equity_point: dict[str, Any] = {
            "time": time_value,
            "equity": round(cash + unrealized, 4),
            "close": current_close,
        }
        for col in ("short_ma", "long_ma"):
            if col in data.columns:
                equity_point[col] = _safe_round(signal_row.get(col))
        equity_curve.append(equity_point)

    metrics = _calculate_metrics(equity_curve, trades, config.initial_cash)
    return BacktestResult(config=config, metrics=metrics, trades=trades, equity_curve=equity_curve, signals=signals)


def _eval_conditions(data: pd.DataFrame, conditions: list[dict[str, Any]], logic: str = "and") -> pd.Series:
    """根据 DSL 条件列表生成布尔信号序列。

    每个条件可包含 cross_above/cross_below/above/below/greater_than/less_than 等操作符。
    信号在条件满足的 bar 的 close 处产生，下一 bar 的 open 执行。
    """
    if not conditions:
        return pd.Series(False, index=data.index)

    results: list[pd.Series] = []
    for cond in conditions:
        indicator = cond.get("indicator", "")
        operator = cond.get("operator", "")
        indicator2 = cond.get("indicator2", "")
        value = cond.get("value")

        col1 = _compute_indicator(data, indicator)
        prev_col1 = col1.shift(1)

        if indicator2:
            col2 = _compute_indicator(data, indicator2)
            prev_col2 = col2.shift(1)
        elif value is not None:
            col2 = pd.Series(float(value), index=data.index)
            prev_col2 = col2
        else:
            col2 = pd.Series(0, index=data.index)
            prev_col2 = col2

        if operator == "cross_above":
            signal = (prev_col1 <= prev_col2) & (col1 > col2)
        elif operator == "cross_below":
            signal = (prev_col1 >= prev_col2) & (col1 < col2)
        elif operator == "above":
            signal = col1 > col2
        elif operator == "below":
            signal = col1 < col2
        elif operator == "greater_than":
            signal = col1 > col2
        elif operator == "less_than":
            signal = col1 < col2
        elif operator == "equal":
            signal = (col1 - col2).abs() < 1e-9
        elif operator == "between":
            # between 需要 value 和 indicator2 同时提供，这里简化处理
            signal = (col1 > col2) & (col1 < col2.shift(1))  # 不太常见，先占位
            logger.warning("between 操作符在回测中简化处理")
        else:
            signal = pd.Series(False, index=data.index)

        results.append(signal.fillna(False))

    if logic == "or":
        combined = pd.Series(False, index=data.index)
        for r in results:
            combined = combined | r
        return combined
    # default: and
    combined = pd.Series(True, index=data.index)
    for r in results:
        combined = combined & r
    return combined


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


# ------------------------------------------------------------------
# 指标计算
# ------------------------------------------------------------------


def _compute_indicator(df: pd.DataFrame, indicator: str) -> pd.Series:
    """根据指标名计算对应序列。支持基础名及带周期后缀的变体。"""
    close = df["close"]
    high = df.get("high", close)
    low = df.get("low", close)
    volume = df.get("volume", pd.Series(0, index=df.index))

    # 1. 直接列（如 close, high, low, volume）
    if indicator in df.columns:
        return df[indicator]

    # 2. 基础指标（不带后缀）
    if indicator == "sma":
        return close.rolling(20).mean()
    if indicator == "ema":
        return close.ewm(span=20).mean()
    if indicator == "rsi":
        return _rsi(close, 14)
    if indicator == "macd":
        return _macd(close)[2]  # macd_bar
    if indicator == "macd_dif":
        return _macd(close)[0]
    if indicator == "macd_dea":
        return _macd(close)[1]
    if indicator == "boll_upper":
        return _bollinger(close)[0]
    if indicator == "boll_mid":
        return _bollinger(close)[1]
    if indicator == "boll_lower":
        return _bollinger(close)[2]
    if indicator == "atr":
        return _atr(high, low, close)
    if indicator == "kdj_k":
        return _kdj(high, low, close)[0]
    if indicator == "kdj_d":
        return _kdj(high, low, close)[1]
    if indicator == "kdj_j":
        return _kdj(high, low, close)[2]

    # 3. 带周期后缀的变体（如 sma5, ema20, rsi24）
    base = re.sub(r"[_-]?\d+$", "", indicator)
    period_match = re.search(r"(\d+)", indicator)
    period = int(period_match.group(1)) if period_match else 20

    if base == "sma":
        return close.rolling(period, min_periods=period).mean()
    if base == "ema":
        return close.ewm(span=period).mean()
    if base == "rsi":
        return _rsi(close, period)
    if base == "boll":
        return _bollinger(close, period)[1]  # mid
    if base == "high":
        return high.rolling(period, min_periods=period).max()
    if base == "low":
        return low.rolling(period, min_periods=period).min()
    if base == "volume":
        return volume.rolling(period, min_periods=period).mean()

    # 默认返回 close
    logger.warning("未知指标 %s，回退到 close", indicator)
    return close


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / (avg_loss + 1e-12)
    return 100 - (100 / (1 + rs))


def _macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    bar = dif - dea
    return dif, dea, bar


def _bollinger(series: pd.Series, period: int = 20, std: int = 2) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = series.rolling(period, min_periods=period).mean()
    std_dev = series.rolling(period, min_periods=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def _kdj(
    high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9, m1: int = 3, m2: int = 3
) -> tuple[pd.Series, pd.Series, pd.Series]:
    rsv = (close - low.rolling(n).min()) / (high.rolling(n).max() - low.rolling(n).min() + 1e-12) * 100
    k = rsv.ewm(alpha=1 / m1, adjust=False).mean()
    d = k.ewm(alpha=1 / m2, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j
