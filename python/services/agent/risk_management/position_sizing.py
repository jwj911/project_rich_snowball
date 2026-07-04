"""仓位管理模块。

提供基于账户资金、风险偏好的仓位计算。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RiskProfile = Literal["conservative", "moderate", "aggressive"]


@dataclass
class PositionSizingResult:
    """仓位计算结果。"""

    account_balance: float  # 账户资金
    risk_per_trade_pct: float  # 单次交易风险比例（%）
    risk_amount: float  # 单次最大亏损金额
    position_size_pct: float  # 建议仓位比例（%）
    max_position_size_pct: float  # 最大允许仓位比例（%）
    suggested_lots: float  # 建议手数（基于最小交易单位）
    margin_required: float  # 所需保证金
    margin_ratio: float  # 保证金占用比例
    notes: list[str]  # 说明


def calculate_position_sizing(
    account_balance: float,
    entry_price: float,
    stop_loss_price: float,
    margin_rate: float | None = None,
    contract_multiplier: float = 10.0,
    risk_profile: RiskProfile = "moderate",
    max_drawdown_pct: float = 20.0,
) -> PositionSizingResult:
    """计算建议仓位。

    基于固定风险比例法：每次交易最大亏损 = 账户资金 × 风险比例。
    根据止损距离反推仓位。

    Args:
        account_balance: 账户总资金
        entry_price: 入场价格
        stop_loss_price: 止损价格
        margin_rate: 保证金比例（如 0.1 表示 10%）
        contract_multiplier: 合约乘数（每手对应多少吨/桶/克等）
        risk_profile: 风险偏好
        max_drawdown_pct: 最大回撤限制（%）

    Returns:
        PositionSizingResult
    """
    notes: list[str] = []

    # 1. 确定风险比例
    risk_profile_config: dict[RiskProfile, dict[str, float]] = {
        "conservative": {
            "risk_per_trade": 1.0,  # 单次 1%
            "max_position": 30.0,  # 最大总仓位 30%
            "target_rr": 1.5,  # 最低风险收益比
        },
        "moderate": {
            "risk_per_trade": 2.0,
            "max_position": 50.0,
            "target_rr": 2.0,
        },
        "aggressive": {
            "risk_per_trade": 3.0,
            "max_position": 70.0,
            "target_rr": 2.5,
        },
    }

    config = risk_profile_config[risk_profile]
    risk_per_trade_pct = config["risk_per_trade"]
    max_position_pct = config["max_position"]

    notes.append(f"风险偏好：{risk_profile}（单次风险 {risk_per_trade_pct}%，最大仓位 {max_position_pct}%）")

    # 2. 计算单次最大亏损金额
    risk_amount = account_balance * (risk_per_trade_pct / 100)

    # 3. 计算每手最大亏损
    price_distance = abs(entry_price - stop_loss_price)
    if price_distance <= 0:
        notes.append("⚠️ 止损距离为零，无法计算仓位，请重新设置止损")
        return PositionSizingResult(
            account_balance=account_balance,
            risk_per_trade_pct=risk_per_trade_pct,
            risk_amount=risk_amount,
            position_size_pct=0.0,
            max_position_size_pct=max_position_pct,
            suggested_lots=0.0,
            margin_required=0.0,
            margin_ratio=0.0,
            notes=notes,
        )

    loss_per_lot = price_distance * contract_multiplier

    # 4. 反推建议手数
    suggested_lots = risk_amount / loss_per_lot if loss_per_lot > 0 else 0

    # 5. 计算仓位比例（基于名义价值）
    notional_value = suggested_lots * entry_price * contract_multiplier
    position_size_pct = (notional_value / account_balance) * 100 if account_balance > 0 else 0

    # 6. 限制检查
    if position_size_pct > max_position_pct:
        notes.append(f"⚠️ 计算仓位 {position_size_pct:.1f}% 超过最大限制 {max_position_pct}%，已调整")
        position_size_pct = max_position_pct
        suggested_lots = (max_position_pct / 100 * account_balance) / (entry_price * contract_multiplier)
        risk_amount = suggested_lots * loss_per_lot
        risk_per_trade_pct = (risk_amount / account_balance) * 100 if account_balance > 0 else 0

    # 7. 保证金计算
    margin_required = 0.0
    margin_ratio = 0.0
    if margin_rate is not None and margin_rate > 0:
        margin_required = notional_value * margin_rate
        margin_ratio = (margin_required / account_balance) * 100 if account_balance > 0 else 0
        notes.append(f"保证金占用：{margin_ratio:.1f}%（所需 {margin_required:.0f}）")

    # 8. 回撤关联检查
    max_trades_before_drawdown = max_drawdown_pct / risk_per_trade_pct if risk_per_trade_pct > 0 else float("inf")
    notes.append(f"连续 {max_trades_before_drawdown:.0f} 次止损将触及最大回撤限制（{max_drawdown_pct}%）")

    # 9. 建议调整
    if position_size_pct > 50:
        notes.append("⚠️ 建议仓位较高，建议分批建仓或降低单笔风险比例")
    elif position_size_pct < 5:
        notes.append("⚠️ 建议仓位较低，可能因止损距离过宽导致，建议重新评估止损位置")

    notes.append(f"每手止损距离：{price_distance:.2f}，每手最大亏损：{loss_per_lot:.0f}")
    notes.append(f"建议建仓：{suggested_lots:.2f} 手，名义价值 {notional_value:.0f}")

    return PositionSizingResult(
        account_balance=account_balance,
        risk_per_trade_pct=risk_per_trade_pct,
        risk_amount=risk_amount,
        position_size_pct=position_size_pct,
        max_position_size_pct=max_position_pct,
        suggested_lots=round(suggested_lots, 2),
        margin_required=margin_required,
        margin_ratio=margin_ratio,
        notes=notes,
    )
