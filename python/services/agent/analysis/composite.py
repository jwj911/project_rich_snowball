"""综合评分模块。

整合趋势、形态、背离、指标等多维度信息，给出综合评分（0-100）和多空结论。
"""

from __future__ import annotations

import pandas as pd

from services.agent.analysis.divergence import detect_divergence
from services.agent.analysis.pattern import detect_patterns
from services.agent.analysis.trend import analyze_trend


def composite_score(df: pd.DataFrame) -> dict[str, object]:
    """综合技术分析评分。

    评分维度：
    - 趋势（0-30）：均线排列 + 价格位置 + ADX
    - 动量（0-25）：MACD + RSI + KDJ + WR
    - 量能（0-15）：成交量比率 + OBV
    - 形态（0-15）：K线形态 + 结构形态
    - 波动（0-15）：ATR + BOLL 位置

    总分 0-100：
    - >= 70：偏强
    - 40-69：震荡
    - < 40：偏弱
    """
    if len(df) < 20:
        return {
            "score": None,
            "rating": "数据不足",
            "direction": "unknown",
            "details": {},
            "notes": "需要至少 20 根 K 线数据",
        }

    latest = df.iloc[-1]
    close = latest["close"]

    scores = {}

    # 1. 趋势评分 (0-30)
    trend = analyze_trend(df)
    trend_score = 15  # 中性基准
    if trend["direction"] in ["上涨", "偏多震荡"]:
        trend_score += 10
        if trend["strength"] == "强":
            trend_score += 5
    elif trend["direction"] in ["下跌", "偏空震荡"]:
        trend_score -= 10
        if trend["strength"] == "强":
            trend_score -= 5
    scores["trend"] = max(0, min(30, trend_score))

    # 2. 动量评分 (0-25)
    momentum_score = 12.5

    # MACD
    macd_bar = latest.get("macd_bar")
    if macd_bar is not None:
        if macd_bar > 0:
            momentum_score += 3
        else:
            momentum_score -= 3

    # RSI
    rsi24 = latest.get("rsi24")
    if rsi24 is not None:
        if rsi24 > 70:
            momentum_score -= 2  # 超买
        elif rsi24 > 50:
            momentum_score += 2
        elif rsi24 < 30:
            momentum_score += 2  # 超卖（潜在反弹）
        else:
            momentum_score -= 2

    # KDJ
    kdj_j = latest.get("kdj_j")
    if kdj_j is not None:
        if kdj_j > 80:
            momentum_score -= 2
        elif kdj_j < 20:
            momentum_score += 2

    # WR
    wr14 = latest.get("wr14")
    if wr14 is not None:
        if wr14 < -80:
            momentum_score += 2  # 超卖
        elif wr14 > -20:
            momentum_score -= 2  # 超买

    scores["momentum"] = max(0, min(25, momentum_score))

    # 3. 量能评分 (0-15)
    volume_score = 7.5
    vol_ratio = latest.get("vol_ratio")
    if vol_ratio is not None:
        if vol_ratio > 1.5:
            volume_score += 4  # 放量
        elif vol_ratio > 1.2:
            volume_score += 2
        elif vol_ratio < 0.8:
            volume_score -= 3  # 缩量

    # OBV 趋势（最近 5 日 vs 20 日）
    obv_5 = df["obv"].iloc[-5:].mean() if len(df) >= 5 else latest.get("obv")
    obv_20 = df["obv"].iloc[-20:].mean() if len(df) >= 20 else latest.get("obv")
    if obv_5 is not None and obv_20 is not None:
        if obv_5 > obv_20:
            volume_score += 2
        else:
            volume_score -= 2

    scores["volume"] = max(0, min(15, volume_score))

    # 4. 形态评分 (0-15)
    pattern = detect_patterns(df)
    pattern_score = 7.5
    if "双底" in pattern["pattern"] or "W底" in pattern["pattern"]:
        pattern_score += 5
    elif "双顶" in pattern["pattern"] or "M头" in pattern["pattern"]:
        pattern_score -= 5
    elif "三角形收敛" in pattern["pattern"]:
        pattern_score += 0  # 中性，等待突破

    if any("吞没" in n and "看涨" in n for n in pattern["notes"].split("；")):
        pattern_score += 3
    if any("吞没" in n and "看跌" in n for n in pattern["notes"].split("；")):
        pattern_score -= 3
    if "锤子线" in pattern["notes"]:
        pattern_score += 2
    if "上吊线" in pattern["notes"]:
        pattern_score -= 2

    scores["pattern"] = max(0, min(15, pattern_score))

    # 5. 波动评分 (0-15)
    volatility_score = 7.5

    # BOLL 位置
    boll_upper = latest.get("boll_upper")
    boll_lower = latest.get("boll_lower")
    boll_mid = latest.get("boll_mid")
    if boll_upper is not None and boll_lower is not None and boll_mid is not None:
        boll_width = boll_upper - boll_lower
        if boll_width > 0:
            boll_position = (close - boll_lower) / boll_width
            if boll_position > 0.8:
                volatility_score -= 3  # 接近上轨，压力
            elif boll_position < 0.2:
                volatility_score += 3  # 接近下轨，支撑

    # ATR 相对水平
    atr14 = latest.get("atr14")
    if atr14 is not None and boll_mid is not None and boll_mid > 0:
        atr_ratio = atr14 / boll_mid
        if atr_ratio > 0.05:  # 波动较大
            volatility_score += 0  # 中性，波动大是风险不是方向

    scores["volatility"] = max(0, min(15, volatility_score))

    # 总分
    total = sum(scores.values())

    # 背离调整
    divergence = detect_divergence(df)
    if "顶背离" in divergence["divergence"]:
        total -= 8
    elif "底背离" in divergence["divergence"]:
        total += 8

    total = max(0, min(100, total))

    # 评级
    if total >= 70:
        rating = "偏强"
        direction = "偏多"
    elif total >= 55:
        rating = "中性偏强"
        direction = "偏多"
    elif total >= 45:
        rating = "中性"
        direction = "震荡"
    elif total >= 30:
        rating = "中性偏弱"
        direction = "偏空"
    else:
        rating = "偏弱"
        direction = "偏空"

    # 综合建议
    notes = []
    notes.append(f"综合评分 {total:.1f}/100，评级：{rating}")
    notes.append(f"趋势维度：{scores['trend']:.1f}/30 — {trend['notes']}")
    notes.append(
        f"动量维度：{scores['momentum']:.1f}/25 — RSI:{latest.get('rsi24', 'N/A'):.1f}, MACD柱状:{latest.get('macd_bar', 'N/A'):.2f}"
    )
    notes.append(f"量能维度：{scores['volume']:.1f}/15 — 量比:{latest.get('vol_ratio', 'N/A'):.2f}")
    notes.append(f"形态维度：{scores['pattern']:.1f}/15 — {pattern['pattern']}")
    notes.append(f"波动维度：{scores['volatility']:.1f}/15")
    if divergence["divergence"] != "无":
        notes.append(f"背离信号：{divergence['notes']}")

    # 操作建议
    if direction == "偏多":
        if total >= 70:
            notes.append("建议：趋势较强，回调可考虑偏多思路")
        else:
            notes.append("建议：偏多思路，但需确认量能配合")
    elif direction == "偏空":
        if total <= 30:
            notes.append("建议：趋势偏弱，反弹可考虑偏空思路")
        else:
            notes.append("建议：偏空思路，注意下方支撑")
    else:
        notes.append("建议：震荡格局，等待方向明确")

    return {
        "score": round(total, 1),
        "rating": rating,
        "direction": direction,
        "details": {k: round(v, 1) for k, v in scores.items()},
        "trend_summary": trend,
        "pattern_summary": pattern,
        "divergence_summary": divergence,
        "notes": "\n".join(notes),
    }
