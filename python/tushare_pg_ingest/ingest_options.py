"""Ingest Tushare option contract metadata and daily bars.

Purpose:
    Pulls option data from Tushare Pro and writes it into standalone
    PostgreSQL/SQLite tables managed by this script:

    - ``opt_contracts`` from Tushare ``opt_basic``
    - ``opt_daily_data`` from Tushare ``opt_daily``

Tushare APIs used:
    ``opt_basic`` - option contract metadata.
    ``opt_daily`` - option daily OHLCV bars.

Key CLI arguments:
    --dataset {basic,daily,all}  Which API(s) to ingest; default all
    --start-date YYYYMMDD        Daily start date
    --end-date   YYYYMMDD        Daily end date
    --date       YYYYMMDD        Daily single-date shortcut
    --exchanges COMMA_LIST       e.g. SSE,SZSE,DCE,SHFE
    --ts-codes COMMA_LIST        Option contract TS codes
    --list-date YYYYMMDD         opt_basic filter
    --opt-code CODE              opt_basic underlying/standard contract code
    --call-put VALUE             opt_basic call/put filter
    --allow-sqlite
    --dry-run
    --min-interval SECONDS

Usage examples:
    python tushare_pg_ingest/ingest_options.py --dataset basic --exchanges DCE,SHFE
    python tushare_pg_ingest/ingest_options.py --dataset daily --date 20250529 --exchanges DCE,SHFE
    python tushare_pg_ingest/ingest_options.py --dataset daily --ts-codes M2509-C-3000.DCE --start-date 20250101 --end-date 20250529
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from common import (
    IngestStats,
    TushareClient,
    add_common_args,
    comma_list,
    configure_database,
    date_window,
    iter_yyyymmdd,
    print_stats,
    records_from_df,
)
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


OPTION_EXCHANGES = ["SSE", "SZSE", "CFFEX", "DCE", "SHFE", "CZCE"]

OPT_BASIC_FIELDS = ",".join(
    [
        "ts_code",
        "exchange",
        "name",
        "per_unit",
        "opt_code",
        "opt_type",
        "call_put",
        "exercise_type",
        "exercise_price",
        "s_month",
        "maturity_date",
        "list_price",
        "list_date",
        "delist_date",
        "last_edate",
        "last_ddate",
        "quote_unit",
        "min_price_chg",
    ]
)

OPT_DAILY_FIELDS = ",".join(
    [
        "ts_code",
        "trade_date",
        "exchange",
        "pre_settle",
        "pre_close",
        "open",
        "high",
        "low",
        "close",
        "settle",
        "vol",
        "amount",
        "oi",
    ]
)

metadata = MetaData()

opt_contracts = Table(
    "opt_contracts",
    metadata,
    Column("ts_code", String(40), primary_key=True),
    Column("exchange", String(10), index=True),
    Column("name", String(100)),
    Column("per_unit", String(50)),
    Column("opt_code", String(40), index=True),
    Column("opt_type", String(20)),
    Column("call_put", String(10), index=True),
    Column("exercise_type", String(20)),
    Column("exercise_price", Numeric(19, 4)),
    Column("s_month", String(10), index=True),
    Column("maturity_date", Date, index=True),
    Column("list_price", Numeric(19, 4)),
    Column("list_date", Date, index=True),
    Column("delist_date", Date, index=True),
    Column("last_edate", Date),
    Column("last_ddate", Date),
    Column("quote_unit", String(50)),
    Column("min_price_chg", String(30)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)

opt_daily_data = Table(
    "opt_daily_data",
    metadata,
    Column("ts_code", String(40), nullable=False, index=True),
    Column("trade_date", Date, nullable=False, index=True),
    Column("exchange", String(10), index=True),
    Column("pre_settle", Numeric(19, 4)),
    Column("pre_close", Numeric(19, 4)),
    Column("open_price", Numeric(19, 4)),
    Column("high_price", Numeric(19, 4)),
    Column("low_price", Numeric(19, 4)),
    Column("close_price", Numeric(19, 4)),
    Column("settle", Numeric(19, 4)),
    Column("vol", Numeric(19, 4)),
    Column("amount", Numeric(19, 4)),
    Column("oi", Numeric(19, 4)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    UniqueConstraint("ts_code", "trade_date", name="uix_opt_daily_data_ts_code_trade_date"),
)


def _dialect_insert(table: Table):
    """Return an insert builder with native upsert support for the active DB."""
    from models import engine

    if engine.dialect.name == "postgresql":
        return pg_insert(table)
    return sqlite_insert(table)


def _parse_date(value: Any):
    """Convert a YYYYMMDD-ish value into ``datetime.date``; keep blanks as None."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    return datetime.strptime(text, "%Y%m%d").date()


def _option_exchanges(value: str | None) -> list[str]:
    """Parse option exchanges, defaulting to the exchanges documented by Tushare."""
    return comma_list(value) or OPTION_EXCHANGES


def _map_opt_basic(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Map a Tushare opt_basic record into opt_contracts columns."""
    ts_code = raw.get("ts_code")
    if not ts_code:
        return None
    return {
        "ts_code": str(ts_code).upper(),
        "exchange": raw.get("exchange"),
        "name": raw.get("name"),
        "per_unit": raw.get("per_unit"),
        "opt_code": raw.get("opt_code"),
        "opt_type": raw.get("opt_type"),
        "call_put": raw.get("call_put"),
        "exercise_type": raw.get("exercise_type"),
        "exercise_price": raw.get("exercise_price"),
        "s_month": raw.get("s_month"),
        "maturity_date": _parse_date(raw.get("maturity_date")),
        "list_price": raw.get("list_price"),
        "list_date": _parse_date(raw.get("list_date")),
        "delist_date": _parse_date(raw.get("delist_date")),
        "last_edate": _parse_date(raw.get("last_edate")),
        "last_ddate": _parse_date(raw.get("last_ddate")),
        "quote_unit": raw.get("quote_unit"),
        "min_price_chg": None if raw.get("min_price_chg") is None else str(raw.get("min_price_chg")),
    }


def _map_opt_daily(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Map a Tushare opt_daily record into opt_daily_data columns."""
    ts_code = raw.get("ts_code")
    trade_date = raw.get("trade_date")
    if not ts_code or not trade_date:
        return None
    return {
        "ts_code": str(ts_code).upper(),
        "trade_date": _parse_date(trade_date),
        "exchange": raw.get("exchange"),
        "pre_settle": raw.get("pre_settle"),
        "pre_close": raw.get("pre_close"),
        "open_price": raw.get("open"),
        "high_price": raw.get("high"),
        "low_price": raw.get("low"),
        "close_price": raw.get("close"),
        "settle": raw.get("settle"),
        "vol": raw.get("vol"),
        "amount": raw.get("amount"),
        "oi": raw.get("oi"),
    }


def _upsert_contracts(db, rows: list[dict[str, Any]]) -> int:
    """Upsert opt_contracts rows in manageable batches."""
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), 1000):
        batch = rows[i : i + 1000]
        stmt = _dialect_insert(opt_contracts).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_code"],
            set_={
                "exchange": stmt.excluded.exchange,
                "name": stmt.excluded.name,
                "per_unit": stmt.excluded.per_unit,
                "opt_code": stmt.excluded.opt_code,
                "opt_type": stmt.excluded.opt_type,
                "call_put": stmt.excluded.call_put,
                "exercise_type": stmt.excluded.exercise_type,
                "exercise_price": stmt.excluded.exercise_price,
                "s_month": stmt.excluded.s_month,
                "maturity_date": stmt.excluded.maturity_date,
                "list_price": stmt.excluded.list_price,
                "list_date": stmt.excluded.list_date,
                "delist_date": stmt.excluded.delist_date,
                "last_edate": stmt.excluded.last_edate,
                "last_ddate": stmt.excluded.last_ddate,
                "quote_unit": stmt.excluded.quote_unit,
                "min_price_chg": stmt.excluded.min_price_chg,
                "updated_at": func.now(),
            },
        )
        result = db.execute(stmt)
        total += result.rowcount if hasattr(result, "rowcount") else len(batch)
    return total


def _upsert_daily(db, rows: list[dict[str, Any]]) -> int:
    """Upsert opt_daily_data rows in manageable batches."""
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), 1000):
        batch = rows[i : i + 1000]
        stmt = _dialect_insert(opt_daily_data).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_code", "trade_date"],
            set_={
                "exchange": stmt.excluded.exchange,
                "pre_settle": stmt.excluded.pre_settle,
                "pre_close": stmt.excluded.pre_close,
                "open_price": stmt.excluded.open_price,
                "high_price": stmt.excluded.high_price,
                "low_price": stmt.excluded.low_price,
                "close_price": stmt.excluded.close_price,
                "settle": stmt.excluded.settle,
                "vol": stmt.excluded.vol,
                "amount": stmt.excluded.amount,
                "oi": stmt.excluded.oi,
                "updated_at": func.now(),
            },
        )
        result = db.execute(stmt)
        total += result.rowcount if hasattr(result, "rowcount") else len(batch)
    return total


def _prepare_tables(dry_run: bool, no_create_tables: bool) -> None:
    """Create option tables unless the run is read-only or creation is disabled."""
    if dry_run or no_create_tables:
        return
    from models import engine

    metadata.create_all(bind=engine, tables=[opt_contracts, opt_daily_data])


def ingest_basic(client: TushareClient, db, args: argparse.Namespace) -> IngestStats:
    """Fetch and upsert Tushare opt_basic data."""
    stats = IngestStats()
    ts_codes = comma_list(args.ts_codes)

    query_params: list[dict[str, Any]] = []
    if ts_codes:
        query_params = [{"ts_code": ts_code} for ts_code in ts_codes]
    else:
        for exchange in _option_exchanges(args.exchanges):
            query_params.append(
                {
                    "exchange": exchange,
                    "list_date": args.list_date,
                    "opt_code": args.opt_code,
                    "call_put": args.call_put,
                }
            )

    for params in query_params:
        label = params.get("ts_code") or params.get("exchange") or "opt_basic"
        try:
            df = client.query("opt_basic", fields=OPT_BASIC_FIELDS, **params)
        except Exception as e:
            print(f"[FAIL] opt_basic {label}: {e}")
            stats.failed += 1
            continue

        raw_rows = records_from_df(df)
        stats.fetched += len(raw_rows)
        rows = [row for row in (_map_opt_basic(raw) for raw in raw_rows) if row]
        stats.skipped += len(raw_rows) - len(rows)

        if args.dry_run:
            print(f"[DRY] opt_basic {label}: fetched={len(raw_rows)} mapped={len(rows)}")
            continue

        written = _upsert_contracts(db, rows)
        db.commit()
        stats.written += written
        print(f"[OK] opt_basic {label}: fetched={len(raw_rows)} upserted={written}")

    return stats


def ingest_daily(client: TushareClient, db, args: argparse.Namespace) -> IngestStats:
    """Fetch and upsert Tushare opt_daily data."""
    stats = IngestStats()
    ts_codes = comma_list(args.ts_codes)
    start_date, end_date = date_window(args)

    query_params: list[dict[str, Any]] = []
    if ts_codes:
        for ts_code in ts_codes:
            query_params.append({"ts_code": ts_code, "start_date": start_date, "end_date": end_date})
    else:
        for trade_date in iter_yyyymmdd(start_date, end_date):
            for exchange in _option_exchanges(args.exchanges):
                query_params.append({"trade_date": trade_date, "exchange": exchange})

    for params in query_params:
        label = params.get("ts_code") or f"{params.get('trade_date')} {params.get('exchange')}"
        try:
            df = client.query("opt_daily", fields=OPT_DAILY_FIELDS, **params)
        except Exception as e:
            print(f"[FAIL] opt_daily {label}: {e}")
            stats.failed += 1
            continue

        raw_rows = records_from_df(df)
        stats.fetched += len(raw_rows)
        rows = [row for row in (_map_opt_daily(raw) for raw in raw_rows) if row]
        stats.skipped += len(raw_rows) - len(rows)

        if args.dry_run:
            print(f"[DRY] opt_daily {label}: fetched={len(raw_rows)} mapped={len(rows)}")
            continue

        written = _upsert_daily(db, rows)
        db.commit()
        stats.written += written
        print(f"[OK] opt_daily {label}: fetched={len(raw_rows)} upserted={written}")

    return stats


def ingest(args: argparse.Namespace) -> IngestStats:
    """Run the selected option ingestion workflow."""
    if args.dataset in ("daily", "all") and not args.trade_date and not (args.start_date and args.end_date):
        raise ValueError("Daily option ingestion requires --date or both --start-date and --end-date")

    configure_database(args.allow_sqlite)
    _prepare_tables(args.dry_run, args.no_create_tables)

    from models import SessionLocal

    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    db = SessionLocal()
    try:
        if args.dataset in ("basic", "all"):
            stats.add(ingest_basic(client, db, args))
        if args.dataset in ("daily", "all"):
            stats.add(ingest_daily(client, db, args))
    finally:
        db.close()
    return stats


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for this script."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument("--dataset", choices=["basic", "daily", "all"], default="all")
    parser.add_argument(
        "--exchanges",
        help=f"Comma-separated option exchanges; default: {','.join(OPTION_EXCHANGES)}",
    )
    parser.add_argument("--ts-codes", help="Comma-separated option TS codes, e.g. M2509-C-3000.DCE")
    parser.add_argument("--list-date", help="opt_basic filter: listed on YYYYMMDD")
    parser.add_argument("--opt-code", help="opt_basic filter: underlying/standard contract code")
    parser.add_argument("--call-put", help="opt_basic filter: call/put value as defined by Tushare")
    parser.add_argument("--no-create-tables", action="store_true", help="Do not auto-create option tables")
    return parser


def main() -> int:
    """Entry point."""
    stats = ingest(build_parser().parse_args())
    print_stats("options", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
