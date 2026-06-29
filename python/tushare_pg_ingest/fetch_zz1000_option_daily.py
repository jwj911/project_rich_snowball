"""Fetch CFFEX CSI 1000 index option daily bars via Tushare Pro.

Interface:
    tushare opt_daily(ts_code="MO2506-C-3900.CFX", start_date="20250501", end_date="20250603")
    tushare opt_basic(exchange="CFFEX")  -- discover contracts

Description:
    中金所-中证1000指数期权-日频行情（含持仓量 oi）。

Output columns:
    ts_code, trade_date, exchange, pre_settle, pre_close,
    open, high, low, close, settle, vol, amount, oi

Usage examples:
    # 自动发现 MO2606 全部合约并拉取日频
    python tushare_pg_ingest/fetch_zz1000_option_daily.py --symbol MO2606 --start-date 20260601 --end-date 20260603

    # 直接指定合约
    python tushare_pg_ingest/fetch_zz1000_option_daily.py --ts-codes MO2606-C-6000.CFX,MO2606-P-6000.CFX --start-date 20260601 --end-date 20260603

    # 保存 CSV
    python tushare_pg_ingest/fetch_zz1000_option_daily.py --symbol MO2606 --start-date 20260601 --end-date 20260603 --output mo2606_daily.csv

    # 干跑预览合约列表
    python tushare_pg_ingest/fetch_zz1000_option_daily.py --symbol MO2606 --start-date 20260601 --end-date 20260603 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PYTHON_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_DIR))

from tushare_pg_ingest.common import (
    TushareClient,
    comma_list,
    date_window,
    records_from_df,
)


def discover_contracts(client: TushareClient, symbol: str) -> list[str]:
    """Query opt_basic and return ts_codes matching *symbol* (e.g. MO2506)."""
    print(f"[INFO] Discovering contracts for {symbol} via opt_basic ...")
    df = client.query("opt_basic", exchange="CFFEX")
    if df is None or df.empty:
        return []

    prefix = symbol.upper()
    matched = df[df["ts_code"].astype(str).str.startswith(prefix, na=False)]
    codes = matched["ts_code"].astype(str).str.upper().tolist()
    codes.sort()
    print(f"[OK] Discovered {len(codes)} contracts for {symbol}")
    return codes


def fetch_daily(client: TushareClient, ts_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Fetch opt_daily for a single contract."""
    try:
        df = client.query(
            "opt_daily",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        print(f"[FAIL] opt_daily {ts_code}: {exc}")
        return []

    return records_from_df(df)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", help='Contract month symbol, e.g. "MO2506"')
    parser.add_argument(
        "--ts-codes",
        help='Comma-separated option TS codes, e.g. "MO2506-C-3900.CFX,MO2506-P-3900.CFX"',
    )
    parser.add_argument("--start-date", help="Start date, YYYYMMDD")
    parser.add_argument("--end-date", help="End date, YYYYMMDD")
    parser.add_argument("--date", dest="trade_date", help="Single date, YYYYMMDD")
    parser.add_argument("--output", help="Optional CSV output path")
    parser.add_argument("--dry-run", action="store_true", help="Preview contracts only, do not fetch daily bars")
    parser.add_argument("--min-interval", type=float, default=0.55, help="Seconds between Tushare calls")
    args = parser.parse_args()

    if not args.symbol and not args.ts_codes:
        print("[ERROR] Provide --symbol or --ts-codes")
        return 1

    start_date, end_date = date_window(args)

    client = TushareClient(min_interval=args.min_interval)

    codes = comma_list(args.ts_codes)
    if not codes and args.symbol:
        codes = discover_contracts(client, args.symbol)
        if not codes:
            print(f"[WARN] No contracts found for {args.symbol}")
            return 0

    if args.dry_run:
        print(f"[DRY] Would fetch opt_daily for {len(codes)} contracts from {start_date} to {end_date}")
        for c in codes:
            print(f"  - {c}")
        return 0

    all_rows: list[dict[str, Any]] = []
    for ts_code in codes:
        rows = fetch_daily(client, ts_code, start_date, end_date)
        if rows:
            all_rows.extend(rows)
            print(f"[OK] {ts_code}: fetched {len(rows)} rows")
        else:
            print(f"[OK] {ts_code}: 0 rows")

    if not all_rows:
        print("[WARN] No daily data returned.")
        return 0

    import pandas as pd

    df = pd.DataFrame(all_rows)
    # Reorder columns for readability
    cols = [
        "ts_code", "trade_date", "exchange", "pre_settle", "pre_close",
        "open", "high", "low", "close", "settle", "vol", "amount", "oi",
    ]
    present = [c for c in cols if c in df.columns]
    df = df[present]

    print(f"[DONE] Total rows: {len(df)}  contracts: {len(codes)}")

    if args.output:
        out_path = Path(args.output)
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"[OK] Saved to {out_path}")

    # Pretty print sample
    pd.set_option("display.unicode.ambiguous_as_wide", True)
    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    print(df.head(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
