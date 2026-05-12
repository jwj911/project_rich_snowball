"""Shared helpers for standalone Tushare -> PostgreSQL ingestion scripts."""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
PYTHON_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_DIR))


def _load_env(path: Path) -> None:
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


_load_env(ROOT / ".env")


EXCHANGE_SUFFIX = {
    "SHFE": ".SHF",
    "DCE": ".DCE",
    "CZCE": ".ZCE",
    "ZCE": ".ZCE",
    "INE": ".INE",
    "CFFEX": ".CFX",
    "GFEX": ".GFE",
}

TUSHARE_EXCHANGES = ["SHFE", "DCE", "CZCE", "INE", "CFFEX", "GFEX"]


@dataclass
class IngestStats:
    fetched: int = 0
    written: int = 0
    skipped: int = 0
    failed: int = 0

    def add(self, other: "IngestStats") -> None:
        self.fetched += other.fetched
        self.written += other.written
        self.skipped += other.skipped
        self.failed += other.failed

    def as_dict(self) -> dict[str, int]:
        return {
            "fetched": self.fetched,
            "written": self.written,
            "skipped": self.skipped,
            "failed": self.failed,
        }


class TushareClient:
    """Tiny rate-limited wrapper around Tushare Pro."""

    def __init__(self, min_interval: float = 0.55):
        token = os.getenv("TUSHARE_TOKEN")
        if not token or token == "your-tushare-token-here":
            raise RuntimeError("TUSHARE_TOKEN is not configured in project-root .env")

        import tushare as ts

        ts.set_token(token)
        self.pro = ts.pro_api()
        self.min_interval = min_interval
        self._last_call_at = 0.0

    def query(self, api_name: str, **kwargs: Any):
        elapsed = time.time() - self._last_call_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call_at = time.time()

        api = getattr(self.pro, api_name)
        filtered = {k: v for k, v in kwargs.items() if v not in (None, "")}

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
                    wait = 2 ** attempt
                    print(f"[RETRY {attempt + 1}/3] {api_name} failed, waiting {wait}s: {e}")
                    time.sleep(wait)
        raise last_exc


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start-date", help="Start date, YYYYMMDD")
    parser.add_argument("--end-date", help="End date, YYYYMMDD")
    parser.add_argument("--date", dest="trade_date", help="Single trade date, YYYYMMDD")
    parser.add_argument("--allow-sqlite", action="store_true", help="Allow writing to SQLite for local experiments")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and map data, but do not write rows")
    parser.add_argument("--min-interval", type=float, default=0.55, help="Seconds between Tushare calls")


def configure_database(allow_sqlite: bool = False) -> None:
    from models import engine, init_db

    if engine.dialect.name != "postgresql" and not allow_sqlite:
        raise RuntimeError(
            f"DATABASE_URL points to {engine.dialect.name}. "
            "Set DATABASE_URL to local PostgreSQL or pass --allow-sqlite for experiments."
        )
    init_db()


def date_window(args: argparse.Namespace) -> tuple[str, str]:
    if args.trade_date:
        return args.trade_date, args.trade_date
    if not args.start_date or not args.end_date:
        raise ValueError("Provide --date or both --start-date and --end-date")
    return args.start_date, args.end_date


def iter_yyyymmdd(start_date: str, end_date: str) -> Iterable[str]:
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    if end < start:
        raise ValueError("end date must be greater than or equal to start date")
    current = start
    while current <= end:
        yield current.strftime("%Y%m%d")
        current += timedelta(days=1)


def comma_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def parse_exchanges(value: str | None) -> list[str]:
    exchanges = comma_list(value)
    return exchanges or TUSHARE_EXCHANGES


def ts_code_for_symbol(symbol: str, exchange: str | None = None) -> str:
    from models import SessionLocal, VarietyDB

    if "." in symbol:
        return symbol.upper()

    if exchange:
        suffix = EXCHANGE_SUFFIX.get(exchange.upper())
        if not suffix:
            raise ValueError(f"Unsupported exchange: {exchange}")
        return f"{symbol.upper()}{suffix}"

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
    from models import SessionLocal, VarietyDB

    symbol = ts_code.split(".", 1)[0]
    letters = "".join(ch for ch in symbol if ch.isalpha()).upper()
    db = SessionLocal()
    try:
        variety = db.query(VarietyDB).filter(VarietyDB.symbol == letters).first()
        return variety.id if variety else None
    finally:
        db.close()


def records_from_df(df) -> list[dict[str, Any]]:
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
    print(f"[DONE] {name}: {stats.as_dict()}")
