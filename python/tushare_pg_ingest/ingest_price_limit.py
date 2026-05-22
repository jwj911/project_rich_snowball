"""Ingest Tushare ft_limit rows into fut_price_limits.

Purpose:
    Backfills daily price-limit (涨跌停板) data for futures contracts from
    Tushare's ``ft_limit`` interface into the ``fut_price_limits`` table.

Tushare API used:
    ``ft_limit`` - daily upper / lower price limits by contract.

Target database table:
    ``fut_price_limits`` (``FutPriceLimitDB`` model).

Key CLI arguments:
    --start-date YYYYMMDD
    --end-date   YYYYMMDD
    --date       YYYYMMDD
    --symbols    COMMA_LIST  e.g. AU,CU (optional; mapped to ``cont`` param)
    --allow-sqlite
    --dry-run
    --min-interval SECONDS

Usage examples:
    python ingest_price_limit.py --date 20250507
    python ingest_price_limit.py --start-date 20250501 --end-date 20250507 --symbols AU,CU

Known limitations:
    - Tushare ``ft_limit`` uses ``cont`` (品种代码) rather than a full
      ``ts_code``; the script maps the user's ``--symbols`` accordingly.
    - Some exchanges or products may not have limit data available for every
      trading day.
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
    """Run the ``ft_limit`` ingestion workflow.

    Iterates every calendar day in the requested window.  For each day,
    queries either the specific symbols provided (mapped to ``cont``) or a
    single unfiltered call.

    Args:
        args: Parsed namespace from ``build_parser()``.

    Returns:
        ``IngestStats`` summarising fetched, written, and skipped rows.
    """
    configure_database(args.allow_sqlite)

    from data_collector.adapters import map_tushare_ft_limit
    from data_collector.upsert import upsert_fut_price_limit_bulk
    from models import SessionLocal

    start_date, end_date = date_window(args)
    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    symbols = comma_list(args.symbols)
    db = SessionLocal()
    try:
        for trade_date in iter_yyyymmdd(start_date, end_date):
            query_symbols = symbols or [None]
            for symbol in query_symbols:
                # Tushare ft_limit uses 'cont' for product code filter.
                df = client.query("ft_limit", trade_date=trade_date, cont=symbol)
                raw_rows = records_from_df(df)
                rows = [map_tushare_ft_limit(row) for row in raw_rows]
                rows = [row for row in rows if row.get("ts_code") and row.get("trade_date")]
                stats.fetched += len(raw_rows)
                stats.skipped += len(raw_rows) - len(rows)
                if args.dry_run:
                    print(f"[DRY] {trade_date} {symbol or 'ALL'}: fetched={len(raw_rows)} mapped={len(rows)}")
                    continue
                stats.written += upsert_fut_price_limit_bulk(db, rows)
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
    print_stats("fut_price_limits", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
