"""Ingest Tushare fut_basic rows into fut_contracts table.

This script pulls all futures contract metadata from Tushare and persists it
to PostgreSQL/SQLite. Other ingest scripts (e.g. ingest_daily.py) then read
from this table to discover which concrete contracts to poll for market data.
"""

from __future__ import annotations

import argparse

from common import (
    IngestStats,
    TushareClient,
    comma_list,
    configure_database,
    print_stats,
    records_from_df,
)

# Tushare 支持的全部国内期货交易所
DEFAULT_EXCHANGES = ["SHFE", "DCE", "CZCE", "INE", "CFFEX", "GFEX"]


def ingest(args: argparse.Namespace) -> IngestStats:
    configure_database(args.allow_sqlite)

    from data_collector.adapters import map_tushare_fut_contract
    from data_collector.upsert import upsert_fut_contract_bulk
    from models import SessionLocal

    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    db = SessionLocal()

    exchanges = comma_list(args.exchanges) or DEFAULT_EXCHANGES
    try:
        for exchange in exchanges:
            kwargs = {"exchange": exchange}
            if args.fut_type:
                kwargs["fut_type"] = args.fut_type
            if args.list_date:
                kwargs["list_date"] = args.list_date

            df = client.query("fut_basic", **kwargs)
            raw_rows = records_from_df(df)
            stats.fetched += len(raw_rows)

            rows = [map_tushare_fut_contract(raw) for raw in raw_rows]
            rows = [row for row in rows if row.get("ts_code")]
            stats.skipped += len(raw_rows) - len(rows)

            if args.dry_run:
                print(f"[DRY] {exchange}: fetched={len(raw_rows)} mapped={len(rows)}")
                continue

            written = upsert_fut_contract_bulk(db, rows)
            db.commit()
            stats.written += written
            print(f"[OK] {exchange}: fetched={len(raw_rows)} upserted={written}")
    finally:
        db.close()

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exchanges",
        help=f"Comma-separated exchanges; default all domestic futures exchanges: {','.join(DEFAULT_EXCHANGES)}",
    )
    parser.add_argument("--fut-type", help="1=normal contracts, 2=main/continuous contracts; default all")
    parser.add_argument("--list-date", help="Only contracts listed since YYYYMMDD")
    parser.add_argument("--allow-sqlite", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and map data, but do not write rows")
    parser.add_argument("--min-interval", type=float, default=0.55, help="Seconds between Tushare calls")
    return parser


def main() -> int:
    stats = ingest(build_parser().parse_args())
    print_stats("fut_basic -> fut_contracts", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
