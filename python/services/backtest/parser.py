"""Rule-based strategy intent parser.

The first version intentionally supports a compact strategy DSL inferred from
Chinese natural language. It gives the BacktestAgent a deterministic fallback
before a future LLM-generated strategy compiler is introduced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from services.agent.utils import resolve_symbol


@dataclass(slots=True)
class StrategyIntent:
    symbol: str
    period: str = "1d"
    strategy_type: str = "ma_cross"
    short_window: int = 5
    long_window: int = 20
    initial_cash: float = 100_000.0
    quantity: int = 1
    direction: str = "long"
    limit: int = 500


_PERIOD_ALIASES = {
    "日线": "1d",
    "日": "1d",
    "周线": "1w",
    "周": "1w",
    "小时": "1h",
    "1小时": "1h",
    "15分钟": "15m",
    "十五分钟": "15m",
    "5分钟": "5m",
    "五分钟": "5m",
}


def parse_strategy_intent(db: Session, query: str) -> StrategyIntent | None:
    """Parse a natural-language query into a supported backtest intent."""
    symbol = resolve_symbol(db, query)
    if not symbol:
        return None

    text = query.strip()
    period = _parse_period(text)
    short_window, long_window = _parse_ma_windows(text)
    initial_cash = _parse_cash(text)
    quantity = _parse_quantity(text)
    direction = "short" if any(token in text for token in ("做空", "空头", "卖空")) else "long"

    return StrategyIntent(
        symbol=symbol,
        period=period,
        strategy_type="ma_cross",
        short_window=short_window,
        long_window=long_window,
        initial_cash=initial_cash,
        quantity=quantity,
        direction=direction,
    )


def _parse_period(text: str) -> str:
    for key, value in _PERIOD_ALIASES.items():
        if key in text:
            return value
    return "1d"


def _parse_ma_windows(text: str) -> tuple[int, int]:
    matches = [int(n) for n in re.findall(r"(\d+)\s*(?:日|天|周期|根)?(?:均线|ma|MA)", text)]
    if len(matches) >= 2:
        short_window, long_window = sorted(matches[:2])
        return max(2, short_window), max(short_window + 1, long_window)

    pair = re.search(r"(\d+)\s*(?:/|和|与|,|，)\s*(\d+)", text)
    if pair:
        short_window, long_window = sorted((int(pair.group(1)), int(pair.group(2))))
        return max(2, short_window), max(short_window + 1, long_window)

    return 5, 20


def _parse_cash(text: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(万)?\s*(?:资金|本金|账户)", text)
    if not match:
        return 100_000.0
    value = float(match.group(1))
    if match.group(2):
        value *= 10_000
    return max(value, 1_000.0)


def _parse_quantity(text: str) -> int:
    match = re.search(r"(\d+)\s*手", text)
    if not match:
        return 1
    return max(int(match.group(1)), 1)
