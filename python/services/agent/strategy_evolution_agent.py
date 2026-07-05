"""自进化策略 Agent。

Phase 1：最小闭环 —— 市场状态识别 → 因子发现 → 种群初始化 → 进化迭代 → 适应度评估 → 策略产出。
Phase 2A：完整 GA (交叉+多类型变异) + OOS 验证 + 多样性维护。
Phase 2B：GP 因子生成 + Pareto 多目标适应度 + 贝叶斯优化参数精调。

从价格数据中自动发现和进化交易策略。支持 SSE 流式展示进化过程。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any

import pandas as pd

from services.agent.core import Agent, AgentEvent, AgentEventType, AgentResult, AgentStatus
from services.agent.data_tools import _get_kline_data
from services.agent.evolution.factor_discovery import FactorCandidate, discover_factors
from services.agent.evolution.fitness import (
    compute_fitness,
    compute_fitness_with_oos,
    compute_pareto_fitness,
    split_train_test_dates,
)
from services.agent.evolution.genetic_operators import next_generation
from services.agent.evolution.market_regime import detect_regime
from services.agent.evolution.strategy_population import (
    StrategyIndividual,
    initialize_population,
    population_diversity,
)
from services.agent.evolution.strategy_population import (
    best_individual as pop_best_individual,
)
from services.agent.factor_engine.dsl import PanelData, evaluate_factor
from services.agent.utils import resolve_symbol
from services.backtest.service import run_dsl_backtest
from services.data_catalog import DataCatalogService

logger = logging.getLogger(__name__)

# 默认进化配置
_DEFAULT_EVOLUTION_CONFIG: dict[str, Any] = {
    "population_size": 40,
    "generations": 10,
    "elite_count": 5,
    "mutation_rate": 0.3,
    "mutation_strength": 0.15,
    "factor_top_n": 15,
    "factor_min_abs_rank_ic": 0.02,
    "symbol": None,  # 运行时自动解析
    "period": "1d",
    "direction": "long",
    "initial_cash": 100_000.0,
    "quantity": 1,
    "limit": 500,
    "min_kline_bars": 60,
    "early_stop_generations": 5,  # 连续 N 代无提升后提前终止
    "oos_split_ratio": 0.3,  # OOS 验证的数据占比（0=禁用）
    "crossover_rate": 0.7,  # 交叉概率
    # Phase 2B: GP + Pareto + Bayesian Optimization
    "use_gp_factors": False,  # 启用 GP 因子生成
    "gp_n_generate": 80,  # GP 初始因子数量
    "gp_generations": 3,  # GP 进化代数
    "use_pareto_fitness": False,  # 启用 NSGA-II Pareto 适应度
    "use_bayesian_optimization": False,  # 启用贝叶斯优化参数精调
    "bo_iterations": 30,  # BO 迭代次数
    "bo_initial_samples": 10,  # BO 初始采样数
}


def _compute_factor_columns(
    db,
    df: pd.DataFrame,
    symbol: str,
    factors: list[FactorCandidate],
) -> dict[str, pd.Series]:
    """为因子列表预计算 custom_columns（单品种面板上求值）。

    每个因子以 factor_custom:<hash> 为 key 缓存。

    Args:
        db: 数据库会话。
        df: K 线 DataFrame（含 time 列）。
        symbol: 品种代码。
        factors: 因子列表。

    Returns:
        {column_name: pd.Series} 字典用于注入回测。
    """
    if df.empty or "time" not in df.columns:
        return {}

    df_time = df.copy()
    df_time["time"] = pd.to_datetime(df_time["time"], format="mixed")
    df_indexed = df_time.set_index("time").copy()

    panel = PanelData(
        open=pd.DataFrame({symbol: df_indexed["open"]}),
        high=pd.DataFrame({symbol: df_indexed["high"]}),
        low=pd.DataFrame({symbol: df_indexed["low"]}),
        close=pd.DataFrame({symbol: df_indexed["close"]}),
        volume=pd.DataFrame({symbol: df_indexed["volume"]}),
    )

    columns: dict[str, pd.Series] = {}
    for factor in factors:
        formula_hash = hashlib.md5(factor.formula.encode()).hexdigest()[:12]
        col_name = f"factor_custom:{formula_hash}"
        if col_name in columns:
            continue
        try:
            result = evaluate_factor(factor.formula, panel)
            series = result[symbol]
            columns[col_name] = series
        except (ValueError, KeyError, Exception) as exc:
            logger.debug("因子列计算失败 %s：%s", factor.label, exc)

    return columns


def _evaluate_population(
    db,
    df: pd.DataFrame,
    symbol: str,
    period: str,
    population: list[StrategyIndividual],
    factor_columns: dict[str, pd.Series],
    config: dict[str, Any],
) -> None:
    """对种群中所有未评估个体执行回测并计算适应度。

    原地修改每个个体的 fitness 和 backtest_result。

    Args:
        db: 数据库会话。
        df: K 线 DataFrame。
        symbol: 品种代码。
        period: 周期。
        population: 种群。
        factor_columns: 预计算的因子列。
        config: 进化配置。
    """
    direction = config.get("direction", "long")
    initial_cash = float(config.get("initial_cash", 100_000))
    quantity = int(config.get("quantity", 1))
    limit_val = int(config.get("limit", 500))
    use_pareto = config.get("use_pareto_fitness", False)

    # 收集本轮需要评估的个体
    unevaluated = [ind for ind in population if ind.fitness is None]
    if not unevaluated:
        return

    backtest_results: list[dict[str, Any] | None] = []
    condition_counts: list[int] = []

    for individual in unevaluated:
        entry_conditions = deepcopy(individual.entry_conditions)
        exit_conditions = deepcopy(individual.exit_conditions)

        try:
            result = run_dsl_backtest(
                db,
                symbol=symbol,
                period=period,
                direction=direction,
                entry_conditions=entry_conditions,
                exit_conditions=exit_conditions,
                initial_cash=initial_cash,
                quantity=quantity,
                limit=limit_val,
                custom_columns=factor_columns,
            )
            individual.backtest_result = result
            backtest_results.append(result)
            condition_counts.append(len(entry_conditions) + len(exit_conditions))
        except Exception as exc:
            logger.warning("个体 %s 回测失败：%s", individual.uid, exc)
            individual.fitness = 0.0
            individual.backtest_result = None
            backtest_results.append(None)
            condition_counts.append(0)

    # 适应度计算
    if use_pareto and backtest_results:
        # Pareto 多目标适应度
        valid_indices = [i for i, bt in enumerate(backtest_results) if bt is not None]
        valid_results = [backtest_results[i] for i in valid_indices]
        valid_counts = [condition_counts[i] for i in valid_indices]
        valid_individuals = [unevaluated[i] for i in valid_indices]

        pareto_scores = compute_pareto_fitness(valid_results, valid_counts)
        for ind, score in zip(valid_individuals, pareto_scores, strict=False):
            ind.fitness = score.total
            ind.fitness_components = score.components

        # 回测失败的个体设为最低适应度
        for i, bt in enumerate(backtest_results):
            if bt is None:
                unevaluated[i].fitness = 0.0
                unevaluated[i].fitness_components = {}
    else:
        # 标量加权适应度
        for individual, bt, cc in zip(unevaluated, backtest_results, condition_counts, strict=False):
            if individual.fitness is not None:
                continue
            if bt is None:
                individual.fitness = 0.0
                continue
            fitness = compute_fitness(bt, condition_count=cc)
            individual.fitness = fitness.total
            individual.fitness_components = fitness.components


class StrategyEvolutionAgent(Agent):
    """自进化策略发现 Agent。

    从价格数据中自动生成和进化交易策略。
    """

    name = "strategy_evolution"
    description = "自进化策略引擎：自动从价格变化中发现、进化、优化交易策略"

    async def run(self, query: str) -> AgentResult:
        """执行自进化策略发现。

        Args:
            query: 用户查询，例如 "为螺纹钢日线自动发现策略，进化 10 代"。

        Returns:
            AgentResult 包含进化报告和最优策略 DSL。
        """
        self._add_step("thought", f"开始自进化策略发现：{query}")
        db = self.context.db

        # ─── 1. 解析意图 ───
        symbol = resolve_symbol(db, query)
        if not symbol:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message="无法识别品种，请提供品种代码（如 RB、AU）或品种名称。",
                steps=self.get_steps(),
            )

        config = dict(_DEFAULT_EVOLUTION_CONFIG)
        config["symbol"] = symbol
        # 从查询中提取可选配置
        if "做空" in query or "short" in query.lower():
            config["direction"] = "short"
        # 代数 override
        import re

        gen_match = re.search(r"(\d+)\s*代", query)
        if gen_match:
            config["generations"] = min(int(gen_match.group(1)), 50)

        self._add_step(
            "action",
            f"品种：{symbol}，周期：{config['period']}，方向：{config['direction']}，进化 {config['generations']} 代",
        )

        # ─── 2. 数据前置检查 ───
        catalog = DataCatalogService(db)
        coverage = catalog.get_symbol_data_coverage(symbol, period=config["period"])
        kline_cov = coverage["datasets"]["kline_data"]
        row_count = int(kline_cov.get("row_count") or 0)
        if row_count < config["min_kline_bars"]:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"{symbol} 可用 K 线仅 {row_count} 根，需要至少 {config['min_kline_bars']} 根（目前无法回测）。",
                steps=self.get_steps(),
            )
        self._add_step(
            "observation",
            f"数据检查通过：{symbol} K 线 {row_count} 根（{kline_cov.get('first_date')} ~ {kline_cov.get('last_date')}）",
        )

        # ─── 3. 加载 K 线 ───
        klines = _get_kline_data(db, symbol, period=config["period"], limit=config["limit"])
        df = pd.DataFrame(klines)
        if len(df) < config["min_kline_bars"]:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"{symbol} 实际加载 {len(df)} 根 K 线，不足 {config['min_kline_bars']}。",
                steps=self.get_steps(),
            )

        # ─── 4. 市场状态识别 ───
        try:
            regime = detect_regime(df)
            self._add_step(
                "observation",
                f"市场状态：{regime.regime}（置信度 {regime.confidence}，ADX={regime.metrics['adx']}，Hurst={regime.metrics['hurst']}）",
            )
        except Exception as exc:
            logger.warning("市场状态识别失败：%s", exc)
            regime = None  # 退化：不依赖 regime 继续

        # ─── 5. 因子发现 ───
        self._add_step("thought", "开始因子自动发现（模板生成 + IC 筛选）...")
        factors = discover_factors(
            db,
            symbols=[symbol],
            period=config["period"],
            min_bars=config["min_kline_bars"],
            min_abs_rank_ic=config["factor_min_abs_rank_ic"],
            top_n=config["factor_top_n"],
            use_gp=config.get("use_gp_factors", False),
            n_gp=config.get("gp_n_generate", 80),
            gp_generations=config.get("gp_generations", 3),
        )
        if not factors:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"因子发现失败：{symbol} 上没有找到有效的预测因子。请检查数据量是否充足。",
                steps=self.get_steps(),
            )
        top_rank_ic = f"{factors[0].rank_ic_mean:.4f}" if factors[0].rank_ic_mean is not None else "N/A"
        self._add_step("observation", f"因子发现完成：{len(factors)} 个有效因子（Top Rank IC: {top_rank_ic}）")

        # 预计算所有因子列（供回测复用）
        factor_columns = _compute_factor_columns(db, df, symbol, factors)

        # ─── 6. 初始化种群 ───
        self._add_step("thought", f"初始化策略种群（大小 {config['population_size']}）...")
        population = initialize_population(
            factors,
            symbol=symbol,
            timeframe=config["period"],
            population_size=config["population_size"],
            direction=config["direction"],
            regime=regime,
        )
        self._add_step("action", "种群已初始化，开始第 0 代评估")

        # ─── 7. 进化循环 ───
        best_fitness_history: list[float] = []
        best_individual_overall: StrategyIndividual | None = None
        evolution_log: list[dict[str, Any]] = []

        for gen in range(config["generations"] + 1):
            # 评估种群
            _evaluate_population(db, df, symbol, config["period"], population, factor_columns, config)

            # 统计
            fitnesses = [ind.fitness for ind in population if ind.fitness is not None]
            if not fitnesses:
                self._add_step("error", f"第 {gen} 代全部回测失败")
                break

            avg_fitness = sum(fitnesses) / len(fitnesses)
            best_ind = pop_best_individual(population)
            if best_ind is None:
                break

            diversity = population_diversity(population)
            best_fitness_history.append(best_ind.fitness or 0)

            if best_individual_overall is None or (best_ind.fitness or 0) > (best_individual_overall.fitness or 0):
                best_individual_overall = deepcopy(best_ind)

            gen_log = {
                "generation": gen,
                "best_fitness": best_ind.fitness,
                "avg_fitness": round(avg_fitness, 2),
                "diversity": round(diversity, 3),
                "best_uid": best_ind.uid,
            }
            evolution_log.append(gen_log)
            self._add_step(
                "observation",
                f"第 {gen} 代 | 最佳适应度 {best_ind.fitness:.1f} | 平均 {avg_fitness:.1f} | 多样性 {diversity:.2f} | 最优策略 {best_ind.uid[:8]}",
            )

            # 早停检查
            if gen >= config["early_stop_generations"]:
                recent = best_fitness_history[-config["early_stop_generations"] :]
                if len(recent) >= config["early_stop_generations"] and max(recent) - min(recent) < 1.0:
                    self._add_step("system", f"连续 {config['early_stop_generations']} 代无显著提升，提前终止")
                    break

            if gen < config["generations"]:
                # 产生下一代
                population = next_generation(
                    population,
                    elite_count=config["elite_count"],
                    mutation_rate=config["mutation_rate"],
                    mutation_strength=config["mutation_strength"],
                    crossover_rate=config.get("crossover_rate", 0.7),
                    factor_pool=factors,
                )

        # ─── 8. OOS 验证 ───
        oos_result = None
        oos_fitness = None
        bo_result = None
        df_dates = pd.to_datetime(df["time"], format="mixed")
        data_start = df_dates.iloc[0].date()
        data_end = df_dates.iloc[-1].date()

        if config.get("oos_split_ratio", 0) > 0:
            split = split_train_test_dates(
                data_start,
                data_end,
                test_ratio=config["oos_split_ratio"],
                min_train_bars=config["min_kline_bars"],
            )
            if split:
                (train_start, train_end), (test_start, test_end) = split
                self._add_step(
                    "action",
                    f"样本外验证：IS {train_start} ~ {train_end} / OOS {test_start} ~ {test_end}",
                )
                try:
                    oos_klines = _get_kline_data(
                        db,
                        symbol,
                        period=config["period"],
                        limit=config["limit"],
                        start_date=test_start,
                        end_date=test_end,
                    )
                    if len(oos_klines) >= 10:
                        oos_result = run_dsl_backtest(
                            db,
                            symbol=symbol,
                            period=config["period"],
                            direction=config["direction"],
                            entry_conditions=best_individual_overall.entry_conditions,
                            exit_conditions=best_individual_overall.exit_conditions,
                            initial_cash=float(config.get("initial_cash", 100_000)),
                            quantity=int(config.get("quantity", 1)),
                            limit=config["limit"],
                            custom_columns=factor_columns,
                            start_date=test_start,
                            end_date=test_end,
                        )
                        condition_count = len(best_individual_overall.entry_conditions) + len(
                            best_individual_overall.exit_conditions
                        )
                        oos_fitness = compute_fitness_with_oos(
                            best_individual_overall.backtest_result or {},
                            oos_result,
                            condition_count=condition_count,
                            oos_consistency_weight=0.25,
                        )
                        self._add_step(
                            "observation",
                            f"OOS 验证完成 — IS Sharpe: {best_individual_overall.backtest_result.get('metrics', {}).get('sharpe', '—')} | OOS Sharpe: {oos_result.get('metrics', {}).get('sharpe', '—')} | 一致性评分: {oos_fitness.total:.1f}",
                        )
                    else:
                        self._add_step("observation", "OOS 数据不足（<10 根 K 线），跳过验证")
                except Exception as exc:
                    logger.warning("OOS 验证失败：%s", exc)
                    self._add_step("observation", f"OOS 验证失败：{exc}")
            else:
                self._add_step("observation", "数据不足以进行 OOS 切分，跳过验证")

        # ─── 8b. 贝叶斯优化参数精调（可选） ───
        if (
            config.get("use_bayesian_optimization", False)
            and best_individual_overall is not None
            and best_individual_overall.backtest_result is not None
        ):
            self._add_step("thought", "开始贝叶斯优化参数精调...")
            try:
                from services.agent.evolution.bayesian_optimizer import optimize_strategy_params_bayesian

                n_conditions = len(best_individual_overall.entry_conditions)
                init_params = {
                    "stop_loss_atr": float(best_individual_overall.risk.get("stop_loss", {}).get("value", 2.0)),
                    "take_profit_rr": float(best_individual_overall.risk.get("take_profit", {}).get("value", 2.0)),
                    "position_size_pct": float(
                        best_individual_overall.risk.get("position_size", {}).get("value", 20) / 100
                    ),
                    "thresholds": [
                        best_individual_overall.entry_conditions[i].get("value", 0.5)
                        for i in range(min(n_conditions, 3))
                    ],
                }

                def bo_objective(param_dict: dict[str, Any]) -> float:
                    """BO 目标函数：根据参数调整策略后回测，返回适应度。"""
                    test_ind = deepcopy(best_individual_overall)

                    # 应用参数
                    test_ind.risk["stop_loss"]["value"] = param_dict["stop_loss_atr"]
                    test_ind.risk["take_profit"]["value"] = param_dict["take_profit_rr"]
                    test_ind.risk["position_size"]["value"] = int(param_dict["position_size_pct"] * 100)

                    for i, thresh in enumerate(param_dict.get("thresholds", [])):
                        if i < len(test_ind.entry_conditions):
                            test_ind.entry_conditions[i]["value"] = thresh

                    try:
                        result = run_dsl_backtest(
                            db,
                            symbol=symbol,
                            period=config["period"],
                            direction=config["direction"],
                            entry_conditions=test_ind.entry_conditions,
                            exit_conditions=test_ind.exit_conditions,
                            initial_cash=float(config.get("initial_cash", 100_000)),
                            quantity=int(config.get("quantity", 1)),
                            limit=config["limit"],
                            custom_columns=factor_columns,
                        )
                        cc = len(test_ind.entry_conditions) + len(test_ind.exit_conditions)
                        return compute_fitness(result, condition_count=cc).total
                    except Exception:
                        return 0.0

                bo_best_params, bo_best_fitness, bo_history = optimize_strategy_params_bayesian(
                    backtest_fn=bo_objective,
                    initial_params=init_params,
                    n_iterations=config.get("bo_iterations", 30),
                    n_initial=config.get("bo_initial_samples", 10),
                )
                bo_result = {
                    "params": bo_best_params,
                    "fitness": bo_best_fitness,
                    "history": bo_history,
                }

                # 将 BO 最优参数应用到最优个体
                best_individual_overall.risk["stop_loss"]["value"] = bo_best_params["stop_loss_atr"]
                best_individual_overall.risk["take_profit"]["value"] = bo_best_params["take_profit_rr"]
                best_individual_overall.risk["position_size"]["value"] = int(bo_best_params["position_size_pct"] * 100)
                for i, thresh in enumerate(bo_best_params.get("thresholds", [])):
                    if i < len(best_individual_overall.entry_conditions):
                        best_individual_overall.entry_conditions[i]["value"] = thresh

                # 用优化后的参数重新回测
                final_result = run_dsl_backtest(
                    db,
                    symbol=symbol,
                    period=config["period"],
                    direction=config["direction"],
                    entry_conditions=best_individual_overall.entry_conditions,
                    exit_conditions=best_individual_overall.exit_conditions,
                    initial_cash=float(config.get("initial_cash", 100_000)),
                    quantity=int(config.get("quantity", 1)),
                    limit=config["limit"],
                    custom_columns=factor_columns,
                )
                best_individual_overall.backtest_result = final_result
                cc = len(best_individual_overall.entry_conditions) + len(best_individual_overall.exit_conditions)
                best_fitness = compute_fitness(final_result, condition_count=cc)
                best_individual_overall.fitness = best_fitness.total
                best_individual_overall.fitness_components = best_fitness.components

                self._add_step(
                    "observation",
                    f"贝叶斯优化完成：最优适应度 {bo_best_fitness:.1f}（{len(bo_history)} 次评估）",
                )
            except Exception as exc:
                logger.warning("贝叶斯优化失败：%s", exc)
                self._add_step("observation", f"贝叶斯优化跳过：{exc}")
                bo_result = None

        # ─── 9. 生成报告 ───
        if best_individual_overall is None:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message="进化未产生任何有效策略",
                steps=self.get_steps(),
            )

        dsl = best_individual_overall.to_dsl(
            name=f"{symbol} 自进化策略 v{best_individual_overall.generation}",
            symbol=symbol,
        )
        # 注入因子来源信息 + OOS 验证结果 + BO 优化结果
        oos_metrics = oos_result.get("metrics", {}) if oos_result else None
        dsl["_evolution_meta"] = {
            "best_fitness": best_individual_overall.fitness,
            "fitness_components": best_individual_overall.fitness_components,
            "source_factors": best_individual_overall.source_factors,
            "generation": best_individual_overall.generation,
            "regime": regime.regime if regime else None,
            "regime_confidence": regime.confidence if regime else None,
            "evolution_log": evolution_log,
            "oos_result": oos_metrics,
            "oos_fitness": oos_fitness.total if oos_fitness else None,
            "is_oos_validated": oos_result is not None,
            "bo_result": bo_result,
            "is_bo_optimized": bo_result is not None,
            "use_pareto": config.get("use_pareto_fitness", False),
            "use_gp": config.get("use_gp_factors", False),
        }

        explanation = _build_evolution_report(
            symbol=symbol,
            config=config,
            regime=regime,
            factors=factors,
            best_individual=best_individual_overall,
            evolution_log=evolution_log,
            dsl=dsl,
            oos_result=oos_result,
            oos_fitness=oos_fitness,
            bo_result=bo_result,
        )

        self._add_step("system", "进化完成，报告已生成")

        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=explanation,
            data={
                "dsl": dsl,
                "json": json.dumps(dsl, ensure_ascii=False, indent=2, default=str),
                "best_fitness": best_individual_overall.fitness,
                "evolution_log": evolution_log,
                "factors_used": len(factors),
                "regime": regime.regime if regime else "unknown",
                "symbol": symbol,
            },
            steps=self.get_steps(),
        )

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行进化过程。"""
        result = await self.run(query)

        for step in result.steps:
            yield AgentEvent(
                event_type=self._map_role_to_event_type(step.role),
                step_number=step.step_number,
                role=step.role,
                content=step.content,
                tool_name=step.tool_name,
                tool_input=step.tool_input,
                tool_output=step.tool_output,
            ).to_dict()

        if result.success:
            yield AgentEvent(
                event_type=AgentEventType.RESULT,
                content=result.answer,
                result=result.to_dict(),
            ).to_dict()
        else:
            yield AgentEvent(
                event_type=AgentEventType.ERROR,
                content=result.error_message or "进化失败",
                error_message=result.error_message,
                result=result.to_dict(),
            ).to_dict()

    @staticmethod
    def _map_role_to_event_type(role: str) -> AgentEventType:
        mapping = {
            "thought": AgentEventType.THOUGHT,
            "action": AgentEventType.ACTION,
            "observation": AgentEventType.OBSERVATION,
            "system": AgentEventType.THOUGHT,
            "error": AgentEventType.ERROR,
        }
        return mapping.get(role, AgentEventType.THOUGHT)


def _build_evolution_report(
    symbol: str,
    config: dict[str, Any],
    regime,
    factors: list[FactorCandidate],
    best_individual: StrategyIndividual,
    evolution_log: list[dict[str, Any]],
    dsl: dict[str, Any],
    oos_result: dict[str, Any] | None = None,
    oos_fitness: Any = None,
    bo_result: dict[str, Any] | None = None,
) -> str:
    """生成 Markdown 进化报告。"""
    direction_label = "做多" if config["direction"] == "long" else "做空"
    regime_label = {
        "trending_up": "趋势上行",
        "trending_down": "趋势下行",
        "range_bound": "区间震荡",
        "high_volatility": "高波动",
        "low_volatility": "低波动",
    }

    lines = [
        f"## 策略进化报告 — {symbol}",
        "",
        f"**方向**：{direction_label} | **周期**：{config['period']} | **进化代数**：{len(evolution_log)}",
        "",
        "### 市场状态",
    ]

    if regime:
        lines.append(f"- 状态：{regime_label.get(regime.regime, regime.regime)}（置信度 {regime.confidence:.0%}）")
        lines.append(
            f"- ADX：{regime.metrics.get('adx', '—')} | Hurst：{regime.metrics.get('hurst', '—')} | 波动率百分位：{regime.metrics.get('vol_percentile', '—')}"
        )
    else:
        lines.append("- 无法识别（数据不足）")

    lines.extend(
        [
            "",
            "### 进化过程",
            f"- 种群大小：{config['population_size']} | 代数：{len(evolution_log)} | 精英保留：{config['elite_count']}",
        ]
    )

    if len(evolution_log) >= 2:
        first_best = evolution_log[0]["best_fitness"]
        last_best = evolution_log[-1]["best_fitness"]
        if first_best > 0:
            improvement = (last_best - first_best) / first_best * 100
            lines.append(f"- 初始最优适应度：{first_best:.1f} → 最终：{last_best:.1f}（+{improvement:.0f}%）")

    lines.append(f"- 种群多样性：{evolution_log[-1]['diversity']:.2f}" if evolution_log else "- 无进化记录")

    lines.extend(
        [
            "",
            "### 发现的关键因子",
        ]
    )
    for i, f in enumerate(factors[:5], start=1):
        rank_ic_str = f"{f.rank_ic_mean:.4f}" if f.rank_ic_mean is not None else "—"
        icir_str = f"{f.rank_icir:.2f}" if f.rank_icir is not None else "—"
        lines.append(f"{i}. `{f.formula}` — Rank IC: {rank_ic_str}，ICIR: {icir_str}")

    lines.extend(
        [
            "",
            "### 最优策略",
            f"**入场条件**（{best_individual.entry_logic.upper()}）：",
        ]
    )
    for cond in best_individual.entry_conditions:
        lines.append(
            f"- {cond.get('indicator', '?')} {cond.get('operator', '?')} {cond.get('value') or cond.get('indicator2', '')}"
        )

    lines.append(f"**出场条件**（{best_individual.exit_logic.upper()}）：")
    for cond in best_individual.exit_conditions:
        lines.append(
            f"- {cond.get('indicator', '?')} {cond.get('operator', '?')} {cond.get('value') or cond.get('indicator2', '')}"
        )

    risk = best_individual.risk
    sl = risk.get("stop_loss", {})
    tp = risk.get("take_profit", {})
    pos = risk.get("position_size", {})
    lines.extend(
        [
            f"**风控**：止损 {sl.get('type', '—')} {sl.get('value', '')} | 止盈 {tp.get('type', '—')} {tp.get('value', '')} | 仓位 {pos.get('type', '—')} {pos.get('value', '')}",
            "",
            "### 回测表现",
        ]
    )
    if best_individual.backtest_result:
        metrics = best_individual.backtest_result.get("metrics", {})
        is_sharpe = metrics.get("sharpe", "—")
        lines.extend(
            [
                f"- 年化收益：{metrics.get('annualized_return_pct', '—')}% | 最大回撤：{metrics.get('max_drawdown_pct', '—')}%",
                f"- Sharpe：{is_sharpe} | 胜率：{metrics.get('win_rate_pct', '—')}%",
                f"- 盈亏比：{metrics.get('profit_factor', '—')} | 交易次数：{metrics.get('trade_count', '—')}",
                f"- 综合评分：{metrics.get('score', '—')}/100",
            ]
        )
    else:
        lines.append("- 回测未完成")

    # OOS 验证结果
    if oos_result:
        oos_metrics = oos_result.get("metrics", {})
        oos_sharpe = oos_metrics.get("sharpe", "—")
        lines.extend(
            [
                "",
                "### 样本外 (OOS) 验证",
                f"- OOS Sharpe：{oos_sharpe} | OOS 年化收益：{oos_metrics.get('annualized_return_pct', '—')}%",
                f"- OOS 最大回撤：{oos_metrics.get('max_drawdown_pct', '—')}% | OOS 交易次数：{oos_metrics.get('trade_count', '—')}",
            ]
        )
        if oos_fitness:
            lines.append(f"- IS/OOS 一致性评分：{oos_fitness.total:.1f}")
            stability = oos_fitness.components.get("stability", "—")
            stability_str = f"{stability:.0f}/100" if isinstance(stability, int | float) else str(stability)
            lines.append(f"- 稳定性：{stability_str}")

    # BO 优化结果
    if bo_result:
        lines.extend(
            [
                "",
                "### 贝叶斯优化 (Bayesian Optimization)",
                f"- BO 最优适应度：{bo_result.get('fitness', '—')}",
                f"- 优化参数：SL={bo_result['params'].get('stop_loss_atr', '—')}x ATR，TP={bo_result['params'].get('take_profit_rr', '—')}x RR，仓位={bo_result['params'].get('position_size_pct', '—')}",
                f"- 评估次数：{len(bo_result.get('history', []))} 次",
            ]
        )

    lines.extend(
        [
            "",
            "### 适应度分解",
            f"- 总分：{best_individual.fitness}",
        ]
    )
    for k, v in best_individual.fitness_components.items():
        score = v.get("score", v) if isinstance(v, dict) else v
        lines.append(f"- {k}：{score:.1f}")

    lines.extend(
        [
            "",
            "> ⚠️ 以上策略由遗传算法自动生成，存在过拟合风险。建议先在模拟环境验证 2-4 周。所有分析不构成投资建议。",
        ]
    )

    return "\n".join(str(line) for line in lines)
