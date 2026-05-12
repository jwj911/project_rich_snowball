"""Check for duplicate rows in fut_daily_data.

The table has a unique constraint on (variety_id, period, trade_date).
If upsert is working correctly there should be zero duplicates.
"""

from __future__ import annotations

import argparse

from sqlalchemy import func

from common import configure_database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-sqlite", action="store_true")
    parser.add_argument("--limit", type=int, default=20, help="Max duplicate groups to display")
    args = parser.parse_args()

    configure_database(args.allow_sqlite)

    from models import SessionLocal, FutDailyDataDB

    db = SessionLocal()
    try:
        dupes = (
            db.query(
                FutDailyDataDB.variety_id,
                FutDailyDataDB.period,
                FutDailyDataDB.trade_date,
                FutDailyDataDB.ts_code,
                func.count(FutDailyDataDB.id).label("cnt"),
            )
            .group_by(
                FutDailyDataDB.variety_id,
                FutDailyDataDB.period,
                FutDailyDataDB.trade_date,
                FutDailyDataDB.ts_code,
            )
            .having(func.count(FutDailyDataDB.id) > 1)
            .order_by(func.count(FutDailyDataDB.id).desc())
            .limit(args.limit)
            .all()
        )

        total_dedup = (
            db.query(
                func.sum(func.count(FutDailyDataDB.id) - 1).label("extra_rows")
            )
            .group_by(
                FutDailyDataDB.variety_id,
                FutDailyDataDB.period,
                FutDailyDataDB.trade_date,
            )
            .having(func.count(FutDailyDataDB.id) > 1)
            .scalar()
        )

        if not dupes:
            print("✅ No duplicates found. The unique constraint is working correctly.")
            return 0

        print(f"⚠️  Found {len(dupes)} duplicate group(s), ~{total_dedup or 0} extra row(s).\n")
        print(f"  {'variety_id':>10}  {'period':>6}  {'trade_date':>12}  {'ts_code':>15}  {'count':>5}")
        print(f"  {'-'*10}  {'-'*6}  {'-'*12}  {'-'*15}  {'-'*5}")
        for vid, period, tdate, ts_code, cnt in dupes:
            print(f"  {vid:>10}  {period:>6}  {str(tdate):>12}  {ts_code:>15}  {cnt:>5}")

    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
