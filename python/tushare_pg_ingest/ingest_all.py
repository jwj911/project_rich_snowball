"""Run a conservative historical Tushare backfill into local PostgreSQL.

Purpose:
    Orchestrates the entire backfill pipeline by invoking sibling ingest
    scripts in a sensible order:

        1. ``ingest_basic``      - seed / refresh ``varieties`` metadata
        2. ``ingest_contracts``  - populate ``fut_contracts``
        3. ``ingest_mapping``    - update main-contract mappings
        4. ``ingest_daily``      - backfill daily bars (D)
        5. ``ingest_daily``      - backfill weekly bars (W)
        6. ``ingest_daily``      - backfill monthly bars (M)
        7. ``ingest_settle``     - settlement parameters
        8. ``ingest_wsr``        - warehouse receipts
        9. ``ingest_holding``    - broker rankings
       10. ``ingest_price_limit`` - price limits
       11. ``ingest_weekly_detail`` - weekly trading statistics

    Each step can be skipped independently via ``--skip-*`` flags.

Tushare/AKShare APIs used:
    Delegates to sibling scripts; see their individual docstrings.

Target database tables:
    ``varieties``, ``fut_contracts``, ``fut_daily_data``, ``fut_settle``,
    ``fut_wsr``, ``fut_holding``, ``fut_price_limits``, ``fut_weekly_detail``.

Key CLI arguments:
    --start-date YYYYMMDD       (required)
    --end-date   YYYYMMDD       (required)
    --symbols    COMMA_LIST     e.g. AU,AG,CU (default: a small active set)
    --exchanges  COMMA_LIST     e.g. SHFE,DCE
    --skip-basic
    --skip-contracts
    --skip-daily
    --skip-weekly-monthly
    --skip-settle
    --skip-wsr
    --skip-holding
    --skip-limit
    --skip-mapping
    --skip-weekly-detail
    --contract-type COMMA_LIST  e.g. MAIN,CONTINUOUS,NORMAL
    --allow-sqlite
    --dry-run
    --min-interval SECONDS

Usage example:
    python ingest_all.py --start-date 20240101 --end-date 20240131 --allow-sqlite

Known limitations:
    - The script runs steps sequentially; there is no parallelism.
    - ``--dry-run`` is forwarded to each sub-script, so no database writes
      occur anywhere in the pipeline.
    - Sibling scripts are imported directly, so this module must be executed
      from the ``tushare_pg_ingest/`` directory (or with correct ``sys.path``).
"""

from __future__ import annotations

import argparse

import ingest_basic
import ingest_contracts
import ingest_daily
import ingest_holding
import ingest_mapping
import ingest_price_limit
import ingest_settle
import ingest_weekly_detail
import ingest_wsr
from common import IngestStats, print_stats


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for this script."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, help="Start date, YYYYMMDD")
    parser.add_argument("--end-date", required=True, help="End date, YYYYMMDD")
    parser.add_argument("--symbols", default="AU,AG,CU,AL,RB,HC,I,M,CF,SR", help="Base symbols for market data")
    parser.add_argument("--exchanges", help="Exchanges for exchange-scoped endpoints; default all")
    parser.add_argument("--skip-basic", action="store_true")
    parser.add_argument("--skip-contracts", action="store_true")
    parser.add_argument("--skip-daily", action="store_true")
    parser.add_argument("--skip-weekly-monthly", action="store_true")
    parser.add_argument("--skip-settle", action="store_true")
    parser.add_argument("--skip-wsr", action="store_true")
    parser.add_argument("--skip-holding", action="store_true")
    parser.add_argument("--skip-limit", action="store_true")
    parser.add_argument("--skip-mapping", action="store_true")
    parser.add_argument("--skip-weekly-detail", action="store_true")
    parser.add_argument(
        "--contract-type",
        help="Contract types for daily/weekly/monthly ingest, e.g. MAIN,CONTINUOUS,NORMAL; default all",
    )
    parser.add_argument("--allow-sqlite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-interval", type=float, default=0.55)
    return parser


def _ns(args: argparse.Namespace, **overrides):
    """Clone *args* and override specific attributes.

    This lets us reuse the same parsed namespace across sibling scripts
    while injecting per-step parameters (e.g. ``period="W"``).
    """
    values = vars(args).copy()
    values.update(overrides)
    return argparse.Namespace(**values)


def ingest(args: argparse.Namespace) -> IngestStats:
    """Execute the full backfill pipeline, honouring all ``--skip-*`` flags.

    Args:
        args: Parsed namespace from ``build_parser()``.

    Returns:
        Aggregated ``IngestStats`` across all executed steps.
    """
    total = IngestStats()

    if not args.skip_basic:
        total.add(ingest_basic.ingest(_ns(args)))
    if not args.skip_contracts:
        total.add(ingest_contracts.ingest(_ns(args)))
    if not args.skip_mapping:
        total.add(ingest_mapping.ingest(_ns(args, trade_date=None)))
    if not args.skip_daily:
        total.add(ingest_daily.ingest(_ns(args, trade_date=None, ts_codes=None, period="D")))
    if not args.skip_weekly_monthly:
        total.add(ingest_daily.ingest(_ns(args, trade_date=None, ts_codes=None, period="W")))
        total.add(ingest_daily.ingest(_ns(args, trade_date=None, ts_codes=None, period="M")))
    if not args.skip_settle:
        total.add(ingest_settle.ingest(_ns(args, trade_date=None)))
    if not args.skip_wsr:
        total.add(ingest_wsr.ingest(_ns(args, trade_date=None)))
    if not args.skip_holding:
        total.add(ingest_holding.ingest(_ns(args, trade_date=None)))
    if not args.skip_limit:
        total.add(ingest_price_limit.ingest(_ns(args, trade_date=None)))
    if not args.skip_weekly_detail:
        total.add(ingest_weekly_detail.ingest(_ns(args, trade_date=None)))

    return total


def main() -> int:
    """Entry point."""
    stats = ingest(build_parser().parse_args())
    print_stats("all", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
