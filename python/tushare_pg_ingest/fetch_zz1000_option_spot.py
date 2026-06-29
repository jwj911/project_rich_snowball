"""Fetch CFFEX CSI 1000 index option real-time spot quotes via AKShare.

Interface:
    ak.option_cffex_zz1000_spot_sina(symbol="mo2506")

Target:
    https://stock.finance.sina.com.cn/futures/view/optionsCffexDP.php

Description:
    新浪财经-中金所-中证1000指数-指定合约-实时行情

Output columns (17 total):
    看涨合约-买量, 看涨合约-买价, 看涨合约-最新价, 看涨合约-卖价,
    看涨合约-卖量, 看涨合约-持仓量, 看涨合约-涨跌,
    行权价,
    看涨合约-标识,
    看跌合约-买量, 看跌合约-买价, 看跌合约-最新价, 看跌合约-卖价,
    看跌合约-卖量, 看跌合约-持仓量, 看跌合约-涨跌,
    看跌合约-标识

Usage examples:
    python tushare_pg_ingest/fetch_zz1000_option_spot.py --symbol mo2506
    python tushare_pg_ingest/fetch_zz1000_option_spot.py --symbol mo2509 --output zz1000_options.csv
    python tushare_pg_ingest/fetch_zz1000_option_spot.py --symbol mo2506 --max-rows 10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Ensure project python/ is on path so sibling imports resolve if needed.
PYTHON_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_DIR))


COLUMNS = [
    "看涨合约-买量",
    "看涨合约-买价",
    "看涨合约-最新价",
    "看涨合约-卖价",
    "看涨合约-卖量",
    "看涨合约-持仓量",
    "看涨合约-涨跌",
    "行权价",
    "看涨合约-标识",
    "看跌合约-买量",
    "看跌合约-买价",
    "看跌合约-最新价",
    "看跌合约-卖价",
    "看跌合约-卖量",
    "看跌合约-持仓量",
    "看跌合约-涨跌",
    "看跌合约-标识",
]


def fetch(symbol: str) -> Any:
    """Call AKShare ``option_cffex_zz1000_spot_sina`` and return a DataFrame."""
    import akshare as ak

    df = ak.option_cffex_zz1000_spot_sina(symbol=symbol)
    return df


def display(df: Any, max_rows: int | None = None) -> None:
    """Pretty-print the DataFrame to stdout with UTF-8 safety."""
    if df is None or df.empty:
        print("[WARN] No data returned.")
        return

    import pandas as pd

    pd.set_option("display.unicode.ambiguous_as_wide", True)
    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)

    if max_rows is not None:
        pd.set_option("display.max_rows", max_rows)
        to_show = df.head(max_rows)
    else:
        to_show = df

    # Print with explicit UTF-8 encoding to avoid Windows console garbling.
    output = to_show.to_string(index=False)
    try:
        sys.stdout.buffer.write(output.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
    except Exception:
        print(output)


def save_csv(df: Any, path: Path) -> None:
    """Persist DataFrame to CSV with UTF-8 BOM for Excel compatibility."""
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[OK] Saved {len(df)} rows to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbol",
        required=True,
        help='Contract month symbol, e.g. "mo2506" or "mo2509"',
    )
    parser.add_argument(
        "--output",
        help="Optional CSV output path (e.g. zz1000_options.csv)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        help="Max rows to display (default: show all)",
    )
    args = parser.parse_args()

    print(f"[INFO] Fetching CFFEX CSI 1000 option spot for symbol={args.symbol} ...")
    try:
        df = fetch(args.symbol)
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1

    print(f"[OK] Fetched {len(df)} rows x {len(df.columns)} cols")

    if args.output:
        save_csv(df, Path(args.output))

    display(df, max_rows=args.max_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
