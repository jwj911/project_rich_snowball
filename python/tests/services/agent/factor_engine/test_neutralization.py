"""因子中性化测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.agent.factor_engine.neutralization import neutralize_factor


@pytest.fixture
def sample_df():
    """构造 3 天 × 2 行业 × 5 品种的多日截面数据。"""
    np.random.seed(42)
    dates = []
    industries = []
    caps = []
    factors = []
    for d in range(3):
        for ind in ["银行", "科技"]:
            for sym in range(5):
                dates.append(f"2026-01-{d*2 + 5:02d}")
                industries.append(ind)
                caps.append(100 + np.random.randint(0, 500))
                # 银行因子值整体偏高，科技偏低 → 系统性偏差
                base = 0.1 if ind == "银行" else -0.05
                factors.append(base + np.random.normal(0, 0.02))

    return pd.DataFrame({
        "trade_date": dates,
        "industry": industries,
        "market_cap": caps,
        "factor_val": factors,
    })


class TestNeutralizeFactor:
    def test_demean_industry(self, sample_df):
        result = neutralize_factor(
            sample_df,
            factor_col="factor_val",
            industry_col="industry",
            method="demean",
        )
        assert result is not None
        assert len(result) == len(sample_df)
        assert not result.isna().all()
        # 中性化后，各行业的均值应接近 0
        group_means = sample_df.assign(_neut=result).groupby("industry")["_neut"].mean()
        for mean_val in group_means:
            assert abs(mean_val) < 0.05  # 均值接近 0

    def test_demean_by_param(self, sample_df):
        """使用 by=["industry"] 快捷参数。"""
        result = neutralize_factor(
            sample_df,
            factor_col="factor_val",
            by=["industry"],
            method="demean",
            industry_col="industry",
        )
        assert len(result) == len(sample_df)

    def test_residual_method(self, sample_df):
        result = neutralize_factor(
            sample_df,
            factor_col="factor_val",
            industry_col="industry",
            method="residual",
        )
        assert len(result) == len(sample_df)
        assert result.dtype == float

    def test_residual_with_market_cap(self, sample_df):
        result = neutralize_factor(
            sample_df,
            factor_col="factor_val",
            industry_col="industry",
            market_cap_col="market_cap",
            method="residual",
        )
        assert len(result) == len(sample_df)

    def test_missing_factor_col_raises(self, sample_df):
        with pytest.raises(ValueError, match="因子列"):
            neutralize_factor(
                sample_df,
                factor_col="nonexistent",
                industry_col="industry",
                method="demean",
            )

    def test_no_neutralization_dimension_raises(self, sample_df):
        with pytest.raises(ValueError, match="至少需要指定"):
            neutralize_factor(
                sample_df,
                factor_col="factor_val",
                method="residual",
            )

    def test_demean_with_market_cap_only(self, sample_df):
        result = neutralize_factor(
            sample_df,
            factor_col="factor_val",
            market_cap_col="market_cap",
            method="demean",
        )
        assert len(result) == len(sample_df)

    def test_small_sample_fallback(self):
        """样本太少时回退到原始值。"""
        df = pd.DataFrame({
            "trade_date": ["2026-01-05"] * 3,
            "industry": ["A", "B", "C"],
            "market_cap": [100, 200, 300],
            "factor_val": [0.1, 0.2, 0.3],
        })
        result = neutralize_factor(
            df,
            factor_col="factor_val",
            industry_col="industry",
            method="residual",
        )
        # 回归样本不足，应保留原值
        assert len(result) == 3

    def test_nan_handling(self):
        """含 NaN 的因子值应被正确处理。"""
        n = 40
        df = pd.DataFrame({
            "trade_date": ["2026-01-05"] * (n // 2) + ["2026-01-06"] * (n // 2),
            "industry": (["银行"] * 10 + ["科技"] * 10 + ["银行"] * 10 + ["科技"] * 10),
            "market_cap": list(range(100, 140, 1)),
            "factor_val": [0.05] * 8 + [np.nan] * 2 + [-0.03] * 10 + [0.06] * 10 + [-0.02] * 10,
        })
        result = neutralize_factor(
            df,
            factor_col="factor_val",
            industry_col="industry",
            method="demean",
        )
        assert len(result) == 40
        # NaN 的输入对应 NaN 的输出
        nan_mask = df["factor_val"].isna()
        assert result[nan_mask].isna().all()
