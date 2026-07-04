"""参数优化器。

对策略 DSL 定义的可调参数执行网格搜索（grid search），
找出最优参数组合，返回按评分排名的结果。

支持：
- 均线周期扫描（短周期 × 长周期）
- RSI 阈值扫描
- 通用数值参数扫描
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from services.agent.strategy_compiler_agent import StrategyDSL
from services.backtest.service import run_dsl_backtest

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """单组参数的回测结果。"""

    params: dict[str, Any]
    metrics: dict[str, Any]
    rank: int = 0

    @property
    def score(self) -> float:
        return float(self.metrics.get("score", 0))


@dataclass
class OptimizationReport:
    """参数优化完整报告。"""

    symbol: str
    strategy_name: str
    total_combinations: int
    valid_results: int
    best_params: dict[str, Any]
    best_metrics: dict[str, Any]
    results: list[OptimizationResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "total_combinations": self.total_combinations,
            "valid_results": self.valid_results,
            "best_params": self.best_params,
            "best_metrics": self.best_metrics,
            "top_results": [
                {"rank": r.rank, "params": r.params, "score": r.score, "metrics": r.metrics} for r in self.results[:10]
            ],
        }


# ------------------------------------------------------------------
# 参数网格生成
# ------------------------------------------------------------------


def _generate_ma_param_grid(query: str) -> list[dict[str, Any]]:
    """从查询中推断均线参数扫描范围。

    默认：short in [5, 10, 15, 20, 30], long in [10, 20, 30, 60, 120]
    用户可指定范围：如"5到30日"、"20-60日"
    """
    import re

    short_values = [5, 10, 15, 20, 30]
    long_values = [10, 20, 30, 60, 120]

    # 尝试从 query 中提取用户指定的范围
    range_match = re.search(r"(\d+)\s*(?:到|至|-|~)\s*(\d+)", query)
    if range_match:
        lo = int(range_match.group(1))
        hi = int(range_match.group(2))
        short_values = [v for v in short_values if lo <= v <= hi]
        long_values = [v for v in long_values if lo <= v <= hi]

    return [{"short_window": s, "long_window": lw} for s in short_values for lw in long_values if s < lw]


def _generate_rsi_param_grid(query: str) -> list[dict[str, Any]]:
    """RSI 阈值扫描：入场阈值 × 出场阈值。"""
    buy_thresholds = [20, 25, 30, 35, 40]
    sell_thresholds = [60, 65, 70, 75, 80]
    return [{"rsi_buy": b, "rsi_sell": s} for b in buy_thresholds for s in sell_thresholds if b < s]


def _generate_macd_param_grid(query: str) -> list[dict[str, Any]]:
    """MACD 参数扫描：fast × slow × signal。"""
    fast_values = [5, 8, 12, 16]
    slow_values = [17, 26, 34]
    signal_values = [5, 9, 12]
    return [
        {"macd_fast": f, "macd_slow": s, "macd_signal": sig}
        for f, s, sig in itertools.product(fast_values, slow_values, signal_values)
        if f < s
    ]


_PARAM_GRID_GENERATORS = {
    "均线": _generate_ma_param_grid,
    "ma": _generate_ma_param_grid,
    "MACD": _generate_macd_param_grid,
    "macd": _generate_macd_param_grid,
    "RSI": _generate_rsi_param_grid,
    "rsi": _generate_rsi_param_grid,
}


def _infer_param_grid(query: str) -> list[dict[str, Any]]:
    """根据查询关键词推断参数网格类型。"""
    for keyword, generator in _PARAM_GRID_GENERATORS.items():
        if keyword in query:
            return generator(query)
    # 默认均线网格
    return _generate_ma_param_grid(query)


# ------------------------------------------------------------------
# 优化执行
# ------------------------------------------------------------------


def optimize_strategy(
    db: Session,
    dsl: StrategyDSL,
    query: str = "",
    top_n: int = 10,
) -> OptimizationReport:
    """对策略 DSL 执行参数网格搜索优化。

    Args:
        db: 数据库会话。
        dsl: 已编译的策略 DSL。
        query: 用户原始查询（用于推断扫描范围）。
        top_n: 返回前 N 组最优参数。

    Returns:
        OptimizationReport，包含排名结果和最佳参数。
    """
    symbol = dsl.universe[0] if dsl.universe else "?"
    param_grid = _infer_param_grid(query or dsl.description)

    results: list[OptimizationResult] = []
    errors = 0

    for params in param_grid:
        # 根据参数类型修改 DSL 条件中的数值
        adjusted_entry = _apply_params_to_conditions(dsl.entry.get("conditions", []), params)
        adjusted_exit = _apply_params_to_conditions(dsl.exit.get("conditions", []), params)

        try:
            bt_result = run_dsl_backtest(
                db,
                symbol=symbol,
                period=dsl.timeframe,
                direction=dsl.direction,
                entry_conditions=adjusted_entry,
                exit_conditions=adjusted_exit,
            )
            results.append(OptimizationResult(params=params, metrics=bt_result["metrics"]))
        except ValueError as e:
            errors += 1
            logger.debug("Optimization: params %s failed: %s", params, e)
            continue

    # 排名
    results.sort(key=lambda r: r.score, reverse=True)
    for i, r in enumerate(results, start=1):
        r.rank = i

    best = results[0] if results else None

    return OptimizationReport(
        symbol=symbol,
        strategy_name=dsl.name,
        total_combinations=len(param_grid),
        valid_results=len(results),
        best_params=best.params if best else {},
        best_metrics=best.metrics if best else {},
        results=results[:top_n],
    )


def _apply_params_to_conditions(conditions: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    """将参数网格中的数值应用到 DSL 条件中。

    替换规则：
    - short_window / long_window → 修改 smaN / emaN 指标名中的数字
    - rsi_buy / rsi_sell → 修改 RSI 条件的 value 阈值
    - macd_fast/macd_slow/macd_signal → 当前回测引擎使用固定 MACD 计算，
      这些参数暂时通过 DIF/DEA 条件间接影响（保留占位，需未来扩展引擎支持）
    """
    adjusted = []
    for cond in conditions:
        c = dict(cond)  # 浅拷贝

        # 均线窗口替换
        if "short_window" in params and "long_window" in params:
            sw = params["short_window"]
            lw = params["long_window"]
            for key in ("indicator", "indicator2"):
                if key in c and isinstance(c[key], str):
                    c[key] = _replace_ma_period(c[key], sw, lw)

        # RSI 阈值替换
        if (
            "rsi_buy" in params
            and "rsi_sell" in params
            and c.get("indicator")
            and "rsi" in str(c.get("indicator", "")).lower()
        ):
            op = c.get("operator", "")
            if op in ("less_than", "below"):
                c["value"] = params["rsi_buy"]
            elif op in ("greater_than", "above"):
                c["value"] = params["rsi_sell"]

        adjusted.append(c)

    return adjusted


def _replace_ma_period(indicator: str, short_w: int, long_w: int) -> str:
    """替换指标名中的均线周期数字。"""
    import re

    m = re.search(r"(\d+)$", indicator)
    if not m:
        return indicator
    base = re.sub(r"\d+$", "", indicator)
    period = int(m.group(1))

    # 判断是短周期还是长周期 — 如果 period <= 20 且 short_w <= 20，判定为短；
    # 否则判定为长
    if period <= 20:
        return f"{base}{short_w}"
    else:
        return f"{base}{long_w}"


# ------------------------------------------------------------------
# Markdown 报告生成
# ------------------------------------------------------------------


def format_optimization_report(report: OptimizationReport) -> str:
    """生成可读的参数优化报告。"""
    lines = [
        f"## 参数优化结果 — {report.strategy_name}",
        "",
        f"**品种**：{report.symbol}",
        f"**测试组合数**：{report.total_combinations}，**有效结果**：{report.valid_results}",
        "",
        "### 最佳参数",
    ]

    if report.best_params:
        params_desc = ", ".join(f"**{k}**={v}" for k, v in report.best_params.items())
        lines.append(f"- {params_desc}")
        lines.append(f"- 评分：{report.best_metrics.get('score', '—')}/100")
        lines.append(f"- 总收益：{report.best_metrics.get('total_return_pct', '—')}%")
        lines.append(f"- 最大回撤：{report.best_metrics.get('max_drawdown_pct', '—')}%")
        lines.append(f"- 夏普：{report.best_metrics.get('sharpe', '—')}")

    lines.extend(
        [
            "",
            "### 前 10 名结果",
            "",
            "| 排名 | 参数 | 评分 | 总收益 | 最大回撤 | 夏普 | 胜率 | 交易次数 |",
            "|------|------|------|--------|----------|------|------|----------|",
        ]
    )

    for r in report.results:
        params_short = ", ".join(f"{k}={v}" for k, v in r.params.items())
        m = r.metrics
        lines.append(
            f"| {r.rank} "
            f"| {params_short} "
            f"| {m.get('score', '—')} "
            f"| {m.get('total_return_pct', '—')}% "
            f"| {m.get('max_drawdown_pct', '—')}% "
            f"| {m.get('sharpe', '—')} "
            f"| {m.get('win_rate_pct', '—')}% "
            f"| {m.get('trade_count', '—')} |"
        )

    lines.extend(
        [
            "",
            "> 参数优化基于历史数据网格搜索，存在过拟合风险。建议结合样本外验证使用。",
        ]
    )

    return "\n".join(lines)
