"""回撤控制模块。

提供账户回撤监控、单日亏损限制、连续亏损控制等规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RiskLevel = Literal["low", "medium", "high"]


@dataclass
class DrawdownControlResult:
    """回撤控制规则。"""

    max_daily_loss_pct: float  # 单日最大亏损比例
    max_drawdown_pct: float  # 总最大回撤比例
    max_consecutive_losses: int  # 最大连续亏损次数
    position_size_reduction: float  # 回撤时的仓位缩减比例
    trading_halt_drawdown: float  # 暂停交易回撤阈值
    notes: list[str]


@dataclass
class RiskManagementPlan:
    """完整风控计划。"""

    position_sizing: dict
    stop_loss: dict
    take_profit: dict
    drawdown_control: DrawdownControlResult
    daily_limits: dict
    total_limits: dict
    notes: list[str]


def calculate_drawdown_control(
    account_balance: float,
    risk_level: RiskLevel = "medium",
) -> DrawdownControlResult:
    """计算回撤控制规则。

    Args:
        account_balance: 账户总资金
        risk_level: 风险等级

    Returns:
        DrawdownControlResult
    """
    notes: list[str] = []

    configs: dict[RiskLevel, dict[str, float]] = {
        "low": {
            "max_daily_loss": 2.0,
            "max_drawdown": 10.0,
            "position_reduction": 50.0,
            "trading_halt": 15.0,
        },
        "medium": {
            "max_daily_loss": 3.0,
            "max_drawdown": 20.0,
            "position_reduction": 50.0,
            "trading_halt": 30.0,
        },
        "high": {
            "max_daily_loss": 5.0,
            "max_drawdown": 30.0,
            "position_reduction": 50.0,
            "trading_halt": 40.0,
        },
    }

    config = configs[risk_level]

    max_daily_loss = account_balance * (config["max_daily_loss"] / 100)
    max_drawdown = account_balance * (config["max_drawdown"] / 100)
    trading_halt = account_balance * (config["trading_halt"] / 100)

    # 最大连续亏损次数：基于凯利简化
    # 假设胜率 40%，单次风险 2%，最大回撤 20% -> 约 10 次
    # 简化公式：连续亏损次数 = max_drawdown / (单次风险 * 1.5 倍安全系数)
    avg_risk_per_trade = 2.0  # 假设平均 2%
    max_consecutive = int(config["max_drawdown"] / (avg_risk_per_trade * 1.5))
    max_consecutive = max(3, min(max_consecutive, 15))

    notes.append(f"风险等级：{risk_level}")
    notes.append(f"单日最大亏损：{config['max_daily_loss']}%（{max_daily_loss:.0f}）")
    notes.append(f"总最大回撤：{config['max_drawdown']}%（{max_drawdown:.0f}）")
    notes.append(f"回撤 {config['position_reduction']}% 时仓位缩减一半")
    notes.append(f"回撤 {config['trading_halt']}% 时暂停交易，需复盘后重启")
    notes.append(f"建议最大连续亏损：{max_consecutive} 次后强制暂停")

    return DrawdownControlResult(
        max_daily_loss_pct=config["max_daily_loss"],
        max_drawdown_pct=config["max_drawdown"],
        max_consecutive_losses=max_consecutive,
        position_size_reduction=config["position_reduction"] / 100,
        trading_halt_drawdown=config["trading_halt"] / 100,
        notes=notes,
    )


def generate_risk_management_plan(
    account_balance: float,
    entry_price: float,
    direction: Literal["long", "short"],
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    risk_level: RiskLevel = "medium",
    margin_rate: float | None = None,
    contract_multiplier: float = 10.0,
    tick_size: float = 1.0,
    df: object | None = None,  # pd.DataFrame, but avoid direct import in type hint for flexibility
    support_levels: list[float] | None = None,
    resistance_levels: list[float] | None = None,
) -> RiskManagementPlan:
    """生成完整风控计划。

    整合仓位管理、止损、止盈、回撤控制等所有风控维度。
    """
    import pandas as pd

    from services.agent.risk_management.position_sizing import calculate_position_sizing
    from services.agent.risk_management.stop_loss import calculate_stop_loss
    from services.agent.risk_management.take_profit import calculate_take_profit

    notes: list[str] = []

    # 1. 回撤控制
    drawdown = calculate_drawdown_control(account_balance, risk_level)

    # 2. 止损（如果未提供）
    sl_result = None
    if stop_loss_price is None:
        df_pd = df if isinstance(df, pd.DataFrame) else None
        sl_result = calculate_stop_loss(
            entry_price=entry_price,
            direction=direction,
            df=df_pd,
            method="atr" if df_pd is not None and "atr14" in df_pd.columns else "fixed_pct",
            support_resistance_levels=support_levels if direction == "long" else resistance_levels,
            tick_size=tick_size,
        )
        stop_loss_price = sl_result.stop_loss_price
        notes.extend(sl_result.notes)
    else:
        notes.append(f"用户自定义止损：{stop_loss_price}")

    # 3. 止盈（如果未提供）
    tp_result = None
    if take_profit_price is None:
        df_pd = df if isinstance(df, pd.DataFrame) else None
        tp_result = calculate_take_profit(
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            direction=direction,
            df=df_pd,
            method="risk_reward",
            target_rr=2.0,
            resistance_levels=resistance_levels if direction == "long" else support_levels,
        )
        take_profit_price = tp_result.take_profit_price
        notes.extend(tp_result.notes)
    else:
        notes.append(f"用户自定义止盈：{take_profit_price}")

    # 4. 仓位管理
    position = calculate_position_sizing(
        account_balance=account_balance,
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        margin_rate=margin_rate,
        contract_multiplier=contract_multiplier,
        risk_profile="moderate" if risk_level == "medium" else ("conservative" if risk_level == "low" else "aggressive"),
        max_drawdown_pct=drawdown.max_drawdown_pct,
    )
    notes.extend(position.notes)

    # 5. 汇总规则
    risk_distance = abs(entry_price - stop_loss_price)
    reward_distance = abs(take_profit_price - entry_price)
    rr = reward_distance / risk_distance if risk_distance > 0 else 0

    total_limits = {
        "max_total_risk_pct": drawdown.max_drawdown_pct,
        "max_daily_risk_pct": drawdown.max_daily_loss_pct,
        "max_single_trade_risk_pct": position.risk_per_trade_pct,
        "max_position_size_pct": position.max_position_size_pct,
    }

    daily_limits = {
        "max_daily_loss_amount": account_balance * (drawdown.max_daily_loss_pct / 100),
        "max_daily_trades": 5,  # 建议上限
        "max_daily_risk_pct": drawdown.max_daily_loss_pct,
    }

    return RiskManagementPlan(
        position_sizing={
            "account_balance": account_balance,
            "risk_per_trade_pct": position.risk_per_trade_pct,
            "risk_amount": position.risk_amount,
            "suggested_lots": position.suggested_lots,
            "position_size_pct": position.position_size_pct,
            "max_position_size_pct": position.max_position_size_pct,
            "margin_required": position.margin_required,
            "margin_ratio": position.margin_ratio,
        },
        stop_loss={
            "entry_price": entry_price,
            "stop_loss_price": stop_loss_price,
            "risk_distance": risk_distance,
            "risk_distance_pct": (risk_distance / entry_price) * 100 if entry_price > 0 else 0,
            "method": sl_result.method if sl_result else "custom",
        },
        take_profit={
            "take_profit_price": take_profit_price,
            "reward_distance": reward_distance,
            "reward_distance_pct": (reward_distance / entry_price) * 100 if entry_price > 0 else 0,
            "risk_reward_ratio": rr,
            "method": tp_result.method if tp_result else "custom",
            "trailing_trigger": tp_result.trailing_trigger if tp_result else None,
            "trailing_stop": tp_result.trailing_stop if tp_result else None,
        },
        drawdown_control=drawdown,
        daily_limits=daily_limits,
        total_limits=total_limits,
        notes=notes,
    )
