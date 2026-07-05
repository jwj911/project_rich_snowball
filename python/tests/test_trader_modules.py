"""交易员 Agent 子模块单元测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.agent.trader.candlestick import calculate_bull_bear_strength, detect_candlestick_patterns
from services.agent.trader.market_structure import (
    detect_breakout_or_fakeout,
    find_support_resistance,
    identify_trend,
)
from services.agent.trader.multi_timeframe import analyze_multi_timeframe
from services.agent.trader.risk_check import validate_trade_plan
from services.agent.trader.trade_plan import generate_trade_plan


def _make_uptrend_df(n: int = 60) -> pd.DataFrame:
    """构造一个上涨趋势 DataFrame。"""
    np.random.seed(42)
    base = np.linspace(100, 130, n)
    noise = np.random.normal(0, 1, n)
    close = base + noise
    high = close + np.abs(np.random.normal(0.5, 0.3, n))
    low = close - np.abs(np.random.normal(0.5, 0.3, n))
    open_ = close + np.random.normal(0, 0.3, n)
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=n, freq="D"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.random.randint(1000, 5000, n),
        }
    )


def _make_downtrend_df(n: int = 60) -> pd.DataFrame:
    """构造一个下跌趋势 DataFrame。"""
    np.random.seed(43)
    base = np.linspace(130, 100, n)
    noise = np.random.normal(0, 1, n)
    close = base + noise
    high = close + np.abs(np.random.normal(0.5, 0.3, n))
    low = close - np.abs(np.random.normal(0.5, 0.3, n))
    open_ = close + np.random.normal(0, 0.3, n)
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=n, freq="D"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.random.randint(1000, 5000, n),
        }
    )


def test_identify_trend_uptrend():
    df = _make_uptrend_df(80)
    result = identify_trend(df)
    assert result["trend"] == "uptrend"
    assert result["direction"] == "up"
    assert result["strength"] > 50


def test_identify_trend_downtrend():
    df = _make_downtrend_df(80)
    result = identify_trend(df)
    assert result["trend"] == "downtrend"
    assert result["direction"] == "down"
    assert result["strength"] > 50


def test_identify_trend_insufficient_data():
    df = _make_uptrend_df(10)
    result = identify_trend(df)
    assert result["trend"] == "sideways"


def test_find_support_resistance():
    df = _make_uptrend_df(80)
    levels = find_support_resistance(df, lookback=30)
    assert isinstance(levels, list)
    # 趋势行情中可能识别出支撑或阻力
    if levels:
        assert all(level["type"] in ("support", "resistance") for level in levels)
        assert all("level" in level for level in levels)


def test_detect_breakout_or_fakeout():
    df = _make_uptrend_df(30)
    # 取当前最高价附近作为阻力位
    level = df["high"].iloc[-5]
    result = detect_breakout_or_fakeout(df, level, "resistance")
    assert result["result"] in ("breakout", "fakeout", "none")
    assert "description" in result


def test_analyze_multi_timeframe():
    tf_data = {
        "1d": _make_uptrend_df(80),
        "1h": _make_uptrend_df(80),
    }
    result = analyze_multi_timeframe(tf_data)
    assert result["dominant_trend"] == "uptrend"
    assert result["direction"] == "up"
    assert result["alignment_score"] > 0
    assert result["entry_timeframe"] in tf_data


def test_detect_candlestick_patterns_bullish_engulfing():
    """构造一个看涨吞没形态。"""
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=5, freq="D"),
            "open": [102, 103, 104, 105, 104],
            "high": [103, 104, 105, 106, 107],
            "low": [101, 102, 103, 104, 103],
            "close": [102.5, 103.5, 104.5, 104, 106],  # 最后一根阳线吞没前一根阴线
            "volume": [1000, 1000, 1000, 1000, 2000],
        }
    )
    patterns = detect_candlestick_patterns(df)
    names = [p["name"] for p in patterns]
    assert "吞没形态" in names


def test_calculate_bull_bear_strength_bullish():
    """构造一根大阳线，测试多头力量评分。"""
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=5, freq="D"),
            "open": [100, 101, 102, 103, 104],
            "high": [101, 102, 103, 104, 107],
            "low": [99, 100, 101, 102, 104],
            "close": [101, 102, 103, 104, 107],
            "volume": [1000, 1000, 1000, 1000, 3000],
        }
    )
    result = calculate_bull_bear_strength(df)
    assert result["score"] > 0
    assert "多头" in result["description"] or result["score"] > 0.3


def test_generate_trade_plan_long():
    """在上涨趋势中生成多头交易计划。"""
    df = _make_uptrend_df(80)
    tf_data = {"1h": df, "1d": df}
    plan = generate_trade_plan(
        symbol="RB",
        current_price=float(df["close"].iloc[-1]),
        dominant_trend="uptrend",
        direction="up",
        entry_timeframe="1h",
        timeframe_data=tf_data,
        style="intraday_swing",
        account_balance=100000.0,
        risk_per_trade=0.02,
        multiplier=10.0,
    )
    assert plan is not None
    assert plan["direction"] == "long"
    assert plan["stop_loss"] < plan["entry_price"]
    assert plan["take_profit"] > plan["entry_price"]
    assert plan["risk_reward_ratio"] >= 1.2
    assert plan["position_size"] >= 1


def test_generate_trade_plan_insufficient_rr():
    """测试盈亏比不足时返回 None。"""
    df = _make_uptrend_df(80)
    # 强行把价格压得很平，使关键位接近
    df["close"] = 100.0 + np.random.normal(0, 0.05, len(df))
    df["high"] = df["close"] + 0.05
    df["low"] = df["close"] - 0.05
    tf_data = {"1h": df}
    plan = generate_trade_plan(
        symbol="RB",
        current_price=100.0,
        dominant_trend="sideways",
        direction="neutral",
        entry_timeframe="1h",
        timeframe_data=tf_data,
        style="intraday_swing",
        account_balance=100000.0,
        risk_per_trade=0.02,
        multiplier=10.0,
    )
    assert plan is None


def test_validate_trade_plan_valid():
    plan = {
        "direction": "long",
        "style": "intraday_swing",
        "entry_price": 100.0,
        "stop_loss": 98.0,
        "take_profit": 104.0,
        "position_size": 1,
        "actual_risk_amount": 2000.0,
        "risk_reward_ratio": 2.0,
        "min_risk_reward": 1.5,
        "risk_per_trade": 0.02,
        "confidence": "high",
    }
    result = validate_trade_plan(plan, 100000.0)
    assert result["valid"] is True
    assert result["risk_percent"] == 0.02


def test_validate_trade_plan_risk_too_high():
    plan = {
        "direction": "long",
        "style": "intraday_swing",
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "take_profit": 110.0,
        "position_size": 100,
        "actual_risk_amount": 100000.0,
        "risk_reward_ratio": 1.0,
        "min_risk_reward": 1.5,
        "risk_per_trade": 0.02,
        "confidence": "low",
    }
    result = validate_trade_plan(plan, 100000.0)
    assert result["valid"] is False
    assert any("风险" in w for w in result["warnings"])
