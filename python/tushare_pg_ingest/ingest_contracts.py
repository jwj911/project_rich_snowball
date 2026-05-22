"""Ingest Tushare fut_basic rows into the fut_contracts table.

Purpose:
    Pulls all futures contract metadata from Tushare's ``fut_basic`` interface
    and persists it to PostgreSQL (or SQLite with ``--allow-sqlite``).  Other
    ingest scripts (e.g. ``ingest_daily.py``) read from ``fut_contracts`` to
    discover which concrete contracts to poll for market data.

Tushare API used:
    ``fut_basic`` - futures contract metadata.

Target database table:
    ``fut_contracts`` (``FutContractDB`` model).

Key CLI arguments:
    --exchanges COMMA_LIST      e.g. SHFE,DCE (default: all domestic exchanges)
    --fut-type {1,2}            1=normal contracts, 2=main/continuous; default all
    --list-date YYYYMMDD        Only contracts listed since this date
    --allow-sqlite              Permit SQLite writes
    --dry-run                   Fetch and map data, but do not write rows
    --min-interval SECONDS      Throttle between Tushare calls (default 0.55)

Usage examples:
    python ingest_contracts.py --dry-run
    python ingest_contracts.py --exchanges SHFE --fut-type 1

Known limitations:
    - Rows without a ``ts_code`` are skipped because they cannot be referenced
      by downstream market-data queries.
    - The script performs a full upsert per exchange; on large exchange sets
      this may take several minutes.
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
    TUSHARE_EXCHANGES,
)


def ingest(args: argparse.Namespace) -> IngestStats:
    """Run the ``fut_basic -> fut_contracts`` ingestion workflow.

    Args:
        args: Parsed namespace from ``build_parser()``.

    Returns:
        ``IngestStats`` summarising fetched, written, and skipped rows.
    """
    configure_database(args.allow_sqlite)

    from data_collector.adapters import map_tushare_fut_contract
    from data_collector.upsert import upsert_fut_contract_bulk
    from models import SessionLocal

    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    db = SessionLocal()

    exchanges = comma_list(args.exchanges) or TUSHARE_EXCHANGES
    try:
        for exchange in exchanges:
            # Build per-exchange kwargs; omit optional keys when absent so
            # Tushare uses its own defaults.
            kwargs = {"exchange": exchange}
            if args.fut_type:
                kwargs["fut_type"] = args.fut_type
            if args.list_date:
                kwargs["list_date"] = args.list_date

            df = client.query("fut_basic", **kwargs)
            raw_rows = records_from_df(df)
            stats.fetched += len(raw_rows)

            # Map raw Tushare rows to ORM-compatible dicts.
            rows = [map_tushare_fut_contract(raw) for raw in raw_rows]
            # Drop rows that lack a ts_code - they are unusable downstream.
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
    """Construct the argument parser for this script."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exchanges",
        help=f"Comma-separated exchanges; default all domestic futures exchanges: {','.join(TUSHARE_EXCHANGES)}",
    )
    parser.add_argument("--fut-type", help="1=normal contracts, 2=main/continuous contracts; default all")
    parser.add_argument("--list-date", help="Only contracts listed since YYYYMMDD")
    parser.add_argument("--allow-sqlite", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and map data, but do not write rows")
    parser.add_argument("--min-interval", type=float, default=0.55, help="Seconds between Tushare calls")
    return parser


def main() -> int:
    """Entry point."""
    stats = ingest(build_parser().parse_args())
    print_stats("fut_basic -> fut_contracts", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
