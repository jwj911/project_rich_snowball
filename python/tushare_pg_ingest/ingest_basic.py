"""Refresh local VarietyDB metadata from Tushare fut_basic main/continuous contracts.

Purpose:
    Pulls futures contract metadata from Tushare's ``fut_basic`` interface
    and upserts it into the application's ``varieties`` table.  This script
    is typically the first step in a backfill workflow because downstream
    ingest scripts rely on ``VarietyDB.symbol`` / ``VarietyDB.exchange`` to
    map concrete contracts to base varieties.

Tushare API used:
    ``fut_basic`` - futures contract metadata (main/continuous by default).

Target database table:
    ``varieties`` (``VarietyDB`` model).

Key CLI arguments:
    --exchanges COMMA_LIST      e.g. SHFE,DCE (default: all domestic exchanges)
    --fut-type {1,2}            1=normal contracts, 2=main/continuous; default 2
    --list-date YYYYMMDD        Only contracts listed since this date
    --insert-missing            Insert new base varieties when they don't exist
    --allow-sqlite              Permit SQLite writes (default rejects SQLite)
    --dry-run                   Fetch and map data, but do not commit
    --min-interval SECONDS      Throttle between Tushare calls (default 0.55)

Usage examples:
    python ingest_basic.py --insert-missing
    python ingest_basic.py --exchanges SHFE,DCE --insert-missing --dry-run

Known limitations:
    - ``fut_basic`` may return both main and continuous rows for the same
      underlying symbol; the script deduplicates by ``fut_code`` / symbol.
    - The fallback lookup on ``contract_code`` exists solely to avoid unique
      constraint violations when symbol derivation differs from existing rows.
"""

from __future__ import annotations

import argparse
from datetime import datetime

from common import IngestStats, TushareClient, configure_database, parse_exchanges, print_stats, records_from_df


def _parse_date(value):
    """Parse an ``YYYYMMDD`` string into a ``datetime`` object.

    Returns ``None`` for falsy or unparseable input.
    """
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y%m%d")
    except ValueError:
        return None


def ingest(args: argparse.Namespace) -> IngestStats:
    """Run the ``fut_basic -> varieties`` ingestion workflow.

    Args:
        args: Parsed namespace from ``build_parser()``.

    Returns:
        ``IngestStats`` summarising fetched, written, and skipped rows.
    """
    configure_database(args.allow_sqlite)

    from models import SessionLocal, VarietyDB

    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    db = SessionLocal()
    try:
        for exchange in parse_exchanges(args.exchanges):
            # Query Tushare for contract metadata on this exchange.
            df = client.query("fut_basic", exchange=exchange, fut_type=args.fut_type, list_date=args.list_date)
            raw_rows = records_from_df(df)
            stats.fetched += len(raw_rows)

            seen_symbols: set[str] = set()
            for raw in raw_rows:
                # Derive the canonical symbol.  ``ts_code`` is the full code
                # (e.g. "AU.SHF"); ``fut_code`` is the base variety code.
                ts_symbol = (raw.get("symbol") or raw.get("ts_code") or "").split(".", 1)[0].upper()
                fut_code = (raw.get("fut_code") or "").upper()
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
                    # Fallback: avoid unique constraint violation on contract_code
                    # when symbol derivation differs from existing rows.
                    variety = db.query(VarietyDB).filter(VarietyDB.contract_code == (ts_symbol or symbol)).first()
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

                # Overwrite mutable fields with the latest upstream values.
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
    """Construct the argument parser for this script."""
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
    """Entry point."""
    stats = ingest(build_parser().parse_args())
    print_stats("fut_basic -> varieties", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
