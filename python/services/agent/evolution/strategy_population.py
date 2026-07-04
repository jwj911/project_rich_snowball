"""策略种群管理。

将因子组合成完整的可回测 Strategy DSL 个体，形成初始种群。
每个个体 = 入场条件（含因子阈值）+ 出场条件 + 风控参数。

Phase 1：简化版 —— 每个因子通过阈值比较转为 DSL condition，
单因子入场 + 均线交叉出场 + 默认风控。
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from services.agent.evolution.factor_discovery import FactorCandidate
from services.agent.evolution.market_regime import MarketRegime

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 出场条件模板
# ------------------------------------------------------------------

_EXIT_TEMPLATES: list[dict[str, Any]] = [
    # 均线跌破
    {
        "conditions": [
            {"indicator": "close", "operator": "cross_below", "indicator2": "sma10"},
        ],
        "logic": "and",
    },
    {
        "conditions": [
            {"indicator": "close", "operator": "cross_below", "indicator2": "sma20"},
        ],
        "logic": "and",
    },
    # ATR 追踪止损（用于 DSL，回测会用止损逻辑处理）
    {
        "conditions": [
            {"indicator": "close", "operator": "cross_below", "indicator2": "sma5"},
        ],
        "logic": "and",
    },
    # 固定比例出场（价格跌破入场价的 N%）
    # 注：这需要在回测中追踪入场价，这里用简单的均线兜底
    {
        "conditions": [
            {"indicator": "close", "operator": "cross_below", "indicator2": "boll_mid"},
        ],
        "logic": "and",
    },
]


@dataclass
class StrategyIndividual:
    """种群中的一个策略个体。"""

    uid: str
    """唯一标识（UUID）"""

    entry_conditions: list[dict[str, Any]]
    """入场条件列表（DSL format）"""

    entry_logic: str
    """入场逻辑门：and | or"""

    exit_conditions: list[dict[str, Any]]
    """出场条件列表（DSL format）"""

    exit_logic: str
    """出场逻辑门：and | or"""

    risk: dict[str, Any]
    """风控参数"""

    direction: str
    """方向：long | short"""

    timeframe: str
    """周期"""

    # 元信息
    source_factors: list[str] = field(default_factory=list)
    """来源因子公式列表"""
    generation: int = 0
    parent_uids: list[str] = field(default_factory=list)

    # 评估结果（后续填入）
    fitness: float | None = None
    fitness_components: dict[str, float] = field(default_factory=dict)
    backtest_result: dict[str, Any] | None = None

    def to_dsl(self, name: str | None = None, symbol: str = "") -> dict[str, Any]:
        """转换为 StrategyDSL 字典。"""
        return {
            "name": name or f"evolved-{self.uid[:8]}",
            "description": f"自动进化策略 — 因子: {', '.join(self.source_factors[:2])}",
            "universe": [symbol],
            "timeframe": self.timeframe,
            "direction": self.direction,
            "entry": {
                "conditions": deepcopy(self.entry_conditions),
                "logic": self.entry_logic,
            },
            "exit": {
                "conditions": deepcopy(self.exit_conditions),
                "logic": self.exit_logic,
            },
            "risk": deepcopy(self.risk),
        }

    def to_dict(self) -> dict[str, Any]:
        """序列化（用于种群快照持久化）。"""
        return {
            "uid": self.uid,
            "entry_conditions": self.entry_conditions,
            "entry_logic": self.entry_logic,
            "exit_conditions": self.exit_conditions,
            "exit_logic": self.exit_logic,
            "risk": self.risk,
            "direction": self.direction,
            "timeframe": self.timeframe,
            "source_factors": self.source_factors,
            "generation": self.generation,
            "parent_uids": self.parent_uids,
            "fitness": self.fitness,
            "fitness_components": self.fitness_components,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyIndividual:
        return cls(
            uid=data["uid"],
            entry_conditions=data["entry_conditions"],
            entry_logic=data["entry_logic"],
            exit_conditions=data["exit_conditions"],
            exit_logic=data["exit_logic"],
            risk=data["risk"],
            direction=data["direction"],
            timeframe=data["timeframe"],
            source_factors=data.get("source_factors", []),
            generation=data.get("generation", 0),
            parent_uids=data.get("parent_uids", []),
            fitness=data.get("fitness"),
            fitness_components=data.get("fitness_components", {}),
        )


def _factor_to_condition(factor: FactorCandidate, direction: str) -> dict[str, Any]:
    """将因子转换为 DSL 条件。

    根据因子 Rank IC 的正负确定阈值方向：
    - 正 IC：因子值高于阈值时做多
    - 负 IC：因子值低于阈值时做多

    对于 DSL condition，使用 custom_columns 注入因子值。
    condition 的 indicator 使用因子公式的稳定 hash 作为列名。
    """
    rank_ic = factor.rank_ic_mean or 0
    formula_hash = hashlib.md5(factor.formula.encode()).hexdigest()[:12]

    if rank_ic >= 0:
        # 正向因子：值高做多
        operator = "greater_than"
        threshold = 0.5  # 默认用中位数阈值（在回测中折算）
    else:
        # 负向因子：值低做多
        operator = "less_than"
        threshold = -0.5

    # 使用 factor:<hash> 作为 indicator 引用
    # 回测引擎 _inject_factor_columns 会自动注入
    return {
        "indicator": f"factor_custom:{formula_hash}",
        "operator": operator,
        "value": threshold,
    }


def initialize_population(
    factors: list[FactorCandidate],
    symbol: str,
    timeframe: str = "1d",
    population_size: int = 50,
    direction: str = "long",
    regime: MarketRegime | None = None,
) -> list[StrategyIndividual]:
    """从因子池初始化策略种群。

    每个策略 = 1-3 个因子作为入场条件 + 出场模板 + 风控参数。

    Args:
        factors: 候选因子列表（已排序，最优在前）。
        symbol: 品种代码。
        timeframe: K 线周期。
        population_size: 种群大小。
        direction: 方向。
        regime: 市场状态（用于调整策略偏好）。

    Returns:
        策略个体列表。
    """
    if not factors:
        raise ValueError("因子池为空，无法初始化种群")

    population: list[StrategyIndividual] = []

    # 根据市场状态调整因子选择偏好
    if regime:
        if regime.regime in ("range_bound", "low_volatility"):
            # 震荡市：偏向反转因子
            reversal_factors = [f for f in factors if "ts_zscore" in f.formula or "-1" in f.formula]
            primary = reversal_factors or factors
        elif regime.regime in ("high_volatility",):
            # 高波动：偏向趋势/突破类
            trend_factors = [
                f for f in factors if "ts_rank" in f.formula or "ts_max" in f.formula or "ts_min" in f.formula
            ]
            primary = trend_factors or factors
        else:
            primary = factors
    else:
        primary = factors

    # 确保有足够因子供采样
    source_pool = primary if len(primary) >= 3 else factors

    for _i in range(population_size):
        # 随机选 1-3 个因子
        n_factors = random.randint(1, min(3, len(source_pool)))
        selected = random.sample(source_pool, n_factors)

        entry_conditions = [_factor_to_condition(f, direction) for f in selected]
        entry_logic = random.choice(["and", "and", "or"])  # 2/3 概率选 AND

        # 出场条件：从模板中随机选
        exit_template = random.choice(_EXIT_TEMPLATES)
        exit_conditions = deepcopy(exit_template["conditions"])
        exit_logic = exit_template["logic"]

        # 风控参数：带一定随机性
        risk = {
            "position_size": {
                "type": random.choice(["fixed_lots", "risk_percent"]),
                "value": random.choice([1, 2, 3]) if direction == "long" else random.choice([1, 2]),
            },
            "stop_loss": {
                "type": "atr_multiple",
                "value": round(random.uniform(1.5, 3.0), 1),
            },
            "take_profit": {
                "type": "risk_reward_ratio",
                "value": round(random.uniform(1.5, 3.0), 1),
            },
        }

        individual = StrategyIndividual(
            uid=str(uuid.uuid4()),
            entry_conditions=entry_conditions,
            entry_logic=entry_logic,
            exit_conditions=exit_conditions,
            exit_logic=exit_logic,
            risk=risk,
            direction=direction,
            timeframe=timeframe,
            source_factors=[f.formula for f in selected],
            generation=0,
        )
        population.append(individual)

    logger.info("种群初始化完成：%d 个个体，因子池 %d", population_size, len(factors))
    return population


def population_diversity(population: list[StrategyIndividual]) -> float:
    """计算种群多样性（基于唯一 entry_condition 指纹的比例）。

    返回 0-1 的值，1 表示完全多样（无重复），0 表示全部相同。
    """
    if len(population) <= 1:
        return 1.0

    fingerprints: set[str] = set()
    for ind in population:
        # 用 entry_conditions 的稳定字符串表示作为指纹
        cond_str = json.dumps(ind.entry_conditions, sort_keys=True)
        fp = hashlib.md5(cond_str.encode()).hexdigest()[:8]
        fingerprints.add(fp)

    return len(fingerprints) / len(population)


def best_individual(population: list[StrategyIndividual]) -> StrategyIndividual | None:
    """返回种群中适应度最高的个体。"""
    evaluated = [ind for ind in population if ind.fitness is not None]
    if not evaluated:
        return None
    return max(evaluated, key=lambda ind: ind.fitness)
