"""Ingest Tushare fut_weekly_detail rows into fut_weekly_detail."""

from __future__ import annotations

import argparse
from datetime import datetime

from common import IngestStats, TushareClient, add_common_args, configure_database, print_stats, records_from_df


def _date_to_week(value: str) -> str:
    if len(value) == 6:
        return value
    dt = datetime.strptime(value, "%Y%m%d")
    year, week, _ = dt.isocalendar()
    return f"{year}{week:02d}"


def ingest(args: argparse.Namespace) -> IngestStats:
    configure_database(args.allow_sqlite)

    from data_collector.adapters import map_tushare_fut_weekly_detail
    from data_collector.upsert import upsert_fut_weekly_detail_bulk
    from models import SessionLocal

    start_week = _date_to_week(args.start_date) if args.start_date else None
    end_week = _date_to_week(args.end_date) if args.end_date else None
    if args.trade_date:
        start_week = end_week = _date_to_week(args.trade_date)
    if not start_week or not end_week:
        raise ValueError("Provide --date or both --start-date and --end-date")

    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    db = SessionLocal()
    try:
        df = client.query("fut_weekly_detail", start_week=start_week, end_week=end_week)
        raw_rows = records_from_df(df)
        rows = [map_tushare_fut_weekly_detail(row) for row in raw_rows]
        rows = [row for row in rows if row.get("week") and row.get("prd") and row.get("exchange")]
        stats.fetched = len(raw_rows)
        stats.skipped = len(raw_rows) - len(rows)
        if args.dry_run:
            print(f"[DRY] weeks {start_week}-{end_week}: fetched={len(raw_rows)} mapped={len(rows)}")
        else:
            stats.written = upsert_fut_weekly_detail_bulk(db, rows)
            db.commit()
            print(f"[OK] weeks {start_week}-{end_week}: fetched={len(raw_rows)}")
    finally:
        db.close()
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    return parser


def main() -> int:
    stats = ingest(build_parser().parse_args())
    print_stats("fut_weekly_detail", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

