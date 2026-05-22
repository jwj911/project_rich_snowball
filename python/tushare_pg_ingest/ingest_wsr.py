"""Ingest Tushare fut_wsr warehouse receipt rows into fut_wsr.

Purpose:
    Backfills daily warehouse-receipt (inventory) data for futures commodities
    from Tushare's ``fut_wsr`` interface into the ``fut_wsr`` table.

Tushare API used:
    ``fut_wsr`` - daily warehouse receipt summary by product and exchange.

Target database table:
    ``fut_wsr`` (``FutWsrDB`` model).

Key CLI arguments:
    --start-date YYYYMMDD
    --end-date   YYYYMMDD
    --date       YYYYMMDD
    --symbols    COMMA_LIST  e.g. AU,CU (optional; default queries all symbols)
    --allow-sqlite
    --dry-run
    --min-interval SECONDS

Usage examples:
    python ingest_wsr.py --date 20250507
    python ingest_wsr.py --start-date 20250501 --end-date 20250507 --symbols AU,CU

Known limitations:
    - Tushare ``fut_wsr`` coverage varies by exchange and product; some
      dates return zero rows even for active commodities.
    - The ``symbol`` parameter accepts product codes, not full ``ts_code``.
"""

from __future__ import annotations

import argparse

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


def ingest(args: argparse.Namespace) -> IngestStats:
    """Run the ``fut_wsr`` ingestion workflow.

    Iterates every calendar day in the requested window.  For each day,
    queries either the specific symbols provided or a single unfiltered call
    (``symbol=None``) to fetch all available products.

    Args:
        args: Parsed namespace from ``build_parser()``.

    Returns:
        ``IngestStats`` summarising fetched, written, and skipped rows.
    """
    configure_database(args.allow_sqlite)

    from data_collector.adapters import map_tushare_fut_wsr
    from data_collector.upsert import upsert_fut_wsr_bulk
    from models import SessionLocal

    start_date, end_date = date_window(args)
    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    symbols = comma_list(args.symbols)
    db = SessionLocal()
    try:
        for trade_date in iter_yyyymmdd(start_date, end_date):
            # When no symbols are given, perform one unfiltered query per day.
            query_symbols = symbols or [None]
            for symbol in query_symbols:
                df = client.query("fut_wsr", trade_date=trade_date, symbol=symbol)
                raw_rows = records_from_df(df)
                rows = [map_tushare_fut_wsr(row) for row in raw_rows]
                # Enforce presence of the three natural-key fields.
                rows = [row for row in rows if row.get("trade_date") and row.get("symbol") and row.get("warehouse")]
                stats.fetched += len(raw_rows)
                stats.skipped += len(raw_rows) - len(rows)
                if args.dry_run:
                    print(f"[DRY] {trade_date} {symbol or 'ALL'}: fetched={len(raw_rows)} mapped={len(rows)}")
                    continue
                stats.written += upsert_fut_wsr_bulk(db, rows)
                db.commit()
                print(f"[OK] {trade_date} {symbol or 'ALL'}: fetched={len(raw_rows)}")
    finally:
        db.close()
    return stats


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for this script."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument("--symbols", help="Optional comma-separated product codes, e.g. AU,CU")
    return parser


def main() -> int:
    """Entry point."""
    stats = ingest(build_parser().parse_args())
    print_stats("fut_wsr", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
