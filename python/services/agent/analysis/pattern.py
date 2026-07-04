"""形态识别模块。

基于高低点结构识别常见 K 线形态。
"""

from __future__ import annotations

import pandas as pd


def _find_pivots(df: pd.DataFrame, window: int = 5) -> tuple[list[int], list[int]]:
    """寻找局部高点和低点索引。

    高点：window 日内最高
    低点：window 日内最低
    """
    highs = df["high"].values
    lows = df["low"].values

    high_idx = []
    low_idx = []

    for i in range(window, len(df) - window):
        if highs[i] == max(highs[i - window : i + window + 1]):
            high_idx.append(i)
        if lows[i] == min(lows[i - window : i + window + 1]):
            low_idx.append(i)

    return high_idx, low_idx


def detect_patterns(df: pd.DataFrame) -> dict[str, str]:
    """检测常见形态。

    当前简化实现：头肩顶/底、双顶/底、三角形收敛。
    """
    if len(df) < 30:
        return {"pattern": "数据不足", "notes": "需要至少 30 根 K 线数据"}

    high_idx, low_idx = _find_pivots(df, window=3)

    if len(high_idx) < 3 or len(low_idx) < 3:
        return {"pattern": "未识别", "notes": "未找到足够的高低点结构"}

    highs = df.iloc[high_idx]["high"].values
    lows = df.iloc[low_idx]["low"].values

    notes = []
    pattern = "未识别"

    # 双顶检测：最近 3 个高点，中间一个略高，前后接近
    if len(high_idx) >= 3:
        recent_highs = high_idx[-3:]
        h_vals = [df.iloc[i]["high"] for i in recent_highs]
        if h_vals[1] > h_vals[0] and h_vals[1] > h_vals[2] and abs(h_vals[0] - h_vals[2]) / (h_vals[1] + 1e-10) < 0.03:
            pattern = "双顶（M头）"
            notes.append(f"近期高点结构类似双顶：{h_vals[0]:.2f} - {h_vals[1]:.2f} - {h_vals[2]:.2f}")

    # 双底检测：最近 3 个低点，中间一个略低，前后接近
    if len(low_idx) >= 3 and pattern == "未识别":
        recent_lows = low_idx[-3:]
        l_vals = [df.iloc[i]["low"] for i in recent_lows]
        if l_vals[1] < l_vals[0] and l_vals[1] < l_vals[2] and abs(l_vals[0] - l_vals[2]) / (l_vals[1] + 1e-10) < 0.03:
            pattern = "双底（W底）"
            notes.append(f"近期低点结构类似双底：{l_vals[0]:.2f} - {l_vals[1]:.2f} - {l_vals[2]:.2f}")

    # 三角形收敛：高点逐步降低 + 低点逐步抬高
    if len(high_idx) >= 3 and len(low_idx) >= 3 and pattern == "未识别":
        recent_h = highs[-3:]
        recent_l = lows[-3:]
        if recent_h[0] > recent_h[1] > recent_h[2] and recent_l[0] < recent_l[1] < recent_l[2]:
            pattern = "三角形收敛"
            notes.append("近期高点逐步降低、低点逐步抬高，形成三角形收敛")

    # K 线组合（最近 3 根）
    last3 = df.iloc[-3:]
    o = last3["open"].values
    c = last3["close"].values
    h = last3["high"].values
    lv = last3["low"].values

    # 吞没形态
    if len(c) >= 2:
        if c[-2] < o[-2] and c[-1] > o[-1] and c[-1] > o[-2] and o[-1] < c[-2]:
            notes.append("最近出现看涨吞没形态")
        elif c[-2] > o[-2] and c[-1] < o[-1] and c[-1] < o[-2] and o[-1] > c[-2]:
            notes.append("最近出现看跌吞没形态")

    # 锤子线 / 上吊线（简化：实体小，下影线长）
    body = abs(c[-1] - o[-1])
    lower_shadow = min(o[-1], c[-1]) - lv[-1]
    upper_shadow = h[-1] - max(o[-1], c[-1])
    if body > 0 and lower_shadow / body > 2 and upper_shadow / body < 0.5:
        if c[-1] > o[-1]:
            notes.append("最近出现锤子线（潜在反转信号）")
        else:
            notes.append("最近出现上吊线（潜在反转信号）")

    # 十字星
    if body / (h[-1] - lv[-1] + 1e-10) < 0.1:
        notes.append("最近出现十字星（多空平衡）")

    if not notes:
        notes.append("未识别到明显形态")

    return {
        "pattern": pattern,
        "notes": "；".join(notes),
    }
