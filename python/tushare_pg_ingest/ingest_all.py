"""Run a conservative historical Tushare backfill into local PostgreSQL."""

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
    values = vars(args).copy()
    values.update(overrides)
    return argparse.Namespace(**values)


def ingest(args: argparse.Namespace) -> IngestStats:
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
    stats = ingest(build_parser().parse_args())
    print_stats("all", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

