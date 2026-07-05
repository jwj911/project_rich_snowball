"""多周期共振分析模块。

汇总日线、4H、1H、15min、5min 等多个周期的趋势，给出综合研判。
"""

from __future__ import annotations

from typing import Any

from services.agent.trader.market_structure import identify_trend

# 默认周期权重：大周期权重更高
_DEFAULT_TIMEFRAME_WEIGHTS = {
    "1d": 1.0,
    "4h": 0.8,
    "1h": 0.6,
    "15m": 0.4,
    "5m": 0.2,
}

# 周期排序（从大到小）
_TIMEFRAME_ORDER = ["1d", "4h", "1h", "15m", "5m"]


def analyze_multi_timeframe(
    timeframe_data: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """分析多周期趋势共振。

    Args:
        timeframe_data: 键为周期（如 "1d"/"1h"），值为该周期 K 线 DataFrame 的字典。
        weights: 各周期权重，默认使用内置权重。

    Returns:
        {
            "dominant_trend": "uptrend" | "downtrend" | "sideways" | "range_bound",
            "direction": "up" | "down" | "neutral",
            "alignment_score": float,  # 0-100
            "entry_timeframe": str,    # 推荐入场周期
            "timeframe_analysis": list[dict],
            "conflict_notes": str,
            "summary": str,
        }
    """
    weights = weights or _DEFAULT_TIMEFRAME_WEIGHTS
    timeframe_analysis = []

    for tf in _TIMEFRAME_ORDER:
        df = timeframe_data.get(tf)
        if df is None or len(df) < 20:
            continue

        trend = identify_trend(df)
        timeframe_analysis.append(
            {
                "timeframe": tf,
                "trend": trend["trend"],
                "direction": trend["direction"],
                "strength": trend["strength"],
                "description": trend["description"],
                "ma_short": trend["ma_short"],
                "ma_long": trend["ma_long"],
            }
        )

    if not timeframe_analysis:
        return {
            "dominant_trend": "sideways",
            "direction": "neutral",
            "alignment_score": 0.0,
            "entry_timeframe": "",
            "timeframe_analysis": [],
            "conflict_notes": "数据不足，无法完成多周期分析",
            "summary": "数据不足，建议观望",
        }

    # 计算加权趋势得分
    up_score = 0.0
    down_score = 0.0
    total_weight = 0.0
    up_weights = 0.0
    down_weights = 0.0

    for analysis in timeframe_analysis:
        tf = analysis["timeframe"]
        weight = weights.get(tf, 0.5)
        total_weight += weight

        if analysis["direction"] == "up":
            up_score += analysis["strength"] * weight
            up_weights += weight
        elif analysis["direction"] == "down":
            down_score += analysis["strength"] * weight
            down_weights += weight

    # 主导趋势
    if up_score > down_score * 1.3 and up_score > total_weight * 20:
        dominant_trend = "uptrend"
        direction = "up"
    elif down_score > up_score * 1.3 and down_score > total_weight * 20:
        dominant_trend = "downtrend"
        direction = "down"
    elif up_score > total_weight * 10 or down_score > total_weight * 10:
        dominant_trend = "range_bound"
        direction = "neutral"
    else:
        dominant_trend = "sideways"
        direction = "neutral"

    # 共振评分：同向周期权重占比
    aligned_weight = up_weights if direction == "up" else (down_weights if direction == "down" else 0.0)
    alignment_score = (aligned_weight / total_weight * 100) if total_weight > 0 else 0.0

    # 推荐入场周期：主导方向下最小同向周期，或最大反向周期结束的位置
    entry_timeframe = _select_entry_timeframe(timeframe_analysis, direction)

    # 周期矛盾说明
    conflict_notes = _build_conflict_notes(timeframe_analysis, direction)

    # 一句话总结
    summary = _build_summary(dominant_trend, direction, alignment_score, entry_timeframe)

    return {
        "dominant_trend": dominant_trend,
        "direction": direction,
        "alignment_score": round(alignment_score, 1),
        "entry_timeframe": entry_timeframe,
        "timeframe_analysis": timeframe_analysis,
        "conflict_notes": conflict_notes,
        "summary": summary,
    }


def _select_entry_timeframe(timeframe_analysis: list[dict[str, Any]], direction: str) -> str:
    """选择推荐入场周期。"""
    if not timeframe_analysis:
        return ""

    # 从大到小排序
    ordered = sorted(timeframe_analysis, key=lambda x: _TIMEFRAME_ORDER.index(x["timeframe"]))

    if direction in ("up", "down"):
        # 找最小同向周期作为入场周期
        same_direction = [a for a in reversed(ordered) if a["direction"] == direction]
        if same_direction:
            return same_direction[0]["timeframe"]

    # 否则选择最大周期作为方向参考
    return ordered[0]["timeframe"]


def _build_conflict_notes(timeframe_analysis: list[dict[str, Any]], direction: str) -> str:
    """构建周期矛盾说明。"""
    if not timeframe_analysis:
        return ""

    if direction == "neutral":
        up_tfs = [a["timeframe"] for a in timeframe_analysis if a["direction"] == "up"]
        down_tfs = [a["timeframe"] for a in timeframe_analysis if a["direction"] == "down"]
        if up_tfs and down_tfs:
            return f"周期方向矛盾：{','.join(up_tfs)} 偏多，{','.join(down_tfs)} 偏空，建议等待方向明朗"
        return "各周期均无明显方向，处于整理阶段"

    # 主导方向明确时，指出反向小周期
    reverse_tfs = [
        a["timeframe"] for a in timeframe_analysis if a["direction"] != direction and a["direction"] != "neutral"
    ]
    if reverse_tfs:
        return f"{','.join(reverse_tfs)} 出现反向信号，注意回调风险"
    return "各周期方向一致，共振度较高"


def _build_summary(dominant_trend: str, direction: str, alignment_score: float, entry_timeframe: str) -> str:
    """构建一句话总结。"""
    trend_map = {
        "uptrend": "上涨趋势",
        "downtrend": "下跌趋势",
        "sideways": "横盘整理",
        "range_bound": "区间震荡",
    }
    trend_text = trend_map.get(dominant_trend, "方向不明")

    if direction == "neutral":
        return f"当前整体处于{trend_text}，周期共振度 {alignment_score:.0f}%，建议观望"

    return f"当前主要趋势为{trend_text}，周期共振度 {alignment_score:.0f}%，可在 {entry_timeframe} 寻找顺势入场机会"
