"""多维适应度评分。

Phase 1：简化版 — 基于回测指标的加权综合评分。
考虑风险调整收益 + 交易质量 + 简洁性，防止单指标过拟合。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FitnessScore:
    """多维适应度评分结果。"""

    total: float
    """综合评分 0-100"""

    components: dict[str, float]
    """各维度得分"""

    weights: dict[str, float]
    """各维度权重"""


# 默认权重
_DEFAULT_WEIGHTS = {
    "sharpe": 0.30,  # Sharpe 比率
    "return_drawdown": 0.25,  # 收益回撤比（Calmar-like）
    "win_rate": 0.10,  # 胜率
    "profit_factor": 0.10,  # 盈亏比
    "trade_quality": 0.10,  # 交易数量合理性
    "simplicity": 0.15,  # 简洁性（条件数惩罚）
}


def _sharpe_score(sharpe: float) -> float:
    """Sharpe 映射到 0-100 分。1.5 → 75, 2.0 → 90, 3.0 → 100。"""
    if sharpe <= 0:
        return max(0, 25 + sharpe * 10)
    return min(100, 50 + sharpe * 25)


def _return_drawdown_score(annual_return: float, max_drawdown: float) -> float:
    """收益回撤比评分。Calmar > 3 → 100 分。"""
    if max_drawdown < 0.1:
        max_drawdown = 0.1
    calmar = abs(annual_return) / max_drawdown
    if annual_return < 0:
        calmar = 0
    return min(100, calmar * 25)


def _win_rate_score(win_rate_pct: float) -> float:
    """胜率评分：40% → 50 分, 55% → 80 分, 70%+ → 100 分。"""
    if win_rate_pct <= 30:
        return max(0, win_rate_pct)
    return min(100, 30 + (win_rate_pct - 30) * 2.5)


def _profit_factor_score(profit_factor: float) -> float:
    """盈亏比评分：1.5 → 50 分, 2.0 → 75 分, 3.0+ → 100 分。"""
    if profit_factor <= 1.0:
        return max(0, profit_factor * 20)
    return min(100, 30 + profit_factor * 24)


def _trade_count_score(trade_count: int) -> float:
    """交易次数合理性评分：
    < 3: 过少，可能过拟合 → 20 分
    3-5: 偏少 → 50 分
    5-30: 合理 → 100 分
    30-60: 稍多 → 80 分
    > 60: 可能过度交易 → 50 分
    """
    if trade_count < 3:
        return 20
    if trade_count < 5:
        return 50
    if trade_count <= 30:
        return 100
    if trade_count <= 60:
        return max(50, 100 - (trade_count - 30) * 1.5)
    return max(20, 50 - (trade_count - 60) * 0.3)


def _simplicity_score(condition_count: int) -> float:
    """简洁性评分：条件越少越高，惩罚过度复杂。

    1-2: 100 分, 3: 85 分, 4: 65 分, 5: 40 分, 6+: 15 分
    """
    if condition_count <= 2:
        return 100
    if condition_count == 3:
        return 85
    if condition_count == 4:
        return 65
    if condition_count == 5:
        return 40
    return max(5, 100 - condition_count * 18)


def compute_fitness(
    backtest_result: dict[str, Any],
    condition_count: int = 1,
    weights: dict[str, float] | None = None,
) -> FitnessScore:
    """计算策略个体的多维适应度。

    Args:
        backtest_result: run_dsl_backtest() 返回的结果字典，包含 metrics 字段。
        condition_count: 入场+出场条件总数。
        weights: 维度权重（None 使用默认权重）。

    Returns:
        FitnessScore 对象。
    """
    if weights is None:
        weights = dict(_DEFAULT_WEIGHTS)

    metrics = backtest_result.get("metrics", {})
    if not metrics:
        return FitnessScore(total=0.0, components={}, weights=weights)

    sharpe_val = float(metrics.get("sharpe", 0) or 0)
    annual_return = float(metrics.get("annualized_return_pct", 0) or 0)
    max_drawdown = float(metrics.get("max_drawdown_pct", 0.1) or 0.1)
    win_rate = float(metrics.get("win_rate_pct", 0) or 0)
    profit_factor = float(metrics.get("profit_factor", 0) or 0)
    trade_count = int(metrics.get("trade_count", 0) or 0)

    components = {
        "sharpe": _sharpe_score(sharpe_val),
        "return_drawdown": _return_drawdown_score(annual_return, max_drawdown),
        "win_rate": _win_rate_score(win_rate),
        "profit_factor": _profit_factor_score(profit_factor),
        "trade_quality": _trade_count_score(trade_count),
        "simplicity": _simplicity_score(condition_count),
    }

    total = sum(components[k] * weights[k] for k in weights)
    total = round(max(0, min(100, total)), 2)

    return FitnessScore(total=total, components=components, weights=weights)
