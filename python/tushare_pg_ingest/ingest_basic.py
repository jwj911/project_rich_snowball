"""Refresh local VarietyDB metadata from Tushare fut_basic main/continuous contracts."""

from __future__ import annotations

import argparse
from datetime import datetime

from common import IngestStats, TushareClient, configure_database, parse_exchanges, print_stats, records_from_df


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y%m%d")
    except ValueError:
        return None


def ingest(args: argparse.Namespace) -> IngestStats:
    configure_database(args.allow_sqlite)

    from models import SessionLocal, VarietyDB

    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    db = SessionLocal()
    try:
        for exchange in parse_exchanges(args.exchanges):
            df = client.query("fut_basic", exchange=exchange, fut_type=args.fut_type, list_date=args.list_date)
            raw_rows = records_from_df(df)
            stats.fetched += len(raw_rows)
            seen_symbols: set[str] = set()
            for raw in raw_rows:
                fut_code = (raw.get("fut_code") or raw.get("symbol") or "").upper()
                ts_symbol = (raw.get("symbol") or raw.get("ts_code") or "").split(".", 1)[0].upper()
                symbol = fut_code or "".join(ch for ch in ts_symbol if ch.isalpha()).upper()
                if not symbol:
                    stats.skipped += 1
                    continue

                # Deduplicate within this batch: fut_basic may return both main and
                # continuous rows for the same underlying symbol (e.g. BR + BRL).
                if symbol in seen_symbols:
                    continue
                seen_symbols.add(symbol)

                variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
                if not variety:
                    if not args.insert_missing:
                        stats.skipped += 1
                        continue
                    variety = VarietyDB(
                        symbol=symbol,
                        contract_code=ts_symbol or symbol,
                        name=raw.get("name") or symbol,
                        exchange=exchange,
                        category="期货",
                    )
                    db.add(variety)

                variety.name = raw.get("name") or variety.name
                variety.exchange = raw.get("exchange") or exchange
                variety.multiplier = raw.get("multiplier") or variety.multiplier
                variety.listing_date = _parse_date(raw.get("list_date")) or variety.listing_date
                variety.last_trading_date = _parse_date(raw.get("delist_date")) or variety.last_trading_date
                stats.written += 1
            if args.dry_run:
                db.rollback()
                print(f"[DRY] {exchange}: fetched={len(raw_rows)}")
            else:
                db.commit()
                print(f"[OK] {exchange}: fetched={len(raw_rows)}")
    finally:
        db.close()
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchanges", help="Comma-separated exchanges; default all domestic futures exchanges")
    parser.add_argument("--fut-type", default="2", help="1=normal contracts, 2=main/continuous contracts; default 2")
    parser.add_argument("--list-date", help="Only contracts listed since YYYYMMDD")
    parser.add_argument("--insert-missing", action="store_true", help="Insert missing base varieties")
    parser.add_argument("--allow-sqlite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-interval", type=float, default=0.55)
    return parser


def main() -> int:
    stats = ingest(build_parser().parse_args())
    print_stats("fut_basic -> varieties", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

