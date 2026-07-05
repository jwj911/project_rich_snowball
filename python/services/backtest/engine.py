"""Vector-friendly backtesting engine for simple futures strategies."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from services.agent.factor_engine.filters import FilterCondition, FilterPipeline

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
    filter_list: list[FilterCondition] = field(default_factory=list)
    stop_loss: dict[str, Any] | None = None
    take_profit: dict[str, Any] | None = None


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
    fee: float


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
                "filter_list": [
                    {"field": f.field, "expression": f.expression, "is_and": f.is_and} for f in self.config.filter_list
                ],
                "stop_loss": self.config.stop_loss,
                "take_profit": self.config.take_profit,
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

    # 应用过滤条件
    filter_removed = 0
    if config.filter_list:
        pipeline = FilterPipeline()
        filter_result = pipeline.apply(data, config.filter_list, date_col="time")
        if len(filter_result.filtered) == 0:
            raise ValueError("过滤条件过于严格：所有数据均被排除")
        filter_removed = filter_result.removed_count
        data = filter_result.filtered
        logger.info("回测过滤完成：排除 %d 行，保留 %d 行", filter_removed, len(data))

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

    # 预计算 ATR，供止损/止盈（atr_multiple）使用
    if "atr" not in data.columns:
        data["atr"] = _atr(data["high"], data["low"], data["close"])

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
        high = float(row["high"])
        low = float(row["low"])

        exit_reason: str | None = None
        exit_trigger_price: float | None = None

        # 优先检查止损/止盈（基于当前 bar 的高低点）
        if position_entry_price is not None:
            sl_price, tp_price = _resolve_stop_levels(config, position_entry_price, data, i)
            if sl_price is not None and (
                config.direction == "long" and low <= sl_price or config.direction == "short" and high >= sl_price
            ):
                exit_reason = "stop_loss"
                exit_trigger_price = sl_price
            if (
                exit_reason is None
                and tp_price is not None
                and (config.direction == "long" and high >= tp_price or config.direction == "short" and low <= tp_price)
            ):
                exit_reason = "take_profit"
                exit_trigger_price = tp_price

        if position_entry_price is None and bool(entry_signal.iloc[i - 1]):
            position_entry_price = execution_price
            position_entry_time = time_value
            signals.append({"time": time_value, "type": "entry", "price": execution_price})
        elif position_entry_price is not None and (exit_reason or bool(exit_signal.iloc[i - 1])):
            exit_price = (
                _calculate_exit_price(config.direction, execution_price, exit_trigger_price, high, low, exit_reason)
                if exit_reason
                else execution_price
            )
            gross = _position_pnl(
                config.direction,
                position_entry_price,
                exit_price,
                config.quantity,
                config.multiplier,
            )
            fee = (position_entry_price + exit_price) * config.quantity * config.multiplier * config.fee_rate
            pnl = gross - fee
            cash += pnl
            base = position_entry_price * config.quantity * config.multiplier
            trades.append(
                BacktestTrade(
                    entry_time=position_entry_time or time_value,
                    exit_time=time_value,
                    direction=config.direction,
                    entry_price=round(position_entry_price, 4),
                    exit_price=round(exit_price, 4),
                    quantity=config.quantity,
                    pnl=round(pnl, 4),
                    return_pct=round(pnl / base * 100, 4) if base else 0.0,
                    fee=round(fee, 4),
                )
            )
            signals.append({"time": time_value, "type": "exit", "price": exit_price, "reason": exit_reason or "signal"})
            position_entry_price = None
            position_entry_time = None

        unrealized = 0.0
        position_ratio = 0.0
        if position_entry_price is not None:
            unrealized = _position_pnl(
                config.direction,
                position_entry_price,
                current_close,
                config.quantity,
                config.multiplier,
            )
            position_value = position_entry_price * config.quantity * config.multiplier
            position_ratio = position_value / (cash + unrealized) if (cash + unrealized) > 0 else 0.0
        equity_point: dict[str, Any] = {
            "time": time_value,
            "equity": round(cash + unrealized, 4),
            "close": current_close,
            "position_ratio": round(position_ratio, 4),
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

        # between 单独处理：value 为 [lower, upper]
        if operator == "between":
            if isinstance(value, list | tuple) and len(value) == 2:
                lower, upper = float(value[0]), float(value[1])
                signal = (col1 > lower) & (col1 < upper)
            else:
                signal = pd.Series(False, index=data.index)
                logger.warning("between 操作符需要 value 为长度 2 的数值列表")
            results.append(signal.fillna(False))
            continue

        if indicator2:
            col2 = _compute_indicator(data, indicator2)
            # 支持对 indicator2 进行变换，例如 volume > volume_sma * 1.5
            transform = cond.get("transform")
            if transform == "multiply_value" and value is not None:
                col2 = col2 * float(value)
            elif transform == "multiply_indicator2":
                # 语义同 multiply_value：col1 > col2 * value
                col2 = col2 * (float(value) if value is not None else 1.0)
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


def _resolve_stop_levels(
    config: BacktestConfig, entry_price: float, data: pd.DataFrame, i: int
) -> tuple[float | None, float | None]:
    """根据 DSL risk 配置和当前数据解析止损/止盈触发价。"""
    sl_price: float | None = None
    tp_price: float | None = None

    sl = config.stop_loss
    if sl and entry_price is not None:
        sl_type = sl.get("type")
        sl_value = sl.get("value")
        if sl_type == "fixed_price" and sl_value is not None:
            sl_price = float(sl_value)
        elif sl_type == "percent_below":
            sl_price = entry_price * (1 - float(sl_value or 0))
        elif sl_type == "percent_above":
            sl_price = entry_price * (1 + float(sl_value or 0))
        elif sl_type == "atr_multiple":
            atr_value = float(data["atr"].iloc[i]) if i < len(data) and not pd.isna(data["atr"].iloc[i]) else 0.0
            if config.direction == "long":
                sl_price = entry_price - atr_value * float(sl_value or 0)
            else:
                sl_price = entry_price + atr_value * float(sl_value or 0)

    tp = config.take_profit
    if tp and entry_price is not None:
        tp_type = tp.get("type")
        tp_value = tp.get("value")
        if tp_type == "target_price" and tp_value is not None:
            tp_price = float(tp_value)
        elif tp_type == "percent_below":
            tp_price = entry_price * (1 - float(tp_value or 0))
        elif tp_type == "percent_above":
            tp_price = entry_price * (1 + float(tp_value or 0))
        elif tp_type == "risk_reward_ratio" and sl_price is not None:
            risk = abs(entry_price - sl_price)
            if config.direction == "long":
                tp_price = entry_price + risk * float(tp_value or 0)
            else:
                tp_price = entry_price - risk * float(tp_value or 0)

    return sl_price, tp_price


def _calculate_exit_price(
    direction: str,
    open_price: float,
    trigger_price: float,
    high: float,
    low: float,
    reason: str,
) -> float:
    """根据止损/止盈触发价和当前 bar 的高低开，确定实际出场价。"""
    if direction == "long":
        if reason == "stop_loss":
            # 开盘跳空低于止损，按开盘出；否则按止损价
            return min(open_price, trigger_price)
        # take_profit
        return max(open_price, trigger_price)
    else:
        if reason == "stop_loss":
            # 开盘跳空高于止损，按开盘出；否则按止损价
            return max(open_price, trigger_price)
        # take_profit
        return min(open_price, trigger_price)


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
    total_multiplier = equity[-1] / initial_cash
    annualized = -100.0 if total_multiplier <= 0 else (total_multiplier ** (252 / periods) - 1) * 100
    rolling_peak = np.maximum.accumulate(equity)
    drawdown = (equity / rolling_peak - 1) * 100
    max_drawdown = abs(float(drawdown.min())) if len(drawdown) else 0.0
    wins = [trade.pnl for trade in trades if trade.pnl > 0]
    losses = [trade.pnl for trade in trades if trade.pnl < 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    loss_rate = len(losses) / len(trades) * 100 if trades else 0.0
    profit_factor = sum(wins) / abs(sum(losses)) if losses else (float(len(wins)) if wins else 0.0)
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = abs(np.mean(losses)) if losses else 0.0
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else (float(len(wins)) if wins else 0.0)
    sharpe = (returns.mean() / (returns.std(ddof=0) + 1e-12)) * np.sqrt(252) if not returns.empty else 0.0
    total_fee = sum(trade.fee for trade in trades)
    avg_fee_per_trade = total_fee / len(trades) if trades else 0.0
    score = _score_strategy(total_return, max_drawdown, win_rate, profit_factor, len(trades))

    return {
        "total_return_pct": round(float(total_return), 2),
        "annualized_return_pct": round(float(annualized), 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "win_rate_pct": round(float(win_rate), 2),
        "loss_rate_pct": round(float(loss_rate), 2),
        "profit_factor": round(float(profit_factor), 2),
        "profit_loss_ratio": round(float(profit_loss_ratio), 2),
        "sharpe": round(float(sharpe), 2),
        "total_fee": round(float(total_fee), 4),
        "avg_fee_per_trade": round(float(avg_fee_per_trade), 4),
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
    if trade_count == 0:
        return 0  # 无交易：回测无意义，0 分明确告知用户
    score = 50
    # 收益贡献：-30%~50% 映射到 -15~25 分
    score += min(max(total_return, -30), 50) * 0.5
    # 回撤惩罚：0~40% 映射到 0~28 分
    score -= min(max_drawdown, 40) * 0.7
    # 盈亏比贡献：0~3 映射到 0~12 分
    score += min(profit_factor, 3) * 4
    # 胜率温和奖励：仅在 30%~70% 区间微调，避免低胜率过度惩罚
    score += (min(max(win_rate, 30), 70) - 50) * 0.1
    # 交易次数惩罚：过少样本不可靠
    if trade_count < 3:
        score -= 15
    elif trade_count < 5:
        score -= 5
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

    # 1.5 volume_sma<N>：成交量均线
    if indicator.startswith("volume_sma"):
        period_match = re.search(r"(\d+)", indicator)
        period = int(period_match.group(1)) if period_match else 20
        return volume.rolling(period, min_periods=period).mean()

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
    if indicator == "cci":
        return _cci(high, low, close, 20)

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
    if base == "cci":
        return _cci(high, low, close, period)
    if base == "kdj_k":
        return _kdj(high, low, close, n=period)[0]
    if base == "kdj_d":
        return _kdj(high, low, close, n=period)[1]
    if base == "kdj_j":
        return _kdj(high, low, close, n=period)[2]
    if base == "boll":
        return _bollinger(close, period)[1]  # mid
    if base == "high":
        return high.rolling(period, min_periods=period).max()
    if base == "low":
        return low.rolling(period, min_periods=period).min()
    if base == "volume":
        return volume.rolling(period, min_periods=period).mean()

    # 布林带上下轨带后缀：boll_upper_20_2 / boll_lower_20_2
    boll_parts = indicator.split("_")
    if len(boll_parts) >= 4 and boll_parts[0] == "boll" and boll_parts[2].isdigit() and boll_parts[3].isdigit():
        band = boll_parts[1]
        boll_period = int(boll_parts[2])
        std = int(boll_parts[3])
        upper, mid, lower = _bollinger(close, boll_period, std)
        if band == "upper":
            return upper
        if band == "lower":
            return lower
        if band == "mid":
            return mid

    # ATR 通道：atr_upper_<p>_<m> / atr_lower_<p>_<m>
    atr_parts = indicator.split("_")
    if len(atr_parts) >= 4 and atr_parts[0] == "atr" and atr_parts[2].isdigit() and atr_parts[3].isdigit():
        band = atr_parts[1]
        atr_period = int(atr_parts[2])
        atr_mult = int(atr_parts[3])
        atr_value = _atr(high, low, close, atr_period)
        if band == "upper":
            return close + atr_value * atr_mult
        if band == "lower":
            return close - atr_value * atr_mult

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


def _cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    """Commodity Channel Index。"""
    tp = (high + low + close) / 3
    ma = tp.rolling(period, min_periods=period).mean()
    md = (tp - ma).abs().rolling(period, min_periods=period).mean()
    return (tp - ma) / (0.015 * md + 1e-12)
