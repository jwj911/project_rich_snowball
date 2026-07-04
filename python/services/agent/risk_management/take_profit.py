"""止盈计算模块。

提供风险收益比止盈、移动止盈、目标位止盈等方法。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


TakeProfitMethod = Literal["risk_reward", "atr", "resistance", "trailing", "fixed_pct"]


@dataclass
class TakeProfitResult:
    """止盈计算结果。"""

    take_profit_price: float
    method: TakeProfitMethod
    reward_distance: float
    reward_distance_pct: float
    risk_reward_ratio: float
    trailing_trigger: float | None  # 移动止盈触发价格
    trailing_stop: float | None  # 移动止盈价位
    notes: list[str]


def calculate_take_profit(
    entry_price: float,
    stop_loss_price: float,
    direction: Literal["long", "short"],
    df: pd.DataFrame | None = None,
    method: TakeProfitMethod = "risk_reward",
    target_rr: float = 2.0,
    atr_multiplier: float = 3.0,
    resistance_levels: list[float] | None = None,
    trailing_pct: float = 5.0,
    fixed_pct: float = 6.0,
) -> TakeProfitResult:
    """计算建议止盈价位。

    Args:
        entry_price: 入场价格
        stop_loss_price: 止损价格
        direction: 做多/做空
        df: K 线 DataFrame
        method: 止盈方法
        target_rr: 目标风险收益比
        atr_multiplier: ATR 倍数（用于 ATR 止盈）
        resistance_levels: 阻力/支撑目标位
        trailing_pct: 移动止盈回撤百分比
        fixed_pct: 固定百分比止盈

    Returns:
        TakeProfitResult
    """
    notes: list[str] = []
    take_profit = entry_price
    used_method = method
    risk_distance = abs(entry_price - stop_loss_price)
    trailing_trigger = None
    trailing_stop = None

    if method == "risk_reward":
        if direction == "long":
            take_profit = entry_price + risk_distance * target_rr
        else:
            take_profit = entry_price - risk_distance * target_rr
        notes.append(f"风险收益比止盈：目标 R:R = 1:{target_rr}，止盈={take_profit:.2f}")

    elif method == "atr":
        if df is not None and "atr14" in df.columns and len(df) > 0:
            atr_val = df["atr14"].iloc[-1]
            if direction == "long":
                take_profit = entry_price + atr_val * atr_multiplier
            else:
                take_profit = entry_price - atr_val * atr_multiplier
            notes.append(f"ATR 止盈：ATR(14)={atr_val:.2f}，倍数={atr_multiplier}，止盈={take_profit:.2f}")
        else:
            notes.append("ATR 数据不可用，回退到风险收益比")
            used_method = "risk_reward"
            if direction == "long":
                take_profit = entry_price + risk_distance * target_rr
            else:
                take_profit = entry_price - risk_distance * target_rr

    elif method == "resistance":
        if resistance_levels:
            if direction == "long":
                targets = [r for r in resistance_levels if r > entry_price]
                if targets:
                    nearest = min(targets)
                    take_profit = nearest
                    notes.append(f"阻力位止盈：目标位={nearest:.2f}，止盈={take_profit:.2f}")
                else:
                    notes.append("未找到上方目标位，回退到风险收益比")
                    used_method = "risk_reward"
                    take_profit = entry_price + risk_distance * target_rr
            else:
                targets = [r for r in resistance_levels if r < entry_price]
                if targets:
                    nearest = max(targets)
                    take_profit = nearest
                    notes.append(f"支撑位止盈：目标位={nearest:.2f}，止盈={take_profit:.2f}")
                else:
                    notes.append("未找到下方目标位，回退到风险收益比")
                    used_method = "risk_reward"
                    take_profit = entry_price - risk_distance * target_rr
        else:
            notes.append("未提供目标位，回退到风险收益比")
            used_method = "risk_reward"
            take_profit = entry_price + (risk_distance * target_rr if direction == "long" else -risk_distance * target_rr)

    elif method == "trailing":
        # 移动止盈：先设一个目标触发价，触发后按回撤百分比跟踪
        trigger_rr = target_rr * 0.7  # 触发价按 70% 目标 R:R
        if direction == "long":
            trailing_trigger = entry_price + risk_distance * trigger_rr
            # 触发后，如果回撤 trailing_pct，则止盈
            trailing_stop = trailing_trigger * (1 - trailing_pct / 100)
        else:
            trailing_trigger = entry_price - risk_distance * trigger_rr
            trailing_stop = trailing_trigger * (1 + trailing_pct / 100)
        take_profit = trailing_trigger  # 初始目标价
        notes.append(
            f"移动止盈：触发价={trailing_trigger:.2f}（R:R 1:{trigger_rr:.1f}），"
            f"触发后回撤 {trailing_pct}% 止盈，跟踪止损={trailing_stop:.2f}"
        )

    elif method == "fixed_pct":
        if direction == "long":
            take_profit = entry_price * (1 + fixed_pct / 100)
        else:
            take_profit = entry_price * (1 - fixed_pct / 100)
        notes.append(f"固定百分比止盈：{fixed_pct}%，止盈={take_profit:.2f}")

    # 计算收益距离和风险收益比
    reward_distance = abs(take_profit - entry_price)
    reward_distance_pct = (reward_distance / entry_price) * 100 if entry_price > 0 else 0
    actual_rr = reward_distance / risk_distance if risk_distance > 0 else 0

    notes.append(f"止损距离：{risk_distance:.2f}（{risk_distance / entry_price * 100:.1f}%）")
    notes.append(f"止盈距离：{reward_distance:.2f}（{reward_distance_pct:.1f}%）")
    notes.append(f"实际风险收益比：1:{actual_rr:.2f}")

    if actual_rr < 1.5:
        notes.append("⚠️ 风险收益比偏低（<1.5），建议重新评估入场或寻找更优目标位")
    elif actual_rr >= 3.0:
        notes.append("✅ 风险收益比优秀（≥3.0），盈亏比有利")

    return TakeProfitResult(
        take_profit_price=round(take_profit, 2),
        method=used_method,
        reward_distance=round(reward_distance, 2),
        reward_distance_pct=round(reward_distance_pct, 2),
        risk_reward_ratio=round(actual_rr, 2),
        trailing_trigger=round(trailing_trigger, 2) if trailing_trigger else None,
        trailing_stop=round(trailing_stop, 2) if trailing_stop else None,
        notes=notes,
    )
