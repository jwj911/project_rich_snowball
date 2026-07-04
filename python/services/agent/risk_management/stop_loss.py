"""止损计算模块。

提供多种止损方法的计算和评估。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


StopLossMethod = Literal["atr", "fixed_pct", "swing_low", "support_resistance", "volatility"]


@dataclass
class StopLossResult:
    """止损计算结果。"""

    stop_loss_price: float
    method: StopLossMethod
    risk_distance: float  # 止损距离
    risk_distance_pct: float  # 止损距离百分比
    notes: list[str]


def calculate_stop_loss(
    entry_price: float,
    direction: Literal["long", "short"],
    df: pd.DataFrame | None = None,
    method: StopLossMethod = "atr",
    atr_multiplier: float = 2.0,
    fixed_pct: float = 3.0,
    swing_lookback: int = 5,
    support_resistance_levels: list[float] | None = None,
    tick_size: float = 1.0,
) -> StopLossResult:
    """计算建议止损价位。

    Args:
        entry_price: 入场价格
        direction: 做多/做空
        df: K 线 DataFrame（含 atr14 等）
        method: 止损方法
        atr_multiplier: ATR 倍数
        fixed_pct: 固定百分比止损
        swing_lookback: 前低/前高回溯周期
        support_resistance_levels: 支撑/阻力位列表
        tick_size: 最小变动价位

    Returns:
        StopLossResult
    """
    notes: list[str] = []
    stop_loss = entry_price
    used_method = method

    if method == "atr":
        if df is not None and "atr14" in df.columns and len(df) > 0:
            atr_val = df["atr14"].iloc[-1]
            if direction == "long":
                stop_loss = entry_price - atr_val * atr_multiplier
            else:
                stop_loss = entry_price + atr_val * atr_multiplier
            notes.append(f"ATR 止损：ATR(14)={atr_val:.2f}，倍数={atr_multiplier}，止损={stop_loss:.2f}")
        else:
            notes.append("ATR 数据不可用，回退到固定百分比止损")
            used_method = "fixed_pct"

    if used_method == "fixed_pct":
        if direction == "long":
            stop_loss = entry_price * (1 - fixed_pct / 100)
        else:
            stop_loss = entry_price * (1 + fixed_pct / 100)
        notes.append(f"固定百分比止损：{fixed_pct}%，止损={stop_loss:.2f}")

    elif used_method == "swing_low":
        if df is not None and len(df) >= swing_lookback:
            if direction == "long":
                recent_low = df["low"].iloc[-swing_lookback:].min()
                stop_loss = recent_low - tick_size * 2
                notes.append(f"前低止损：近{swing_lookback}根K线低点={recent_low:.2f}，止损={stop_loss:.2f}")
            else:
                recent_high = df["high"].iloc[-swing_lookback:].max()
                stop_loss = recent_high + tick_size * 2
                notes.append(f"前高止损：近{swing_lookback}根K线高点={recent_high:.2f}，止损={stop_loss:.2f}")
        else:
            notes.append("K线数据不足，回退到固定百分比止损")
            used_method = "fixed_pct"

    elif used_method == "support_resistance":
        if support_resistance_levels:
            if direction == "long":
                # 找最近支撑位下方
                supports = [s for s in support_resistance_levels if s < entry_price]
                if supports:
                    nearest = max(supports)
                    stop_loss = nearest - tick_size * 2
                    notes.append(f"支撑止损：最近支撑位={nearest:.2f}，止损={stop_loss:.2f}")
                else:
                    notes.append("未找到有效支撑位，回退到固定百分比")
                    used_method = "fixed_pct"
            else:
                resistances = [r for r in support_resistance_levels if r > entry_price]
                if resistances:
                    nearest = min(resistances)
                    stop_loss = nearest + tick_size * 2
                    notes.append(f"阻力止损：最近阻力位={nearest:.2f}，止损={stop_loss:.2f}")
                else:
                    notes.append("未找到有效阻力位，回退到固定百分比")
                    used_method = "fixed_pct"
        else:
            notes.append("未提供支撑/阻力位，回退到固定百分比")
            used_method = "fixed_pct"

    elif used_method == "volatility":
        if df is not None and len(df) >= 20:
            std = df["close"].iloc[-20:].std()
            if direction == "long":
                stop_loss = entry_price - std * 2
            else:
                stop_loss = entry_price + std * 2
            notes.append(f"波动率止损：20日标准差={std:.2f}，止损={stop_loss:.2f}")
        else:
            notes.append("波动率数据不足，回退到固定百分比")
            used_method = "fixed_pct"

    # 统一止损距离计算
    risk_distance = abs(entry_price - stop_loss)
    risk_distance_pct = (risk_distance / entry_price) * 100 if entry_price > 0 else 0

    # 合理性检查
    if risk_distance_pct > 10:
        notes.append("⚠️ 止损距离超过 10%，建议重新评估入场时机或缩小止损")
    elif risk_distance_pct < 1:
        notes.append("⚠️ 止损距离小于 1%，容易被正常波动触发，建议放宽止损")

    return StopLossResult(
        stop_loss_price=round(stop_loss, 2),
        method=used_method,
        risk_distance=round(risk_distance, 2),
        risk_distance_pct=round(risk_distance_pct, 2),
        notes=notes,
    )
