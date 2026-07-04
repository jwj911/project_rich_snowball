"""趋势分析模块。

基于均线排列、价格位置、ADX 判断趋势方向和强度。
"""

from __future__ import annotations

import pandas as pd


def analyze_trend(df: pd.DataFrame) -> dict[str, str]:
    """分析趋势。

    返回趋势方向、强度描述、关键价位。
    """
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    close = latest["close"]

    # 均线排列
    ma5 = latest.get("sma5")
    ma20 = latest.get("sma20")
    ma60 = latest.get("sma60")
    ma120 = latest.get("sma120")

    ma_bullish = False
    ma_bearish = False
    if ma5 is not None and ma20 is not None and ma60 is not None:
        if ma5 > ma20 > ma60:
            ma_bullish = True
        elif ma5 < ma20 < ma60:
            ma_bearish = True

    # 价格相对均线位置
    above_ma20 = close > ma20 if ma20 else None
    above_ma60 = close > ma60 if ma60 else None

    # ADX 趋势强度
    adx = latest.get("adx14")
    trend_strength = "unknown"
    if adx is not None:
        if adx > 40:
            trend_strength = "强"
        elif adx > 25:
            trend_strength = "中等"
        else:
            trend_strength = "弱"

    # DMI 多空方向
    dmi_plus = latest.get("dmi_plus")
    dmi_minus = latest.get("dmi_minus")
    dmi_direction = "unknown"
    if dmi_plus is not None and dmi_minus is not None:
        if dmi_plus > dmi_minus:
            dmi_direction = "多头主导"
        else:
            dmi_direction = "空头主导"

    # 综合判断
    if ma_bullish:
        direction = "上涨"
    elif ma_bearish:
        direction = "下跌"
    elif above_ma20 and above_ma60:
        direction = "偏多震荡"
    elif not above_ma20 and not above_ma60:
        direction = "偏空震荡"
    else:
        direction = "震荡"

    notes = []
    if ma_bullish:
        notes.append("均线多头排列（5>20>60），趋势向好")
    elif ma_bearish:
        notes.append("均线空头排列（5<20<60），趋势偏弱")
    else:
        notes.append("均线排列未形成明确趋势方向")

    if adx is not None:
        notes.append(f"ADX {adx:.1f}，趋势强度{trend_strength}")

    if dmi_direction != "unknown":
        notes.append(f"DMI: {dmi_direction}")

    if above_ma20 is not None:
        notes.append(f"价格{'位于' if above_ma20 else '跌破'}20日均线上方")

    return {
        "direction": direction,
        "strength": trend_strength,
        "dmi_direction": dmi_direction,
        "ma_bullish": str(ma_bullish),
        "ma_bearish": str(ma_bearish),
        "above_ma20": str(above_ma20) if above_ma20 is not None else "unknown",
        "above_ma60": str(above_ma60) if above_ma60 is not None else "unknown",
        "notes": "；".join(notes),
    }
