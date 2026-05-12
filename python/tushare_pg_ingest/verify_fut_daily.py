"""Verify futures daily data quality and optionally cross-check against Tushare API.

Dimensions checked:
1. Basic stats: row count, variety coverage, date range
2. OHLC consistency: open <= high >= low, close within [low, high]
3. Zero / negative price detection
4. Per-variety row count distribution
5. Date continuity: flag varieties with unexpectedly low record counts
6. (Optional) Tushare API spot-check: randomly sample N rows and compare values
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta

from sqlalchemy import func

from common import configure_database, TushareClient, records_from_df

# Eager import so that verification functions can reference them
from models import SessionLocal, FutDailyDataDB, VarietyDB


def _fmt_date(dt) -> str:
    return dt.strftime("%Y%m%d") if dt else "None"


def verify_basic(db) -> dict:
    """1. Basic statistics."""
    print("\n=== 1. Basic Statistics ===")
    total = db.query(FutDailyDataDB).count()
    variety_cnt = db.query(func.count(func.distinct(FutDailyDataDB.variety_id))).scalar()
    min_dt, max_dt = db.query(
        func.min(FutDailyDataDB.trade_date),
        func.max(FutDailyDataDB.trade_date),
    ).first()
    period_dist = (
        db.query(FutDailyDataDB.period, func.count(FutDailyDataDB.id))
        .group_by(FutDailyDataDB.period)
        .all()
    )

    print(f"  Total rows         : {total}")
    print(f"  Unique varieties   : {variety_cnt}")
    print(f"  Date range         : {min_dt} ~ {max_dt}")
    print(f"  Period distribution: {dict(period_dist)}")
    return {"total": total, "varieties": variety_cnt, "min_date": min_dt, "max_date": max_dt}


def verify_ohlc(db) -> int:
    """2. OHLC consistency check."""
    print("\n=== 2. OHLC Consistency ===")
    invalid = (
        db.query(FutDailyDataDB)
        .filter(
            (FutDailyDataDB.open_price > FutDailyDataDB.high_price)
            | (FutDailyDataDB.low_price > FutDailyDataDB.high_price)
            | (FutDailyDataDB.close_price > FutDailyDataDB.high_price)
            | (FutDailyDataDB.open_price < FutDailyDataDB.low_price)
            | (FutDailyDataDB.close_price < FutDailyDataDB.low_price)
        )
        .count()
    )
    print(f"  Invalid OHLC rows  : {invalid}")
    if invalid:
        samples = (
            db.query(FutDailyDataDB)
            .filter(
                (FutDailyDataDB.open_price > FutDailyDataDB.high_price)
                | (FutDailyDataDB.low_price > FutDailyDataDB.high_price)
                | (FutDailyDataDB.close_price > FutDailyDataDB.high_price)
                | (FutDailyDataDB.open_price < FutDailyDataDB.low_price)
                | (FutDailyDataDB.close_price < FutDailyDataDB.low_price)
            )
            .limit(5)
            .all()
        )
        for s in samples:
            print(
                f"    {s.ts_code} {_fmt_date(s.trade_date)}: "
                f"O={s.open_price} H={s.high_price} L={s.low_price} C={s.close_price}"
            )
    return invalid


def verify_zeros(db) -> int:
    """3. Zero / negative price detection."""
    print("\n=== 3. Zero / Negative Prices ===")
    zero_rows = (
        db.query(FutDailyDataDB)
        .filter(
            (FutDailyDataDB.open_price == 0)
            | (FutDailyDataDB.high_price == 0)
            | (FutDailyDataDB.low_price == 0)
            | (FutDailyDataDB.close_price == 0)
            | (FutDailyDataDB.open_price < 0)
            | (FutDailyDataDB.high_price < 0)
            | (FutDailyDataDB.low_price < 0)
            | (FutDailyDataDB.close_price < 0)
        )
        .count()
    )
    print(f"  Rows with zero/negative price: {zero_rows}")
    return zero_rows


def verify_per_variety(db, expected_days: int) -> list:
    """4. Per-variety row count and coverage."""
    print("\n=== 4. Per-Variety Coverage ===")
    rows = (
        db.query(
            VarietyDB.symbol,
            VarietyDB.exchange,
            func.count(FutDailyDataDB.id).label("cnt"),
            func.min(FutDailyDataDB.trade_date).label("first"),
            func.max(FutDailyDataDB.trade_date).label("last"),
        )
        .join(FutDailyDataDB, FutDailyDataDB.variety_id == VarietyDB.id)
        .group_by(VarietyDB.id)
        .order_by(func.count(FutDailyDataDB.id).desc())
        .all()
    )

    print(f"  {'Symbol':<8} {'Exch':<6} {'Count':>8} {'First':>12} {'Last':>12}")
    print(f"  {'-'*8} {'-'*6} {'-'*8} {'-'*12} {'-'*12}")
    underrepresented = []
    for symbol, exchange, cnt, first, last in rows:
        marker = ""
        if cnt < expected_days * 0.5:
            marker = " <-- LOW"
            underrepresented.append((symbol, exchange, cnt))
        print(
            f"  {symbol:<8} {exchange:<6} {cnt:>8} {_fmt_date(first):>12} {_fmt_date(last):>12}{marker}"
        )

    if underrepresented:
        print(f"\n  Warning: {len(underrepresented)} varieties have <50% of expected rows.")
    else:
        print(f"\n  All {len(rows)} varieties look healthy.")
    return underrepresented


def verify_tushare_spotcheck(db, client: TushareClient, sample_size: int = 5):
    """6. Randomly sample rows and compare with live Tushare API."""
    if sample_size <= 0 or not client:
        return

    print(f"\n=== 6. Tushare API Spot-Check ({sample_size} samples) ===")
    total = db.query(FutDailyDataDB).count()
    if total == 0:
        print("  No data to sample.")
        return

    # Pick random offsets
    offsets = random.sample(range(total), min(sample_size, total))
    mismatches = 0
    for offset in offsets:
        row = db.query(FutDailyDataDB).offset(offset).first()
        if not row or not row.ts_code or not row.trade_date:
            continue

        trade_date = row.trade_date.strftime("%Y%m%d")
        df = client.query("fut_daily", ts_code=row.ts_code, start_date=trade_date, end_date=trade_date)
        raw_rows = records_from_df(df)
        if not raw_rows:
            print(f"  [WARN] {row.ts_code} {trade_date}: Tushare returned empty")
            mismatches += 1
            continue

        api = raw_rows[0]
        db_o = float(row.open_price or 0)
        db_h = float(row.high_price or 0)
        db_l = float(row.low_price or 0)
        db_c = float(row.close_price or 0)
        api_o = float(api.get("open") or 0)
        api_h = float(api.get("high") or 0)
        api_l = float(api.get("low") or 0)
        api_c = float(api.get("close") or 0)

        # Allow tiny floating-point diff
        tol = 0.01
        ok = (
            abs(db_o - api_o) <= tol
            and abs(db_h - api_h) <= tol
            and abs(db_l - api_l) <= tol
            and abs(db_c - api_c) <= tol
        )

        status = "OK" if ok else "MISMATCH"
        print(
            f"  [{status}] {row.ts_code} {trade_date}  "
            f"DB(OHLC)={db_o},{db_h},{db_l},{db_c}  "
            f"API(OHLC)={api_o},{api_h},{api_l},{api_c}"
        )
        if not ok:
            mismatches += 1

    print(f"  Spot-check done: {sample_size - mismatches}/{sample_size} passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-sqlite", action="store_true")
    parser.add_argument("--expected-days", type=int, default=300, help="Expected trading days per variety")
    parser.add_argument("--spot-check", type=int, default=5, help="Random sample size to compare with Tushare API; 0 to skip")
    parser.add_argument("--min-interval", type=float, default=0.55)
    args = parser.parse_args()

    configure_database(args.allow_sqlite)

    db = SessionLocal()
    try:
        stats = verify_basic(db)
        bad_ohlc = verify_ohlc(db)
        bad_price = verify_zeros(db)
        low_varieties = verify_per_variety(db, args.expected_days)

        client = None
        if args.spot_check > 0:
            try:
                client = TushareClient(min_interval=args.min_interval)
            except RuntimeError as e:
                print(f"\n  Tushare client unavailable, skipping spot-check: {e}")

        if client:
            verify_tushare_spotcheck(db, client, args.spot_check)

        # Summary
        print("\n=== Summary ===")
        issues = bad_ohlc + bad_price + len(low_varieties)
        if issues == 0:
            print("  ✅ All checks passed. Data looks good for backfill.")
        else:
            print(f"  ⚠️  Found {issues} issue(s); review details above before backfilling.")

    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
