"""因子评估器测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.agent.factor_engine.dsl import PanelData, evaluate_factor
from services.agent.factor_engine.evaluator import evaluate_factor as evaluate_factor_performance


@pytest.fixture
def sample_panel():
    """生成预测性较强的面板数据：因子值与未来收益正相关。"""
    dates = pd.date_range("2026-01-01", periods=50, freq="B")
    symbols = ["A", "B", "C", "D", "E"]

    # close 每个品种线性上升，带噪声
    np.random.seed(42)
    close_data = {}
    volume_data = {}
    for i, sym in enumerate(symbols):
        base = np.linspace(100, 150, 50) + np.random.normal(0, 2, 50)
        close_data[sym] = base
        volume_data[sym] = np.random.randint(1000, 2000, 50)

    close = pd.DataFrame(close_data, index=dates)
    open_df = close + np.random.normal(0, 0.5, close.shape)
    high = close + 1
    low = close - 1
    volume = pd.DataFrame(volume_data, index=dates)

    return PanelData(open=open_df, high=high, low=low, close=close, volume=volume)


def test_evaluate_momentum_factor(sample_panel):
    """动量因子（5 日收益）应具有一定的正向 IC。"""
    try:
        from scipy import stats
    except ImportError:
        pytest.skip("scipy not available")
    factor = evaluate_factor("close / ts_delay(close, 5) - 1", sample_panel)
    result = evaluate_factor_performance("momentum", "close / ts_delay(close, 5) - 1", factor, sample_panel)

    assert result.ic_mean is not None
    assert result.rank_ic_mean is not None
    assert result.coverage > 0.8
    assert len(result.quantile_returns) == 5


def test_evaluate_coverage_and_report(sample_panel):
    factor = evaluate_factor("ts_zscore(close, 10)", sample_panel)
    result = evaluate_factor_performance("zscore", "ts_zscore(close, 10)", factor, sample_panel)

    assert result.factor_name == "zscore"
    assert result.formula == "ts_zscore(close, 10)"
    assert result.symbols == ["A", "B", "C", "D", "E"]
    assert 0 <= result.coverage <= 1
    assert result.to_dict()["ic_mean"] == result.ic_mean
