"""Update varieties.contract_code from Tushare fut_mapping.

Purpose:
    Reads the daily main-contract mapping from Tushare's ``fut_mapping`` interface
    and updates ``varieties.contract_code`` so that the application always
    knows the current main (active) contract for each base variety.

Tushare API used:
    ``fut_mapping`` - daily mapping between base symbol and active contract.

Target database table:
    ``varieties`` (``VarietyDB`` model), specifically the ``contract_code``
    column.

Key CLI arguments:
    --start-date YYYYMMDD
    --end-date   YYYYMMDD
    --date       YYYYMMDD
    --allow-sqlite
    --dry-run
    --min-interval SECONDS

Usage examples:
    python ingest_mapping.py --date 20250507
    python ingest_mapping.py --start-date 20250501 --end-date 20250507

Known limitations:
    - Only the *latest* mapping within the requested window is effectively
      preserved because the script overwrites ``contract_code`` in-place.
    - If a ``VarietyDB`` row does not yet exist for a mapped symbol, the row
      is skipped (no auto-insertion).
"""

from __future__ import annotations

import argparse

from common import (
    IngestStats,
    TushareClient,
    add_common_args,
    configure_database,
    date_window,
    print_stats,
    records_from_df,
)


def _is_valid_contract_month(contract_code: str) -> bool:
    """校验合约代码中的月份是否有效（非00）。"""
    if len(contract_code) < 4:
        return False
    month_str = contract_code[-2:]
    if not month_str.isdigit():
        return False
    return month_str != "00"


def ingest(args: argparse.Namespace) -> IngestStats:
    """Run the ``fut_mapping -> varieties`` update workflow.

    Args:
        args: Parsed namespace from ``build_parser()``.

    Returns:
        ``IngestStats`` where ``written`` counts varieties whose
        ``contract_code`` actually changed.
    """
    configure_database(args.allow_sqlite)

    from data_collector.adapters import map_tushare_fut_mapping
    from models import SessionLocal, VarietyDB

    start_date, end_date = date_window(args)
    client = TushareClient(min_interval=args.min_interval)
    stats = IngestStats()
    db = SessionLocal()
    try:
        # 预加载当前 contract_code 占用情况到内存，避免同一事务内 pending UPDATE 冲突检测失效
        code_owner: dict[str, int] = {
            v.contract_code: v.id
            for v in db.query(VarietyDB).filter(VarietyDB.contract_code.isnot(None)).all()
        }

        df = client.query("fut_mapping", start_date=start_date, end_date=end_date)
        raw_rows = records_from_df(df)
        stats.fetched += len(raw_rows)
        for row in (map_tushare_fut_mapping(raw) for raw in raw_rows):
            ts_code = row.get("ts_code")
            mapping_ts_code = row.get("mapping_ts_code")
            if not ts_code or not mapping_ts_code:
                stats.skipped += 1
                continue
            # Derive the base symbol from the full ts_code.
            symbol = ts_code.split(".", 1)[0].upper()
            contract_code = mapping_ts_code.split(".", 1)[0].upper()
            if not _is_valid_contract_month(contract_code):
                print(f"[WARN] Invalid contract month in mapping: {contract_code} for {symbol}, skipping")
                stats.skipped += 1
                continue
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
            if not variety:
                stats.skipped += 1
                continue
            if variety.contract_code != contract_code:
                # 检测唯一约束冲突：contract_code 是否已被其他品种占用
                existing_id = code_owner.get(contract_code)
                if existing_id and existing_id != variety.id:
                    existing = db.query(VarietyDB).filter(VarietyDB.id == existing_id).first()
                    print(
                        f"[WARN] contract_code={contract_code} already belongs to "
                        f"{existing.symbol if existing else '?' }(id={existing_id}), skipping "
                        f"{symbol}(id={variety.id})"
                    )
                    stats.skipped += 1
                    continue
                code_owner[contract_code] = variety.id
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
    """Construct the argument parser for this script."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    return parser


def main() -> int:
    """Entry point."""
    stats = ingest(build_parser().parse_args())
    print_stats("fut_mapping -> varieties", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
