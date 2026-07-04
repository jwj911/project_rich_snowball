"""因子引擎包。

提供因子 DSL 安全求值、面板数据加载、因子评估能力。
"""

from services.agent.factor_engine.data_loader import load_panel_data
from services.agent.factor_engine.dsl import PanelData, evaluate_factor, validate_factor_formula
from services.agent.factor_engine.evaluator import FactorEvaluationResult, evaluate_factor as evaluate_factor_performance

__all__ = [
    "PanelData",
    "evaluate_factor",
    "validate_factor_formula",
    "load_panel_data",
    "FactorEvaluationResult",
    "evaluate_factor_performance",
]
