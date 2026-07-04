"""因子引擎包。

提供因子 DSL 安全求值、面板数据加载、因子评估、多因子组合、
声明式过滤、因子注册表、因子中性化能力。
"""

from services.agent.factor_engine.compositor import (
    CompositeConfig,
    CompositeResult,
    FactorCompositor,
    FactorSpec,
)
from services.agent.factor_engine.data_loader import load_panel_data
from services.agent.factor_engine.dsl import PanelData, evaluate_factor, validate_factor_formula
from services.agent.factor_engine.evaluator import (
    FactorEvaluationResult,
)
from services.agent.factor_engine.evaluator import (
    evaluate_factor as evaluate_factor_performance,
)
from services.agent.factor_engine.factor_meta import FactorMeta
from services.agent.factor_engine.filters import (
    FilterCondition,
    FilterPipeline,
    FilterResult,
    build_conditions_from_tuples,
)
from services.agent.factor_engine.neutralization import neutralize_factor
from services.agent.factor_engine.registry import FactorRegistry

__all__ = [
    # DSL
    "PanelData",
    "evaluate_factor",
    "validate_factor_formula",
    # 数据
    "load_panel_data",
    # 评估
    "FactorEvaluationResult",
    "evaluate_factor_performance",
    # 组合
    "CompositeConfig",
    "CompositeResult",
    "FactorCompositor",
    "FactorSpec",
    # 过滤
    "FilterCondition",
    "FilterPipeline",
    "FilterResult",
    "build_conditions_from_tuples",
    # 注册表
    "FactorRegistry",
    "FactorMeta",
    # 中性化
    "neutralize_factor",
]
