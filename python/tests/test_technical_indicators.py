"""技术指标库测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.technical_indicators import (
    adx_dmi,
    atr,
    bollinger,
    cci,
    calculate_all_indicators,
    ema,
    kdj,
    macd,
    obv,
    rsi,
    sma,
    volume_ratio,
    williams_r,
)


@pytest.fixture
def sample_kline():
    """生成 50 根模拟 K 线数据（上升趋势）。"""
    np.random.seed(42)
    n = 50
    base = np.linspace(3500, 4000, n)
    noise = np.random.normal(0, 30, n)
    close = base + noise
    open_price = close + np.random.normal(0, 15, n)
    high = np.maximum(open_price, close) + np.random.uniform(10, 50, n)
    low = np.minimum(open_price, close) - np.random.uniform(10, 50, n)
    volume = np.random.uniform(10000, 50000, n)
    df = pd.DataFrame({
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    df.index = pd.date_range("2024-01-01", periods=n, freq="D")
    return df


@pytest.fixture
def bullish_df():
    """纯均线多头排列数据（强上涨）。"""
    close = np.array([100, 102, 105, 108, 112, 115, 120, 125, 130, 135])
    high = close + 2
    low = close - 2
    return pd.DataFrame({
        "open": close - 1,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.ones(10) * 10000,
    })


@pytest.fixture
def bearish_df():
    """纯均线空头排列数据（强下跌）。"""
    close = np.array([135, 130, 125, 120, 115, 112, 108, 105, 102, 100])
    high = close + 2
    low = close - 2
    return pd.DataFrame({
        "open": close + 1,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.ones(10) * 10000,
    })


class TestSMA:
    def test_sma_returns_series(self, bullish_df):
        result = sma(bullish_df["close"], 5)
        assert isinstance(result, pd.Series)
        assert len(result) == len(bullish_df)

    def test_sma_first_n_equals_first_value(self, bullish_df):
        result = sma(bullish_df["close"], 5)
        assert result.iloc[0] == bullish_df["close"].iloc[0]

    def test_sma_window5_correct(self, bullish_df):
        result = sma(bullish_df["close"], 5)
        expected = bullish_df["close"].iloc[-5:].mean()
        assert pytest.approx(result.iloc[-1], abs=0.01) == expected


class TestEMA:
    def test_ema_returns_series(self, bullish_df):
        result = ema(bullish_df["close"], 5)
        assert isinstance(result, pd.Series)

    def test_ema_weights_recent(self, bullish_df):
        result = ema(bullish_df["close"], 5)
        assert result.iloc[-1] > sma(bullish_df["close"], 5).iloc[-1]


class TestRSI:
    def test_rsi_returns_series(self, bullish_df):
        result = rsi(bullish_df["close"], 14)
        assert isinstance(result, pd.Series)

    def test_rsi_range_0_to_100(self, bullish_df):
        result = rsi(bullish_df["close"], 14)
        assert result.min() >= 0
        assert result.max() <= 100

    def test_rising_trend_rsi_above_50(self, bullish_df):
        result = rsi(bullish_df["close"], 6)
        assert result.iloc[-1] > 50

    def test_falling_trend_rsi_below_50(self, bearish_df):
        result = rsi(bearish_df["close"], 6)
        assert result.iloc[-1] < 50


class TestMACD:
    def test_macd_returns_dataframe(self, bullish_df):
        result = macd(bullish_df["close"])
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["dif", "dea", "macd"]

    def test_macd_bullish_dif_above_dea(self, bullish_df):
        result = macd(bullish_df["close"])
        assert result["dif"].iloc[-1] > result["dea"].iloc[-1]
        assert result["macd"].iloc[-1] > 0

    def test_macd_bearish_dif_below_dea(self, bearish_df):
        result = macd(bearish_df["close"])
        assert result["dif"].iloc[-1] < result["dea"].iloc[-1]
        assert result["macd"].iloc[-1] < 0


class TestBollinger:
    def test_bollinger_returns_dataframe(self, bullish_df):
        result = bollinger(bullish_df["close"], 5)
        assert list(result.columns) == ["mid", "upper", "lower"]

    def test_bollinger_upper_above_mid(self, bullish_df):
        result = bollinger(bullish_df["close"], 5)
        assert all(result["upper"] >= result["mid"])
        assert all(result["mid"] >= result["lower"])

    def test_price_within_bands(self, sample_kline):
        result = bollinger(sample_kline["close"], 20)
        last = sample_kline["close"].iloc[-1]
        assert result["lower"].iloc[-1] <= last <= result["upper"].iloc[-1]


class TestKDJ:
    def test_kdj_returns_dataframe(self, bullish_df):
        result = kdj(bullish_df, 9, 3, 3)
        assert list(result.columns) == ["k", "d", "j"]

    def test_kdj_j_equals_3k_minus_2d(self, bullish_df):
        result = kdj(bullish_df, 9, 3, 3)
        assert pytest.approx(result["j"].iloc[-1], abs=0.1) == 3 * result["k"].iloc[-1] - 2 * result["d"].iloc[-1]

    def test_kdj_values_in_range(self, sample_kline):
        result = kdj(sample_kline, 9, 3, 3)
        assert result["k"].min() >= 0 and result["k"].max() <= 100
        assert result["d"].min() >= 0 and result["d"].max() <= 100


class TestATR:
    def test_atr_returns_series(self, bullish_df):
        result = atr(bullish_df, 5)
        assert isinstance(result, pd.Series)

    def test_atr_positive(self, sample_kline):
        result = atr(sample_kline, 14)
        assert all(result > 0)


class TestCCI:
    def test_cci_returns_series(self, bullish_df):
        result = cci(bullish_df, 14)
        assert isinstance(result, pd.Series)

    def test_rising_trend_cci_positive(self, bullish_df):
        result = cci(bullish_df, 14)
        assert result.iloc[-1] > 0


class TestOBV:
    def test_obv_returns_series(self, bullish_df):
        result = obv(bullish_df)
        assert isinstance(result, pd.Series)

    def test_rising_obv_positive(self, bullish_df):
        result = obv(bullish_df)
        assert result.iloc[-1] > 0

    def test_falling_obv_negative(self, bearish_df):
        result = obv(bearish_df)
        assert result.iloc[-1] < 0


class TestADX:
    def test_adx_dmi_returns_dataframe(self, bullish_df):
        result = adx_dmi(bullish_df, 5)
        assert list(result.columns) == ["plus_di", "minus_di", "adx"]

    def test_adx_in_range(self, sample_kline):
        result = adx_dmi(sample_kline, 14)
        assert result["adx"].min() >= 0 and result["adx"].max() <= 100


class TestVolumeRatio:
    def test_volume_ratio_returns_series(self, bullish_df):
        result = volume_ratio(bullish_df, 2, 5)
        assert isinstance(result, pd.Series)


class TestWilliamsR:
    def test_williams_r_returns_series(self, bullish_df):
        result = williams_r(bullish_df, 14)
        assert isinstance(result, pd.Series)

    def test_williams_r_range(self, sample_kline):
        result = williams_r(sample_kline, 14)
        assert result.min() >= -100 and result.max() <= 0


class TestCalculateAllIndicators:
    def test_calculate_all_returns_all_columns(self, sample_kline):
        result = calculate_all_indicators(sample_kline)
        expected_cols = [
            "sma5", "ema5", "rsi6", "rsi24", "macd_dif", "macd_dea", "macd_bar",
            "boll_mid", "boll_upper", "boll_lower", "kdj_k", "kdj_d", "kdj_j",
            "atr14", "cci14", "obv", "dmi_plus", "dmi_minus", "adx14", "vol_ratio", "wr14",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_calculate_all_does_not_change_original_rows(self, sample_kline):
        original_len = len(sample_kline)
        result = calculate_all_indicators(sample_kline)
        assert len(result) == original_len
