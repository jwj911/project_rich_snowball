"""风控校验模块。

校验交易计划是否满足风控要求，并提供风险提示。
"""

from __future__ import annotations

from typing import Any


def validate_trade_plan(plan: dict[str, Any], account_balance: float) -> dict[str, Any]:
    """校验交易计划的风控合规性。

    Args:
        plan: generate_trade_plan 生成的交易计划。
        account_balance: 账户权益。

    Returns:
        {
            "valid": bool,
            "risk_percent": float,  # 实际风险占比
            "risk_reward_ratio": float,
            "warnings": list[str],
            "recommendations": list[str],
            "max_position_size": int,  # 风控允许的最大手数
        }
    """
    warnings: list[str] = []
    recommendations: list[str] = []

    if not plan:
        return {
            "valid": False,
            "risk_percent": 0.0,
            "risk_reward_ratio": 0.0,
            "warnings": ["交易计划为空"],
            "recommendations": ["当前不满足交易条件，建议观望"],
            "max_position_size": 0,
        }

    risk_amount = plan.get("actual_risk_amount", 0.0)
    risk_percent = risk_amount / account_balance if account_balance > 0 else 0.0
    rr = plan.get("risk_reward_ratio", 0.0)
    min_rr = plan.get("min_risk_reward", 1.5)
    position_size = plan.get("position_size", 0)
    risk_per_trade = plan.get("risk_per_trade", 0.02)
    confidence = plan.get("confidence", "low")

    valid = True

    # 1. 单笔风险校验
    if risk_percent > risk_per_trade * 1.1:
        valid = False
        warnings.append(f"单笔风险 {risk_percent * 100:.2f}% 超过设定上限 {risk_per_trade * 100:.2f}%")
        recommendations.append("降低仓位或放宽止损以控制单笔风险")

    # 2. 盈亏比校验
    if rr < min_rr:
        valid = False
        warnings.append(f"盈亏比 {rr:.2f} 低于最低要求 {min_rr:.2f}")
        recommendations.append("等待更优入场点或更远止盈位")

    # 3. 仓位合理性校验
    max_position_by_risk = (
        int((account_balance * risk_per_trade) / (risk_amount / position_size))
        if risk_amount > 0 and position_size > 0
        else 0
    )
    if position_size > max_position_by_risk and max_position_by_risk > 0:
        valid = False
        warnings.append(f"建议仓位不超过 {max_position_by_risk} 手")
        recommendations.append(f"将仓位从 {position_size} 手调整至 {max_position_by_risk} 手")

    # 4. 置信度提示
    if confidence == "low":
        recommendations.append("当前研判置信度较低，建议轻仓或观望")
    elif confidence == "medium":
        recommendations.append("当前研判置信度中等，建议控制仓位")

    # 5. 回撤控制提示
    if risk_percent > 0.05:
        warnings.append("单笔风险超过 5%，属于激进仓位")
        recommendations.append("单笔风险建议控制在 2% 以内")

    # 6. 正向建议
    if valid and confidence in ("high", "medium"):
        recommendations.append("交易计划通过风控校验，严格执行止损")

    return {
        "valid": valid,
        "risk_percent": round(risk_percent, 4),
        "risk_reward_ratio": rr,
        "warnings": warnings,
        "recommendations": recommendations,
        "max_position_size": max_position_by_risk if max_position_by_risk > 0 else position_size,
    }
