"""遗传算子。

Phase 2：完整的 GA — 锦标赛选择 + 交叉 + 多类型变异 + 精英保留。
"""

from __future__ import annotations

import copy
import hashlib
import logging
import random
from typing import TYPE_CHECKING

from services.agent.evolution.strategy_population import StrategyIndividual

if TYPE_CHECKING:
    from services.agent.evolution.factor_discovery import FactorCandidate

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


# ------------------------------------------------------------------
# Phase 1 mutation operators (retained)
# ------------------------------------------------------------------


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


# ------------------------------------------------------------------
# Phase 2 mutation operators
# ------------------------------------------------------------------


def mutate_swap_factor(
    individual: StrategyIndividual,
    factor_pool: list[FactorCandidate],
) -> StrategyIndividual:
    """替换因子变异：将某个入场条件的因子替换为因子池中随机的一个。"""
    if not factor_pool or not individual.entry_conditions:
        return individual

    cond_idx = random.randint(0, len(individual.entry_conditions) - 1)
    new_factor = random.choice(factor_pool)

    formula_hash = hashlib.md5(new_factor.formula.encode()).hexdigest()[:12]
    rank_ic = new_factor.rank_ic_mean or 0

    if rank_ic >= 0:
        operator = "greater_than"
        threshold = 0.5
    else:
        operator = "less_than"
        threshold = -0.5

    individual.entry_conditions[cond_idx] = {
        "indicator": f"factor_custom:{formula_hash}",
        "operator": operator,
        "value": threshold,
    }

    if len(individual.source_factors) > cond_idx:
        individual.source_factors[cond_idx] = new_factor.formula
    else:
        individual.source_factors.append(new_factor.formula)

    return individual


def mutate_add_condition(
    individual: StrategyIndividual,
    factor_pool: list[FactorCandidate],
    max_conditions: int = 5,
) -> StrategyIndividual:
    """新增条件变异：从因子池中随机取一个因子添加为入场条件。"""
    if len(individual.entry_conditions) >= max_conditions:
        return individual

    if not factor_pool:
        return individual

    new_factor = random.choice(factor_pool)

    formula_hash = hashlib.md5(new_factor.formula.encode()).hexdigest()[:12]
    rank_ic = new_factor.rank_ic_mean or 0

    if rank_ic >= 0:
        operator = "greater_than"
        threshold = 0.5
    else:
        operator = "less_than"
        threshold = -0.5

    individual.entry_conditions.append(
        {
            "indicator": f"factor_custom:{formula_hash}",
            "operator": operator,
            "value": threshold,
        }
    )
    individual.source_factors.append(new_factor.formula)

    return individual


def mutate_remove_condition(
    individual: StrategyIndividual,
) -> StrategyIndividual:
    """删除条件变异：移除一个入场条件（保留至少 1 个）。"""
    if len(individual.entry_conditions) <= 1:
        return individual

    idx = random.randint(0, len(individual.entry_conditions) - 1)
    individual.entry_conditions.pop(idx)
    if idx < len(individual.source_factors):
        individual.source_factors.pop(idx)

    return individual


def mutate_adjust_risk(
    individual: StrategyIndividual,
    mutation_strength: float = 0.2,
) -> StrategyIndividual:
    """风控参数变异：调整止损/止盈/仓位参数。"""
    stop_loss = individual.risk.get("stop_loss", {})
    if isinstance(stop_loss.get("value"), int | float):
        delta = random.uniform(-0.5, 0.5)
        stop_loss["value"] = round(max(0.5, stop_loss["value"] + delta), 1)

    take_profit = individual.risk.get("take_profit", {})
    if isinstance(take_profit.get("value"), int | float):
        delta = random.uniform(-0.5, 0.5)
        take_profit["value"] = round(max(1.0, take_profit["value"] + delta), 1)

    position_size = individual.risk.get("position_size", {})
    if isinstance(position_size.get("value"), int | float) and random.random() < 0.3:
        delta = random.choice([-1, 0, 1])
        position_size["value"] = max(1, int(position_size["value"]) + delta)

    return individual


# ------------------------------------------------------------------
# Composite mutate (Phase 2: multi-type dispatch)
# ------------------------------------------------------------------


def mutate(
    individual: StrategyIndividual,
    mutation_strength: float = 0.15,
    factor_pool: list[FactorCandidate] | None = None,
) -> StrategyIndividual:
    """复合变异：随机选择一种变异类型。

    变异类型及概率（有 factor_pool 时）：
    - mutate_threshold: 35%（阈值微调）
    - mutate_swap_factor: 25%（替换因子）
    - mutate_add_condition: 10%（新增条件）
    - mutate_remove_condition: 10%（删除条件）
    - mutate_logic_switch: 10%（AND↔OR）
    - mutate_adjust_risk: 10%（风控参数调整）

    无 factor_pool 时回退到 Phase 1 行为（threshold + logic_switch）。

    Args:
        individual: 待变异的个体。
        mutation_strength: 变异幅度。
        factor_pool: 因子池（swap/add 变异需要）。

    Returns:
        变异后的个体。
    """
    if not factor_pool:
        # Phase 1 兼容：仅 threshold + logic_switch
        individual = mutate_threshold(individual, mutation_strength)
        individual = mutate_logic_switch(individual)
        return individual

    # 构建可用变异类型
    mutators: list[tuple[float, callable]] = [
        (0.35, lambda ind: mutate_threshold(ind, mutation_strength)),
        (0.25, lambda ind: mutate_swap_factor(ind, factor_pool)),
        (0.10, lambda ind: mutate_add_condition(ind, factor_pool)),
    ]

    if len(individual.entry_conditions) >= 2:
        mutators.append((0.10, lambda ind: mutate_remove_condition(ind)))
    else:
        mutators[0] = (mutators[0][0] + 0.10, mutators[0][1])

    mutators.append((0.10, lambda ind: mutate_logic_switch(ind)))
    mutators.append((0.10, lambda ind: mutate_adjust_risk(ind, mutation_strength)))

    # 根据概率随机选择一个变异操作
    total_weight = sum(w for w, _ in mutators)
    r = random.random() * total_weight
    cumulative = 0.0
    for weight, func in mutators:
        cumulative += weight
        if r <= cumulative:
            individual = func(individual)
            break

    return individual


# ------------------------------------------------------------------
# Phase 2: Crossover
# ------------------------------------------------------------------


def crossover(
    parent_a: StrategyIndividual,
    parent_b: StrategyIndividual,
) -> tuple[StrategyIndividual, StrategyIndividual]:
    """策略交叉：随机选择交叉点交换基因。

    四种交叉点（等概率随机选择）：
    1. entry_conditions — 交换一个入场条件
    2. exit_conditions — 交换出场条件
    3. risk_params — 交换风控参数
    4. entry_logic — 交换逻辑门

    Args:
        parent_a: 父本 A。
        parent_b: 父本 B。

    Returns:
        两个子代个体。
    """
    child_a = copy.deepcopy(parent_a)
    child_b = copy.deepcopy(parent_b)

    cross_type = random.choice(["entry", "exit", "risk", "logic"])

    if cross_type == "entry" and parent_a.entry_conditions and parent_b.entry_conditions:
        idx_a = random.randint(0, len(parent_a.entry_conditions) - 1)
        idx_b = random.randint(0, len(parent_b.entry_conditions) - 1)
        child_a.entry_conditions[idx_a] = copy.deepcopy(parent_b.entry_conditions[idx_b])
        child_b.entry_conditions[idx_b] = copy.deepcopy(parent_a.entry_conditions[idx_a])
        # 同步 source_factors
        if idx_a < len(parent_a.source_factors) and idx_b < len(parent_b.source_factors):
            child_a.source_factors[idx_a] = parent_b.source_factors[idx_b]
            child_b.source_factors[idx_b] = parent_a.source_factors[idx_a]

    elif cross_type == "exit" and parent_a.exit_conditions and parent_b.exit_conditions:
        idx_a = random.randint(0, len(parent_a.exit_conditions) - 1)
        idx_b = random.randint(0, len(parent_b.exit_conditions) - 1)
        child_a.exit_conditions[idx_a] = copy.deepcopy(parent_b.exit_conditions[idx_b])
        child_b.exit_conditions[idx_b] = copy.deepcopy(parent_a.exit_conditions[idx_a])

    elif cross_type == "risk":
        child_a.risk = copy.deepcopy(parent_b.risk)
        child_b.risk = copy.deepcopy(parent_a.risk)

    elif cross_type == "logic":
        child_a.entry_logic, child_b.entry_logic = parent_b.entry_logic, parent_a.entry_logic
        child_a.exit_logic, child_b.exit_logic = parent_b.exit_logic, parent_a.exit_logic

    return child_a, child_b


# ------------------------------------------------------------------
# Elite preservation
# ------------------------------------------------------------------


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


# ------------------------------------------------------------------
# Generation advancement (Phase 2: crossover + multi-type mutation)
# ------------------------------------------------------------------


def next_generation(
    population: list[StrategyIndividual],
    elite_count: int = 5,
    mutation_rate: float = 0.3,
    mutation_strength: float = 0.15,
    crossover_rate: float = 0.7,
    factor_pool: list[FactorCandidate] | None = None,
    diversity_threshold: float = 0.35,
    fresh_blood_count: int = 3,
) -> list[StrategyIndividual]:
    """产生下一代种群。

    流程：
    1. 精英保留（直接复制 Top-N）
    2. 剩余位置：选择两个父本 → 交叉（crossover_rate 概率） → 变异（mutation_rate 概率）
    3. 去重检查 + 多样性不足时注入新鲜血液

    Args:
        population: 当前种群（所有个体都必须有 fitness 值）。
        elite_count: 精英保留数量。
        mutation_rate: 每个后代个体被变异的概率。
        mutation_strength: 变异幅度。
        crossover_rate: 交叉概率（每对父本）。
        factor_pool: 因子池（供需要因子的变异类型使用）。
        diversity_threshold: 多样性低于此阈值时注入新鲜血液。
        fresh_blood_count: 注入的新鲜个体数。

    Returns:
        新一代种群（大小与输入相同，generation +1）。
    """
    if not population:
        raise ValueError("种群为空")

    from services.agent.evolution.strategy_population import (
        deduplicate_population,
        initialize_population,
        inject_fresh_blood,
        population_diversity,
    )

    pop_size = len(population)
    generation = population[0].generation + 1

    # 1. 精英保留
    elites = elitism_preserve(population, min(elite_count, pop_size))
    next_pop: list[StrategyIndividual] = []
    for e in elites:
        e.generation = generation
        e.parent_uids = [e.uid]
        e.uid = f"{e.uid}-g{generation}"
        e.fitness = None
        e.backtest_result = None
    next_pop.extend(elites)

    # 2. 填充剩余位置（选择 → 交叉 → 变异）
    while len(next_pop) < pop_size:
        parent_a = tournament_select(population, tournament_size=3)
        parent_b = tournament_select(population, tournament_size=3)

        if random.random() < crossover_rate and parent_a.uid != parent_b.uid:
            child_a, child_b = crossover(parent_a, parent_b)

            for child, p_a, p_b in [(child_a, parent_a, parent_b), (child_b, parent_b, parent_a)]:
                child.generation = generation
                child.parent_uids = [p_a.uid, p_b.uid]
                child.uid = f"{child.uid.split('-g')[0]}-g{generation}-{len(next_pop)}"
                child.fitness = None
                child.backtest_result = None

                if random.random() < mutation_rate:
                    child = mutate(child, mutation_strength, factor_pool=factor_pool)

            next_pop.append(child_a)
            if len(next_pop) < pop_size:
                next_pop.append(child_b)
        else:
            winner = parent_a if (parent_a.fitness or 0) >= (parent_b.fitness or 0) else parent_b
            child = copy.deepcopy(winner)
            child.generation = generation
            child.parent_uids = [winner.uid]
            child.uid = f"{child.uid.split('-g')[0]}-g{generation}-{len(next_pop)}"
            child.fitness = None
            child.backtest_result = None

            if random.random() < mutation_rate:
                child = mutate(child, mutation_strength, factor_pool=factor_pool)

            next_pop.append(child)

    # 截断到 pop_size
    result = next_pop[:pop_size]

    # 3. 多样性维护：去重（仅在能补充新个体时执行）
    if factor_pool:
        deduped = deduplicate_population(result)
        if len(deduped) < pop_size:
            shortage = pop_size - len(deduped)
            logger.info("多样性维护：去重后缺 %d 个，用随机个体填充", shortage)
            fillers = initialize_population(
                factor_pool,
                symbol="",
                timeframe=result[0].timeframe,
                population_size=shortage,
                direction=result[0].direction,
            )
            for f in fillers:
                f.generation = generation
            deduped.extend(fillers)
        result = deduped[:pop_size]
    else:
        result = result[:pop_size]

    # 4. 多样性不足时注入新鲜血液
    div = population_diversity(result)
    if div < diversity_threshold and factor_pool:
        logger.info("多样性低于阈值（%.2f < %.2f），注入 %d 个新鲜个体", div, diversity_threshold, fresh_blood_count)
        result = inject_fresh_blood(
            result,
            factor_pool,
            symbol="",
            timeframe=result[0].timeframe,
            n_fresh=fresh_blood_count,
            direction=result[0].direction,
        )

    logger.info(
        "新一代产生：%d 个个体（精英 %d，交叉率 %.0f%%，变异率 %.0f%%），第 %d 代，多样性 %.2f",
        len(result),
        len(elites),
        crossover_rate * 100,
        mutation_rate * 100,
        generation,
        div,
    )
    return result
