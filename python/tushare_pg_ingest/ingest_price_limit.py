"""Ingest Tushare ft_limit rows into fut_price_limits."""

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
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument("--symbols", help="Optional comma-separated product codes, e.g. AU,CU")
    return parser


def main() -> int:
    stats = ingest(build_parser().parse_args())
    print_stats("fut_price_limits", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

