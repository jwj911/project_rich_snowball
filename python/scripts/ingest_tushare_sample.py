"""Small, controlled Tushare ingestion probe for local research.

Usage:
    cd python
    python scripts/ingest_tushare_sample.py --symbols AU --period 1d --limit 10

The script loads the project-root .env, initializes local metadata, pulls a
small Tushare sample, writes it through the normal pipeline, and prints row
counts before/after. It never prints TUSHARE_TOKEN.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
PYTHON_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(PYTHON_DIR))


def _mask_database_url(url: str) -> str:
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return f"{scheme}://***"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest a small Tushare sample into the local DB.")
    parser.add_argument("--symbols", default="AU", help="Comma-separated variety symbols, e.g. AU,AG,CU")
    parser.add_argument("--period", default="1d", help="K-line period: 1d is safest for Tushare permissions")
    parser.add_argument("--limit", type=int, default=10, help="K-line rows per symbol")
    parser.add_argument("--skip-realtime", action="store_true", help="Skip realtime quote pipeline")
    parser.add_argument("--skip-kline", action="store_true", help="Skip K-line pipeline")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    token = os.getenv("TUSHARE_TOKEN")
    if not token or token == "your-tushare-token-here":
        print("[ERROR] TUSHARE_TOKEN is not configured in project-root .env")
        return 1

    from config import DATABASE_URL
    from data_collector.adapters import map_tushare_kline, map_tushare_realtime
    from data_collector.cleaner import clean_kline, clean_realtime
    from data_collector.init_varieties import init_varieties
    from data_collector.pipeline import DataPipeline
    from data_collector.tushare_collector import TushareCollector
    from models import KlineDataDB, RealtimeQuoteDB, SessionLocal, VarietyDB, init_db

    print("[INFO] TUSHARE_TOKEN loaded: yes")
    print(f"[INFO] DATABASE_URL: {_mask_database_url(DATABASE_URL)}")

    init_db()
    init_varieties()

    collector = TushareCollector()
    realtime_pipeline = DataPipeline(collector=collector, adapter=map_tushare_realtime, cleaner=clean_realtime)
    kline_pipeline = DataPipeline(collector=collector, adapter=map_tushare_kline, cleaner=clean_kline)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("[ERROR] No symbols provided")
        return 1

    db = SessionLocal()
    try:
        contract_codes = {
            v.symbol: v.contract_code
            for v in db.query(VarietyDB).filter(VarietyDB.symbol.in_(symbols)).all()
        }
        missing = [symbol for symbol in symbols if symbol not in contract_codes]
        if missing:
            print(f"[ERROR] Missing varieties: {missing}. Check init_varieties metadata.")
            return 1

        before_realtime = db.query(RealtimeQuoteDB).count()
        before_kline = db.query(KlineDataDB).count()
        print(f"[INFO] Before counts: realtime_quotes={before_realtime}, kline_data={before_kline}")
    finally:
        db.close()

    if not args.skip_realtime:
        print(f"[RUN] realtime symbols={symbols}")
        try:
            stats = realtime_pipeline.run_realtime(symbols)
            print(f"[OK] realtime stats: {stats}")
        except Exception as exc:
            print(f"[WARN] realtime failed: {exc}")

    if not args.skip_kline:
        for symbol in symbols:
            contract_code = contract_codes[symbol]
            print(f"[RUN] kline symbol={symbol} contract={contract_code} period={args.period} limit={args.limit}")
            try:
                stats = kline_pipeline.run_kline(contract_code, args.period, limit=args.limit)
                print(f"[OK] kline stats for {symbol}: {stats}")
            except Exception as exc:
                print(f"[WARN] kline failed for {symbol}: {exc}")

    db = SessionLocal()
    try:
        after_realtime = db.query(RealtimeQuoteDB).count()
        after_kline = db.query(KlineDataDB).count()
        print(f"[INFO] After counts: realtime_quotes={after_realtime}, kline_data={after_kline}")
        print(f"[INFO] Delta: realtime_quotes={after_realtime - before_realtime}, kline_data={after_kline - before_kline}")
    finally:
        db.close()

    print("[DONE] Tushare sample ingestion probe completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
