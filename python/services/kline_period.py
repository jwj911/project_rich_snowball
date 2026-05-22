"""K-line period compatibility helpers."""

PERIOD_ALIASES: dict[str, tuple[str, ...]] = {
    "1m": ("1m", "1"),
    "1": ("1", "1m"),
    "5m": ("5m", "5"),
    "5": ("5", "5m"),
    "15m": ("15m", "15"),
    "15": ("15", "15m"),
    "30m": ("30m", "30"),
    "30": ("30", "30m"),
    "1h": ("1h", "60"),
    "60": ("60", "1h"),
    "1d": ("1d", "D"),
    "D": ("D", "1d"),
    "1w": ("1w", "W"),
    "W": ("W", "1w"),
    "M": ("M",),
}


def period_candidates(period: str) -> tuple[str, ...]:
    """Return query candidates, preserving the caller's requested period first."""
    return PERIOD_ALIASES.get(period, (period,))
