"""Ingest Tushare fut_holding broker ranking rows into fut_holding."""

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
    parse_exchanges,
    print_stats,
    records_from_df,
)


def ingest(args: argparse.Namespace) -> IngestStats:
    configure_database(args.allow_sqlite)

    from data_collector.adapters import map_tushare_fut_holding
    from data_collector.upsert import upsert_fut_holding_bulk
    from models import SessionLocal

    start_date, end_date = date_window(args)
    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    symbols = comma_list(args.symbols)
    exchanges = parse_exchanges(args.exchanges)
    db = SessionLocal()
    try:
        for trade_date in iter_yyyymmdd(start_date, end_date):
            query_symbols = symbols or [None]
            for exchange in exchanges:
                for symbol in query_symbols:
                    df = client.query("fut_holding", trade_date=trade_date, symbol=symbol, exchange=exchange)
                    raw_rows = records_from_df(df)
                    rows = [map_tushare_fut_holding(row) for row in raw_rows]
                    rows = [row for row in rows if row.get("trade_date") and row.get("symbol") and row.get("broker")]
                    stats.fetched += len(raw_rows)
                    stats.skipped += len(raw_rows) - len(rows)
                    if args.dry_run:
                        print(f"[DRY] {trade_date} {exchange} {symbol or 'ALL'}: fetched={len(raw_rows)} mapped={len(rows)}")
                        continue
                    stats.written += upsert_fut_holding_bulk(db, rows)
                    db.commit()
                    print(f"[OK] {trade_date} {exchange} {symbol or 'ALL'}: fetched={len(raw_rows)}")
    finally:
        db.close()
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument("--symbols", help="Optional comma-separated product codes, e.g. AU,CU")
    parser.add_argument("--exchanges", help="Comma-separated exchanges; default all domestic futures exchanges")
    return parser


def main() -> int:
    stats = ingest(build_parser().parse_args())
    print_stats("fut_holding", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

