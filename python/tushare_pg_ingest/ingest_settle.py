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


def _ingest_one_date_exchange(
    client: TushareClient,
    db,
    trade_date: str,
    exchange: str,
    *,
    dry_run: bool,
) -> tuple[int, int, int] | None:
    """Fetch and upsert ``fut_settle`` for a single (date, exchange) pair.

    Returns:
        A tuple of (fetched, skipped, written) counters.  Raises on API failure
        so the caller can decide whether to retry.
    """
    from data_collector.adapters import map_tushare_fut_settle
    from data_collector.upsert import upsert_fut_settle_bulk

    df = client.query("fut_settle", trade_date=trade_date, exchange=exchange)
    raw_rows = records_from_df(df)
    rows = [map_tushare_fut_settle(row) for row in raw_rows]
    rows = [row for row in rows if row.get("ts_code") and row.get("trade_date")]
    # FIX #1: inject exchange because Tushare response omits it
    for row in rows:
        row["exchange"] = exchange

    fetched = len(raw_rows)
    skipped = len(raw_rows) - len(rows)
    if dry_run:
        print(f"[DRY] {trade_date} {exchange}: fetched={fetched} mapped={len(rows)}")
        return fetched, skipped, 0

    if not raw_rows:
        print(f"[WARN] {trade_date} {exchange}: 0 rows (Tushare coverage may be limited)")
    else:
        print(f"[OK] {trade_date} {exchange}: fetched={fetched}")
    written = upsert_fut_settle_bulk(db, rows)
    db.commit()
    return fetched, skipped, written


def ingest(args: argparse.Namespace) -> IngestStats:
    """Run the ``fut_settle`` ingestion workflow.

    Supports two modes:

    *Mode A* (``--ts-code``):
        Query by individual contract codes.  Date and exchange arguments are
        ignored because Tushare returns all available history for the code.

    *Mode B* (default):
        Iterate every calendar day in the requested window (skipping weekends)
        and query per exchange.  A single (date, exchange) failure is logged
        and skipped instead of aborting the whole batch; failed items are
        retried once at the end.

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
                # Mode A does not know exchange; leave as None.
                rows = [map_tushare_fut_settle(row) for row in raw_rows]
                rows = [row for row in rows if row.get("ts_code") and row.get("trade_date")]
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
        failures: list[tuple[str, str, Exception]] = []
        tasks = [
            (trade_date, exchange)
            for trade_date in iter_yyyymmdd(start_date, end_date)
            if not _is_weekend(trade_date)
            for exchange in exchanges
        ]

        for trade_date, exchange in tasks:
            try:
                fetched, skipped, written = _ingest_one_date_exchange(
                    client, db, trade_date, exchange, dry_run=args.dry_run
                )
                stats.fetched += fetched
                stats.skipped += skipped
                stats.written += written
            except Exception as e:
                stats.failed += 1
                failures.append((trade_date, exchange, e))
                print(f"[FAIL] {trade_date} {exchange}: {e}")

        # Retry failed tasks once more before giving up.  Network hiccups
        # (e.g. chunked encoding dropped) often succeed on a second pass.
        if failures:
            print(f"\n[RETRY] {len(failures)} failed task(s) will be retried once...\n")
            still_failed: list[tuple[str, str, Exception]] = []
            for trade_date, exchange, _ in failures:
                try:
                    fetched, skipped, written = _ingest_one_date_exchange(
                        client, db, trade_date, exchange, dry_run=args.dry_run
                    )
                    stats.fetched += fetched
                    stats.skipped += skipped
                    stats.written += written
                    stats.failed = max(0, stats.failed - 1)
                    print(f"[RECOVERED] {trade_date} {exchange}")
                except Exception as e:
                    still_failed.append((trade_date, exchange, e))
                    print(f"[STILL FAIL] {trade_date} {exchange}: {e}")
            failures = still_failed

        if failures:
            print(f"\n[SUMMARY] {len(failures)} task(s) still failed after retry:")
            for trade_date, exchange, e in failures:
                print(f"  - {trade_date} {exchange}: {e}")
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
