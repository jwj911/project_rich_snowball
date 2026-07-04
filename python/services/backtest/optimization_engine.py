"""策略参数优化引擎。

支持参数网格搜索，对 DSL 条件中的可变参数进行枚举组合，
自动运行多组回测并输出最优参数与敏感性分析。
"""

from __future__ import annotations

import itertools
import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from services.backtest.service import run_dsl_backtest

logger = logging.getLogger(__name__)


def substitute_params(conditions: list[dict[str, Any]], params: dict[str, int | float]) -> list[dict[str, Any]]:
    """将 conditions 中的 {param_name} 占位符替换为具体值。"""
    result = []
    for cond in conditions:
        new_cond = {}
        for key, value in cond.items():
            if isinstance(value, str):
                for pname, pval in params.items():
                    value = value.replace(f"{{{pname}}}", str(pval))
            new_cond[key] = value
        result.append(new_cond)
    return result


def optimize_strategy_params(
    db: Session,
    symbol: str,
    period: str,
    direction: str,
    entry_conditions: list[dict[str, Any]],
    exit_conditions: list[dict[str, Any]],
    param_space: dict[str, list[int | float]],
    initial_cash: float = 100_000.0,
    quantity: int = 1,
    limit: int = 500,
    top_n: int = 5,
    metric_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """参数网格搜索核心引擎。

    Args:
        db: 数据库会话
        symbol: 品种代码
        period: K线周期
        direction: 方向
        entry_conditions: 参数化的 entry conditions（含 {param_name} 占位符）
        exit_conditions: 参数化的 exit conditions（含 {param_name} 占位符）
        param_space: 参数搜索空间，如 {"short": [5,10,15], "long": [20,30,40]}
        initial_cash: 初始资金
        quantity: 手数
        limit: K线数据长度
        top_n: 返回最优结果数量
        metric_weights: 综合评分权重，默认 {"sharpe": 0.4, "total_return_pct": 0.3, "max_drawdown_pct": -0.2, "win_rate_pct": 0.1}

    Returns:
        包含最优参数、Top-N 结果、敏感性矩阵的字典
    """
    if metric_weights is None:
        metric_weights = {
            "sharpe": 0.4,
            "total_return_pct": 0.3,
            "max_drawdown_pct": -0.2,
            "win_rate_pct": 0.1,
        }

    param_names = list(param_space.keys())
    param_values = list(param_space.values())
    total_combinations = 1
    for values in param_values:
        total_combinations *= len(values)

    if total_combinations > 1000:
        raise ValueError(f"参数组合过多 ({total_combinations})，请缩小搜索空间")

    start_time = time.time()
    logger.info(
        "strategy_optimization_start",
        extra={
            "symbol": symbol,
            "period": period,
            "direction": direction,
            "total_combinations": total_combinations,
            "param_space": param_space,
        },
    )
    results = []

    for combo in itertools.product(*param_values):
        params = dict(zip(param_names, combo))
        actual_entry = substitute_params(entry_conditions, params)
        actual_exit = substitute_params(exit_conditions, params)

        try:
            result = run_dsl_backtest(
                db,
                symbol=symbol,
                period=period,
                direction=direction,
                entry_conditions=actual_entry,
                exit_conditions=actual_exit,
                initial_cash=initial_cash,
                quantity=quantity,
                limit=limit,
            )
            metrics = result["metrics"]
            score = _calculate_composite_score(metrics, metric_weights)
            results.append({
                "params": params,
                "metrics": metrics,
                "score": score,
                "trades_count": metrics.get("trade_count", 0),
            })
        except Exception as exc:
            logger.warning("回测失败 params=%s: %s", params, exc)
            results.append({
                "params": params,
                "metrics": None,
                "score": -9999.0,
                "trades_count": 0,
                "error": str(exc),
            })

    runtime = time.time() - start_time

    # 过滤失败的
    valid_results = [r for r in results if r.get("metrics") is not None]
    valid_results.sort(key=lambda x: x["score"], reverse=True)

    best = valid_results[0] if valid_results else None

    # 构建敏感性矩阵
    sensitivity = _build_sensitivity_matrix(valid_results, param_names)

    logger.info(
        "strategy_optimization_complete",
        extra={
            "symbol": symbol,
            "total_combinations": total_combinations,
            "tested_combinations": len(valid_results),
            "runtime_seconds": round(runtime, 3),
            "best_score": round(best["score"], 4) if best else None,
            "best_params": best["params"] if best else None,
        },
    )

    return {
        "best_params": best["params"] if best else {},
        "best_score": round(best["score"], 4) if best else 0.0,
        "best_metrics": best["metrics"] if best else None,
        "top_results": valid_results[:top_n],
        "param_space": param_space,
        "total_combinations": total_combinations,
        "tested_combinations": len(valid_results),
        "runtime_seconds": round(runtime, 3),
        "sensitivity_matrix": sensitivity,
    }


def _calculate_composite_score(metrics: dict[str, Any], weights: dict[str, float]) -> float:
    """根据多指标权重计算综合评分。"""
    score = 0.0
    for key, weight in weights.items():
        value = metrics.get(key, 0)
        if value is None:
            value = 0
        # 最大回撤是负向指标，权重本身可能是负数
        score += float(value) * weight
    # 交易次数惩罚：太少信号说明过拟合
    trade_count = metrics.get("trade_count", 0)
    if trade_count < 3:
        score -= 20.0
    elif trade_count < 5:
        score -= 5.0
    return score


def _build_sensitivity_matrix(
    results: list[dict[str, Any]], param_names: list[str]
) -> dict[str, Any]:
    """构建单参数敏感性矩阵。

    对每个参数，计算其不同取值下的平均评分，用于判断参数敏感性。
    """
    if len(param_names) < 1 or not results:
        return {}

    matrix = {}
    for pname in param_names:
        param_scores = {}
        for r in results:
            pval = r["params"].get(pname)
            if pval is None:
                continue
            key = str(pval)
            if key not in param_scores:
                param_scores[key] = []
            param_scores[key].append(r["score"])

        matrix[pname] = {
            key: round(sum(scores) / len(scores), 4)
            for key, scores in param_scores.items()
        }

    return matrix
