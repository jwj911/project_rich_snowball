"""Ingest Tushare fut_weekly_monthly rows into fut_daily_data.

Purpose:
    Pulls futures weekly/monthly OHLC bars from Tushare's ``fut_weekly_monthly``
    interface and writes them to ``fut_daily_data`` (period='W' or 'M').

    Unlike the old ``fut_weekly_detail`` (trading-statistics) endpoint, this
    script queries **by variety-level ts_code** (e.g. ``SM.ZCE``, ``AU.SHF``)
    so that each variety gets a single continuous weekly/monthly series.
    This avoids the 6000-row-per-call limit that truncates data when querying
    by date-range only, and it also avoids duplicate-key collisions between
    individual contracts (e.g. SM2608.ZCE vs SM2607.ZCE).

Tushare API used:
    ``fut_weekly_monthly`` — weekly/monthly OHLC bars.
    Query mode: ``ts_code=<variety_code>`` (e.g. SM.ZCE) + ``freq=week/month``.

Target database table:
    ``fut_daily_data`` (``FutDailyDataDB`` model), ``period=W`` or ``M``.

Key CLI arguments:
    --start-date YYYYMMDD
    --end-date   YYYYMMDD
    --date       YYYYMMDD
    --freq       week or month (default: week)
    --symbols    COMMA_LIST  e.g. SM,AU,PP (optional; default queries all varieties)
    --exchanges  COMMA_LIST  e.g. SHFE,DCE (optional; default queries all exchanges)
    --allow-sqlite
    --dry-run
    --min-interval SECONDS

Usage examples:
    # Weekly bars for all varieties
    python tushare_pg_ingest/ingest_weekly_detail.py --start-date 20260101 --end-date 20260515

    # Monthly bars for specific varieties
    python tushare_pg_ingest/ingest_weekly_detail.py --start-date 20260101 --end-date 20260515 --freq month --symbols SM,AU

    # Dry-run to preview mapped rows
    python tushare_pg_ingest/ingest_weekly_detail.py --start-date 20260501 --end-date 20260515 --dry-run
"""

from __future__ import annotations

import argparse
from datetime import datetime

from common import (
    IngestStats,
    TushareClient,
    comma_list,
    configure_database,
    date_window,
    print_stats,
    records_from_df,
    ts_code_for_symbol,
)

_FREQ_MAP = {"week": "W", "month": "M"}


def ingest(args: argparse.Namespace) -> IngestStats:
    configure_database(args.allow_sqlite)

    from data_collector.adapters import map_tushare_fut_daily
    from data_collector.upsert import upsert_fut_daily_bulk
    from models import SessionLocal, VarietyDB

    start_date, end_date = date_window(args)
    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    db = SessionLocal()

    # Build variety filter
    target_symbols = set(comma_list(args.symbols))
    target_exchanges = set(comma_list(args.exchanges))

    try:
        query = db.query(VarietyDB)
        if target_symbols:
            query = query.filter(VarietyDB.symbol.in_(target_symbols))
        if target_exchanges:
            query = query.filter(VarietyDB.exchange.in_(target_exchanges))
        varieties = query.all()

        period = _FREQ_MAP[args.freq]
        rows: list[dict] = []
        mapped_ts_codes: set[str] = set()
        skipped_varieties: list[str] = []

        total_varieties = len(varieties)
        for idx, variety in enumerate(varieties, start=1):
            symbol = variety.symbol
            exchange = variety.exchange
            if not symbol or not exchange:
                print(f"[{idx}/{total_varieties}] SKIP  {symbol or '?'} | exchange={exchange or '?'} — missing symbol or exchange")
                skipped_varieties.append(f"{symbol or '?'}/{exchange or '?'}")
                continue

            try:
                ts_code = ts_code_for_symbol(symbol, exchange)
            except ValueError as e:
                print(f"[{idx}/{total_varieties}] SKIP  {symbol} | exchange={exchange} — {e}")
                skipped_varieties.append(f"{symbol}/{exchange} ({e})")
                continue

            try:
                df = client.query(
                    "fut_weekly_monthly",
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    freq=args.freq,
                )
            except Exception as e:
                print(f"[{idx}/{total_varieties}] FAIL {symbol} | exchange={exchange} | ts_code={ts_code} — {e}")
                stats.failed += 1
                continue

            raw_rows = records_from_df(df)
            if not raw_rows:
                print(f"[{idx}/{total_varieties}] NONE {symbol} | exchange={exchange} | ts_code={ts_code} — no data returned")
                continue

            stats.fetched += len(raw_rows)
            mapped_ts_codes.add(ts_code)
            print(f"[{idx}/{total_varieties}] OK   {symbol} | exchange={exchange} | ts_code={ts_code} | rows={len(raw_rows)}")

            for raw in raw_rows:
                row = map_tushare_fut_daily(raw, variety.id, period=period)
                if row.get("trade_date") and row.get("variety_id"):
                    rows.append(row)
                else:
                    stats.skipped += 1

        # Deduplicate by (variety_id, trade_date) — fut_weekly_monthly should
        # not return duplicates when queried by variety-level ts_code, but we
        # keep this guard just in case.
        deduped: list[dict] = []
        seen: set[tuple[int, datetime]] = set()
        for row in rows:
            key = (row["variety_id"], row["trade_date"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        dupes = len(rows) - len(deduped)
        if dupes:
            print(f"[INFO] Removed {dupes} duplicate row(s) by (variety_id, trade_date)")

        _print_summary(mapped_ts_codes, skipped_varieties, varieties)

        if args.dry_run:
            print(
                f"[DRY] {start_date}-{end_date} freq={args.freq}: "
                f"varieties={len(varieties)} fetched={stats.fetched} mapped={len(deduped)} skipped={stats.skipped}"
            )
        else:
            stats.written = upsert_fut_daily_bulk(db, deduped)
            db.commit()
            print(
                f"[OK] {start_date}-{end_date} freq={args.freq}: "
                f"varieties={len(varieties)} fetched={stats.fetched} mapped={len(deduped)} written={stats.written} skipped={stats.skipped}"
            )
    finally:
        db.close()
    return stats


def _print_summary(
    mapped_ts_codes: set[str],
    skipped_varieties: list[str],
    varieties: list,
) -> None:
    print(f"\n[INFO] Successfully queried {len(mapped_ts_codes)} variety-level ts_code(s):")
    for code in sorted(mapped_ts_codes):
        print(f"  {code}")

    if skipped_varieties:
        print(f"\n[WARN] Skipped {len(skipped_varieties)} variety(s) (missing symbol/exchange):")
        for v in skipped_varieties:
            print(f"  {v}")
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", help="Start date, YYYYMMDD")
    parser.add_argument("--end-date", help="End date, YYYYMMDD")
    parser.add_argument("--date", dest="trade_date", help="Single trade date, YYYYMMDD")
    parser.add_argument(
        "--freq",
        choices=["week", "month"],
        default="week",
        help="Frequency: week or month (default: week)",
    )
    parser.add_argument(
        "--symbols",
        help="Optional comma-separated base symbols, e.g. SM,AU,PP. Default: all varieties in DB.",
    )
    parser.add_argument(
        "--exchanges",
        help="Optional comma-separated exchanges, e.g. SHFE,DCE. Default: all exchanges.",
    )
    parser.add_argument("--allow-sqlite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-interval", type=float, default=0.55)
    return parser


def main() -> int:
    stats = ingest(build_parser().parse_args())
    print_stats("fut_weekly_monthly -> fut_daily_data", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
