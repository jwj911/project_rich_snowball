"""背离检测模块。

检测价格与指标之间的顶背离和底背离。
"""

from __future__ import annotations

import pandas as pd


def _find_local_extrema(series: pd.Series, window: int = 5, is_high: bool = True) -> list[tuple[int, float]]:
    """寻找局部极值点（索引, 值）。"""
    extrema = []
    vals = series.values
    for i in range(window, len(series) - window):
        if (
            is_high
            and vals[i] == max(vals[i - window : i + window + 1])
            or not is_high
            and vals[i] == min(vals[i - window : i + window + 1])
        ):
            extrema.append((i, vals[i]))
    return extrema


def detect_divergence(df: pd.DataFrame) -> dict[str, str]:
    """检测价格与 MACD/RSI/KDJ 的背离。

    返回背离类型和说明。
    """
    if len(df) < 20:
        return {"divergence": "数据不足", "notes": "需要至少 20 根 K 线数据"}

    close = df["close"]

    results = []

    # MACD 背离
    macd_bar = df.get("macd_bar")
    if macd_bar is not None:
        high_pts = _find_local_extrema(close, 5, True)[-3:]
        macd_high_pts = _find_local_extrema(macd_bar, 5, True)[-3:]

        if (
            len(high_pts) >= 2
            and len(macd_high_pts) >= 2
            and (
                close.iloc[high_pts[-1][0]] > close.iloc[high_pts[-2][0]]
                and macd_high_pts[-1][1] < macd_high_pts[-2][1]
            )
        ):
            results.append("MACD 顶背离：价格创新高，MACD 未创新高")

        low_pts = _find_local_extrema(close, 5, False)[-3:]
        macd_low_pts = _find_local_extrema(macd_bar, 5, False)[-3:]

        if (
            len(low_pts) >= 2
            and len(macd_low_pts) >= 2
            and close.iloc[low_pts[-1][0]] < close.iloc[low_pts[-2][0]]
            and macd_low_pts[-1][1] > macd_low_pts[-2][1]
        ):
            results.append("MACD 底背离：价格创新低，MACD 未创新低")

    # RSI 背离
    rsi24 = df.get("rsi24")
    if rsi24 is not None:
        rsi_high_pts = _find_local_extrema(rsi24, 5, True)[-3:]
        rsi_low_pts = _find_local_extrema(rsi24, 5, False)[-3:]

        high_pts = _find_local_extrema(close, 5, True)[-3:]
        low_pts = _find_local_extrema(close, 5, False)[-3:]

        if (
            len(high_pts) >= 2
            and len(rsi_high_pts) >= 2
            and close.iloc[high_pts[-1][0]] > close.iloc[high_pts[-2][0]]
            and rsi_high_pts[-1][1] < rsi_high_pts[-2][1]
        ):
            results.append("RSI 顶背离：价格创新高，RSI 未创新高")

        if (
            len(low_pts) >= 2
            and len(rsi_low_pts) >= 2
            and close.iloc[low_pts[-1][0]] < close.iloc[low_pts[-2][0]]
            and rsi_low_pts[-1][1] > rsi_low_pts[-2][1]
        ):
            results.append("RSI 底背离：价格创新低，RSI 未创新低")

    # KDJ 背离 (J 值)
    kdj_j = df.get("kdj_j")
    if kdj_j is not None:
        j_high_pts = _find_local_extrema(kdj_j, 5, True)[-3:]
        j_low_pts = _find_local_extrema(kdj_j, 5, False)[-3:]

        high_pts = _find_local_extrema(close, 5, True)[-3:]
        low_pts = _find_local_extrema(close, 5, False)[-3:]

        if (
            len(high_pts) >= 2
            and len(j_high_pts) >= 2
            and close.iloc[high_pts[-1][0]] > close.iloc[high_pts[-2][0]]
            and j_high_pts[-1][1] < j_high_pts[-2][1]
        ):
            results.append("KDJ 顶背离：价格创新高，J 值未创新高")

        if (
            len(low_pts) >= 2
            and len(j_low_pts) >= 2
            and close.iloc[low_pts[-1][0]] < close.iloc[low_pts[-2][0]]
            and j_low_pts[-1][1] > j_low_pts[-2][1]
        ):
            results.append("KDJ 底背离：价格创新低，J 值未创新低")

    if not results:
        return {"divergence": "无", "notes": "未检测到明显背离信号"}

    divergence_type = "顶背离" if any("顶" in r for r in results) else "底背离"

    return {
        "divergence": divergence_type,
        "notes": "；".join(results),
    }
