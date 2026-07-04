"""将 Strategy DSL 转换为回测配置。

连接 StrategyCompilerAgent（Phase 3）与 BacktestAgent（Phase 2），
实现"先编译策略，再回测验证"的完整链路。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from services.agent.strategy_compiler_agent import StrategyDSL
from services.backtest.engine import BacktestConfig

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# DSL -> BacktestConfig
# ------------------------------------------------------------------

def dsl_to_backtest_config(
    dsl: StrategyDSL,
    initial_cash: float = 100_000.0,
    quantity: int = 1,
) -> BacktestConfig:
    """将策略 DSL 转换为回测引擎配置。

    同时从 DSL 的风控参数中解析仓位、止损等自定义值。
    """
    period = _timeframe_to_period(dsl.timeframe)
    direction = dsl.direction

    # 尝试从 entry/exit conditions 推断窗口参数（用于兼容现有 config 字段）
    short_window, long_window = _extract_ma_windows(dsl.entry)
    if short_window is None:
        short_window = 5
    if long_window is None:
        long_window = 20

    # 风控参数解析
    risk = dsl.risk
    position = risk.get("position_size", {})
    stop_loss = risk.get("stop_loss", {})
    take_profit = risk.get("take_profit", {})

    # 从止损类型推断数量（如 fixed_lots 的 value 直接就是手数）
    if position.get("type") == "fixed_lots":
        quantity = int(position.get("value", quantity))

    return BacktestConfig(
        symbol=dsl.universe[0] if dsl.universe else "",
        period=period,
        strategy_type="dsl",
        short_window=short_window,
        long_window=long_window,
        initial_cash=initial_cash,
        quantity=quantity,
        multiplier=1.0,
        fee_rate=0.0001,
        direction=direction,
    )


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def _timeframe_to_period(timeframe: str) -> str:
    """将 DSL 周期转换为回测周期。"""
    mapping = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w", "1mo": "1mo",
    }
    return mapping.get(timeframe, "1d")


def _extract_ma_windows(entry: dict[str, Any]) -> tuple[int | None, int | None]:
    """从 entry conditions 中提取均线窗口参数。"""
    conditions = entry.get("conditions", [])
    short = None
    long = None
    for cond in conditions:
        ind = cond.get("indicator", "")
        ind2 = cond.get("indicator2", "")
        m1 = re.search(r"(\d+)", ind)
        m2 = re.search(r"(\d+)", ind2)
        if m1 and m2:
            v1 = int(m1.group(1))
            v2 = int(m2.group(1))
            if v1 < v2:
                short = v1
                long = v2
            else:
                short = v2
                long = v1
            break
    return short, long
