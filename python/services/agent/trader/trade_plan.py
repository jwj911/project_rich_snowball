"""交易计划生成模块。

根据市场结构、多周期共振、K线形态生成具体的交易计划。
"""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from services.agent.trader.candlestick import calculate_bull_bear_strength, volume_confirmation
from services.agent.trader.market_structure import _calculate_atr, detect_breakout_or_fakeout, find_support_resistance

TradingStyle = Literal["scalping", "intraday_swing", "short_term_trend", "medium_term_trend"]

# 默认风格参数：风险倍数、最小盈亏比
_STYLE_PARAMS: dict[TradingStyle, dict[str, float]] = {
    "scalping": {"atr_stop_mult": 0.8, "atr_tp_mult": 1.2, "min_rr": 1.2, "holding_days": 0},
    "intraday_swing": {"atr_stop_mult": 1.2, "atr_tp_mult": 2.0, "min_rr": 1.5, "holding_days": 0},
    "short_term_trend": {"atr_stop_mult": 1.8, "atr_tp_mult": 3.0, "min_rr": 1.8, "holding_days": 7},
    "medium_term_trend": {"atr_stop_mult": 2.5, "atr_tp_mult": 4.0, "min_rr": 2.0, "holding_days": 21},
}


def generate_trade_plan(
    symbol: str,
    current_price: float,
    dominant_trend: str,
    direction: str,
    entry_timeframe: str,
    timeframe_data: dict[str, pd.DataFrame],
    style: TradingStyle,
    account_balance: float,
    risk_per_trade: float = 0.02,
    min_risk_reward: float | None = None,
    multiplier: float = 1.0,
) -> dict[str, Any] | None:
    """生成交易计划。

    Args:
        symbol: 品种代码。
        current_price: 当前价格。
        dominant_trend: 主导趋势。
        direction: 方向 "up" | "down" | "neutral"。
        entry_timeframe: 推荐入场周期。
        timeframe_data: 各周期 K 线数据。
        style: 交易风格。
        account_balance: 账户权益。
        risk_per_trade: 单笔风险比例。
        min_risk_reward: 最低盈亏比，None 时使用风格默认值。
        multiplier: 合约乘数。

    Returns:
        交易计划字典，不满足条件时返回 None。
    """
    if direction == "neutral" or dominant_trend in ("sideways",):
        return None

    params = _STYLE_PARAMS.get(style, _STYLE_PARAMS["intraday_swing"])
    min_rr = min_risk_reward if min_risk_reward is not None else params["min_rr"]

    entry_df = timeframe_data.get(entry_timeframe)
    if entry_df is None or len(entry_df) < 20:
        entry_df = timeframe_data.get("1h") or list(timeframe_data.values())[0]

    atr = _calculate_atr(entry_df, 14)
    stop_distance = atr * params["atr_stop_mult"]

    # 确定入场参考：当前价或最近形态/关键位
    entry_price, entry_condition = _determine_entry(current_price, direction, entry_df, dominant_trend)

    # 止损价
    stop_loss = _calculate_stop_loss(entry_price, direction, stop_distance, entry_df)

    # 止盈价（基于盈亏比）
    risk = abs(entry_price - stop_loss)
    take_profit = _calculate_take_profit(entry_price, direction, risk, params["atr_tp_mult"], entry_df)

    # 实际盈亏比
    actual_rr = abs(take_profit - entry_price) / risk if risk > 0 else 0.0

    # 若盈亏比不足，尝试放宽止损或收紧止盈，仍不足则观望
    if actual_rr < min_rr:
        # 尝试用支撑位/阻力位作为更优止盈
        take_profit = _optimize_take_profit_by_levels(entry_price, direction, entry_df, min_rr)
        actual_rr = abs(take_profit - entry_price) / risk if risk > 0 else 0.0
        if actual_rr < min_rr:
            return None

    # 仓位计算
    risk_amount = account_balance * risk_per_trade
    position_value = risk_amount / risk if risk > 0 else 0.0
    # 期货手数 = 风险金额 / (止损距离 × 合约乘数)
    position_size = int(position_value / multiplier) if multiplier > 0 else 0
    if position_size < 1:
        position_size = 1  # 至少 1 手，但需提示风险

    # 重新校验：实际风险金额是否超限
    actual_risk_amount = position_size * risk * multiplier
    if actual_risk_amount > risk_amount * 1.1:
        position_size = max(0, int(risk_amount / (risk * multiplier)))
        if position_size < 1:
            return None

    # 多空力量确认
    strength = calculate_bull_bear_strength(entry_df)
    vol_confirm = volume_confirmation("bullish" if direction == "up" else "bearish", entry_df)

    confidence = _calculate_confidence(
        dominant_trend, direction, actual_rr, min_rr, strength["score"], vol_confirm["confirmed"]
    )

    holding_period = _holding_period_text(style, params["holding_days"])
    invalidation = _build_invalidation(entry_price, stop_loss, direction, entry_df)

    return {
        "symbol": symbol,
        "style": style,
        "direction": "long" if direction == "up" else "short",
        "entry_price": round(entry_price, 2),
        "entry_condition": entry_condition,
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "risk_per_trade": risk_per_trade,
        "risk_amount": round(risk_amount, 2),
        "actual_risk_amount": round(actual_risk_amount, 2),
        "position_size": position_size,
        "position_value": round(position_value, 2),
        "risk_reward_ratio": round(actual_rr, 2),
        "min_risk_reward": min_rr,
        "confidence": confidence,
        "holding_period": holding_period,
        "invalidation": invalidation,
        "bull_bear_strength": strength,
        "volume_confirmation": vol_confirm,
    }


def _determine_entry(
    current_price: float,
    direction: str,
    entry_df: pd.DataFrame,
    dominant_trend: str,
) -> tuple[float, str]:
    """确定入场价与入场条件。"""
    levels = find_support_resistance(entry_df, lookback=15)
    atr = _calculate_atr(entry_df, 14)

    if direction == "up":
        # 优先在支撑位附近入场
        supports = [level["level"] for level in levels if level["type"] == "support" and level["level"] < current_price]
        if supports:
            entry_price = max(supports)  # 最接近当前价的支撑
            return entry_price, f"价格回调至支撑位 {entry_price} 附近企稳后做多"

        # 突破入场
        resistances = [
            level["level"] for level in levels if level["type"] == "resistance" and level["level"] > current_price
        ]
        if resistances:
            level = min(resistances)
            breakout = detect_breakout_or_fakeout(entry_df, level, "resistance")
            if breakout["result"] == "breakout":
                return current_price, f"价格放量突破阻力位 {level}，顺势追多"

        return current_price, f"当前价格 {current_price} 附近顺势做多，止损设在 {round(current_price - atr * 1.2, 2)}"

    else:  # direction == "down"
        resistances = [
            level["level"] for level in levels if level["type"] == "resistance" and level["level"] > current_price
        ]
        if resistances:
            entry_price = min(resistances)
            return entry_price, f"价格反弹至阻力位 {entry_price} 附近受阻后做空"

        supports = [level["level"] for level in levels if level["type"] == "support" and level["level"] < current_price]
        if supports:
            level = max(supports)
            breakout = detect_breakout_or_fakeout(entry_df, level, "support")
            if breakout["result"] == "breakout":
                return current_price, f"价格放量跌破支撑位 {level}，顺势追空"

        return current_price, f"当前价格 {current_price} 附近顺势做空，止损设在 {round(current_price + atr * 1.2, 2)}"


def _calculate_stop_loss(entry_price: float, direction: str, stop_distance: float, df: pd.DataFrame) -> float:
    """计算止损价。"""
    # 优先使用关键位作为止损
    levels = find_support_resistance(df, lookback=15)

    if direction == "up":
        # 找低于入场价的支撑位，止损设在其下方
        supports = [level["level"] for level in levels if level["type"] == "support" and level["level"] < entry_price]
        if supports:
            nearest_support = max(supports)
            stop = nearest_support - stop_distance * 0.3
            if stop < entry_price:
                return stop
        return entry_price - stop_distance

    else:
        resistances = [
            level["level"] for level in levels if level["type"] == "resistance" and level["level"] > entry_price
        ]
        if resistances:
            nearest_resistance = min(resistances)
            stop = nearest_resistance + stop_distance * 0.3
            if stop > entry_price:
                return stop
        return entry_price + stop_distance


def _calculate_take_profit(
    entry_price: float,
    direction: str,
    risk: float,
    atr_tp_mult: float,
    df: pd.DataFrame,
) -> float:
    """计算止盈价。"""
    # 优先使用关键位
    levels = find_support_resistance(df, lookback=20)

    if direction == "up":
        resistances = [
            level["level"] for level in levels if level["type"] == "resistance" and level["level"] > entry_price
        ]
        if resistances:
            return min(resistances)
        return entry_price + risk * 2.0

    else:
        supports = [level["level"] for level in levels if level["type"] == "support" and level["level"] < entry_price]
        if supports:
            return max(supports)
        return entry_price - risk * 2.0


def _optimize_take_profit_by_levels(
    entry_price: float,
    direction: str,
    df: pd.DataFrame,
    min_rr: float,
) -> float:
    """通过关键位优化止盈以满足最低盈亏比。"""
    levels = find_support_resistance(df, lookback=30)
    risk = abs(entry_price - _calculate_stop_loss(entry_price, direction, _calculate_atr(df, 14), df))

    if direction == "up":
        candidates = [
            level["level"] for level in levels if level["type"] == "resistance" and level["level"] > entry_price
        ]
        candidates.sort()
        for tp in candidates:
            if (tp - entry_price) / risk >= min_rr:
                return tp
    else:
        candidates = [level["level"] for level in levels if level["type"] == "support" and level["level"] < entry_price]
        candidates.sort(reverse=True)
        for tp in candidates:
            if (entry_price - tp) / risk >= min_rr:
                return tp

    # 无法满足，使用默认 2R
    return entry_price + risk * 2.0 if direction == "up" else entry_price - risk * 2.0


def _calculate_confidence(
    dominant_trend: str,
    direction: str,
    actual_rr: float,
    min_rr: float,
    strength_score: float,
    volume_confirmed: bool,
) -> Literal["high", "medium", "low"]:
    """计算交易计划置信度。"""
    score = 50

    # 趋势方向匹配
    if (dominant_trend == "uptrend" and direction == "up") or (dominant_trend == "downtrend" and direction == "down"):
        score += 20
    elif dominant_trend in ("range_bound", "sideways"):
        score -= 10

    # 盈亏比
    if actual_rr >= min_rr * 1.5:
        score += 15
    elif actual_rr >= min_rr:
        score += 5
    else:
        score -= 15

    # 多空力量
    if abs(strength_score) > 0.4 and (strength_score > 0) == (direction == "up"):
        score += 10

    # 成交量确认
    if volume_confirmed:
        score += 5

    if score >= 75:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def _holding_period_text(style: TradingStyle, days: int) -> str:
    """持有周期文本。"""
    if style == "scalping":
        return "数分钟 ~ 数小时"
    if style == "intraday_swing":
        return "1 小时 ~ 当日收盘"
    if style == "short_term_trend":
        return f"{max(1, days // 2)} ~ {days} 个交易日"
    return f"{max(7, days // 2)} ~ {days} 个交易日"


def _build_invalidation(entry_price: float, stop_loss: float, direction: str, df: pd.DataFrame) -> str:
    """构建计划失效条件。"""
    atr = _calculate_atr(df, 14)
    if direction == "up":
        return (
            f"价格跌破止损位 {round(stop_loss, 2)} 即止损离场；"
            f"若价格快速回落至 {round(entry_price - atr * 0.5, 2)} 以下且无力收回，考虑提前离场"
        )
    return (
        f"价格涨破止损位 {round(stop_loss, 2)} 即止损离场；"
        f"若价格快速反弹至 {round(entry_price + atr * 0.5, 2)} 以上且无力回落，考虑提前离场"
    )
