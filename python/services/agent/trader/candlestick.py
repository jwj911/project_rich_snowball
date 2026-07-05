"""K线形态识别与多空力量分析模块。

识别常见 K 线形态，结合成交量/持仓量判断多空力量变化。
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def detect_candlestick_patterns(df: pd.DataFrame) -> list[dict[str, Any]]:
    """识别常见 K 线形态。

    Args:
        df: K线 DataFrame，需包含 open/high/low/close/volume 列。

    Returns:
        识别到的形态列表，按时间顺序排列，最近的在最后。
        每个元素包含：name、type（bullish/bearish/neutral）、confidence、bar_index、description。
    """
    if len(df) < 3:
        return []

    patterns = []
    n = len(df)

    # 只分析最近 10 根 K 线
    lookback = min(10, n - 2)

    for i in range(n - lookback, n):
        if i < 2:
            continue

        prev2 = df.iloc[i - 2]
        prev1 = df.iloc[i - 1]
        curr = df.iloc[i]

        # 吞没形态
        engulf = _detect_engulfing(prev1, curr)
        if engulf:
            patterns.append(_pattern_dict("吞没形态", engulf, i, n))

        # Pin Bar
        pin = _detect_pin_bar(curr)
        if pin:
            patterns.append(_pattern_dict("Pin Bar", pin, i, n))

        # 十字星
        doji = _detect_doji(curr)
        if doji:
            patterns.append(_pattern_dict("十字星", doji, i, n))

        # Inside Bar
        inside = _detect_inside_bar(prev1, curr)
        if inside:
            patterns.append(_pattern_dict("Inside Bar", inside, i, n))

        # 锤子线 / 上吊线
        hammer = _detect_hammer(curr, prev1)
        if hammer:
            patterns.append(_pattern_dict("锤子线/上吊线", hammer, i, n))

        # 早晨之星 / 黄昏之星（需要 prev2, prev1, curr）
        star = _detect_morning_evening_star(prev2, prev1, curr)
        if star:
            patterns.append(_pattern_dict("早晨之星/黄昏之星", star, i, n))

    return patterns


def calculate_bull_bear_strength(df: pd.DataFrame) -> dict[str, Any]:
    """计算当前 K 线多空力量评分。

    Returns:
        {
            "score": float,  # -1 ~ +1
            "description": str,
            "components": dict,
        }
    """
    if len(df) < 5:
        return {"score": 0.0, "description": "数据不足", "components": {}}

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    open_price = float(curr["open"])
    high = float(curr["high"])
    low = float(curr["low"])
    close = float(curr["close"])

    if high == low:
        return {"score": 0.0, "description": "当前 K 线无波动", "components": {}}

    body = close - open_price
    total_range = high - low
    upper_shadow = high - max(open_price, close)
    lower_shadow = min(open_price, close) - low

    # 实体位置评分：-1（实体在下端）到 +1（实体在上端）
    body_position = ((close + open_price) / 2 - low) / total_range * 2 - 1

    # 影线评分：长下影线偏多，长上影线偏空
    shadow_score = 0.0
    if upper_shadow / total_range > 0.4:
        shadow_score -= 0.3
    if lower_shadow / total_range > 0.4:
        shadow_score += 0.3

    # 实体方向评分
    body_score = body / total_range

    # 成交量评分：放量上涨偏多，放量下跌偏空
    volume_score = 0.0
    if "volume" in df.columns:
        avg_volume = df["volume"].iloc[-10:].mean()
        curr_volume = float(curr["volume"])
        if avg_volume > 0 and curr_volume > avg_volume * 1.2:
            volume_score = 0.2 if body_score > 0 else -0.2

    # 持仓量评分：增仓上行偏多，增仓下行偏空
    oi_score = 0.0
    if "open_interest" in df.columns:
        prev_oi = float(prev["open_interest"])
        curr_oi = float(curr["open_interest"])
        if prev_oi > 0:
            oi_change = (curr_oi - prev_oi) / prev_oi
            if abs(oi_change) > 0.001:
                oi_score = 0.15 * (1 if body_score > 0 else -1) if oi_change > 0 else 0

    total_score = body_position * 0.25 + body_score * 0.35 + shadow_score * 0.2 + volume_score + oi_score
    total_score = max(-1.0, min(1.0, total_score))

    if total_score > 0.3:
        description = "多头力量占优"
    elif total_score < -0.3:
        description = "空头力量占优"
    else:
        description = "多空力量均衡"

    return {
        "score": round(total_score, 3),
        "description": description,
        "components": {
            "body_position": round(body_position, 3),
            "body_score": round(body_score, 3),
            "shadow_score": round(shadow_score, 3),
            "volume_score": round(volume_score, 3),
            "oi_score": round(oi_score, 3),
        },
    }


def volume_confirmation(signal_type: str, df: pd.DataFrame, lookback: int = 10) -> dict[str, Any]:
    """判断成交量是否确认当前信号。

    Args:
        signal_type: "bullish" 或 "bearish"。
        df: K线 DataFrame。
        lookback: 平均成交量回看周期。

    Returns:
        {"confirmed": bool, "ratio": float, "description": str}
    """
    if "volume" not in df.columns or len(df) < 2:
        return {"confirmed": False, "ratio": 1.0, "description": "无成交量数据"}

    avg_volume = df["volume"].iloc[-lookback:].mean()
    curr_volume = float(df["volume"].iloc[-1])
    ratio = curr_volume / avg_volume if avg_volume > 0 else 1.0

    confirmed = ratio > 1.2
    description = f"当前成交量 {curr_volume:.0f}，为近 {lookback} 根均量 {avg_volume:.0f} 的 {ratio:.2f} 倍"

    if signal_type == "bullish" and confirmed:
        description += "，放量配合上涨信号"
    elif signal_type == "bearish" and confirmed:
        description += "，放量配合下跌信号"
    elif confirmed:
        description += "，成交量放大"
    else:
        description += "，量能未明显放大"

    return {"confirmed": confirmed, "ratio": round(ratio, 2), "description": description}


def _detect_engulfing(prev: pd.Series, curr: pd.Series) -> str | None:
    """识别吞没形态。"""
    prev_body = abs(prev["close"] - prev["open"])
    curr_body = abs(curr["close"] - curr["open"])

    if curr_body < prev_body * 1.2:
        return None

    # 看涨吞没
    if (
        prev["close"] < prev["open"]
        and curr["close"] > curr["open"]
        and curr["open"] <= prev["close"]
        and curr["close"] >= prev["open"]
    ):
        return "bullish"

    # 看跌吞没
    if (
        prev["close"] > prev["open"]
        and curr["close"] < curr["open"]
        and curr["open"] >= prev["close"]
        and curr["close"] <= prev["open"]
    ):
        return "bearish"

    return None


def _detect_pin_bar(bar: pd.Series) -> str | None:
    """识别 Pin Bar。"""
    open_p = float(bar["open"])
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])

    if high == low:
        return None

    body = abs(close - open_p)
    total_range = high - low
    upper_shadow = high - max(open_p, close)
    lower_shadow = min(open_p, close) - low

    if body / total_range < 0.25:
        if lower_shadow / total_range > 0.6:
            return "bullish"
        if upper_shadow / total_range > 0.6:
            return "bearish"

    return None


def _detect_doji(bar: pd.Series, threshold: float = 0.05) -> str | None:
    """识别十字星。"""
    body = abs(bar["close"] - bar["open"])
    total_range = bar["high"] - bar["low"]
    if total_range == 0:
        return None
    if body / total_range < threshold:
        return "neutral"
    return None


def _detect_inside_bar(prev: pd.Series, curr: pd.Series) -> str | None:
    """识别 Inside Bar。"""
    if curr["high"] <= prev["high"] and curr["low"] >= prev["low"]:
        return "neutral"
    return None


def _detect_hammer(curr: pd.Series, prev: pd.Series) -> str | None:
    """识别锤子线/上吊线。"""
    open_p = float(curr["open"])
    high = float(curr["high"])
    low = float(curr["low"])
    close = float(curr["close"])

    if high == low:
        return None

    body = abs(close - open_p)
    total_range = high - low
    lower_shadow = min(open_p, close) - low
    upper_shadow = high - max(open_p, close)

    if body / total_range < 0.3 and lower_shadow / total_range > 0.5 and upper_shadow / total_range < 0.1:
        # 出现在下跌趋势末端为锤子线，上涨趋势末端为上吊线
        if close > prev["close"]:
            return "bullish"
        return "bearish"

    return None


def _detect_morning_evening_star(prev2: pd.Series, prev1: pd.Series, curr: pd.Series) -> str | None:
    """识别早晨之星/黄昏之星。"""
    # 早晨之星：第一根大阴线，第二根小实体，第三根大阳线收盘价深入第一根实体
    if prev2["close"] < prev2["open"] and curr["close"] > curr["open"]:
        prev2_body = prev2["open"] - prev2["close"]
        prev1_body = abs(prev1["close"] - prev1["open"])
        curr_body = curr["close"] - curr["open"]
        if (
            prev1_body < prev2_body * 0.3
            and curr_body > prev2_body * 0.5
            and curr["close"] > prev2["close"] + prev2_body * 0.5
        ):
            return "bullish"

    # 黄昏之星：第一根大阳线，第二根小实体，第三根大阴线
    if prev2["close"] > prev2["open"] and curr["close"] < curr["open"]:
        prev2_body = prev2["close"] - prev2["open"]
        prev1_body = abs(prev1["close"] - prev1["open"])
        curr_body = curr["open"] - curr["close"]
        if (
            prev1_body < prev2_body * 0.3
            and curr_body > prev2_body * 0.5
            and curr["close"] < prev2["open"] - prev2_body * 0.5
        ):
            return "bearish"

    return None


def _pattern_dict(name: str, type_: str | None, bar_index: int, total: int) -> dict[str, Any]:
    """构建形态字典。"""
    type_map = {"bullish": "看涨", "bearish": "看跌", "neutral": "中性"}
    return {
        "name": name,
        "type": type_ or "neutral",
        "type_text": type_map.get(type_ or "neutral", "中性"),
        "confidence": 70.0 if type_ in ("bullish", "bearish") else 50.0,
        "bar_index": bar_index,
        "recent": bar_index >= total - 3,
        "description": f"{'最近' if bar_index >= total - 3 else ''}K线出现{type_map.get(type_ or 'neutral', '中性')}{name}",
    }
