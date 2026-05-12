"""Update varieties.contract_code from Tushare fut_mapping."""

from __future__ import annotations

import argparse

from common import IngestStats, TushareClient, add_common_args, configure_database, date_window, print_stats, records_from_df


def ingest(args: argparse.Namespace) -> IngestStats:
    configure_database(args.allow_sqlite)

    from data_collector.adapters import map_tushare_fut_mapping
    from models import SessionLocal, VarietyDB

    start_date, end_date = date_window(args)
    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    db = SessionLocal()
    try:
        df = client.query("fut_mapping", start_date=start_date, end_date=end_date)
        raw_rows = records_from_df(df)
        stats.fetched += len(raw_rows)
        for row in (map_tushare_fut_mapping(raw) for raw in raw_rows):
            ts_code = row.get("ts_code")
            mapping_ts_code = row.get("mapping_ts_code")
            if not ts_code or not mapping_ts_code:
                stats.skipped += 1
                continue
            symbol = ts_code.split(".", 1)[0].upper()
            contract_code = mapping_ts_code.split(".", 1)[0].upper()
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
            if not variety:
                stats.skipped += 1
                continue
            if variety.contract_code != contract_code:
                variety.contract_code = contract_code
                stats.written += 1
        if args.dry_run:
            db.rollback()
            print(f"[DRY] {start_date}-{end_date}: fetched={len(raw_rows)} mapped={stats.written}")
        else:
            db.commit()
            print(f"[OK] {start_date}-{end_date}: fetched={len(raw_rows)} updated={stats.written}")
    finally:
        db.close()
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    return parser


def main() -> int:
    stats = ingest(build_parser().parse_args())
    print_stats("fut_mapping -> varieties", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

