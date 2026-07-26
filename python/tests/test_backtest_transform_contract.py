"""Regression tests for executable Strategy DSL transform contracts."""

from __future__ import annotations

import pandas as pd
import pytest

from services.agent.strategy_compiler_agent import StrategyDSL, StrategyValidator
from services.backtest.engine import _eval_conditions
from services.backtest.transform_contract import TransformContractError


def _frame() -> pd.DataFrame:
    volumes = [100] * 34 + [200]
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=len(volumes), freq="D"),
            "open": [100.0] * len(volumes),
            "high": [101.0] * len(volumes),
            "low": [99.0] * len(volumes),
            "close": [100.0] * len(volumes),
            "volume": volumes,
        }
    )


def test_multiply_indicator2_executes_rhs_multiplier():
    signals = _eval_conditions(
        _frame(),
        [
            {
                "indicator": "volume",
                "operator": "greater_than",
                "indicator2": "volume_sma20",
                "value": 1.5,
                "transform": "multiply_indicator2",
            }
        ],
    )

    # The last 200-volume bar is above its 20-bar mean multiplied by 1.5.
    assert bool(signals.iloc[-1]) is True


def test_legacy_multiply_value_remains_executable():
    signals = _eval_conditions(
        _frame(),
        [
            {
                "indicator": "volume",
                "operator": "greater_than",
                "indicator2": "volume_sma20",
                "value": 1.5,
                "transform": "multiply_value",
            }
        ],
    )

    assert bool(signals.iloc[-1]) is True


def test_unknown_transform_is_rejected_in_engine():
    with pytest.raises(TransformContractError, match="不支持的 transform"):
        _eval_conditions(
            _frame(),
            [
                {
                    "indicator": "close",
                    "operator": "greater_than",
                    "indicator2": "sma20",
                    "value": 1.2,
                    "transform": "multiply_unknown",
                }
            ],
        )


def test_transform_requires_positive_numeric_multiplier():
    with pytest.raises(TransformContractError, match="大于 0"):
        _eval_conditions(
            _frame(),
            [
                {
                    "indicator": "close",
                    "operator": "greater_than",
                    "indicator2": "sma20",
                    "value": 0,
                    "transform": "multiply_indicator2",
                }
            ],
        )


def test_compiler_validator_shares_transform_contract():
    dsl = StrategyDSL(
        name="transform contract",
        description="test",
        universe=["RB"],
        timeframe="1d",
        direction="long",
        entry={
            "conditions": [
                {
                    "indicator": "close",
                    "operator": "greater_than",
                    "indicator2": "sma20",
                    "value": 1.1,
                    "transform": "multiply_unknown",
                }
            ],
            "logic": "and",
        },
        exit={"conditions": [{"indicator": "close", "operator": "less_than", "value": 0}], "logic": "and"},
        risk={},
    )

    errors = StrategyValidator.validate(dsl)

    assert any("不支持的 transform" in error for error in errors)
