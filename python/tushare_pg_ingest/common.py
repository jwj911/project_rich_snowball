"""Shared helpers for standalone Tushare -> PostgreSQL ingestion scripts.

Purpose:
    Provides common utilities used by all Tushare/AKShare data ingestion
    scripts in this directory.  This includes environment loading from the
    project-root ``.env``, a rate-limited Tushare Pro client, a small
    statistics dataclass, and various date / exchange / argument helpers.

Tushare/AKShare APIs:
    None directly - this is a utility module.

Target database tables:
    None directly - helpers are consumed by sibling scripts.

Key CLI arguments (sibling scripts add these via ``add_common_args``):
    --start-date YYYYMMDD   Start of date window
    --end-date   YYYYMMDD   End of date window
    --date       YYYYMMDD   Single trade date (shortcut for start==end)
    --allow-sqlite          Permit writing to SQLite (normally rejected)
    --dry-run               Fetch and transform data, but do not commit
    --min-interval SECONDS  Throttle between Tushare calls (default 0.55)

Known limitations:
    - The TushareClient class is intentionally minimal; it does not handle
      Tushare Pro's advanced pagination or multi-page token flow.
    - ``configure_database`` will abort if DATABASE_URL points to anything
      other than PostgreSQL unless ``--allow-sqlite`` is passed.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import requests.exceptions
import urllib3.exceptions

# ---------------------------------------------------------------------------
# Project-path bootstrap
# ---------------------------------------------------------------------------
# All sibling scripts live two levels below the project root.  Insert the
# parent ``python/`` directory into sys.path so that ``from models import …``
# and ``from data_collector import …`` resolve correctly regardless of the
# current working directory.
ROOT = Path(__file__).resolve().parents[2]
PYTHON_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_DIR))


def _load_env(path: Path) -> None:
    """Load key=value pairs from a ``.env`` file into ``os.environ``.

    Falls back to a manual parser when ``python-dotenv`` is not installed.
    Uses ``setdefault`` so existing environment variables take precedence.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(path)
        return
    except ImportError:
        pass

    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Load once at import time so that TUSHARE_TOKEN and DATABASE_URL are
# available before any script logic runs.
_load_env(ROOT / ".env")


# ---------------------------------------------------------------------------
# Exchange constants
# ---------------------------------------------------------------------------
# Mapping from Tushare exchange codes to the suffix used in ``ts_code``
# (e.g. "AU2506.SHF" for SHFE contracts).
EXCHANGE_SUFFIX = {
    "SHFE": ".SHF",
    "DCE": ".DCE",
    "CZCE": ".ZCE",
    "ZCE": ".ZCE",   # Alias used by some older Tushare responses
    "INE": ".INE",
    "CFFEX": ".CFX",
    "GFEX": ".GFE",
}

# Full list of domestic futures exchanges supported by Tushare Pro.
TUSHARE_EXCHANGES = ["SHFE", "DCE", "CZCE", "INE", "CFFEX", "GFEX"]


# ---------------------------------------------------------------------------
# IngestStats
# ---------------------------------------------------------------------------
@dataclass
class IngestStats:
    """Running counters for a single ingestion run.

    Attributes:
        fetched: Raw rows returned by the upstream API.
        written: Rows successfully upserted / committed to the database.
        skipped: Rows discarded because of missing keys, duplicates, or
                 mapping failures.
        failed:  Rows where the API call itself raised an exception.
    """
    fetched: int = 0
    written: int = 0
    skipped: int = 0
    failed: int = 0

    def add(self, other: "IngestStats") -> None:
        """Add counters from another ``IngestStats`` instance in-place."""
        self.fetched += other.fetched
        self.written += other.written
        self.skipped += other.skipped
        self.failed += other.failed

    def as_dict(self) -> dict[str, int]:
        """Return a plain dict suitable for JSON logging or printouts."""
        return {
            "fetched": self.fetched,
            "written": self.written,
            "skipped": self.skipped,
            "failed": self.failed,
        }


# ---------------------------------------------------------------------------
# TushareClient
# ---------------------------------------------------------------------------
class TushareClient:
    """Tiny rate-limited wrapper around Tushare Pro.

    Enforces a configurable minimum interval between API calls and retries
    transient failures up to three times.  Permission / quota errors are
    re-raised immediately to avoid burning retries.
    """

    def __init__(self, min_interval: float = 0.55, timeout: float | None = None):
        """Initialise the client.

        Args:
            min_interval: Minimum seconds between successive API calls.
                          Tushare Pro's free tier is typically ~0.5 s.
            timeout:      HTTP timeout in seconds for the underlying Tushare Pro
                          client. Defaults to ``TUSHARE_TIMEOUT`` env var or 60 s.

        Raises:
            RuntimeError: If ``TUSHARE_TOKEN`` is missing or still set to the
                          placeholder value in ``.env``.
        """
        token = os.getenv("TUSHARE_TOKEN")
        if not token or token == "your-tushare-token-here":
            raise RuntimeError("TUSHARE_TOKEN is not configured in project-root .env")

        import tushare as ts

        ts.set_token(token)
        if timeout is None:
            timeout = float(os.getenv("TUSHARE_TIMEOUT", "60"))
        self.pro = ts.pro_api(timeout=timeout)
        self.min_interval = min_interval
        self._last_call_at = 0.0

    def query(self, api_name: str, **kwargs: Any):
        """Call a Tushare Pro API with rate-limiting and retry logic.

        Args:
            api_name: Method name on ``self.pro``, e.g. ``"fut_daily"``.
            **kwargs: Parameters forwarded to the API.  ``None`` and empty
                      strings are filtered out automatically.

        Returns:
            A ``pandas.DataFrame`` (Tushare's default return type).

        Raises:
            Exception: The last exception raised after three failed attempts,
                       or immediately for permission / quota errors.
        """
        elapsed = time.time() - self._last_call_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call_at = time.time()

        api = getattr(self.pro, api_name)
        # Drop unset optional parameters so Tushare does not receive literal
        # None values which some endpoints reject.
        filtered = {k: v for k, v in kwargs.items() if v not in (None, "")}

        # Network-level errors that are usually transient and worth a longer wait.
        network_errors = (
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            urllib3.exceptions.ProtocolError,
            urllib3.exceptions.ReadTimeoutError,
        )

        last_exc = None
        for attempt in range(3):
            try:
                return api(**filtered)
            except Exception as e:
                last_exc = e
                msg = str(e).lower()
                # Permission/quota/frequency errors: don't waste retries
                if any(k in msg for k in ("unauthorized", "积分", "权限", "freq", "frequency", "配额", "超限", " limit")):
                    raise
                if attempt < 2:
                    # Give network-layer problems more time to recover.
                    if isinstance(e, network_errors):
                        wait = 2 ** (attempt + 1)
                    else:
                        wait = 2 ** attempt
                    print(f"[RETRY {attempt + 1}/3] {api_name} failed, waiting {wait}s: {e}")
                    time.sleep(wait)
        raise last_exc


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------
def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Attach the standard date / dry-run / throttle arguments to *parser*.

    This is the canonical way for sibling scripts to declare their shared
    flags without duplicating boilerplate.
    """
    parser.add_argument("--start-date", help="Start date, YYYYMMDD")
    parser.add_argument("--end-date", help="End date, YYYYMMDD")
    parser.add_argument("--date", dest="trade_date", help="Single trade date, YYYYMMDD")
    parser.add_argument("--allow-sqlite", action="store_true", help="Allow writing to SQLite for local experiments")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and map data, but do not write rows")
    parser.add_argument("--min-interval", type=float, default=0.55, help="Seconds between Tushare calls")


def configure_database(allow_sqlite: bool = False) -> None:
    """Initialise the database engine and tables.

    Args:
        allow_sqlite: If ``False`` (default) and ``DATABASE_URL`` points to
                      SQLite, raises ``RuntimeError`` as a safety guard.

    Raises:
        RuntimeError: When the dialect is SQLite and ``allow_sqlite`` is
                      ``False``.
    """
    from models import engine, init_db

    if engine.dialect.name != "postgresql" and not allow_sqlite:
        raise RuntimeError(
            f"DATABASE_URL points to {engine.dialect.name}. "
            "Set DATABASE_URL to local PostgreSQL or pass --allow-sqlite for experiments."
        )
    init_db()


def date_window(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve a date range from CLI arguments.

    ``--date`` takes precedence.  Otherwise both ``--start-date`` and
    ``--end-date`` must be provided.

    Returns:
        A ``(start_date, end_date)`` tuple of ``YYYYMMDD`` strings.

    Raises:
        ValueError: If the required arguments are missing.
    """
    if args.trade_date:
        return args.trade_date, args.trade_date
    if not args.start_date or not args.end_date:
        raise ValueError("Provide --date or both --start-date and --end-date")
    return args.start_date, args.end_date


def iter_yyyymmdd(start_date: str, end_date: str) -> Iterable[str]:
    """Yield every calendar day between *start_date* and *end_date* inclusive.

    Args:
        start_date: ``YYYYMMDD`` string.
        end_date:   ``YYYYMMDD`` string.

    Yields:
        ``YYYYMMDD`` strings.

    Raises:
        ValueError: If *end_date* precedes *start_date*.
    """
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    if end < start:
        raise ValueError("end date must be greater than or equal to start date")
    current = start
    while current <= end:
        yield current.strftime("%Y%m%d")
        current += timedelta(days=1)


def comma_list(value: str | None) -> list[str]:
    """Split a comma-separated string into upper-cased, stripped tokens.

    Returns an empty list for ``None`` or empty input.
    """
    if not value:
        return []
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def parse_exchanges(value: str | None) -> list[str]:
    """Parse a comma-separated exchange list, defaulting to all domestic ones."""
    exchanges = comma_list(value)
    return exchanges or TUSHARE_EXCHANGES


# ---------------------------------------------------------------------------
# Symbol / ts_code helpers
# ---------------------------------------------------------------------------
def ts_code_for_symbol(symbol: str, exchange: str | None = None) -> str:
    """Build a full ``ts_code`` (``SYMBOL.SUFFIX``) from a base symbol.

    When *exchange* is omitted the function queries ``VarietyDB`` to
    discover the exchange automatically.

    Args:
        symbol:   Base symbol, e.g. ``"AU"``.
        exchange: Optional exchange code, e.g. ``"SHFE"``.

    Returns:
        A full ``ts_code`` such as ``"AU.SHF"``.

    Raises:
        ValueError: If the exchange is unsupported or the symbol is unknown.
    """
    from models import SessionLocal, VarietyDB

    # Already a fully-qualified ts_code - pass through unchanged.
    if "." in symbol:
        return symbol.upper()

    if exchange:
        suffix = EXCHANGE_SUFFIX.get(exchange.upper())
        if not suffix:
            raise ValueError(f"Unsupported exchange: {exchange}")
        return f"{symbol.upper()}{suffix}"

    # Look up the exchange from the local VarietyDB record.
    db = SessionLocal()
    try:
        variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol.upper()).first()
        if not variety:
            raise ValueError(f"Unknown symbol {symbol}; pass a full ts_code or --exchange")
        suffix = EXCHANGE_SUFFIX.get(variety.exchange)
        if not suffix:
            raise ValueError(f"Unsupported exchange for {symbol}: {variety.exchange}")
        return f"{symbol.upper()}{suffix}"
    finally:
        db.close()


def variety_id_for_ts_code(ts_code: str) -> int | None:
    """Map a ``ts_code`` back to the corresponding ``VarietyDB.id``.

    The alphabetic prefix is extracted and matched against ``VarietyDB.symbol``.

    Args:
        ts_code: Full code such as ``"AU2506.SHF"``.

    Returns:
        The primary key of the matching variety, or ``None``.
    """
    from models import SessionLocal, VarietyDB

    symbol = ts_code.split(".", 1)[0]
    letters = "".join(ch for ch in symbol if ch.isalpha()).upper()
    db = SessionLocal()
    try:
        variety = db.query(VarietyDB).filter(VarietyDB.symbol == letters).first()
        return variety.id if variety else None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# DataFrame helpers
# ---------------------------------------------------------------------------
def records_from_df(df) -> list[dict[str, Any]]:
    """Convert a (possibly empty) DataFrame into a list of dict records.

    NaN floats are normalised to ``None`` so that SQLAlchemy does not
    accidentally persist ``nan`` strings.
    """
    if df is None or df.empty:
        return []
    import math

    records = df.to_dict("records")
    for rec in records:
        for k, v in list(rec.items()):
            if isinstance(v, float) and math.isnan(v):
                rec[k] = None
    return records


def print_stats(name: str, stats: IngestStats) -> None:
    """Emit a single-line summary of an ingestion run."""
    print(f"[DONE] {name}: {stats.as_dict()}")
