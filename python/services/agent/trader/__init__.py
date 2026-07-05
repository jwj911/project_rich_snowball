"""交易员 Agent 核心子模块。

提供多周期趋势识别、K线形态分析、交易计划生成与风控校验能力。
"""

from __future__ import annotations

from services.agent.trader.candlestick import calculate_bull_bear_strength, detect_candlestick_patterns
from services.agent.trader.market_structure import (
    detect_breakout_or_fakeout,
    find_support_resistance,
    identify_trend,
)
from services.agent.trader.multi_timeframe import analyze_multi_timeframe
from services.agent.trader.risk_check import validate_trade_plan
from services.agent.trader.trade_plan import generate_trade_plan

__all__ = [
    "identify_trend",
    "find_support_resistance",
    "detect_breakout_or_fakeout",
    "analyze_multi_timeframe",
    "detect_candlestick_patterns",
    "calculate_bull_bear_strength",
    "generate_trade_plan",
    "validate_trade_plan",
]
