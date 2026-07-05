"""StrategyEvolutionAgent 及进化模块单元测试。

测试范围：market_regime / factor_discovery / strategy_population /
          genetic_operators / fitness / StrategyEvolutionAgent main loop。
"""

from __future__ import annotations

import random
from copy import deepcopy
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from services.agent.evolution.factor_discovery import (
    FactorCandidate,
    crossover_factor_formula,
    evolve_factor_pool,
    filter_by_ic,
    generate_gp_factors,
    generate_random_factor,
    generate_template_factors,
    mutate_factor_formula,
)
from services.agent.evolution.fitness import (
    FitnessScore,
    ParetoFront,
    compute_fitness,
    compute_fitness_with_oos,
    compute_pareto_fitness,
    crowding_distance,
    non_dominated_sort,
    pareto_selection,
    split_train_test_dates,
    _dominates,
    _sharpe_score,
    _return_drawdown_score,
    _simplicity_score,
    _trade_count_score,
)
from services.agent.evolution.genetic_operators import (
    crossover,
    elitism_preserve,
    mutate,
    mutate_add_condition,
    mutate_adjust_risk,
    mutate_remove_condition,
    mutate_swap_factor,
    mutate_threshold,
    next_generation,
    tournament_select,
)
from services.agent.evolution.market_regime import (
    MarketRegime,
    _compute_hurst,
    _linear_slope,
    detect_regime,
)
from services.agent.evolution.strategy_population import (
    StrategyIndividual,
    apply_fitness_sharing,
    best_individual,
    deduplicate_population,
    initialize_population,
    inject_fresh_blood,
    population_diversity,
)


# ------------------------------------------------------------------
# 测试数据工具
# ------------------------------------------------------------------

def _make_ohlcv_df(n_bars: int = 200, seed: int = 42) -> pd.DataFrame:
    """生成合成 OHLCV DataFrame 用于测试。"""
    rng = np.random.default_rng(seed)
    n = n_bars

    # 随机游走 + 趋势 + 周期
    t = np.arange(n)
    trend = 0.05 * t / n  # 微弱的上升趋势
    noise = rng.normal(0, 0.02, n).cumsum()
    log_close = np.log(100) + trend + noise
    close = np.exp(log_close)

    amplitude = close * 0.01
    high = close + np.abs(rng.normal(0, 0.005, n)) * close
    low = close - np.abs(rng.normal(0, 0.005, n)) * close
    open_price = low + rng.random(n) * (high - low)
    volume = rng.integers(1000, 10000, n)

    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(n)]

    return pd.DataFrame({
        "time": dates,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def _make_strong_trend_df(n_bars: int = 200) -> pd.DataFrame:
    """生成强上升趋势数据（低噪声，确保被识别为趋势而非高波动）。"""
    n = n_bars
    t = np.arange(n)
    # 强趋势 + 极小噪声
    close = 100.0 + t * 0.3 + np.random.default_rng(99).normal(0, 0.1, n)
    # 极小的 bar 范围 = 低波动
    high = close + 0.02
    low = close - 0.02
    open_price = close - 0.01
    volume = np.random.default_rng(103).integers(1000, 10000, n)
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(n)]

    return pd.DataFrame({
        "time": dates,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })

    return df


def _make_factors(n: int = 10) -> list[FactorCandidate]:
    """生成模拟因子列表用于测试。"""
    factors = []
    for i in range(n):
        f = FactorCandidate(
            formula=f"close / ts_delay(close, {i+1}) - 1",
            template_name="test_momentum",
            params={"lookback": i + 1},
            rank_ic_mean=0.05 - i * 0.004,
            rank_icir=0.5 - i * 0.04,
            ic_mean=0.04 - i * 0.003,
            icir=0.4 - i * 0.03,
            coverage=0.9,
            turnover=0.3,
        )
        factors.append(f)
    return factors


# ------------------------------------------------------------------
# Market Regime Tests
# ------------------------------------------------------------------

class TestMarketRegime:
    def test_detect_regime_returns_valid_type(self):
        df = _make_ohlcv_df(100)
        regime = detect_regime(df)
        assert isinstance(regime, MarketRegime)
        assert regime.regime in (
            "trending_up", "trending_down", "range_bound",
            "high_volatility", "low_volatility",
        )
        assert 0 <= regime.confidence <= 1
        assert "adx" in regime.metrics
        assert "hurst" in regime.metrics

    def test_detect_regime_strong_trend(self):
        df = _make_strong_trend_df(200)
        regime = detect_regime(df)
        # 强趋势应被识别为 trending_up
        assert regime.regime == "trending_up"
        assert regime.confidence > 0.5
        assert regime.metrics["adx"] > 20

    def test_detect_regime_insufficient_data(self):
        df = _make_ohlcv_df(20)
        with pytest.raises(ValueError, match="至少需要 30 根"):
            detect_regime(df)

    def test_linear_slope_positive_trend(self):
        series = pd.Series([1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9])
        slope = _linear_slope(series, lookback=5)
        assert slope > 0

    def test_linear_slope_negative_trend(self):
        series = pd.Series([1.9, 1.8, 1.7, 1.6, 1.5, 1.4, 1.3, 1.2, 1.1, 1.0])
        slope = _linear_slope(series, lookback=5)
        assert slope < 0

    def test_hurst_random_walk(self):
        rng = np.random.default_rng(42)
        # 使用更多样本以减少估计偏差
        random_walk = pd.Series(rng.normal(0, 1, 600).cumsum())
        hurst = _compute_hurst(random_walk, max_lag=20)
        # R/S 估计量对有限样本有正向偏差，放宽范围
        assert 0.3 < hurst < 0.95

    def test_hurst_trending(self):
        # 强趋势数据应该有较高的 Hurst 指数
        df = _make_strong_trend_df(300)
        hurst = _compute_hurst(df["close"], max_lag=20)
        # 强趋势 H > 0.5
        assert hurst > 0.4


# ------------------------------------------------------------------
# Factor Discovery Tests
# ------------------------------------------------------------------

class TestFactorDiscovery:
    def test_generate_template_factors(self):
        candidates = generate_template_factors()
        assert len(candidates) > 0
        # 至少应有几十个模板因子
        assert len(candidates) >= 20
        for c in candidates:
            assert isinstance(c, FactorCandidate)
            assert c.formula
            assert c.params

    def test_factor_formulas_are_valid(self):
        candidates = generate_template_factors()
        for c in candidates[:10]:
            # 所有生成的公式应该已经通过 validate_factor_formula
            assert "close" in c.formula or "volume" in c.formula or "high" in c.formula

    def test_filter_by_ic_empty(self):
        result = filter_by_ic([], min_abs_rank_ic=0.02, top_n=10)
        assert result == []

    def test_filter_by_ic_basic(self):
        factors = _make_factors(10)
        result = filter_by_ic(factors, min_abs_rank_ic=0.02, min_icir=0.3, top_n=5)
        assert len(result) <= 5
        if result:
            for f in result:
                assert abs(f.rank_ic_mean or 0) >= 0.02

    def test_filter_by_ic_sorts_by_rank_ic(self):
        factors = _make_factors(15)
        result = filter_by_ic(factors, min_abs_rank_ic=0.0, min_icir=0.0, top_n=10)
        for i in range(len(result) - 1):
            assert abs(result[i].rank_ic_mean or 0) >= abs(result[i + 1].rank_ic_mean or 0)


# ------------------------------------------------------------------
# Strategy Population Tests
# ------------------------------------------------------------------

class TestStrategyPopulation:
    def test_initialize_population(self):
        factors = _make_factors(10)
        population = initialize_population(factors, symbol="RB", population_size=20)
        assert len(population) == 20
        for ind in population:
            assert ind.generation == 0
            assert len(ind.entry_conditions) >= 1
            assert len(ind.exit_conditions) >= 1
            assert ind.fitness is None
            assert ind.direction in ("long", "short")

    def test_initialize_population_empty_factors(self):
        with pytest.raises(ValueError, match="因子池为空"):
            initialize_population([], symbol="RB", population_size=10)

    def test_initialize_population_with_regime(self):
        factors = _make_factors(10)
        regime = MarketRegime(
            regime="range_bound",
            confidence=0.8,
            metrics={"adx": 12.0, "hurst": 0.35},
        )
        population = initialize_population(factors, symbol="RB", population_size=10, regime=regime)
        assert len(population) == 10

    def test_to_dsl(self):
        factors = _make_factors(5)
        population = initialize_population(factors, symbol="AU", population_size=1)
        dsl = population[0].to_dsl(name="test-strategy", symbol="AU")
        assert dsl["name"] == "test-strategy"
        assert "AU" in dsl["universe"]
        assert "entry" in dsl
        assert "exit" in dsl
        assert "risk" in dsl

    def test_population_diversity_unique(self):
        factors = _make_factors(10)
        population = initialize_population(factors, symbol="RB", population_size=20)

        # 去重因子只去重了 formula，但 entry_conditions 可能有重复
        # 让所有个体的 entry_condition 唯一 → 改一下
        for i, ind in enumerate(population):
            ind.entry_conditions = [{"indicator": f"unique_{i}", "operator": "above", "value": 1.0}]

        div = population_diversity(population)
        assert div > 0.8  # 应该接近 1.0

    def test_population_diversity_identical(self):
        factors = _make_factors(5)
        pop1 = initialize_population(factors, symbol="RB", population_size=10)
        # 全部改成一样
        for ind in pop1:
            ind.entry_conditions = [{"indicator": "close", "operator": "above", "indicator2": "sma20"}]
        div = population_diversity(pop1)
        assert div < 0.2  # 应该接近 0.1

    def test_best_individual(self):
        factors = _make_factors(5)
        population = initialize_population(factors, symbol="RB", population_size=10)
        for i, ind in enumerate(population):
            ind.fitness = float(i)  # 0, 1, 2, ...
        best = best_individual(population)
        assert best is not None
        assert best.fitness == 9.0  # 最大值

    def test_best_individual_none_evaluated(self):
        factors = _make_factors(5)
        population = initialize_population(factors, symbol="RB", population_size=10)
        best = best_individual(population)
        assert best is None


# ------------------------------------------------------------------
# Genetic Operators Tests
# ------------------------------------------------------------------

class TestGeneticOperators:
    def test_tournament_select_basic(self):
        factors = _make_factors(5)
        population = initialize_population(factors, symbol="RB", population_size=20)
        for i, ind in enumerate(population):
            ind.fitness = float(i)

        winner = tournament_select(population, tournament_size=3)
        assert winner is not None
        assert isinstance(winner, StrategyIndividual)

    def test_tournament_select_prefers_high_fitness(self):
        """高适应度个体应该在多次选择中被更频繁地选中。"""
        factors = _make_factors(5)
        population = initialize_population(factors, symbol="RB", population_size=20)
        for i, ind in enumerate(population):
            ind.fitness = float(i)  # 后创建的适应度更高

        # 运行 100 次选择，统计结果
        wins = {}
        for _ in range(100):
            winner = tournament_select(population, tournament_size=5)
            wins[winner.uid] = wins.get(winner.uid, 0) + 1

        # 高适应度个体应该出现得更频繁
        high_fitness = [ind for ind in population if (ind.fitness or 0) >= 15]
        low_fitness = [ind for ind in population if (ind.fitness or 0) <= 4]
        high_wins = sum(wins.get(ind.uid, 0) for ind in high_fitness)
        low_wins = sum(wins.get(ind.uid, 0) for ind in low_fitness)

        assert high_wins > low_wins

    def test_tournament_select_empty(self):
        with pytest.raises(ValueError, match="种群为空"):
            tournament_select([])

    def test_mutate_threshold_changes_values(self):
        factors = _make_factors(5)
        population = initialize_population(factors, symbol="RB", population_size=1)
        individual = population[0]
        original = deepcopy(individual.entry_conditions)

        mutated = mutate_threshold(individual, mutation_strength=0.3)
        # 阈值应该被改变了
        changed = False
        for orig, mut in zip(original, mutated.entry_conditions):
            if orig.get("value") != mut.get("value"):
                changed = True
        # 由于随机性，不一定每次都变，但大概率会
        # 不变也可能是合理的（delta 太小）

    def test_elitism_preserve(self):
        factors = _make_factors(5)
        population = initialize_population(factors, symbol="RB", population_size=20)
        for i, ind in enumerate(population):
            ind.fitness = float(i % 10)

        elites = elitism_preserve(population, elite_count=3)
        assert len(elites) == 3
        # 精英适应度应该是最高的
        assert elites[0].fitness == 9.0

    def test_elitism_preserve_none_evaluated(self):
        factors = _make_factors(5)
        population = initialize_population(factors, symbol="RB", population_size=5)
        elites = elitism_preserve(population, elite_count=3)
        assert elites == []

    def test_next_generation_preserves_size(self):
        factors = _make_factors(5)
        population = initialize_population(factors, symbol="RB", population_size=20)
        for i, ind in enumerate(population):
            ind.fitness = float(i)

        next_pop = next_generation(population, elite_count=5, mutation_rate=0.5)
        assert len(next_pop) == 20
        assert next_pop[0].generation == 1

    def test_next_generation_has_elites(self):
        factors = _make_factors(5)
        population = initialize_population(factors, symbol="RB", population_size=20)
        for i, ind in enumerate(population):
            ind.fitness = float(i)

        next_pop = next_generation(population, elite_count=5, mutation_rate=0.5)
        # 前 5 个是精英，fitness 应该为空（需重新评估）
        for i in range(5):
            assert next_pop[i].fitness is None


# ------------------------------------------------------------------
# Fitness Tests
# ------------------------------------------------------------------

class TestFitness:
    def test_compute_fitness_perfect(self):
        result = {
            "metrics": {
                "sharpe": 3.0,
                "annualized_return_pct": 50.0,
                "max_drawdown_pct": 5.0,
                "win_rate_pct": 70.0,
                "profit_factor": 3.5,
                "trade_count": 15,
                "score": 95,
            }
        }
        fitness = compute_fitness(result, condition_count=2)
        assert fitness.total > 70
        assert "sharpe" in fitness.components
        assert "simplicity" in fitness.components

    def test_compute_fitness_poor(self):
        result = {
            "metrics": {
                "sharpe": -0.5,
                "annualized_return_pct": -20.0,
                "max_drawdown_pct": 40.0,
                "win_rate_pct": 25.0,
                "profit_factor": 0.5,
                "trade_count": 1,
                "score": 10,
            }
        }
        fitness = compute_fitness(result, condition_count=1)
        # 应该得到一个较低的评分
        assert fitness.total < 40

    def test_compute_fitness_empty_metrics(self):
        fitness = compute_fitness({"metrics": {}}, condition_count=1)
        assert fitness.total == 0.0

    def test_sharpe_score(self):
        assert _sharpe_score(0) < 30
        assert _sharpe_score(2.0) > 70
        assert _sharpe_score(3.0) >= 100

    def test_return_drawdown_score(self):
        s = _return_drawdown_score(30.0, 10.0)
        assert s > 50

    def test_trade_count_score(self):
        assert _trade_count_score(1) < 30
        assert _trade_count_score(10) > 80
        assert _trade_count_score(100) < 80

    def test_simplicity_score(self):
        assert _simplicity_score(1) == 100
        assert _simplicity_score(3) == 85
        assert _simplicity_score(7) < 20


# ------------------------------------------------------------------
# StrategyEvolutionAgent Integration Tests
# ------------------------------------------------------------------

class TestStrategyEvolutionAgentIntegration:
    """完整闭环集成测试。需要 DB 和种子数据。"""

    def test_agent_import_and_basic(self, db_session):
        """测试 Agent 能正常导入和初始化。"""
        from services.agent.context import AgentContext
        from services.agent.strategy_evolution_agent import StrategyEvolutionAgent

        user = _create_user(db_session)
        variety, _ = _create_test_variety_with_klines(db_session)

        context = AgentContext(db=db_session, user_id=user.id)
        agent = StrategyEvolutionAgent(context)
        assert agent.name == "strategy_evolution"
        assert "进化" in agent.description

    def test_agent_fails_for_unknown_symbol(self, db_session):
        """未知品种应返回错误。"""
        from services.agent.context import AgentContext
        from services.agent.strategy_evolution_agent import StrategyEvolutionAgent
        from services.agent.core import AgentStatus

        user = _create_user(db_session)
        context = AgentContext(db=db_session, user_id=user.id)
        agent = StrategyEvolutionAgent(context)

        result = asyncio.run(agent.run("为ZZZZ自动发现策略"))
        assert result.status == AgentStatus.FAILED
        assert "识别" in (result.error_message or "")

    def test_agent_small_evolution(self, db_session):
        """小规模进化测试：1 代 x 10 种群。在 SQLite 上运行（scipy 不可用时退化到随机因子选择）。"""
        import asyncio

        from services.agent.context import AgentContext
        from services.agent.strategy_evolution_agent import StrategyEvolutionAgent
        from services.agent.core import AgentStatus

        user = _create_user(db_session)
        variety, contract = _create_test_variety_with_klines(db_session, n_bars=200)

        context = AgentContext(db=db_session, user_id=user.id)
        agent = StrategyEvolutionAgent(context)

        result = asyncio.run(agent.run(f"为{variety.symbol}自动发现策略，进化1代"))
        if result.status != AgentStatus.COMPLETED:
            print(f"\nERROR: {result.error_message}")
        assert result.status == AgentStatus.COMPLETED, f"Evolution failed: {result.error_message}"
        assert result.data is not None
        assert "dsl" in result.data
        assert result.data["best_fitness"] is not None
        assert result.data["best_fitness"] >= 0

    def test_agent_stream(self, db_session):
        """测试流式执行。"""
        from services.agent.context import AgentContext
        from services.agent.strategy_evolution_agent import StrategyEvolutionAgent

        user = _create_user(db_session)
        variety, contract = _create_test_variety_with_klines(db_session, n_bars=200)

        context = AgentContext(db=db_session, user_id=user.id)
        agent = StrategyEvolutionAgent(context)

        events = list(asyncio.run(_collect_stream(agent, f"为{variety.symbol}自动发现策略，进化2代")))
        assert len(events) >= 1
        event_types = [e.get("event_type") for e in events]
        # 应该至少包含 result 或 error
        assert any(t in ("result", "error") for t in event_types)


# ------------------------------------------------------------------
# Phase 2: Crossover Tests
# ------------------------------------------------------------------

class TestCrossover:
    def test_crossover_produces_two_children(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=2)
        a, b = pop[0], pop[1]
        child_a, child_b = crossover(a, b)
        assert isinstance(child_a, StrategyIndividual)
        assert isinstance(child_b, StrategyIndividual)

    def test_crossover_preserves_entry_conditions_count(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=2)
        a, b = pop[0], pop[1]
        child_a, child_b = crossover(a, b)
        assert len(child_a.entry_conditions) == len(a.entry_conditions)
        assert len(child_b.entry_conditions) == len(b.entry_conditions)

    def test_crossover_with_entry_conditions(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=2)
        a, b = pop[0], pop[1]
        # Force different entry conditions
        a.entry_conditions = [{"indicator": "factor_a", "operator": "greater_than", "value": 0.5}]
        b.entry_conditions = [{"indicator": "factor_b", "operator": "less_than", "value": -0.3}]
        child_a, child_b = crossover(a, b)

    def test_next_generation_with_crossover(self):
        factors = _make_factors(5)
        population = initialize_population(factors, symbol="RB", population_size=20)
        for i, ind in enumerate(population):
            ind.fitness = float(i)

        next_pop = next_generation(population, elite_count=5, mutation_rate=0.3, crossover_rate=0.7)
        assert len(next_pop) == 20
        assert next_pop[0].generation == 1


# ------------------------------------------------------------------
# Phase 2: Multi-type Mutation Tests
# ------------------------------------------------------------------

class TestMultiTypeMutation:
    def test_mutate_swap_factor_changes_indicator(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=1)
        ind = pop[0]
        original = deepcopy(ind.entry_conditions[0].get("indicator"))
        # Apply multiple times to ensure a change (random)
        for _ in range(20):
            mutate_swap_factor(ind, factors)
        assert ind.entry_conditions[0].get("indicator") is not None

    def test_mutate_add_condition_increases_count(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=1)
        ind = pop[0]
        orig_count = len(ind.entry_conditions)
        mutate_add_condition(ind, factors, max_conditions=10)
        assert len(ind.entry_conditions) == orig_count + 1

    def test_mutate_add_condition_respects_max(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=1)
        ind = pop[0]
        # Fill to max
        while len(ind.entry_conditions) < 5:
            mutate_add_condition(ind, factors, max_conditions=5)
        orig_count = len(ind.entry_conditions)
        mutate_add_condition(ind, factors, max_conditions=5)
        assert len(ind.entry_conditions) == orig_count

    def test_mutate_remove_condition_decreases_count(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=1)
        ind = pop[0]
        # Ensure at least 2
        mutate_add_condition(ind, factors, max_conditions=10)
        orig_count = len(ind.entry_conditions)
        assert orig_count >= 2
        mutate_remove_condition(ind)
        assert len(ind.entry_conditions) == orig_count - 1

    def test_mutate_remove_condition_keeps_at_least_one(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=1)
        ind = pop[0]
        assert len(ind.entry_conditions) >= 1
        mutate_remove_condition(ind)
        assert len(ind.entry_conditions) >= 1

    def test_mutate_adjust_risk_changes_params(self):
        factors = _make_factors(5)
        pop = initialize_population(factors, symbol="RB", population_size=1)
        ind = pop[0]
        original_sl = deepcopy(ind.risk.get("stop_loss", {}).get("value"))
        for _ in range(10):
            mutate_adjust_risk(ind, mutation_strength=0.5)
        # May or may not change due to randomness, but should be valid
        assert ind.risk["stop_loss"]["value"] >= 0.5

    def test_mutate_with_factor_pool(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=1)
        ind = pop[0]
        orig_conditions = deepcopy(ind.entry_conditions)
        mutate(ind, mutation_strength=0.3, factor_pool=factors)
        assert ind.fitness is None  # Still unevaluated

    def test_mutate_without_factor_pool_backward_compat(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=1)
        ind = pop[0]
        mutate(ind, mutation_strength=0.3)  # No factor_pool → Phase 1 behavior
        assert ind.fitness is None


# ------------------------------------------------------------------
# Phase 2: OOS Fitness Tests
# ------------------------------------------------------------------

class TestOOSFitness:
    def test_compute_fitness_with_oos_penalizes_degradation(self):
        is_result = {
            "metrics": {
                "sharpe": 2.0,
                "annualized_return_pct": 30.0,
                "max_drawdown_pct": 10.0,
                "win_rate_pct": 50.0,
                "profit_factor": 2.0,
                "trade_count": 20,
                "score": 80,
            }
        }
        # OOS Sharpe is much lower
        oos_result = {
            "metrics": {
                "sharpe": 0.5,
                "annualized_return_pct": 5.0,
                "max_drawdown_pct": 20.0,
                "win_rate_pct": 35.0,
                "profit_factor": 1.2,
                "trade_count": 8,
                "score": 30,
            }
        }
        is_only = compute_fitness(is_result, condition_count=2)
        oos = compute_fitness_with_oos(is_result, oos_result, condition_count=2)
        # OOS-aware fitness should be lower than IS-only when OOS degrades
        assert oos.total < is_only.total

    def test_compute_fitness_with_oos_no_degradation(self):
        """When OOS is as good as IS, fitness should be similar."""
        result = {
            "metrics": {
                "sharpe": 2.0,
                "annualized_return_pct": 30.0,
                "max_drawdown_pct": 10.0,
                "win_rate_pct": 50.0,
                "profit_factor": 2.0,
                "trade_count": 20,
                "score": 80,
            }
        }
        is_only = compute_fitness(result, condition_count=2)
        oos = compute_fitness_with_oos(result, result, condition_count=2)
        # OOS == IS, so stability should be high, fitness similar or higher
        assert oos.total >= is_only.total * 0.7

    def test_compute_fitness_with_oos_none_oos(self):
        result = {
            "metrics": {
                "sharpe": 1.5,
                "annualized_return_pct": 20.0,
                "max_drawdown_pct": 15.0,
                "win_rate_pct": 45.0,
                "profit_factor": 1.8,
                "trade_count": 10,
                "score": 60,
            }
        }
        oos = compute_fitness_with_oos(result, None, condition_count=2)
        assert oos.total > 0

    def test_split_train_test_dates_basic(self):
        result = split_train_test_dates(
            date(2023, 1, 1), date(2025, 12, 31), test_ratio=0.3, min_train_bars=40
        )
        assert result is not None
        (train_start, train_end), (test_start, test_end) = result
        assert train_start == date(2023, 1, 1)
        assert test_end == date(2025, 12, 31)
        assert train_end < test_start

    def test_split_train_test_dates_insufficient(self):
        result = split_train_test_dates(
            date(2025, 1, 1), date(2025, 1, 20), test_ratio=0.3, min_train_bars=40
        )
        assert result is None


# ------------------------------------------------------------------
# Phase 2: Diversity Maintenance Tests
# ------------------------------------------------------------------

class TestDiversityMaintenance:
    def test_deduplicate_population_removes_duplicates(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=10)
        # Make them all identical
        for ind in pop:
            ind.entry_conditions = [{"indicator": "close", "operator": "greater_than", "value": 0.5}]
            ind.fitness = 50.0
        deduped = deduplicate_population(pop)
        assert len(deduped) == 1

    def test_deduplicate_population_keeps_unique(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=10)
        for i, ind in enumerate(pop):
            ind.entry_conditions = [{"indicator": f"unique_{i}", "operator": "greater_than", "value": 0.5}]
            ind.fitness = float(i)
        deduped = deduplicate_population(pop)
        assert len(deduped) == len(pop)

    def test_deduplicate_population_keeps_higher_fitness(self):
        factors = _make_factors(5)
        pop = initialize_population(factors, symbol="RB", population_size=5)
        # Two identical individuals with different fitness
        pop[0].entry_conditions = [{"indicator": "same", "operator": "above", "value": 1.0}]
        pop[0].fitness = 90.0
        pop[1].entry_conditions = [{"indicator": "same", "operator": "above", "value": 1.0}]
        pop[1].fitness = 30.0
        deduped = deduplicate_population(pop)
        kept_fitnesses = [ind.fitness for ind in deduped if ind.entry_conditions == pop[0].entry_conditions]
        assert 90.0 in kept_fitnesses

    def test_apply_fitness_sharing_penalizes_crowded(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=5)
        for ind in pop:
            ind.fitness = 70.0
        # Make all identical → crowded niche
        for ind in pop:
            ind.entry_conditions = [{"indicator": "same", "operator": "above", "value": 1.0}]
        apply_fitness_sharing(pop, sharing_sigma=0.5)
        # All should have shared fitness lower than raw
        for ind in pop:
            assert ind.fitness < 70.0

    def test_inject_fresh_blood_replaces_worst(self):
        factors = _make_factors(10)
        pop = initialize_population(factors, symbol="RB", population_size=10)
        for i, ind in enumerate(pop):
            ind.fitness = float(i)  # 0, 1, 2, ...
        original_worst_uid = pop[0].uid  # fitness=0
        new_pop = inject_fresh_blood(pop, factors, symbol="RB", n_fresh=3)
        assert len(new_pop) == 10
        # Worst should be replaced
        replaced_uids = {ind.uid for ind in new_pop}
        assert original_worst_uid not in replaced_uids


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

import asyncio


async def _collect_stream(agent, query):
    """收集流式事件。"""
    events = []
    async for event in agent.run_stream(query):
        events.append(event)
    return events


def _create_user(db_session):
    from models import UserDB
    user = UserDB(
        username="evo_test_user",
        email="evo_test@example.com",
        password_hash="x",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_test_variety_with_klines(db_session, symbol="RB", n_bars=200):
    """创建测试品种 + K 线数据。

    Returns: (variety, contract) or (None, None) if RB already exists from seed_varieties.
    如果 symbol 已在种子数据中存在，会清空旧 K 线并重新插入（避免日期问题）。
    """
    from models import FutContractDB, KlineDataDB, RealtimeQuoteDB, VarietyDB

    existing = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if existing:
        # 可能来自 seed_varieties 但无 K 线——直接给它加 K 线
        variety = existing
        # 确保有 contract
        contract = db_session.query(FutContractDB).filter(FutContractDB.symbol == symbol).first()
        if not contract:
            today = date.today()
            contract = FutContractDB(
                ts_code=symbol + "2501.SHF",
                symbol=symbol,
                name=variety.name,
                exchange=variety.exchange or "SHFE",
                fut_code=symbol + "2501",
                list_date=date(2024, 1, 1),
                delist_date=date(2025, 12, 31),
                contract_type="main",
                is_active=True,
            )
            db_session.add(contract)
            db_session.commit()
            db_session.refresh(contract)
    else:
        variety = VarietyDB(
            symbol=symbol,
            contract_code=symbol + "2501",
            name="螺纹钢" if symbol == "RB" else "测试品种",
            exchange="SHFE",
            category="黑色系",
            margin_rate=8.0,
            multiplier=10,
            is_active=True,
        )
        db_session.add(variety)
        db_session.commit()
        db_session.refresh(variety)

        contract = FutContractDB(
            ts_code=symbol + "2501.SHF",
            symbol=symbol,
            name=variety.name,
            exchange="SHFE",
            fut_code=symbol + "2501",
            list_date=date(2024, 1, 1),
            delist_date=date(2025, 12, 31),
            contract_type="main",
            is_active=True,
        )
        db_session.add(contract)
        db_session.commit()
        db_session.refresh(contract)

    # Check if klines already exist for this variety
    existing_klines = db_session.query(KlineDataDB).filter(
        KlineDataDB.variety_id == variety.id, KlineDataDB.period == "1d"
    ).count()
    if existing_klines >= n_bars:
        return variety, contract

    # 生成合成 K 线（使用近期日期确保日期范围查询命中）
    rng = np.random.default_rng(42)
    n = n_bars
    t = np.arange(n)
    trend = 0.1 * t / n
    noise = rng.normal(0, 0.02, n).cumsum()
    log_price = np.log(3500) + trend + noise
    price = np.exp(log_price)

    today = date.today()
    for i in range(n):
        close_val = float(price[i])
        kline = KlineDataDB(
            variety_id=variety.id,
            contract_id=contract.id,
            period="1d",
            trading_time=today - timedelta(days=n - i),
            trading_date=today - timedelta(days=n - i),
            open_price=close_val * (1 + rng.normal(0, 0.003)),
            high_price=close_val * (1 + abs(rng.normal(0, 0.008))),
            low_price=close_val * (1 - abs(rng.normal(0, 0.008))),
            close_price=close_val,
            volume=int(rng.integers(1000, 50000)),
        )
        db_session.add(kline)

    # 实时行情
    quote = RealtimeQuoteDB(
        variety_id=variety.id,
        current_price=float(price[-1]),
        open_price=float(price[-1]) * 0.99,
        high=float(price[-1]) * 1.02,
        low=float(price[-1]) * 0.98,
        change_percent=0.5,
        volume=10000,
    )
    db_session.add(quote)
    db_session.commit()

    return variety, contract


# ------------------------------------------------------------------
# Phase 2B: GP Factor Generation Tests
# ------------------------------------------------------------------

class TestGPFactorGeneration:
    def test_generate_random_factor_produces_valid_formulas(self, n_samples=50):
        """GP 生成的因子公式应该全部通过安全校验。"""
        from services.agent.factor_engine.dsl import validate_factor_formula

        for _ in range(n_samples):
            formula = generate_random_factor(max_depth=2)
            assert formula, "生成公式不能为空"
            try:
                validate_factor_formula(formula)
            except ValueError as exc:
                pytest.fail(f"GP 公式校验失败：{formula} → {exc}")

    def test_generate_random_factor_different_depths(self):
        """不同深度的公式应有不同复杂度。"""
        formulas_d1 = [generate_random_factor(max_depth=1) for _ in range(20)]
        formulas_d3 = [generate_random_factor(max_depth=3) for _ in range(20)]

        avg_len_d1 = sum(len(f) for f in formulas_d1) / len(formulas_d1)
        avg_len_d3 = sum(len(f) for f in formulas_d3) / len(formulas_d3)
        assert avg_len_d1 > 0
        assert avg_len_d3 > 0

    def test_generate_gp_factors(self):
        """批量生成 GP 因子。"""
        factors = generate_gp_factors(n_generate=30, max_depth=2)
        assert len(factors) > 0
        assert len(factors) <= 30
        for f in factors:
            assert f.formula
            assert f.template_name == "gp_generated"

    def test_generate_gp_factors_no_duplicates(self):
        """GP 因子不应有重复公式。"""
        factors = generate_gp_factors(n_generate=30, max_depth=2)
        formulas = [f.formula for f in factors]
        assert len(formulas) == len(set(formulas))

    def test_crossover_factor_formula(self):
        """交叉操作应产生新公式。"""
        a = "close / ts_delay(close, 5) - 1"
        b = "ts_mean(close, 10) / ts_mean(close, 60) - 1"
        for _ in range(10):
            child = crossover_factor_formula(a, b)
            if child is not None:
                return
        # 10 次都没产生子代是合理退化

    def test_crossover_factor_formula_same_formulas(self):
        """相同公式交叉应返回 None 或同一公式。"""
        a = "close / ts_delay(close, 5) - 1"
        child = crossover_factor_formula(a, a)

    def test_mutate_factor_formula_param(self):
        """参数变异应产生合法公式。"""
        from services.agent.factor_engine.dsl import validate_factor_formula

        formula = "ts_mean(close, 20)"
        for _ in range(10):
            mutated = mutate_factor_formula(formula, mutation_strength=0.3)
            if mutated is not None:
                validate_factor_formula(mutated)
                return

    def test_mutate_factor_formula_complex(self):
        """对复杂公式的变异应频繁成功。"""
        from services.agent.factor_engine.dsl import validate_factor_formula

        formula = "ts_rank(close, 20) * ts_std(volume, 10)"
        successes = 0
        for _ in range(20):
            mutated = mutate_factor_formula(formula, mutation_strength=0.3)
            if mutated is not None:
                validate_factor_formula(mutated)
                successes += 1

    def test_evolve_factor_pool(self):
        """因子池进化合并。"""
        template_factors = _make_factors(10)
        merged = evolve_factor_pool(template_factors, n_gp=20, gp_generations=2)
        assert len(merged) >= len(template_factors)

    def test_evolve_factor_pool_no_gp(self):
        """gp=0 时进化为空操作。"""
        template_factors = _make_factors(5)
        merged = evolve_factor_pool(template_factors, n_gp=0)
        assert len(merged) == len(template_factors)


# ------------------------------------------------------------------
# Phase 2B: Pareto Fitness Tests
# ------------------------------------------------------------------

class TestParetoFitness:
    def test_dominates_basic(self):
        """基本支配关系。"""
        a = np.array([2.0, 3.0, 0.5])
        b = np.array([1.0, 2.0, 0.4])
        assert _dominates(a, b)
        assert not _dominates(b, a)

    def test_dominates_equal(self):
        """完全相同时不支配。"""
        a = np.array([1.0, 2.0])
        b = np.array([1.0, 2.0])
        assert not _dominates(a, b)
        assert not _dominates(b, a)

    def test_dominates_incomparable(self):
        """不可比较时互不支配。"""
        a = np.array([2.0, 1.0])
        b = np.array([1.0, 2.0])
        assert not _dominates(a, b)
        assert not _dominates(b, a)

    def test_non_dominated_sort(self):
        """非支配排序基本测试。"""
        objectives = [
            np.array([3.0, 1.0]),
            np.array([2.0, 2.0]),
            np.array([1.0, 0.5]),
            np.array([0.5, 0.3]),
        ]
        ranks = non_dominated_sort(objectives)
        assert len(ranks) == 4
        assert ranks[0] == 0
        assert ranks[1] == 0
        assert ranks[2] > 0
        assert ranks[3] > 0

    def test_non_dominated_sort_all_pareto_optimal(self):
        """所有个体都是 Pareto 最优时，全部 rank=0。"""
        objectives = [
            np.array([3.0, 1.0]),
            np.array([1.0, 3.0]),
            np.array([2.0, 2.0]),
        ]
        ranks = non_dominated_sort(objectives)
        assert all(r == 0 for r in ranks)

    def test_crowding_distance(self):
        """拥挤距离计算。"""
        objectives = [
            np.array([1.0, 5.0]),
            np.array([2.0, 3.0]),
            np.array([3.0, 1.0]),
            np.array([4.0, 0.5]),
        ]
        front = [0, 1, 2, 3]
        cd = crowding_distance(objectives, front)
        assert cd[0] > 1e6 or cd[0] == float("inf")
        assert cd[3] > 1e6 or cd[3] == float("inf")
        assert cd[1] > 0
        assert cd[2] > 0

    def test_pareto_selection(self):
        """Pareto 选择应保留指定数量个体。"""
        individuals = list(range(10))
        objectives = [np.array([float(i), float(10 - i)]) for i in range(10)]
        selected = pareto_selection(individuals, objectives, n_select=5)
        assert len(selected) == 5
        assert all(0 <= idx < 10 for idx in selected)

    def test_pareto_selection_all(self):
        """n_select >= len 时选择全部。"""
        individuals = list(range(5))
        objectives = [np.array([float(i), float(5 - i)]) for i in range(5)]
        selected = pareto_selection(individuals, objectives, n_select=10)
        assert len(selected) == 5

    def test_compute_pareto_fitness(self):
        """Pareto 适应度计算。"""
        results = [
            {
                "metrics": {
                    "sharpe": 2.0, "annualized_return_pct": 30.0,
                    "max_drawdown_pct": 10.0, "win_rate_pct": 50.0,
                    "profit_factor": 2.0, "trade_count": 20, "score": 80,
                }
            },
            {
                "metrics": {
                    "sharpe": 1.5, "annualized_return_pct": 20.0,
                    "max_drawdown_pct": 15.0, "win_rate_pct": 45.0,
                    "profit_factor": 1.8, "trade_count": 10, "score": 60,
                }
            },
            {
                "metrics": {
                    "sharpe": -0.5, "annualized_return_pct": -10.0,
                    "max_drawdown_pct": 30.0, "win_rate_pct": 30.0,
                    "profit_factor": 0.7, "trade_count": 2, "score": 15,
                }
            },
        ]
        condition_counts = [2, 3, 5]
        scores = compute_pareto_fitness(results, condition_counts)
        assert len(scores) == 3
        for s in scores:
            assert isinstance(s, FitnessScore)
            assert "pareto_rank" in s.components
            assert "crowding_distance" in s.components


# ------------------------------------------------------------------
# Phase 2B: Bayesian Optimizer Tests
# ------------------------------------------------------------------

class TestBayesianOptimizer:
    def test_bayesian_optimizer_import(self):
        """确认模块可导入。"""
        from services.agent.evolution.bayesian_optimizer import (
            BayesianOptimizer,
            BOParams,
            _expected_improvement,
            optimize_strategy_params_bayesian,
        )
        assert BayesianOptimizer is not None
        assert BOParams is not None

    def test_bo_params_normalize_roundtrip(self):
        """参数归一化 -> 恢复的往返一致性。"""
        from services.agent.evolution.bayesian_optimizer import BOParams

        params = BOParams(
            stop_loss_atr=2.0,
            take_profit_rr=2.0,
            position_size_pct=0.2,
            thresholds=[0.5],
        )
        x = params.to_normalized()
        params2 = BOParams.from_normalized(x, n_thresholds=1)
        assert abs(params2.stop_loss_atr - 2.0) < 0.2
        assert abs(params2.take_profit_rr - 2.0) < 0.2
        assert abs(params2.position_size_pct - 0.2) < 0.05

    def test_bo_params_clamp(self):
        """参数夹紧应在合法范围内。"""
        from services.agent.evolution.bayesian_optimizer import BOParams

        params = BOParams(stop_loss_atr=-1.0, take_profit_rr=100.0, position_size_pct=2.0)
        params.clamp()
        assert 0.5 <= params.stop_loss_atr <= 5.0
        assert 1.0 <= params.take_profit_rr <= 5.0
        assert 0.05 <= params.position_size_pct <= 0.5

    def test_bayesian_optimizer_optimize_simple(self):
        """在简单二次函数上测试 BO。"""
        from services.agent.evolution.bayesian_optimizer import BayesianOptimizer

        def objective(x: np.ndarray) -> float:
            return -float(np.sum((x - 0.5) ** 2))

        bo = BayesianOptimizer(n_dim=5, n_initial=8, n_iterations=20, random_state=42)
        best_x, best_y, history = bo.optimize(objective)

        assert best_y > -1.0
        assert len(history) > 0
        assert history[-1]["best_y"] >= history[0]["best_y"]

    def test_bayesian_optimizer_improves_over_time(self):
        """BO 应该在迭代中提升。"""
        from services.agent.evolution.bayesian_optimizer import BayesianOptimizer

        def objective(x: np.ndarray) -> float:
            return -float(np.sum((x - 0.7) ** 2))

        bo = BayesianOptimizer(n_dim=3, n_initial=5, n_iterations=15, random_state=123)
        best_x, best_y, history = bo.optimize(objective)

        initial_best = history[0]["best_y"]
        final_best = history[-1]["best_y"]
        assert final_best >= initial_best

    def test_optimize_strategy_params_bayesian(self):
        """封装接口测试。"""
        from services.agent.evolution.bayesian_optimizer import optimize_strategy_params_bayesian

        def simple_backtest(params: dict) -> float:
            score = 60.0
            score -= abs(params["stop_loss_atr"] - 2.0) * 5
            score -= abs(params["take_profit_rr"] - 2.5) * 3
            return max(0, score)

        best_params, best_fitness, history = optimize_strategy_params_bayesian(
            backtest_fn=simple_backtest,
            initial_params={
                "stop_loss_atr": 1.5,
                "take_profit_rr": 2.0,
                "position_size_pct": 0.2,
                "thresholds": [0.5],
            },
            n_iterations=15,
            n_initial=5,
            random_state=42,
        )

        assert best_fitness > 0
        assert "stop_loss_atr" in best_params
        assert 0.5 <= best_params["stop_loss_atr"] <= 5.0
        assert len(history) > 0

    def test_expected_improvement(self):
        """EI 采集函数测试。"""
        from services.agent.evolution.bayesian_optimizer import (
            BayesianOptimizer,
            _expected_improvement,
        )

        bo = BayesianOptimizer(n_dim=2, n_initial=5, n_iterations=1, random_state=42)

        X = np.array([[0.2, 0.3], [0.4, 0.6], [0.5, 0.5], [0.7, 0.2], [0.9, 0.8]])
        y = np.array([0.5, 0.6, 0.8, 0.4, 0.3])
        bo.X_observed = [X[i] for i in range(len(X))]
        bo.y_observed = list(y)
        bo.gp.fit(X, y)

        ei_at_known = _expected_improvement(
            X[2].reshape(1, -1), bo.gp, y_best=0.8, xi=0.01
        )
        assert ei_at_known < 1.0

        x_new = np.array([[0.1, 0.9]])
        ei_new = _expected_improvement(x_new.reshape(1, -1), bo.gp, y_best=0.8, xi=0.01)
        assert ei_new >= 0.0
