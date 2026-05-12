"""Ingest Tushare futures daily/weekly/monthly bars into fut_daily_data.

Workflow:
1. Read concrete contract list from FutContractDB (filtered by symbol/exchange/date-range).
2. Poll fut_daily / fut_weekly_monthly per contract.
3. Upsert rows into fut_daily_data.

If --ts-codes is provided, skip FutContractDB lookup and query the given codes directly.
"""

from __future__ import annotations

import argparse
from datetime import datetime

from sqlalchemy import or_

from common import (
    IngestStats,
    TushareClient,
    add_common_args,
    comma_list,
    configure_database,
    date_window,
    print_stats,
    records_from_df,
    variety_id_for_ts_code,
)


def _ingest_direct(
    client: TushareClient,
    db,
    codes: list[str],
    start_date: str,
    end_date: str,
    period: str,
    dry_run: bool,
    stats: IngestStats,
) -> None:
    """Legacy path: query fut_daily/fut_weekly_monthly directly by ts_code."""
    from data_collector.adapters import map_tushare_fut_daily
    from data_collector.upsert import upsert_fut_daily_bulk

    for ts_code in sorted(set(codes)):
        variety_id = variety_id_for_ts_code(ts_code)
        if variety_id is None:
            print(f"[SKIP] {ts_code}: matching VarietyDB row not found")
            stats.skipped += 1
            continue

        try:
            if period == "D":
                df = client.query("fut_daily", ts_code=ts_code, start_date=start_date, end_date=end_date)
            else:
                freq = "week" if period == "W" else "month"
                df = client.query(
                    "fut_weekly_monthly",
                    ts_code=ts_code,
                    freq=freq,
                    start_date=start_date,
                    end_date=end_date,
                )
        except Exception as e:
            print(f"[FAIL] {ts_code} {period}: {e}")
            stats.failed += 1
            continue

        raw_rows = records_from_df(df)
        stats.fetched += len(raw_rows)
        rows = [
            row
            for row in (map_tushare_fut_daily(raw, variety_id, period) for raw in raw_rows)
            if row.get("trade_date") and row.get("variety_id")
        ]
        stats.skipped += len(raw_rows) - len(rows)
        if dry_run:
            print(f"[DRY] {ts_code} {period}: fetched={len(raw_rows)} mapped={len(rows)}")
            continue
        stats.written += upsert_fut_daily_bulk(db, rows)
        db.commit()
        print(f"[OK] {ts_code} {period}: fetched={len(raw_rows)}")


def _ingest_via_contracts(
    client: TushareClient,
    db,
    symbols: list[str],
    exchanges: list[str],
    contract_types: list[str],
    start_date: str,
    end_date: str,
    period: str,
    dry_run: bool,
    stats: IngestStats,
) -> None:
    """New path: read contracts from FutContractDB, then poll market data per contract."""
    from data_collector.adapters import map_tushare_fut_daily
    from data_collector.upsert import upsert_fut_daily_bulk
    from models import FutContractDB, VarietyDB

    start_dt = datetime.strptime(start_date, "%Y%m%d")
    end_dt = datetime.strptime(end_date, "%Y%m%d")

    # Build query against FutContractDB
    query = db.query(FutContractDB)
    if symbols:
        query = query.filter(FutContractDB.fut_code.in_(symbols))
    if exchanges:
        query = query.filter(FutContractDB.exchange.in_(exchanges))
    if contract_types:
        query = query.filter(FutContractDB.contract_type.in_(contract_types))

    # Only contracts active during the requested date range
    query = query.filter(
        or_(FutContractDB.list_date.is_(None), FutContractDB.list_date <= end_dt)
    )
    query = query.filter(
        or_(FutContractDB.delist_date.is_(None), FutContractDB.delist_date >= start_dt)
    )

    contracts = query.all()
    if not contracts:
        print("[SKIP] no matching contracts in FutContractDB for the given filters/date range")
        stats.skipped += 1
        return

    print(f"[INFO] {len(contracts)} contract(s) to query")

    # Preload all varieties and build a flexible lookup map.
    # Keys: original symbol (upper) AND alphabetic-only version (upper).
    # This handles mismatches like FutContractDB.fut_code='PP_F' -> VarietyDB.symbol='PP'.
    varieties = db.query(VarietyDB).all()
    variety_map: dict[str, VarietyDB] = {}
    for v in varieties:
        sym = (v.symbol or "").upper()
        if sym:
            variety_map[sym] = v
        clean = "".join(ch for ch in sym if ch.isalpha())
        if clean and clean != sym:
            variety_map[clean] = v

    def _lookup_variety(contract) -> VarietyDB | None:
        """Match contract to VarietyDB using fut_code, symbol, and alphabetic fallbacks."""
        for key in (contract.fut_code, contract.symbol):
            if not key:
                continue
            key = key.upper()
            v = variety_map.get(key)
            if v:
                return v
            # Try alphabetic-only fallback, e.g. 'PP_F' -> 'PP'
            clean = "".join(ch for ch in key if ch.isalpha())
            v = variety_map.get(clean)
            if v:
                return v
        return None

    for contract in contracts:
        ts_code = contract.ts_code
        variety = _lookup_variety(contract)
        if not variety:
            # Auto-create VarietyDB from FutContractDB info so we don't depend on
            # a separate ingest_basic.py run.
            symbol = "".join(ch for ch in (contract.fut_code or "") if ch.isalpha()).upper()
            if not symbol:
                symbol = (contract.fut_code or "").upper()
            if not symbol:
                print(f"[SKIP] {ts_code}: cannot determine symbol from contract")
                stats.skipped += 1
                continue

            variety = VarietyDB(
                symbol=symbol,
                contract_code=contract.symbol or symbol,
                name=contract.name or symbol,
                exchange=contract.exchange or "",
                category="期货",
            )
            db.add(variety)
            db.flush()  # Obtain variety.id immediately

            # Index the newly created variety for subsequent lookups
            variety_map[symbol] = variety
            if contract.fut_code:
                variety_map[contract.fut_code.upper()] = variety
            clean = "".join(ch for ch in contract.fut_code if ch.isalpha()) if contract.fut_code else ""
            if clean and clean != symbol:
                variety_map[clean] = variety
            print(f"[AUTO-INSERT] {ts_code} -> VarietyDB symbol={symbol} id={variety.id}")

        if period == "D":
            df = client.query("fut_daily", ts_code=ts_code, start_date=start_date, end_date=end_date)
        else:
            freq = "week" if period == "W" else "month"
            df = client.query(
                "fut_weekly_monthly",
                ts_code=ts_code,
                freq=freq,
                start_date=start_date,
                end_date=end_date,
            )

        raw_rows = records_from_df(df)
        stats.fetched += len(raw_rows)
        rows = [
            row
            for row in (map_tushare_fut_daily(raw, variety.id, period) for raw in raw_rows)
            if row.get("trade_date") and row.get("variety_id")
        ]
        stats.skipped += len(raw_rows) - len(rows)
        if dry_run:
            print(f"[DRY] {ts_code} {period}: fetched={len(raw_rows)} mapped={len(rows)}")
            continue
        stats.written += upsert_fut_daily_bulk(db, rows)
        db.commit()
        print(f"[OK] {ts_code} {period}: fetched={len(raw_rows)}")


def ingest(args: argparse.Namespace) -> IngestStats:
    configure_database(args.allow_sqlite)

    from models import SessionLocal

    start_date, end_date = date_window(args)
    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()

    ts_codes = comma_list(args.ts_codes)
    symbols = comma_list(args.symbols)
    exchanges = comma_list(args.exchanges)
    contract_types = comma_list(args.contract_type)

    db = SessionLocal()
    try:
        if ts_codes:
            _ingest_direct(client, db, ts_codes, start_date, end_date, args.period, args.dry_run, stats)
        elif symbols or exchanges or contract_types:
            _ingest_via_contracts(
                client, db, symbols, exchanges, contract_types, start_date, end_date, args.period, args.dry_run, stats
            )
        else:
            raise ValueError("Provide --symbols, --exchanges, --contract-type, or --ts-codes")
    finally:
        db.close()

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument("--symbols", help="Comma-separated base symbols, e.g. AU,AG,CU")
    parser.add_argument(
        "--exchanges",
        help="Comma-separated exchanges, e.g. SHFE,DCE,CZCE; "
             "if provided without --symbols, all contracts under these exchanges are queried",
    )
    parser.add_argument(
        "--ts-codes",
        help="Comma-separated concrete contract codes, e.g. AU2506.SHF (bypasses FutContractDB lookup)",
    )
    parser.add_argument(
        "--contract-type",
        help="Comma-separated contract types to filter, e.g. MAIN,CONTINUOUS,NORMAL; "
             "default all. MAIN=main/continuous contracts, CONTINUOUS=index continuous, NORMAL=concrete contracts",
    )
    parser.add_argument("--period", choices=["D", "W", "M"], default="D")
    return parser


def main() -> int:
    stats = ingest(build_parser().parse_args())
    print_stats("fut_daily_data", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
