"""遗传算子。

Phase 1：简单 GA — 锦标赛选择 + 阈值变异 + 精英保留。
"""

from __future__ import annotations

import copy
import logging
import random

from services.agent.evolution.strategy_population import StrategyIndividual

logger = logging.getLogger(__name__)


def tournament_select(
    population: list[StrategyIndividual],
    tournament_size: int = 3,
) -> StrategyIndividual:
    """锦标赛选择。

    随机选 tournament_size 个个体，返回适应度最高的。
    适应度为 None 的个体被选中概率极低（适应度假定为 -inf）。

    Args:
        population: 种群。
        tournament_size: 锦标赛规模。

    Returns:
        选中的个体（深拷贝）。
    """
    if not population:
        raise ValueError("种群为空，无法选择")

    k = min(tournament_size, len(population))
    contestants = random.sample(population, k)

    winner = max(contestants, key=lambda ind: ind.fitness if ind.fitness is not None else float("-inf"))
    return copy.deepcopy(winner)


def mutate_threshold(
    individual: StrategyIndividual,
    mutation_strength: float = 0.15,
) -> StrategyIndividual:
    """阈值变异：调整入场条件的阈值。

    对每个 entry_condition 的 value 字段做 ±mutation_strength 的随机扰动。
    约 20% 概率会额外调整止损/止盈参数。

    Args:
        individual: 待变异的个体（原地修改后返回）。
        mutation_strength: 变异幅度（相对于当前值的比例）。

    Returns:
        变异后的个体（同一对象）。
    """
    for cond in individual.entry_conditions:
        value = cond.get("value")
        if isinstance(value, int | float) and value != 0:
            delta = random.uniform(-mutation_strength, mutation_strength) * abs(value)
            cond["value"] = round(value + delta, 4)

    # 小概率调整风控参数
    if random.random() < 0.2:
        stop_loss = individual.risk.get("stop_loss", {})
        if isinstance(stop_loss.get("value"), int | float):
            delta = random.uniform(-0.5, 0.5)
            stop_loss["value"] = round(max(0.5, stop_loss["value"] + delta), 1)

    if random.random() < 0.15:
        take_profit = individual.risk.get("take_profit", {})
        if isinstance(take_profit.get("value"), int | float):
            delta = random.uniform(-0.5, 0.5)
            take_profit["value"] = round(max(1.0, take_profit["value"] + delta), 1)

    return individual


def mutate_logic_switch(individual: StrategyIndividual) -> StrategyIndividual:
    """逻辑门切换变异：AND ↔ OR。

    约 15% 概率翻转 entry_logic。
    """
    if random.random() < 0.15:
        individual.entry_logic = "or" if individual.entry_logic == "and" else "and"

    return individual


def mutate(
    individual: StrategyIndividual,
    mutation_strength: float = 0.15,
) -> StrategyIndividual:
    """复合变异：阈值 + 逻辑门。

    Args:
        individual: 待变异的个体。
        mutation_strength: 变异幅度。

    Returns:
        变异后的个体。
    """
    individual = mutate_threshold(individual, mutation_strength)
    individual = mutate_logic_switch(individual)
    return individual


def elitism_preserve(
    population: list[StrategyIndividual],
    elite_count: int = 5,
) -> list[StrategyIndividual]:
    """精英保留：从种群中选出适应度最高的 elite_count 个个体。

    Args:
        population: 当前种群。
        elite_count: 保留的精英数量。

    Returns:
        精英个体列表（深拷贝）已按适应度降序排序。
    """
    evaluated = [ind for ind in population if ind.fitness is not None]
    if not evaluated:
        return []

    evaluated.sort(key=lambda ind: ind.fitness, reverse=True)
    elites = evaluated[:elite_count]

    return [copy.deepcopy(ind) for ind in elites]


def next_generation(
    population: list[StrategyIndividual],
    elite_count: int = 5,
    mutation_rate: float = 0.3,
    mutation_strength: float = 0.15,
) -> list[StrategyIndividual]:
    """产生下一代种群。

    流程：
    1. 精英保留（直接复制 Top-N）
    2. 剩余位置通过锦标赛选择 + 变异填充

    Args:
        population: 当前种群（所有个体都必须有 fitness 值）。
        elite_count: 精英保留数量。
        mutation_rate: 每个后代个体被变异的概率。
        mutation_strength: 变异幅度。

    Returns:
        新一代种群（大小与输入相同，generation +1）。
    """
    if not population:
        raise ValueError("种群为空")

    pop_size = len(population)
    generation = population[0].generation + 1

    # 1. 精英保留
    elites = elitism_preserve(population, min(elite_count, pop_size))
    next_pop: list[StrategyIndividual] = []
    for e in elites:
        e.generation = generation
        e.parent_uids = [e.uid]
        e.uid = f"{e.uid}-g{generation}"  # 新 UID
        e.fitness = None  # 需要重新评估
        e.backtest_result = None
    next_pop.extend(elites)

    # 2. 填充剩余位置
    while len(next_pop) < pop_size:
        parent = tournament_select(population, tournament_size=3)
        parent.generation = generation
        parent.parent_uids = [parent.uid]
        parent.uid = f"{parent.uid.split('-g')[0]}-g{generation}-{len(next_pop)}"

        if random.random() < mutation_rate:
            parent = mutate(parent, mutation_strength)

        parent.fitness = None
        parent.backtest_result = None
        next_pop.append(parent)

    # 截断到 pop_size
    result = next_pop[:pop_size]
    logger.info(
        "新一代产生：%d 个个体（精英 %d，变异率 %.0f%%），第 %d 代",
        len(result),
        len(elites),
        mutation_rate * 100,
        generation,
    )
    return result
