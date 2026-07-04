"""因子中性化。

去除行业/市值等系统性偏差对被评估因子的影响，
使因子反映"剔除结构因素后的纯 alpha"。

两种方法：
1. residual — 对因子值做截面回归，取残差作为中性化后的因子值
2. demean — 因子值减去按分组维度（如行业）的均值
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def neutralize_factor(
    df: pd.DataFrame,
    factor_col: str,
    by: list[str] | None = None,
    method: Literal["residual", "demean"] = "residual",
    industry_col: str | None = None,
    market_cap_col: str | None = None,
    date_col: str = "trade_date",
) -> pd.Series:
    """对因子值做截面中性化。

    在每个交易日截面上，去除指定维度对因子值的系统性影响。

    Args:
        df: 包含因子值和中性化维度的 DataFrame，每行一条记录。
        factor_col: 要中性化的因子列名。
        by: 快捷参数 — 中性化维度列表，支持 "industry" 和 "market_cap"。
            会映射到 industry_col / market_cap_col。
        method: 中性化方法。
            - "residual": 截面回归取残差（推荐，更彻底）
            - "demean": 分组减去均值（简单直观）
        industry_col: 行业分类列名（用于分组或做哑变量）。
        market_cap_col: 市值列名（用于 log 后做连续控制变量）。
        date_col: 日期分组列名。

    Returns:
        中性化后的因子值 Series，与原 df 同索引。

    Raises:
        ValueError: 参数配置不合法或数据不足。
    """
    if by:
        if "industry" in by:
            industry_col = industry_col or "industry"
        if "market_cap" in by:
            market_cap_col = market_cap_col or "market_cap"

    if industry_col is None and market_cap_col is None:
        raise ValueError("至少需要指定一个中性化维度，请设置 industry_col、market_cap_col 或 by 参数")

    if factor_col not in df.columns:
        raise ValueError(f"因子列 {factor_col!r} 不在 DataFrame 中")
    if date_col not in df.columns:
        raise ValueError(f"日期列 {date_col!r} 不在 DataFrame 中")

    result = df[factor_col].copy()

    if method == "demean":
        if industry_col and industry_col in df.columns:
            group_mean = df.groupby([date_col, industry_col])[factor_col].transform("mean")
            result = result - group_mean
        if market_cap_col and market_cap_col in df.columns:
            # 市值 demean：按市值分 10 组后去均值
            cap_decile = df.groupby(date_col)[market_cap_col].transform(
                lambda x: pd.qcut(x, q=10, labels=False, duplicates="drop")
            )
            cap_mean = df.groupby([date_col, cap_decile])[factor_col].transform("mean")
            result = result - cap_mean
        logger.info("demean 中性化完成：%s，%d 行", factor_col, len(df))
        return result

    # residual 方法
    if method == "residual":
        return _residual_neutralize(df, factor_col, industry_col, market_cap_col, date_col)

    raise ValueError(f"不支持的中性化方法: {method!r}")


def _residual_neutralize(
    df: pd.DataFrame,
    factor_col: str,
    industry_col: str | None,
    market_cap_col: str | None,
    date_col: str,
) -> pd.Series:
    """截面回归取残差。

    对每个交易日，回归: factor ~ industry_dummies + log(market_cap)
    取残差作为中性化后的因子值。
    """
    result = pd.Series(np.nan, index=df.index, dtype=float)

    for _date, group in df.groupby(date_col):
        y = group[factor_col].copy()
        valid_mask = y.notna()
        if valid_mask.sum() < 10:
            # 样本太少，无法可靠回归，保留原值
            result.loc[group.index] = y
            continue

        # 构建自变量
        x_parts: list[pd.Series] = []

        if industry_col and industry_col in group.columns:
            dummies = pd.get_dummies(group[industry_col], prefix="ind", drop_first=True)
            dummies.index = group.index
            for col in dummies.columns:
                x_parts.append(dummies[col])

        if market_cap_col and market_cap_col in group.columns:
            cap = group[market_cap_col].copy()
            cap_log = np.log(cap.replace(0, np.nan))
            x_parts.append(cap_log.rename("log_market_cap"))

        if not x_parts:
            result.loc[group.index] = y
            continue

        x = pd.concat(x_parts, axis=1)
        # 加截距项
        x = x.assign(_const=1.0)

        # 只对 X 和 Y 都有效的样本回归
        valid_idx = x.notna().all(axis=1) & y.notna()
        if valid_idx.sum() < 10 or valid_idx.sum() <= x.shape[1]:
            result.loc[group.index] = y
            continue

        try:
            from numpy.linalg import lstsq

            x_vals = x.loc[valid_idx].values.astype(float)
            y_vals = y.loc[valid_idx].values.astype(float)
            coeff, _residuals, _rank, _s = lstsq(x_vals, y_vals, rcond=None)
            predicted = x.values.astype(float) @ coeff
            residual = y.values.astype(float) - predicted
            result.loc[group.index] = residual
        except np.linalg.LinAlgError:
            result.loc[group.index] = y

    logger.info("residual 中性化完成：%s，回归 %d 个交易日截面", factor_col, len(df[date_col].unique()))
    return result.astype(float)
