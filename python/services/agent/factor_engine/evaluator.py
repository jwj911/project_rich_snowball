"""因子评估器。

计算因子的 IC、Rank IC、ICIR、分层回测、多空收益、最大回撤、换手率等指标。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

try:
    from scipy import stats
except ImportError:
    stats = None

from services.agent.factor_engine.dsl import PanelData

logger = logging.getLogger(__name__)

if stats is None:
    logger.warning("scipy not available, IC computation will be skipped")


@dataclass
class FactorEvaluationResult:
    """因子评估结果。"""

    factor_name: str
    formula: str
    symbols: list[str] = field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    periods: int = 0

    # IC 相关
    ic_mean: float | None = None
    ic_std: float | None = None
    icir: float | None = None
    rank_ic_mean: float | None = None
    rank_ic_std: float | None = None
    rank_icir: float | None = None
    ic_positive_ratio: float | None = None
    rank_ic_positive_ratio: float | None = None

    # 分层回测
    quantile_returns: list[float] = field(default_factory=list)
    long_short_return: float | None = None
    long_short_annual_return: float | None = None
    long_short_max_drawdown: float | None = None
    long_short_sharpe: float | None = None

    # 其他
    turnover: float | None = None
    coverage: float | None = None
    ic_by_year: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_name": self.factor_name,
            "formula": self.formula,
            "symbols": self.symbols,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "periods": self.periods,
            "ic_mean": self.ic_mean,
            "ic_std": self.ic_std,
            "icir": self.icir,
            "rank_ic_mean": self.rank_ic_mean,
            "rank_ic_std": self.rank_ic_std,
            "rank_icir": self.rank_icir,
            "ic_positive_ratio": self.ic_positive_ratio,
            "rank_ic_positive_ratio": self.rank_ic_positive_ratio,
            "quantile_returns": self.quantile_returns,
            "long_short_return": self.long_short_return,
            "long_short_annual_return": self.long_short_annual_return,
            "long_short_max_drawdown": self.long_short_max_drawdown,
            "long_short_sharpe": self.long_short_sharpe,
            "turnover": self.turnover,
            "coverage": self.coverage,
            "ic_by_year": self.ic_by_year,
        }


def _compute_forward_returns(close: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    """计算未来 periods 期收益率。"""
    return close.pct_change(periods).shift(-periods)


def _compute_ic(factor: pd.DataFrame, forward_returns: pd.DataFrame, method: str = "pearson") -> pd.Series:
    """计算每日横截面 IC。"""
    if stats is None:
        logger.warning("scipy not available, skipping IC computation")
        return pd.Series(dtype=float)

    # scipy is available
    from scipy import stats as _scipy_stats

    ic_values: list[float] = []
    dates: list[Any] = []
    for date in factor.index:
        f = factor.loc[date]
        r = forward_returns.loc[date]
        valid = f.notna() & r.notna()
        if valid.sum() < 3:
            continue
        if method == "pearson":
            corr, _ = _scipy_stats.pearsonr(f[valid], r[valid])
        else:
            corr, _ = _scipy_stats.spearmanr(f[valid], r[valid])
        if not np.isnan(corr):
            ic_values.append(corr)
            dates.append(date)
    return pd.Series(ic_values, index=dates)


def _compute_quantile_returns(
    factor: pd.DataFrame,
    forward_returns: pd.DataFrame,
    n_quantiles: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """计算分层回测收益。

    Returns:
        quantile_cum_returns: 每层累计收益 DataFrame（日期 × 分位）。
        long_short_cum: 多空组合累计收益 Series。
    """
    quantile_returns: dict[int, list[float]] = {q: [] for q in range(1, n_quantiles + 1)}
    quantile_dates: list[Any] = []
    long_short_returns: list[float] = []

    for date in factor.index:
        f = factor.loc[date]
        r = forward_returns.loc[date]
        valid = f.notna() & r.notna()
        if valid.sum() < n_quantiles:
            continue

        f_valid = f[valid]
        r_valid = r[valid]

        # 按因子值分位
        try:
            labels = pd.qcut(f_valid, q=n_quantiles, labels=False, duplicates="drop")
        except ValueError:
            continue

        daily_returns: dict[int, float] = {}
        for q in range(n_quantiles):
            mask = labels == q
            if mask.sum() == 0:
                daily_returns[q + 1] = 0.0
            else:
                daily_returns[q + 1] = r_valid[mask].mean()

        quantile_dates.append(date)
        for q in range(1, n_quantiles + 1):
            quantile_returns[q].append(daily_returns[q])

        # 多空：最高分位 - 最低分位
        long_ret = daily_returns[n_quantiles]
        short_ret = daily_returns[1]
        long_short_returns.append(long_ret - short_ret)

    quantile_df = pd.DataFrame(quantile_returns, index=quantile_dates)
    quantile_cum = (1 + quantile_df).cumprod() - 1

    long_short_series = pd.Series(long_short_returns, index=quantile_dates)
    long_short_cum = (1 + long_short_series).cumprod() - 1

    return quantile_cum, long_short_cum


def _compute_turnover(factor: pd.DataFrame) -> float:
    """计算因子换手率（相邻期因子秩相关性的平均）。"""
    rank_df = factor.rank(axis=1, pct=True)
    turnovers: list[float] = []
    for i in range(1, len(rank_df)):
        prev = rank_df.iloc[i - 1]
        curr = rank_df.iloc[i]
        valid = prev.notna() & curr.notna()
        if valid.sum() < 2:
            continue
        # 1 - 秩相关系数 作为换手率近似
        turnover = 1 - prev[valid].corr(curr[valid])
        if not np.isnan(turnover):
            turnovers.append(turnover)
    return float(np.mean(turnovers)) if turnovers else 0.0


def _compute_max_drawdown(cum_returns: pd.Series) -> float:
    """计算最大回撤。"""
    if cum_returns.empty:
        return 0.0
    peak = cum_returns.cummax()
    drawdown = (cum_returns - peak) / (1 + peak)
    return float(drawdown.min())


def evaluate_factor(
    factor_name: str,
    formula: str,
    factor_values: pd.DataFrame,
    panel: PanelData,
    forward_periods: int = 1,
    n_quantiles: int = 5,
) -> FactorEvaluationResult:
    """评估单个因子的有效性。

    Args:
        factor_name: 因子名称。
        formula: 因子公式。
        factor_values: 因子值 DataFrame（日期 × 品种）。
        panel: 面板数据。
        forward_periods: 前瞻收益周期，默认 1 天。
        n_quantiles: 分层数量，默认 5。

    Returns:
        FactorEvaluationResult。
    """
    forward_returns = _compute_forward_returns(panel.close, periods=forward_periods)

    # 覆盖率
    coverage = float(factor_values.notna().mean().mean())

    # IC
    ic_series = _compute_ic(factor_values, forward_returns, method="pearson")
    rank_ic_series = _compute_ic(factor_values, forward_returns, method="spearman")

    ic_mean = float(ic_series.mean()) if not ic_series.empty else None
    ic_std = float(ic_series.std()) if len(ic_series) > 1 else None
    icir = (ic_mean / ic_std) if ic_mean is not None and ic_std is not None and ic_std > 0 else None
    ic_positive_ratio = float((ic_series > 0).mean()) if not ic_series.empty else None

    rank_ic_mean = float(rank_ic_series.mean()) if not rank_ic_series.empty else None
    rank_ic_std = float(rank_ic_series.std()) if len(rank_ic_series) > 1 else None
    rank_icir = (
        (rank_ic_mean / rank_ic_std)
        if rank_ic_mean is not None and rank_ic_std is not None and rank_ic_std > 0
        else None
    )
    rank_ic_positive_ratio = float((rank_ic_series > 0).mean()) if not rank_ic_series.empty else None

    # 按年 IC
    ic_by_year: dict[str, float] = {}
    if not ic_series.empty and isinstance(ic_series.index, pd.DatetimeIndex):
        for year, group in ic_series.groupby(ic_series.index.year):
            ic_by_year[str(year)] = float(group.mean())

    # 分层回测
    quantile_cum, long_short_cum = _compute_quantile_returns(factor_values, forward_returns, n_quantiles=n_quantiles)

    quantile_returns = []
    if not quantile_cum.empty:
        quantile_returns = [float(quantile_cum[q].iloc[-1]) for q in range(1, n_quantiles + 1)]

    long_short_return = float(long_short_cum.iloc[-1]) if not long_short_cum.empty else None
    long_short_max_drawdown = _compute_max_drawdown(long_short_cum) if not long_short_cum.empty else None

    # 年化收益与 Sharpe（假设 252 个交易日）
    long_short_annual_return = None
    long_short_sharpe = None
    if not long_short_cum.empty and len(long_short_cum) > 1:
        daily_returns = long_short_cum.diff().dropna()
        if not daily_returns.empty:
            mean_daily = daily_returns.mean()
            std_daily = daily_returns.std()
            long_short_annual_return = float(mean_daily * 252)
            long_short_sharpe = float(mean_daily / std_daily * np.sqrt(252)) if std_daily > 0 else None

    turnover = _compute_turnover(factor_values)

    return FactorEvaluationResult(
        factor_name=factor_name,
        formula=formula,
        symbols=list(factor_values.columns),
        start_date=str(factor_values.index[0]) if not factor_values.empty else None,
        end_date=str(factor_values.index[-1]) if not factor_values.empty else None,
        periods=len(factor_values),
        ic_mean=ic_mean,
        ic_std=ic_std,
        icir=icir,
        rank_ic_mean=rank_ic_mean,
        rank_ic_std=rank_ic_std,
        rank_icir=rank_icir,
        ic_positive_ratio=ic_positive_ratio,
        rank_ic_positive_ratio=rank_ic_positive_ratio,
        quantile_returns=quantile_returns,
        long_short_return=long_short_return,
        long_short_annual_return=long_short_annual_return,
        long_short_max_drawdown=long_short_max_drawdown,
        long_short_sharpe=long_short_sharpe,
        turnover=turnover,
        coverage=coverage,
        ic_by_year=ic_by_year,
    )
