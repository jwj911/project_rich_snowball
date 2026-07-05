"""多维适应度评分。

Phase 2：标量加权综合 + OOS 一致性惩罚 + 时间序列切分工具。
Phase 2B：NSGA-II 风格 Pareto 多目标排序 + 拥挤距离选择。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np


@dataclass
class FitnessScore:
    """多维适应度评分结果。"""

    total: float
    """综合评分 0-100"""

    components: dict[str, float]
    """各维度得分"""

    weights: dict[str, float]
    """各维度权重"""


@dataclass
class ParetoFront:
    """Pareto 前沿信息。"""

    rank: int
    """Pareto 层级（0=前沿，1=次前沿，...）"""

    crowding_distance: float
    """拥挤距离（前沿上密度越低值越大）"""


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
    """计算策略个体的多维适应度（标量加权）。

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


# ------------------------------------------------------------------
# Exports for strategy_evolution_agent
# ------------------------------------------------------------------

__all__ = [
    "FitnessScore",
    "compute_fitness",
    "compute_fitness_with_oos",
    "split_train_test_dates",
    "_sharpe_score",
    "_return_drawdown_score",
    "_simplicity_score",
    "_trade_count_score",
]


def compute_fitness_with_oos(
    is_backtest_result: dict[str, Any],
    oos_backtest_result: dict[str, Any] | None,
    condition_count: int = 1,
    weights: dict[str, float] | None = None,
    oos_consistency_weight: float = 0.25,
) -> FitnessScore:
    """计算带样本外一致性惩罚的适应度。

    在 IS 标量适应度的基础上，用 OOS 表现的一致性来调整 stability 维度：
    - IS/OOS Sharpe 比率越接近 1，stability 越高
    - 当 OOS 表现严重退化时，stability 分数被大幅压低

    Args:
        is_backtest_result: 样本内回测结果。
        oos_backtest_result: 样本外回测结果（None 则 stability=50 中性）。
        condition_count: 条件总数。
        weights: 维度权重。
        oos_consistency_weight: stability 维度的权重（默认 25% 替代原本的 win_rate+profit_factor 各 5%）。

    Returns:
        FitnessScore 对象，total 已包含 OOS 一致性调整。
    """
    # 使用调整后的权重：stability=0.25，缩减 win_rate 和 profit_factor
    if weights is None:
        weights = dict(_DEFAULT_WEIGHTS)
        # 从 win_rate 和 profit_factor 各借 5% 给 stability
        weights = dict(weights)
        weights["win_rate"] = max(0.05, weights.get("win_rate", 0.10) - 0.05)
        weights["profit_factor"] = max(0.05, weights.get("profit_factor", 0.10) - 0.05)

    # 基础适应度（IS）
    base = compute_fitness(is_backtest_result, condition_count=condition_count, weights=weights)

    # 计算 IS/OOS 一致性并替换 stability 维度
    if oos_backtest_result:
        oos_metrics = oos_backtest_result.get("metrics", {})
        if oos_metrics:
            is_sharpe = float(is_backtest_result.get("metrics", {}).get("sharpe", 0) or 0)
            oos_sharpe = float(oos_metrics.get("sharpe", 0) or 0)

            sharpe_ratio = oos_sharpe / is_sharpe if abs(is_sharpe) > 0.01 else (1.0 if abs(oos_sharpe) < 0.01 else 0.0)

            # 映射 IS/OOS Sharpe 比率到 0-100
            # ratio >= 1.0 → 100（OOS 不退化），ratio=0.5 → 50，ratio<0 → 0
            stability_score = max(0, min(100, sharpe_ratio * 100))
        else:
            stability_score = 50.0
    else:
        stability_score = 50.0

    # 重新计算 total：替换 stability 维度
    components = dict(base.components)
    components["stability"] = stability_score

    adjusted_weights = dict(weights)
    adjusted_weights["stability"] = oos_consistency_weight

    # 重新归一化权重
    weight_sum = sum(adjusted_weights.values())
    if weight_sum > 0:
        for k in adjusted_weights:
            adjusted_weights[k] /= weight_sum

    total = sum(components.get(k, 50) * adjusted_weights.get(k, 0) for k in adjusted_weights)
    total = round(max(0, min(100, total)), 2)

    return FitnessScore(total=total, components=components, weights=adjusted_weights)


def split_train_test_dates(
    data_start: date,
    data_end: date,
    test_ratio: float = 0.3,
    min_train_bars: int = 40,
) -> tuple[tuple[date, date], tuple[date, date]] | None:
    """按时间序列切分训练/测试日期区间。

    始终使用前 train_ratio 的数据用于训练（IS），后 test_ratio 用于测试（OOS）。
    不随机打乱 —— 保证没有前视偏差（look-ahead bias）。

    Args:
        data_start: K 线数据的最早日期。
        data_end: K 线数据的最晚日期。
        test_ratio: 测试集占比（默认 30%）。
        min_train_bars: 训练集最少天数（低于此则返回 None）。

    Returns:
        ((train_start, train_end), (test_start, test_end)) 或 None（数据不足）。
    """
    total_days = (data_end - data_start).days
    if total_days < min_train_bars * 1.5:
        return None

    test_days = int(total_days * test_ratio)
    train_days = total_days - test_days

    if train_days < min_train_bars:
        return None

    train_start = data_start
    train_end = data_start + date.resolution * train_days

    # 测试区间紧接着训练集，避免数据重叠
    test_start = train_end + date.resolution
    test_end = data_end

    if (test_end - test_start).days < 10:
        return None  # OOS 数据太少，无意义

    return (
        (train_start, train_end),
        (test_start, test_end),
    )


# ------------------------------------------------------------------
# Phase 2B: NSGA-II 风格 Pareto 多目标排序
# ------------------------------------------------------------------


def _extract_multi_objectives(
    backtest_result: dict[str, Any],
    condition_count: int = 1,
) -> np.ndarray:
    """从回测结果中提取多目标向量。

    目标维度（均最大化）：
    1. Sharpe 比率
    2. 收益回撤比（Calmar）
    3. Win Rate
    4. Profit Factor
    5. Trade Quality 倒数（越少条件越好 = 越简洁 → 最大化）
    6. 交易数量合理性

    Args:
        backtest_result: 回测结果。
        condition_count: 条件数量。

    Returns:
        shape (6,) 的 numpy 数组，所有维度最大化。
    """
    metrics = backtest_result.get("metrics", {})
    if not metrics:
        return np.zeros(6, dtype=np.float64)

    sharpe = float(metrics.get("sharpe", 0) or 0)
    annual_return = float(metrics.get("annualized_return_pct", 0) or 0)
    max_drawdown = float(metrics.get("max_drawdown_pct", 0.1) or 0.1)
    win_rate = float(metrics.get("win_rate_pct", 0) or 0) / 100.0
    profit_factor = float(metrics.get("profit_factor", 0) or 0)
    trade_count = int(metrics.get("trade_count", 0) or 0)

    # Calmar
    calmar = annual_return / max(max_drawdown, 0.1)

    # Trade quality: 5-30 trades optimal
    if trade_count < 3:
        trade_quality = 0.2
    elif trade_count < 5:
        trade_quality = 0.5
    elif trade_count <= 30:
        trade_quality = 1.0
    elif trade_count <= 60:
        trade_quality = max(0.3, 1.0 - (trade_count - 30) * 0.02)
    else:
        trade_quality = max(0.1, 0.5 - (trade_count - 60) * 0.005)

    # Simplicity: fewer conditions = better
    simplicity = 1.0 - min(condition_count / 10.0, 0.9)

    return np.array(
        [
            max(0, sharpe),
            max(0, calmar),
            win_rate,
            profit_factor,
            simplicity,
            trade_quality,
        ],
        dtype=np.float64,
    )


def _dominates(a: np.ndarray, b: np.ndarray) -> bool:
    """判断 a 是否 Pareto 支配 b（所有维度 ≥，且至少一个 >）。

    所有维度均最大化。
    """
    at_least_equal = np.all(a >= b)
    strictly_better = np.any(a > b)
    return at_least_equal and strictly_better


def non_dominated_sort(
    objectives: list[np.ndarray],
) -> list[int]:
    """NSGA-II 非支配排序。

    返回每个个体对应的 Pareto 层级（0 = 第 1 前沿，1 = 第 2 前沿，...）。

    Args:
        objectives: 每个个体的目标向量列表。

    Returns:
        Pareto 层级列表，长度与 objectives 相同。
    """
    n = len(objectives)
    if n == 0:
        return []

    ranks = [-1] * n
    dominated_by: list[list[int]] = [[] for _ in range(n)]
    dominates_count = [0] * n

    # 计算支配关系
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if _dominates(objectives[i], objectives[j]):
                dominated_by[i].append(j)
            elif _dominates(objectives[j], objectives[i]):
                dominates_count[i] += 1

    # 第 1 前沿：不被任何个体支配
    front: list[int] = []
    for i in range(n):
        if dominates_count[i] == 0:
            ranks[i] = 0
            front.append(i)

    # 迭代构建后续前沿
    current_rank = 0
    while front:
        next_front: list[int] = []
        for i in front:
            for j in dominated_by[i]:
                dominates_count[j] -= 1
                if dominates_count[j] == 0:
                    ranks[j] = current_rank + 1
                    next_front.append(j)
        front = next_front
        current_rank += 1

    return ranks


def crowding_distance(
    objectives: list[np.ndarray],
    front_indices: list[int],
) -> dict[int, float]:
    """计算前沿上个体的拥挤距离。

    拥挤距离 = 各维度上相邻个体距离之和。
    距离越大 → 个体越稀疏 → 被选中的概率越高（多样性更优）。

    Args:
        objectives: 所有个体的目标向量。
        front_indices: 当前前沿包含的个体索引列表。

    Returns:
        {个体索引: 拥挤距离} 字典。
    """
    distances: dict[int, float] = dict.fromkeys(front_indices, 0.0)
    if len(front_indices) <= 2:
        for i in front_indices:
            distances[i] = float("inf")
        return distances

    n_obj = objectives[0].shape[0]

    for m in range(n_obj):
        # 按当前目标值排序
        sorted_idx = sorted(front_indices, key=lambda i: objectives[i][m])
        obj_range = objectives[sorted_idx[-1]][m] - objectives[sorted_idx[0]][m]

        if obj_range < 1e-10:
            continue  # 目标值完全相同时跳过

        # 边界点 → 无限远
        distances[sorted_idx[0]] = float("inf")
        distances[sorted_idx[-1]] = float("inf")

        for k in range(1, len(sorted_idx) - 1):
            distances[sorted_idx[k]] += (
                objectives[sorted_idx[k + 1]][m] - objectives[sorted_idx[k - 1]][m]
            ) / obj_range

    return distances


def pareto_selection(
    population: list[Any],
    objectives: list[np.ndarray],
    n_select: int,
) -> list[int]:
    """NSGA-II 选择：按 Pareto 层级 + 拥挤距离选出 n_select 个个体。

    Args:
        population: 个体列表（用于获取 fitness 和 backtest_result）。
        objectives: 目标向量列表。
        n_select: 要选择的个体数。

    Returns:
        选中的个体索引列表。
    """
    if len(population) <= n_select:
        return list(range(len(population)))

    ranks = non_dominated_sort(objectives)

    # 按层级分组
    fronts: dict[int, list[int]] = {}
    for i, rank in enumerate(ranks):
        fronts.setdefault(rank, []).append(i)

    selected: list[int] = []
    for rank in sorted(fronts.keys()):
        front_indices = fronts[rank]
        if len(selected) + len(front_indices) <= n_select:
            selected.extend(front_indices)
        else:
            # 需要从当前前沿中挑一部分：用拥挤距离
            remaining = n_select - len(selected)
            cd = crowding_distance(objectives, front_indices)
            sorted_front = sorted(front_indices, key=lambda i: cd.get(i, 0), reverse=True)
            selected.extend(sorted_front[:remaining])
            break

    return selected


def compute_pareto_fitness(
    backtest_results: list[dict[str, Any]],
    condition_counts: list[int],
) -> list[FitnessScore]:
    """为种群计算基于 Pareto 排名的适应度分数。

    适应度 = 100 - (rank * 20) + min(crowding_distance * 5, 10)
    - 前沿个体（rank=0）: 100-110
    - 第二前沿（rank=1）: 80-90
    - ...

    这比简单加权更尊重多个目标之间的权衡。

    Args:
        backtest_results: 回测结果列表。
        condition_counts: 每个个体的条件数量列表。

    Returns:
        FitnessScore 列表（total 基于 Pareto 排名 + 拥挤距离）。
    """
    n = len(backtest_results)
    if n == 0:
        return []

    objectives = [_extract_multi_objectives(bt, cc) for bt, cc in zip(backtest_results, condition_counts, strict=False)]

    ranks = non_dominated_sort(objectives)

    # 所有前沿分组算拥挤距离
    fronts: dict[int, list[int]] = {}
    for i, rank in enumerate(ranks):
        fronts.setdefault(rank, []).append(i)

    crowding: dict[int, float] = {}
    for _rank, indices in fronts.items():
        cd = crowding_distance(objectives, indices)
        crowding.update(cd)

    scores: list[FitnessScore] = []
    for i in range(n):
        rank = ranks[i]
        cd_val = crowding.get(i, 0.0)

        # Pareto-based score: 100 - rank*20 + crowding bonus
        total = 100.0 - rank * 20.0 + min(cd_val * 5.0, 10.0)
        total = min(100.0, max(0.0, total))

        # Decompose into components for observability
        obj = objectives[i]
        components = {
            "sharpe": _sharpe_score(obj[0]),
            "return_drawdown": _return_drawdown_score(
                float(backtest_results[i].get("metrics", {}).get("annualized_return_pct", 0) or 0),
                float(backtest_results[i].get("metrics", {}).get("max_drawdown_pct", 0.1) or 0.1),
            ),
            "win_rate": _win_rate_score(float(backtest_results[i].get("metrics", {}).get("win_rate_pct", 0) or 0)),
            "profit_factor": _profit_factor_score(obj[3]),
            "trade_quality": obj[5] * 100,
            "simplicity": obj[4] * 100,
            "pareto_rank": float(rank),
            "crowding_distance": round(float(cd_val), 4),
        }

        scores.append(
            FitnessScore(
                total=round(total, 2),
                components=components,
                weights={"pareto": 1.0},
            )
        )

    return scores


# ------------------------------------------------------------------
# Exports for strategy_evolution_agent
# ------------------------------------------------------------------

__all__ = [
    "FitnessScore",
    "ParetoFront",
    "compute_fitness",
    "compute_fitness_with_oos",
    "compute_pareto_fitness",
    "non_dominated_sort",
    "crowding_distance",
    "pareto_selection",
    "split_train_test_dates",
    "_sharpe_score",
    "_return_drawdown_score",
    "_simplicity_score",
    "_trade_count_score",
]
