"""多因子组合器。

将多个单因子按指定策略组合为复合评分，支撑多因子选股回测。

核心策略：
1. icir_weighted — ICIR 加权组合（偏科生策略）
   - 按配置将因子分组
   - 每组内各因子计算 Rank ICIR（滚动窗口）
   - rank_pct × ICIR 加权求和 → 组内复合因子
   - 各组等权求和 → 最终复合评分

2. equal_weight — 等权排序组合
   - 各因子分别截面排名
   - 排名等权求和 → 最终复合评分

与 evaluator.py 的关系：
- evaluator 关注"单个因子的质量评估"（事后统计 IC/分层回测）
- compositor 关注"多个因子如何组合成选股评分"（事前因子加权）
- compositor 复用了 evaluator 中 _compute_ic / _compute_forward_returns 的计算模式
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

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 数据结构
# ------------------------------------------------------------------


@dataclass
class FactorSpec:
    """单个因子配置。

    Attributes:
        field: 因子值 DataFrame 的列名或面板字段名。
        is_asc: True 表示因子值越小越好（升序排名），False 表示越大越好（降序排名）。
        group: 因子所属的分组标识（如 "组合1"），同组因子在 icir_weighted 模式下相互竞争权重。
    """

    field: str
    is_asc: bool = False
    group: str = "default"


@dataclass
class CompositeConfig:
    """多因子组合配置。

    Attributes:
        factors: 参与组合的因子列表。
        method: 组合方法。
            - "icir_weighted": ICIR 加权组合
            - "equal_weight": 等权排序组合
        future_return_periods: 未来收益周期数（用于 ICIR 计算）。
        icir_recall: ICIR 滚动窗口大小，默认 50。
        icir_min_periods: ICIR 计算的最少周期数，默认 recall/2。
    """

    factors: list[FactorSpec]
    method: str = "icir_weighted"
    future_return_periods: int = 5
    icir_recall: int = 50
    icir_min_periods: int | None = None

    def __post_init__(self) -> None:
        if self.icir_min_periods is None:
            self.icir_min_periods = max(1, self.icir_recall // 2)

    @property
    def factor_fields(self) -> list[str]:
        return [f.field for f in self.factors]

    @property
    def groups(self) -> dict[str, list[FactorSpec]]:
        """返回按 group 分组的因子，保持配置顺序。"""
        groups: dict[str, list[FactorSpec]] = {}
        for f in self.factors:
            groups.setdefault(f.group, []).append(f)
        return groups


@dataclass
class CompositeScoreDetail:
    """复合评分的明细信息。"""

    field: str | None = None
    rank_pct: float | None = None
    icir: float | None = None
    weighted_rank: float | None = None
    group: str | None = None


@dataclass
class CompositeResult:
    """多因子组合结果。

    Attributes:
        composite_score: 复合评分 DataFrame（日期 × 品种），index 为日期，columns 为品种。
        score_column: 评分列名（默认 "复合因子"）。
        icir_by_factor: 每个因子的 ICIR 值字典（仅 icir_weighted 方法返回）。
        group_scores: 每组内复合评分 DataFrame 的字典（仅 icir_weighted 方法返回）。
        details: 每个因子在最后一天的评分明细列表。
    """

    composite_score: pd.DataFrame
    score_column: str = "复合因子"
    method: str = ""
    icir_by_factor: dict[str, float] = field(default_factory=dict)
    group_scores: dict[str, pd.DataFrame] = field(default_factory=dict)
    details: list[CompositeScoreDetail] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_column": self.score_column,
            "method": self.method,
            "icir_by_factor": self.icir_by_factor,
            "date_range": {
                "start": str(self.composite_score.index[0]) if not self.composite_score.empty else None,
                "end": str(self.composite_score.index[-1]) if not self.composite_score.empty else None,
            },
            "symbols": list(self.composite_score.columns),
            "details": [
                {
                    "field": d.field,
                    "rank_pct": d.rank_pct,
                    "icir": d.icir,
                    "weighted_rank": d.weighted_rank,
                    "group": d.group,
                }
                for d in self.details
            ],
        }


# ------------------------------------------------------------------
# 内部工具函数
# ------------------------------------------------------------------


def _compute_forward_returns(close: pd.DataFrame, periods: int) -> pd.DataFrame:
    """计算未来 periods 期收益率矩阵。

    返回的 DataFrame 中，第 t 行表示从 t+1 到 t+periods 的收益。
    """
    if periods <= 0:
        raise ValueError(f"未来收益周期必须 > 0，实际为 {periods}")
    fut = close.pct_change(periods).shift(-periods)
    return fut


def _compute_factor_rank(
    factor_values: pd.DataFrame,
    is_asc: bool,
) -> pd.DataFrame:
    """按日期计算截面分位排名（0~1）。

    is_asc=True  → 因子值越小越好（值小 → rank_pct 接近 1）
    is_asc=False → 因子值越大越好（值大 → rank_pct 接近 1）

    即：rank_pct 始终代表因子的"优选程度"，更高 = 更好。

    Args:
        factor_values: 因子值 DataFrame（日期 × 品种）。
        is_asc: True 表示因子值越小排名越高。

    Returns:
        排名 DataFrame，同形状，NaN 输入对应 NaN 输出。
    """
    # ascending=True 时值最小的 rank=1, pct 最低
    # is_asc=True（小值更好）时 → 需要用 ascending=False，让小值排名数大 → pct 高
    # is_asc=False（大值更好）时 → 需要用 ascending=True，让大值排名数大 → pct 高
    rank_ascending = not is_asc
    rank = factor_values.rank(axis=1, pct=True, ascending=rank_ascending)
    return rank


def _compute_daily_ic(
    factor_values: pd.DataFrame,
    forward_returns: pd.DataFrame,
    method: str = "spearman",
) -> pd.Series:
    """计算每日横截面 IC（信息系数）。

    Args:
        factor_values: 因子值 DataFrame（日期 × 品种）。
        forward_returns: 未来收益 DataFrame。
        method: "pearson" 或 "spearman"。

    Returns:
        每日 IC 的 Series，index 为日期。
    """
    if stats is None:
        logger.warning("scipy not available, IC computation skipped")
        return pd.Series(dtype=float)

    ic_values: dict[Any, float] = {}
    for date in factor_values.index:
        if date not in forward_returns.index:
            continue
        f = factor_values.loc[date]
        r = forward_returns.loc[date]
        valid = f.notna() & r.notna()
        if valid.sum() < 3:
            continue
        try:
            if method == "pearson":
                corr, _ = stats.pearsonr(f[valid], r[valid])
            else:
                corr, _ = stats.spearmanr(f[valid], r[valid])
        except (ValueError, np.linalg.LinAlgError):
            continue
        if not np.isnan(corr):
            ic_values[date] = corr

    return pd.Series(ic_values, name="IC")


def _compute_icir(
    ic_series: pd.Series,
    recall: int,
    min_periods: int,
    shift: int,
) -> pd.Series:
    """从每日 IC 序列计算滚动 ICIR。

    ICIR = rolling_mean(IC, recall) / rolling_std(IC, recall)

    Args:
        ic_series: 每日 IC 序列。
        recall: 滚动窗口大小。
        min_periods: 最少需要的周期数。
        shift: 将 ICIR 向前 shift 的期数（避免未来函数）。

    Returns:
        ICIR 序列，NaN 处表示数据不足。
    """
    ic_clean = ic_series.replace([np.inf, -np.inf], np.nan)
    if ic_clean.empty:
        return pd.Series(dtype=float)

    roll_mean = ic_clean.rolling(window=recall, min_periods=min_periods).mean()
    roll_std = ic_clean.rolling(window=recall, min_periods=min_periods).std()
    # 防止除零
    roll_std = roll_std.replace(0, 1e-8)
    icir = roll_mean / roll_std
    if shift > 0:
        icir = icir.shift(shift)
    return icir


# ------------------------------------------------------------------
# 组合器
# ------------------------------------------------------------------


class FactorCompositor:
    """多因子组合器。

    将多个单因子按指定策略组合为复合评分。

    使用方式：
        compositor = FactorCompositor()
        result = compositor.compute(
            factor_df,            # 日期 × 品种的因子值 DataFrame
            close_df,             # 日期 × 品种的收盘价 DataFrame
            CompositeConfig(...)
        )
        # result.composite_score 即为复合评分
    """

    def compute(
        self,
        factor_panels: dict[str, pd.DataFrame],
        close_df: pd.DataFrame,
        config: CompositeConfig,
    ) -> CompositeResult:
        """计算复合评分。

        Args:
            factor_panels: {因子名: 因子值 DataFrame}，每个 DataFrame 形状为 (日期 × 品种)，
                index 为日期，columns 为品种代码。
            close_df: 收盘价 DataFrame（用于计算未来收益），与因子面板同形状。
            config: 组合配置。

        Returns:
            CompositeResult。

        Raises:
            ValueError: 配置或数据不合法。
        """
        if not config.factors:
            raise ValueError("因子列表不能为空")

        missing = [f.field for f in config.factors if f.field not in factor_panels]
        if missing:
            raise ValueError(f"factor_panels 缺少以下因子: {missing}")

        if config.method == "icir_weighted":
            return self._compute_icir_weighted(factor_panels, close_df, config)
        elif config.method == "equal_weight":
            return self._compute_equal_weight(factor_panels, config)
        else:
            raise ValueError(f"不支持的组合方法: {config.method!r}")

    def _compute_equal_weight(
        self,
        factor_panels: dict[str, pd.DataFrame],
        config: CompositeConfig,
    ) -> CompositeResult:
        """等权排序组合：各因子截面排名等权求和。"""
        rank_sum: pd.DataFrame | None = None

        for spec in config.factors:
            rank = _compute_factor_rank(factor_panels[spec.field], spec.is_asc)
            if rank_sum is None:
                rank_sum = rank
            else:
                # 对齐到共同的日期和品种
                common_idx = rank_sum.index.intersection(rank.index)
                common_cols = rank_sum.columns.intersection(rank.columns)
                if common_idx.empty or common_cols.empty:
                    continue
                rank_sum = rank_sum.loc[common_idx, common_cols] + rank.loc[common_idx, common_cols]

        assert rank_sum is not None
        n_factors = len(config.factors)
        composite = rank_sum / n_factors

        # 最后一日的明细
        last_date = composite.index[-1] if not composite.empty else None
        details: list[CompositeScoreDetail] = []
        if last_date is not None:
            for spec in config.factors:
                rank = _compute_factor_rank(factor_panels[spec.field], spec.is_asc)
                last_rank = float(rank.loc[last_date].mean()) if last_date in rank.index else None
                details.append(
                    CompositeScoreDetail(
                        field=spec.field,
                        rank_pct=last_rank,
                        group=spec.group,
                    )
                )

        return CompositeResult(
            composite_score=composite,
            score_column="复合因子",
            method="equal_weight",
            details=details,
        )

    def _compute_icir_weighted(
        self,
        factor_panels: dict[str, pd.DataFrame],
        close_df: pd.DataFrame,
        config: CompositeConfig,
    ) -> CompositeResult:
        """ICIR 加权组合：偏科生策略的核心算法。

        步骤：
        1. 计算各因子的截面排名（rank_pct）
        2. 计算未来收益（注意避免未来函数）
        3. 用排名与未来收益计算 Rank IC
        4. 滚动 ICIR = mean(Rank IC) / std(Rank IC)
        5. 对 ICIR 做 shift 以避免未来函数
        6. 加权排名 = rank_pct × ICIR
        7. 组内求和 → 组复合因子
        8. 各组等权求和 → 最终复合因子
        """
        if close_df is None or close_df.empty:
            raise ValueError("icir_weighted 方法需要提供 close_df 来计算未来收益")

        # 1. 计算未来收益
        forward_returns = _compute_forward_returns(close_df, config.future_return_periods)

        # 2. 逐因子计算 ICIR + 加权排名
        weighted_ranks: dict[str, pd.DataFrame] = {}
        icir_by_factor: dict[str, float] = {}
        icir_series_by_factor: dict[str, pd.Series] = {}

        for spec in config.factors:
            field = spec.field
            panel = factor_panels[field]
            # 截面排名
            rank = _compute_factor_rank(panel, spec.is_asc)
            # Rank IC（spearman 相关）
            ic = _compute_daily_ic(panel, forward_returns, method="spearman")
            # ICIR
            icir = _compute_icir(
                ic,
                recall=config.icir_recall,
                min_periods=config.icir_min_periods or max(1, config.icir_recall // 2),
                shift=config.future_return_periods,
            )
            icir_series_by_factor[field] = icir

            # 加权排名：截面对齐
            common_dates = rank.index.intersection(icir.index)
            if common_dates.empty:
                logger.warning("因子 %s 的排名和 ICIR 无重叠日期，跳过", field)
                continue

            rank_aligned = rank.loc[common_dates]
            icir_aligned = icir.loc[common_dates]

            # rank_pct × ICIR（广播：ICIR 是 Series，rank 是 DataFrame）
            wr = rank_aligned.mul(icir_aligned, axis=0)
            weighted_ranks[field] = wr

            # 记录最终 ICIR 值
            last_valid = icir.dropna()
            icir_by_factor[field] = float(last_valid.iloc[-1]) if not last_valid.empty else 0.0

        if not weighted_ranks:
            raise ValueError("所有因子均无法计算加权排名，请检查数据窗口是否足够")

        # 3. 按组聚合
        group_scores: dict[str, pd.DataFrame] = {}
        for group_name, group_factors in config.groups.items():
            group_wrs = [weighted_ranks[f.field] for f in group_factors if f.field in weighted_ranks]
            if not group_wrs:
                continue

            # 对齐所有加权排名到共有的日期
            common_idx = group_wrs[0].index
            for wr in group_wrs[1:]:
                common_idx = common_idx.intersection(wr.index)

            if common_idx.empty:
                continue

            aligned = [wr.loc[common_idx] for wr in group_wrs]
            group_score = sum(aligned)  # min_count=1 语义：全 NaN 才为 NaN
            # 对全 NaN 行做处理
            all_nan_mask = pd.DataFrame(True, index=common_idx, columns=group_score.columns)
            for wr in aligned:
                all_nan_mask = all_nan_mask & wr.isna()
            group_score = group_score.where(~all_nan_mask, other=np.nan)
            group_scores[group_name] = group_score

        if not group_scores:
            raise ValueError("所有组均无法计算复合评分，请检查因子分组和数据窗口")

        # 4. 各组等权求和 → 最终复合因子
        composite: pd.DataFrame | None = None
        for _group_name, gs in group_scores.items():
            if composite is None:
                composite = gs.copy()
            else:
                # 对齐到共同的日期/品种
                common_idx = composite.index.intersection(gs.index)
                common_cols = composite.columns.intersection(gs.columns)
                if common_idx.empty or common_cols.empty:
                    continue
                composite = composite.loc[common_idx, common_cols] + gs.loc[common_idx, common_cols]

        if composite is None or composite.empty:
            raise ValueError("复合评分计算结果为空")

        # 5. 最后一日的明细
        last_date = composite.index[-1]
        details: list[CompositeScoreDetail] = []
        if last_date is not None:
            for spec in config.factors:
                icir = icir_by_factor.get(spec.field, None)
                rank = _compute_factor_rank(factor_panels[spec.field], spec.is_asc)
                last_rank = float(rank.loc[last_date].mean()) if last_date in rank.index else None
                wr_val = None
                if spec.field in weighted_ranks and last_date in weighted_ranks[spec.field].index:
                    wr_val = float(weighted_ranks[spec.field].loc[last_date].mean())
                details.append(
                    CompositeScoreDetail(
                        field=spec.field,
                        rank_pct=last_rank,
                        icir=icir,
                        weighted_rank=wr_val,
                        group=spec.group,
                    )
                )

        return CompositeResult(
            composite_score=composite,
            score_column="复合因子",
            method="icir_weighted",
            icir_by_factor=icir_by_factor,
            group_scores=group_scores,
            details=details,
        )
