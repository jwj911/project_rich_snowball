"""Ingest Tushare fut_settle rows into the fut_settle table.

Purpose:
    Backfills futures settlement-parameter data (trading margin, settlement
    price, delivery month, etc.) from Tushare's ``fut_settle`` interface.

Tushare API used:
    ``fut_settle`` - daily settlement parameters per contract.

Target database table:
    ``fut_settle`` (``FutSettleDB`` model).

Key CLI arguments:
    --date       YYYYMMDD   Single trade date
    --start-date YYYYMMDD
    --end-date   YYYYMMDD
    --exchanges  COMMA_LIST Default: SHFE,DCE,CZCE,INE,CFFEX,GFEX
    --ts-code    COMMA_LIST Query by contract code (ignores date/exchange)
    --allow-sqlite
    --dry-run
    --min-interval SECONDS

Usage examples:
    python ingest_settle.py --date 20250507
    python ingest_settle.py --start-date 20250501 --end-date 20250507
    python ingest_settle.py --date 20250507 --dry-run

Fixes applied:
    1. Default to ALL exchanges so you only need to specify --date.
    2. Inject exchange into rows because Tushare response does NOT include
       the 'exchange' column even when exchange=XXX is passed.
    3. Skip weekends when iterating dates to avoid wasted API calls.
    4. Add --ts-code support for querying historical settle data by contract.
    5. Log zero-row exchanges so users know data coverage is limited.

Known limitation:
    - Tushare ``fut_settle`` currently returns data mainly for SHFE and INE;
      DCE/CZCE/CFFEX/GFEX often return empty results.
    - ``offset_today_fee`` is documented but not present in actual responses.
"""

from __future__ import annotations

import argparse
from datetime import datetime

from common import (
    IngestStats,
    TushareClient,
    add_common_args,
    comma_list,
    configure_database,
    date_window,
    iter_yyyymmdd,
    parse_exchanges,
    print_stats,
    records_from_df,
)


def _is_weekend(date_str: str) -> bool:
    """Return ``True`` if *date_str* (``YYYYMMDD``) falls on Saturday or Sunday."""
    return datetime.strptime(date_str, "%Y%m%d").weekday() >= 5


def ingest(args: argparse.Namespace) -> IngestStats:
    """Run the ``fut_settle`` ingestion workflow.

    Supports two modes:

    *Mode A* (``--ts-code``):
        Query by individual contract codes.  Date and exchange arguments are
        ignored because Tushare returns all available history for the code.

    *Mode B* (default):
        Iterate every calendar day in the requested window (skipping weekends)
        and query per exchange.

    Args:
        args: Parsed namespace from ``build_parser()``.

    Returns:
        ``IngestStats`` summarising fetched, written, and skipped rows.
    """
    configure_database(args.allow_sqlite)

    from data_collector.adapters import map_tushare_fut_settle
    from data_collector.upsert import upsert_fut_settle_bulk
    from models import SessionLocal

    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    db = SessionLocal()
    try:
        # ------------------------------------------------------------------
        # Mode A: query by ts_code (ignores date/exchange)
        # ------------------------------------------------------------------
        ts_codes = comma_list(args.ts_code)
        if ts_codes:
            for ts_code in ts_codes:
                print(f"[FETCH] ts_code={ts_code} ...", end=" ")
                df = client.query("fut_settle", ts_code=ts_code)
                raw_rows = records_from_df(df)
                rows = [map_tushare_fut_settle(row) for row in raw_rows]
                rows = [row for row in rows if row.get("ts_code") and row.get("trade_date")]
                # ts_code mode does not know exchange; leave as None
                stats.fetched += len(raw_rows)
                stats.skipped += len(raw_rows) - len(rows)
                if args.dry_run:
                    print(f"DRY fetched={len(raw_rows)} mapped={len(rows)}")
                    continue
                stats.written += upsert_fut_settle_bulk(db, rows)
                db.commit()
                print(f"written={len(rows)}")
            return stats

        # ------------------------------------------------------------------
        # Mode B: query by trade_date + exchange (default)
        # ------------------------------------------------------------------
        start_date, end_date = date_window(args)
        exchanges = parse_exchanges(args.exchanges)
        for trade_date in iter_yyyymmdd(start_date, end_date):
            if _is_weekend(trade_date):
                continue
            for exchange in exchanges:
                df = client.query("fut_settle", trade_date=trade_date, exchange=exchange)
                raw_rows = records_from_df(df)
                rows = [map_tushare_fut_settle(row) for row in raw_rows]
                rows = [row for row in rows if row.get("ts_code") and row.get("trade_date")]
                # FIX #1: inject exchange because Tushare response omits it
                for row in rows:
                    row["exchange"] = exchange
                stats.fetched += len(raw_rows)
                stats.skipped += len(raw_rows) - len(rows)
                if args.dry_run:
                    print(f"[DRY] {trade_date} {exchange}: fetched={len(raw_rows)} mapped={len(rows)}")
                    continue
                if not raw_rows:
                    # Warn once per exchange so user knows coverage is limited
                    print(f"[WARN] {trade_date} {exchange}: 0 rows (Tushare coverage may be limited)")
                else:
                    print(f"[OK] {trade_date} {exchange}: fetched={len(raw_rows)}")
                stats.written += upsert_fut_settle_bulk(db, rows)
                db.commit()
    finally:
        db.close()
    return stats


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for this script."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(parser)
    parser.add_argument(
        "--exchanges",
        default="SHFE,DCE,CZCE,INE,CFFEX,GFEX",
        help="Comma-separated exchanges (default: SHFE,DCE,CZCE,INE,CFFEX,GFEX)",
    )
    parser.add_argument("--ts-code", help="Comma-separated contract codes, e.g. AU2506.SHF,CU2506.SHF. When set, ignores --date/--start-date/--end-date/--exchanges.")
    return parser


def main() -> int:
    """Entry point."""
    stats = ingest(build_parser().parse_args())
    print_stats("fut_settle", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
