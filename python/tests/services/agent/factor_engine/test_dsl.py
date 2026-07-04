"""因子 DSL 安全求值器测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.agent.factor_engine.dsl import (
    PanelData,
    evaluate_factor,
    validate_factor_formula,
)


@pytest.fixture
def sample_panel():
    """生成 10 个交易日 × 3 个品种的面板数据。"""
    dates = pd.date_range("2026-01-01", periods=10, freq="B")
    symbols = ["RB", "AU", "CU"]

    def _frame(values):
        return pd.DataFrame(
            np.tile(values, (len(symbols), 1)).T,
            index=dates,
            columns=symbols,
        )

    close = np.linspace(100, 109, 10)
    return PanelData(
        open=_frame(close + np.random.normal(0, 0.5, 10)),
        high=_frame(close + 1),
        low=_frame(close - 1),
        close=_frame(close),
        volume=_frame(np.arange(10, 20)),
    )


def test_validate_simple_formula():
    validate_factor_formula("close / ts_delay(close, 5) - 1")


def test_validate_rejects_unsafe_code():
    with pytest.raises(ValueError):
        validate_factor_formula("__import__('os').system('ls')")

    with pytest.raises(ValueError):
        validate_factor_formula("open('/etc/passwd').read()")


def test_evaluate_momentum_factor(sample_panel):
    factor = evaluate_factor("close / ts_delay(close, 5) - 1", sample_panel)
    assert isinstance(factor, pd.DataFrame)
    assert factor.shape == sample_panel.close.shape
    assert factor.columns.tolist() == ["RB", "AU", "CU"]


def test_evaluate_volume_price_factor(sample_panel):
    factor = evaluate_factor("ts_rank(close, 5) / ts_rank(volume, 5)", sample_panel)
    assert isinstance(factor, pd.DataFrame)
    assert factor.shape == sample_panel.close.shape


def test_evaluate_cross_sectional_rank(sample_panel):
    factor = evaluate_factor("rank(close)", sample_panel)
    assert isinstance(factor, pd.DataFrame)
    # 由于 close 在所有品种上相同，rank 应该相同
    assert factor.shape == sample_panel.close.shape
