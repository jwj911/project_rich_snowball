"""市场结构识别模块。

识别单周期趋势状态、支撑阻力位、关键高低点、突破/假突破。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def identify_trend(df: pd.DataFrame, short_window: int = 5, long_window: int = 20) -> dict[str, Any]:
    """基于均线排列与高低点结构判断趋势。

    Args:
        df: K线 DataFrame，需包含 open/high/low/close 列。
        short_window: 短期均线窗口。
        long_window: 长期均线窗口。

    Returns:
        {
            "trend": "uptrend" | "downtrend" | "sideways" | "range_bound",
            "direction": "up" | "down" | "neutral",
            "strength": float,  # 0-100
            "description": str,
            "ma_short": float,
            "ma_long": float,
        }
    """
    if len(df) < long_window + 5:
        return {
            "trend": "sideways",
            "direction": "neutral",
            "strength": 0.0,
            "description": "数据不足，无法判断趋势",
            "ma_short": None,
            "ma_long": None,
        }

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    ma_short = pd.Series(closes).rolling(window=short_window, min_periods=1).mean().values
    ma_long = pd.Series(closes).rolling(window=long_window, min_periods=1).mean().values

    latest_close = closes[-1]
    latest_short = ma_short[-1]
    latest_long = ma_long[-1]
    prev_short = ma_short[-2]
    prev_long = ma_long[-2]

    # 均线排列判断
    ma_bullish = latest_short > latest_long and prev_short > prev_long
    ma_bearish = latest_short < latest_long and prev_short < prev_long

    # 高低点结构判断（最近 N 根）
    structure_window = min(20, len(df) // 2)
    recent_highs = highs[-structure_window:]
    recent_lows = lows[-structure_window:]

    higher_highs = recent_highs[-1] > np.max(recent_highs[:-1]) if len(recent_highs) > 1 else False
    higher_lows = recent_lows[-1] > np.min(recent_lows[:-1]) if len(recent_lows) > 1 else False
    lower_highs = recent_highs[-1] < np.max(recent_highs[:-1]) if len(recent_highs) > 1 else False
    lower_lows = recent_lows[-1] < np.min(recent_lows[:-1]) if len(recent_lows) > 1 else False

    # ATR 用于判断横盘
    atr = _calculate_atr(df, 14)
    avg_range = atr / latest_close if latest_close > 0 else 0
    is_sideways = avg_range < 0.005  # 波动率小于 0.5% 视为横盘

    # 综合判断
    if ma_bullish and (higher_highs or higher_lows):
        trend = "uptrend"
        direction = "up"
        strength = 70.0 + (10 if higher_highs else 0) + (10 if higher_lows else 0)
        description = "均线多头排列，价格高点/低点抬升，趋势向上"
    elif ma_bearish and (lower_highs or lower_lows):
        trend = "downtrend"
        direction = "down"
        strength = 70.0 + (10 if lower_highs else 0) + (10 if lower_lows else 0)
        description = "均线空头排列，价格高点/低点降低，趋势向下"
    elif is_sideways or (not ma_bullish and not ma_bearish):
        # 判断是横盘还是区间震荡
        recent_range = (recent_highs.max() - recent_lows.min()) / latest_close if latest_close > 0 else 0
        if recent_range > 0.03:  # 区间幅度大于 3% 视为震荡
            trend = "range_bound"
            direction = "neutral"
            strength = 30.0
            description = "价格在较宽区间内震荡，方向不明"
        else:
            trend = "sideways"
            direction = "neutral"
            strength = 20.0
            description = "均线粘合，波动率低，横盘整理"
    else:
        trend = "sideways"
        direction = "neutral"
        strength = 30.0
        description = "趋势信号矛盾，暂以震荡对待"

    strength = min(100.0, max(0.0, strength))

    return {
        "trend": trend,
        "direction": direction,
        "strength": round(strength, 1),
        "description": description,
        "ma_short": round(float(latest_short), 2),
        "ma_long": round(float(latest_long), 2),
    }


def find_support_resistance(df: pd.DataFrame, lookback: int = 20, touches: int = 2) -> list[dict[str, Any]]:
    """识别近期支撑与阻力位（基于局部极值 + 成交量确认）。

    Args:
        df: K线 DataFrame，需包含 high/low/close/volume 列。
        lookback: 回看周期数。
        touches: 最少接触次数。

    Returns:
        支撑/阻力位列表，每个元素包含 level、type、strength、touches。
    """
    if len(df) < lookback:
        return []

    recent = df.iloc[-lookback:].copy()
    highs = recent["high"].values
    lows = recent["low"].values
    volumes = recent["volume"].values if "volume" in recent.columns else np.ones(len(recent))

    # 找局部极大/极小值
    resistance_levels = _find_local_extremes(highs, mode="max", touches=touches)
    support_levels = _find_local_extremes(lows, mode="min", touches=touches)

    levels = []
    for level, idx_list in resistance_levels:
        avg_volume = float(np.mean(volumes[idx_list])) if volumes.size else 1.0
        levels.append(
            {
                "level": round(float(level), 2),
                "type": "resistance",
                "strength": _level_strength(len(idx_list), avg_volume, volumes.mean() if volumes.mean() else 1.0),
                "touches": len(idx_list),
            }
        )

    for level, idx_list in support_levels:
        avg_volume = float(np.mean(volumes[idx_list])) if volumes.size else 1.0
        levels.append(
            {
                "level": round(float(level), 2),
                "type": "support",
                "strength": _level_strength(len(idx_list), avg_volume, volumes.mean() if volumes.mean() else 1.0),
                "touches": len(idx_list),
            }
        )

    # 按强度排序，最多返回 5 个
    levels.sort(key=lambda x: x["strength"], reverse=True)
    return levels[:5]


def detect_breakout_or_fakeout(df: pd.DataFrame, level: float, type_: str = "resistance") -> dict[str, Any]:
    """判断价格对关键位是有效突破还是假突破。

    Args:
        df: K线 DataFrame，需包含 open/high/low/close/volume 列。
        level: 关键价位。
        type_: "resistance" 或 "support"。

    Returns:
        {
            "result": "breakout" | "fakeout" | "none",
            "confidence": float,  # 0-100
            "description": str,
        }
    """
    if len(df) < 3:
        return {"result": "none", "confidence": 0.0, "description": "数据不足"}

    recent = df.iloc[-3:]
    closes = recent["close"].values
    volumes = recent["volume"].values if "volume" in recent.columns else np.ones(len(recent))
    avg_volume = df["volume"].iloc[-20:].mean() if "volume" in df.columns else volumes.mean()

    if type_ == "resistance":
        broke = closes[-1] > level and closes[-2] <= level
        confirm = volumes[-1] > avg_volume * 1.2 and closes[-1] > closes[-2]
    else:
        broke = closes[-1] < level and closes[-2] >= level
        confirm = volumes[-1] > avg_volume * 1.2 and closes[-1] < closes[-2]

    if not broke:
        return {"result": "none", "confidence": 0.0, "description": "尚未突破关键位"}

    if confirm:
        return {
            "result": "breakout",
            "confidence": 80.0,
            "description": f"价格{'向上突破' if type_ == 'resistance' else '向下突破'} {level}，成交量放大确认",
        }
    else:
        return {
            "result": "fakeout",
            "confidence": 60.0,
            "description": f"价格触及 {level} 但成交量未确认，警惕假突破",
        }


def _calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """计算 Average True Range。"""
    if len(df) < period + 1:
        return float(df["high"].iloc[-1] - df["low"].iloc[-1])

    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=1).mean().iloc[-1]
    return float(atr)


def _find_local_extremes(values: np.ndarray, mode: str = "max", touches: int = 2) -> list[tuple[float, list[int]]]:
    """找局部极值并聚类成关键位。"""
    if len(values) < 3:
        return []

    # 找局部极值点索引
    if mode == "max":
        extrema_idx = []
        for i in range(1, len(values) - 1):
            if values[i] > values[i - 1] and values[i] > values[i + 1]:
                extrema_idx.append(i)
    else:
        extrema_idx = []
        for i in range(1, len(values) - 1):
            if values[i] < values[i - 1] and values[i] < values[i + 1]:
                extrema_idx.append(i)

    if not extrema_idx:
        return []

    # 按价格聚类：价格相近的极值合并为一个关键位
    threshold = np.std(values) * 0.3 if np.std(values) > 0 else values.mean() * 0.005
    clusters: list[tuple[float, list[int]]] = []

    for idx in extrema_idx:
        price = float(values[idx])
        assigned = False
        for i, (center, members) in enumerate(clusters):
            if abs(price - center) <= threshold:
                new_center = (center * len(members) + price) / (len(members) + 1)
                clusters[i] = (new_center, members + [idx])
                assigned = True
                break
        if not assigned:
            clusters.append((price, [idx]))

    # 过滤接触次数
    return [(center, members) for center, members in clusters if len(members) >= touches]


def _level_strength(touches: int, volume_at_level: float, avg_volume: float) -> float:
    """计算关键位强度。"""
    touch_score = min(50, touches * 15)
    volume_score = min(50, (volume_at_level / avg_volume) * 20) if avg_volume > 0 else 0
    return round(float(touch_score + volume_score), 1)
