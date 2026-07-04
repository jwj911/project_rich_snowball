"""增强回测评测指标。

在现有 _calculate_metrics 的基础上提供更丰富的绩效评估维度。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class EnhancedBacktestMetrics:
    """增强的回测评测指标。

    包含现有基础指标 + 新增的高级风险收益指标。
    """

    # ---- 基础指标（与 engine._calculate_metrics 对齐） ----
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    sharpe: float = 0.0
    trade_count: int = 0
    score: int = 0

    # ---- 新增：高级风险收益 ----
    calmar_ratio: float | None = None
    sortino_ratio: float | None = None
    information_ratio: float | None = None

    # ---- 新增：超额收益 ----
    excess_return_pct: float | None = None
    annualized_excess_return_pct: float | None = None

    # ---- 新增：交易特征 ----
    turnover_rate: float | None = None
    avg_hold_days: float | None = None
    max_consecutive_losses: int | None = None

    # ---- 新增：时间维度 ----
    monthly_returns: list[dict[str, Any]] = field(default_factory=list)
    yearly_returns: list[dict[str, Any]] = field(default_factory=list)
    rolling_1y_returns: list[dict[str, Any]] = field(default_factory=list)

    # ---- 选股回测特有 ----
    avg_hold_stocks: float | None = None
    selection_alpha: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_return_pct": self.total_return_pct,
            "annualized_return_pct": self.annualized_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "win_rate_pct": self.win_rate_pct,
            "profit_factor": self.profit_factor,
            "sharpe": self.sharpe,
            "trade_count": self.trade_count,
            "score": self.score,
            "calmar_ratio": self.calmar_ratio,
            "sortino_ratio": self.sortino_ratio,
            "information_ratio": self.information_ratio,
            "excess_return_pct": self.excess_return_pct,
            "annualized_excess_return_pct": self.annualized_excess_return_pct,
            "turnover_rate": self.turnover_rate,
            "avg_hold_days": self.avg_hold_days,
            "max_consecutive_losses": self.max_consecutive_losses,
            "monthly_returns": self.monthly_returns,
            "yearly_returns": self.yearly_returns,
            "rolling_1y_returns": self.rolling_1y_returns,
            "avg_hold_stocks": self.avg_hold_stocks,
            "selection_alpha": self.selection_alpha,
        }


def compute_enhanced_metrics(
    equity_curve: list[dict[str, Any]],
    trades: list[dict[str, Any]] | None = None,
    initial_cash: float = 100_000.0,
    benchmark_returns: list[float] | None = None,
    trading_days_per_year: int = 252,
) -> EnhancedBacktestMetrics:
    """从资金曲线和交易列表计算增强指标。

    Args:
        equity_curve: 资金曲线列表，每项含 "equity" 和可选的 "time"/"close"。
        trades: 交易列表，每项含 "pnl"、"entry_time"、"exit_time"。
        initial_cash: 初始资金。
        benchmark_returns: 基准日收益率序列（可选，用于超额收益/信息比率）。
        trading_days_per_year: 年化使用的交易日数。

    Returns:
        EnhancedBacktestMetrics。
    """
    if not equity_curve:
        return EnhancedBacktestMetrics()

    equity = np.array([p["equity"] for p in equity_curve], dtype=float)
    times = [p.get("time") for p in equity_curve]
    trades_list = trades or []

    # ---- 基础指标 ----
    total_return = (equity[-1] / initial_cash - 1) * 100
    returns = pd.Series(equity).pct_change().dropna()
    periods = max(len(equity), 1)
    annualized = (
        ((equity[-1] / initial_cash) ** (trading_days_per_year / periods) - 1) * 100 if equity[-1] > 0 else -100.0
    )

    rolling_peak = np.maximum.accumulate(equity)
    drawdown = (equity / rolling_peak - 1) * 100
    max_dd = abs(float(drawdown.min())) if len(drawdown) else 0.0

    pnls = [t.get("pnl", 0) for t in trades_list]
    wins_list = [p for p in pnls if p > 0]
    losses_list = [p for p in pnls if p < 0]
    win_rate = len(wins_list) / len(pnls) * 100 if pnls else 0.0
    pf = sum(wins_list) / abs(sum(losses_list)) if losses_list else (float(len(wins_list)) if wins_list else 0.0)
    sharpe = (
        (returns.mean() / (returns.std(ddof=0) + 1e-12)) * np.sqrt(trading_days_per_year) if not returns.empty else 0.0
    )
    score = int(
        max(0, min(100, round(50 + total_return * 0.3 - max_dd * 0.5 + (win_rate - 40) * 0.2 + min(pf, 5) * 3)))
    )

    # ---- 高级风险收益 ----
    calmar = annualized / max_dd if max_dd > 0 else None

    downside_std = returns[returns < 0].std(ddof=0) if not returns.empty else 0
    sortino = (returns.mean() / (downside_std + 1e-12)) * np.sqrt(trading_days_per_year) if downside_std > 0 else None

    ir = None
    excess_return = None
    annualized_excess = None
    if benchmark_returns is not None and len(benchmark_returns) == len(returns):
        bench = pd.Series(benchmark_returns, index=returns.index)
        tracking_diff = returns - bench
        ir = (
            (tracking_diff.mean() / (tracking_diff.std(ddof=0) + 1e-12)) * np.sqrt(trading_days_per_year)
            if not tracking_diff.empty
            else None
        )
        cum_ret = (1 + returns).prod() - 1
        cum_bench = (1 + bench).prod() - 1
        excess_return = (cum_ret - cum_bench) * 100
        annualized_excess = ((1 + cum_ret) / (1 + cum_bench)) ** (trading_days_per_year / periods) - 1
        if not np.isnan(annualized_excess):
            annualized_excess = float(annualized_excess * 100)

    # ---- 交易特征 ----
    turnover = None
    avg_hold = None
    if trades_list:
        hold_days = []
        for t in trades_list:
            entry = t.get("entry_time")
            exit_t = t.get("exit_time")
            if entry and exit_t:
                try:
                    entry_ts = pd.Timestamp(entry)
                    exit_ts = pd.Timestamp(exit_t)
                    hold_days.append((exit_ts - entry_ts).days)
                except (ValueError, TypeError):
                    pass
        avg_hold = float(np.mean(hold_days)) if hold_days else None

    max_consecutive = _max_consecutive_losses(pnls) if pnls else 0

    # ---- 时间维度 ----
    monthly = []
    yearly = []
    rolling_1y = []
    if times and len(times) == len(equity):
        try:
            ts = pd.to_datetime(times, format="mixed")
            eq = pd.Series(equity, index=ts)
            # 月收益
            monthly_eq = eq.resample("ME").last().dropna()
            monthly_ret = monthly_eq.pct_change().dropna()
            for dt, val in monthly_ret.items():
                monthly.append({"period": dt.strftime("%Y-%m"), "return_pct": round(float(val * 100), 2)})
            # 年收益
            yearly_eq = eq.resample("YE").last().dropna()
            yearly_ret = yearly_eq.pct_change().dropna()
            for dt, val in yearly_ret.items():
                yearly.append({"period": dt.strftime("%Y"), "return_pct": round(float(val * 100), 2)})
            # 滚动 1 年收益
            if len(eq) > trading_days_per_year:
                roll = eq.pct_change(trading_days_per_year).dropna()
                for dt, val in roll.items():
                    rolling_1y.append({"date": dt.strftime("%Y-%m-%d"), "return_pct": round(float(val * 100), 2)})
        except Exception:
            pass

    return EnhancedBacktestMetrics(
        total_return_pct=round(float(total_return), 2),
        annualized_return_pct=round(float(annualized), 2),
        max_drawdown_pct=round(max_dd, 2),
        win_rate_pct=round(float(win_rate), 2),
        profit_factor=round(float(pf), 2),
        sharpe=round(float(sharpe), 2),
        trade_count=len(pnls),
        score=score,
        calmar_ratio=round(float(calmar), 2) if calmar is not None else None,
        sortino_ratio=round(float(sortino), 2) if sortino is not None else None,
        information_ratio=round(float(ir), 2) if ir is not None else None,
        excess_return_pct=round(float(excess_return), 2) if excess_return is not None else None,
        annualized_excess_return_pct=round(float(annualized_excess), 2) if annualized_excess is not None else None,
        turnover_rate=turnover,
        avg_hold_days=round(float(avg_hold), 1) if avg_hold is not None else None,
        max_consecutive_losses=max_consecutive,
        monthly_returns=monthly[-12:],
        yearly_returns=yearly,
        rolling_1y_returns=rolling_1y,
    )


def _max_consecutive_losses(pnls: list[float]) -> int:
    """计算最大连续亏损次数。"""
    max_count = 0
    current = 0
    for p in pnls:
        if p < 0:
            current += 1
            max_count = max(max_count, current)
        else:
            current = 0
    return max_count
