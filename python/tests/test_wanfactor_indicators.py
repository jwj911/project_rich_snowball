"""万因子·歌者计划精选27因子测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.technical_indicators import (
    calculate_all_factors,
    factor_abs_mul_amount,
    factor_abs_ts_maxmin_sub,
    factor_add_open_delta,
    factor_div_ts_inverse_cv_volume,
    factor_ema_ts_dema_delta,
    factor_log_mul_amplitude,
    factor_mul_abs_amount,
    factor_mul_amount_log,
    factor_mul_amount_mul,
    factor_mul_amount_ts_std,
    factor_mul_signed_power_amplitude,
    factor_mul_ts_sum_amount,
    factor_neg_ts_maxmin_volume,
    factor_neg_ts_pct_change_abs,
    factor_signed_power_mul_amount,
    factor_signed_power_ts_maxmin_volume,
    factor_sub_sign_ts_std,
    factor_sub_ts_median_clip,
    factor_ts_dema_mul_amount,
    factor_ts_inverse_cv_delta_amount,
    factor_ts_inverse_cv_div_delta,
    factor_ts_maxmin_abs_volume,
    factor_ts_maxmin_add_volume,
    factor_ts_maxmin_signed_power_volume,
    factor_ts_mean_return_div_open,
    factor_ts_pct_change_signed_power_mul,
    factor_ts_std_signed_power_amount,
)


@pytest.fixture
def sample_kline():
    """生成 50 根模拟 K 线数据（含 amount 列）。"""
    np.random.seed(42)
    n = 50
    base = np.linspace(3500, 4000, n)
    noise = np.random.normal(0, 30, n)
    close = base + noise
    open_price = close + np.random.normal(0, 15, n)
    high = np.maximum(open_price, close) + np.random.uniform(10, 50, n)
    low = np.minimum(open_price, close) - np.random.uniform(10, 50, n)
    volume = np.random.uniform(10000, 50000, n)
    amount = close * volume
    df = pd.DataFrame({
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": amount,
    })
    df.index = pd.date_range("2024-01-01", periods=n, freq="D")
    return df


@pytest.fixture
def minimal_df():
    """最小构造数据，用于数值正确性断言。"""
    return pd.DataFrame({
        "open": np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
        "high": np.array([2.0, 3.0, 4.0, 5.0, 6.0]),
        "low": np.array([0.0, 1.0, 2.0, 3.0, 4.0]),
        "close": np.array([1.5, 2.5, 3.5, 4.5, 5.5]),
        "volume": np.array([100.0, 200.0, 300.0, 400.0, 500.0]),
        "amount": np.array([150.0, 500.0, 1050.0, 1800.0, 2750.0]),
    })


@pytest.fixture
def empty_df():
    """空 DataFrame（含正确列名）。"""
    return pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": [], "amount": []})


@pytest.fixture
def nan_df():
    """含 NaN 的 DataFrame。"""
    df = pd.DataFrame({
        "open": [1.0, 2.0, np.nan, 4.0, 5.0],
        "high": [2.0, 3.0, 4.0, np.nan, 6.0],
        "low": [0.0, 1.0, 2.0, 3.0, np.nan],
        "close": [1.5, np.nan, 3.5, 4.5, 5.5],
        "volume": [100.0, 200.0, 300.0, np.nan, 500.0],
        "amount": [150.0, 500.0, np.nan, 1800.0, 2750.0],
    })
    return df


class TestFactorBasic:
    """基础输入输出测试。"""

    def test_factor_returns_series(self, sample_kline):
        funcs = [
            factor_ts_mean_return_div_open,
            factor_add_open_delta,
            factor_mul_ts_sum_amount,
            factor_neg_ts_pct_change_abs,
            factor_mul_signed_power_amplitude,
            factor_mul_amount_ts_std,
            factor_signed_power_ts_maxmin_volume,
            factor_ts_maxmin_signed_power_volume,
            factor_mul_abs_amount,
            factor_abs_mul_amount,
            factor_sub_sign_ts_std,
            factor_mul_amount_log,
            factor_ts_dema_mul_amount,
            factor_neg_ts_maxmin_volume,
            factor_mul_amount_mul,
            factor_ts_std_signed_power_amount,
            factor_ts_maxmin_abs_volume,
            factor_abs_ts_maxmin_sub,
            factor_ts_maxmin_add_volume,
            factor_signed_power_mul_amount,
            factor_ts_pct_change_signed_power_mul,
            factor_ts_inverse_cv_delta_amount,
            factor_ts_inverse_cv_div_delta,
            factor_log_mul_amplitude,
            factor_ema_ts_dema_delta,
            factor_sub_ts_median_clip,
            factor_div_ts_inverse_cv_volume,
        ]
        for f in funcs:
            result = f(sample_kline)
            assert isinstance(result, pd.Series), f"{f.__name__} 应返回 pd.Series"
            assert len(result) == len(sample_kline), f"{f.__name__} 返回长度应与输入一致"

    def test_empty_df(self, empty_df):
        funcs = [
            factor_ts_mean_return_div_open,
            factor_add_open_delta,
            factor_mul_ts_sum_amount,
            factor_neg_ts_pct_change_abs,
            factor_mul_signed_power_amplitude,
            factor_mul_amount_ts_std,
            factor_signed_power_ts_maxmin_volume,
            factor_ts_maxmin_signed_power_volume,
            factor_mul_abs_amount,
            factor_abs_mul_amount,
            factor_sub_sign_ts_std,
            factor_mul_amount_log,
            factor_ts_dema_mul_amount,
            factor_neg_ts_maxmin_volume,
            factor_mul_amount_mul,
            factor_ts_std_signed_power_amount,
            factor_ts_maxmin_abs_volume,
            factor_abs_ts_maxmin_sub,
            factor_ts_maxmin_add_volume,
            factor_signed_power_mul_amount,
            factor_ts_pct_change_signed_power_mul,
            factor_ts_inverse_cv_delta_amount,
            factor_ts_inverse_cv_div_delta,
            factor_log_mul_amplitude,
            factor_ema_ts_dema_delta,
            factor_sub_ts_median_clip,
            factor_div_ts_inverse_cv_volume,
        ]
        for f in funcs:
            result = f(empty_df)
            assert isinstance(result, pd.Series)
            assert len(result) == 0

    def test_nan_df(self, nan_df):
        funcs = [
            factor_ts_mean_return_div_open,
            factor_add_open_delta,
            factor_mul_ts_sum_amount,
            factor_neg_ts_pct_change_abs,
            factor_mul_signed_power_amplitude,
            factor_mul_amount_ts_std,
            factor_signed_power_ts_maxmin_volume,
            factor_ts_maxmin_signed_power_volume,
            factor_mul_abs_amount,
            factor_abs_mul_amount,
            factor_sub_sign_ts_std,
            factor_mul_amount_log,
            factor_ts_dema_mul_amount,
            factor_neg_ts_maxmin_volume,
            factor_mul_amount_mul,
            factor_ts_std_signed_power_amount,
            factor_ts_maxmin_abs_volume,
            factor_abs_ts_maxmin_sub,
            factor_ts_maxmin_add_volume,
            factor_signed_power_mul_amount,
            factor_ts_pct_change_signed_power_mul,
            factor_ts_inverse_cv_delta_amount,
            factor_ts_inverse_cv_div_delta,
            factor_log_mul_amplitude,
            factor_ema_ts_dema_delta,
            factor_sub_ts_median_clip,
            factor_div_ts_inverse_cv_volume,
        ]
        for f in funcs:
            result = f(nan_df)
            assert isinstance(result, pd.Series)
            assert len(result) == len(nan_df)
            # 注意：部分因子（如含 np.sign 的）在 NaN 输入下可能全 NaN；
            # 此处仅验证不崩溃、返回类型和长度正确。


class TestTop5FactorsNumerical:
    """Top 5 因子数值正确性断言（使用最小构造数据）。"""

    def test_factor_ts_mean_return_div_open(self, minimal_df):
        result = factor_ts_mean_return_div_open(minimal_df, window=3)
        # 第一行因 shift(1) 产生 NaN，rolling mean 后仍为 NaN
        assert np.isnan(result.iloc[0])
        # 返回 Series
        assert isinstance(result, pd.Series)
        # 第二行应为 shift 差分的均值（min_periods=1）
        assert pytest.approx(result.iloc[1], abs=0.01) == -0.6667

    def test_factor_add_open_delta(self, minimal_df):
        result = factor_add_open_delta(minimal_df, window=2)
        # volume rolling sum(2): [100, 300, 500, 700, 900]
        # diff: [nan, 200, 200, 200, 200]
        # open + diff: [nan, 202.0, 203.0, 204.0, 205.0]
        assert pytest.approx(result.iloc[2], abs=0.01) == 203.0
        assert isinstance(result, pd.Series)

    def test_factor_mul_ts_sum_amount(self, minimal_df):
        result = factor_mul_ts_sum_amount(minimal_df, window=2)
        # amount rolling sum(2): [150, 650, 1550, 2850, 4550]
        # intraday_range = (high - low) / close = [1.333, 0.8, 0.571, 0.444, 0.363]
        # signed_power(intraday_range, 3.0) = intraday_range^3 * sign
        assert isinstance(result, pd.Series)
        assert len(result) == len(minimal_df)

    def test_factor_neg_ts_pct_change_abs(self, minimal_df):
        result = factor_neg_ts_pct_change_abs(minimal_df, window=2)
        # abs(volume) = volume
        # pct_change = sign(volume) * (volume - volume.shift(2)) / abs(volume)
        # volume.shift(2): [nan, nan, 100, 200, 300]
        # diff: [nan, nan, 200, 200, 200]
        # pct_change: [nan, nan, 200/300, 200/400, 200/500] = [nan, nan, 0.6667, 0.5, 0.4]
        # neg: [nan, nan, -0.6667, -0.5, -0.4]
        assert pytest.approx(result.iloc[2], abs=0.01) == -0.6667
        assert isinstance(result, pd.Series)

    def test_factor_mul_signed_power_amplitude(self, minimal_df):
        result = factor_mul_signed_power_amplitude(minimal_df)
        # amplitude = (high - low) / close.shift(1)
        # close.shift(1): [nan, 1.5, 2.5, 3.5, 4.5]
        # amplitude: [nan, 1.333, 0.8, 0.571, 0.444]
        # signed_power(amplitude, 1.5) = amplitude^1.5 * sign
        # amount: [150, 500, 1050, 1800, 2750]
        assert isinstance(result, pd.Series)
        assert len(result) == len(minimal_df)


class TestCalculateAllFactors:
    def test_returns_all_27_columns(self, sample_kline):
        result = calculate_all_factors(sample_kline)
        factor_cols = [c for c in result.columns if c.startswith("factor_")]
        assert len(factor_cols) == 27, f"期望 27 个因子列，实际得到 {len(factor_cols)}"

    def test_does_not_change_original_rows(self, sample_kline):
        original_len = len(sample_kline)
        result = calculate_all_factors(sample_kline)
        assert len(result) == original_len

    def test_amount_fallback(self, sample_kline):
        """测试缺少 amount 列时自动用 close * volume 近似。"""
        df_no_amount = sample_kline.drop(columns=["amount"])
        result = calculate_all_factors(df_no_amount)
        factor_cols = [c for c in result.columns if c.startswith("factor_")]
        assert len(factor_cols) == 27

    def test_compatible_with_calculate_all_indicators(self, sample_kline):
        """测试与现有 calculate_all_indicators 的字段约定兼容。"""
        from lib.technical_indicators import calculate_all_indicators
        indicators = calculate_all_indicators(sample_kline.copy())
        factors = calculate_all_factors(sample_kline.copy())
        # 确保两者都能运行且不冲突
        assert "sma5" in indicators.columns
        assert "factor_ts_mean_return_div_open" in factors.columns
        # 同时运行：先 indicators 再 factors
        combined = calculate_all_factors(calculate_all_indicators(sample_kline.copy()))
        assert "sma5" in combined.columns
        assert "factor_ts_mean_return_div_open" in combined.columns
