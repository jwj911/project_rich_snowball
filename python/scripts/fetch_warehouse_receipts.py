"""获取各品种仓单日报数据（Tushare fut_wsr）。

symbol 参数说明（已验证）：
- 必须使用品种简称，例如 AU、ZN、CU、AG 等。
- 不能使用主连代码（如 AU.SHF），否则返回空数据。
- 不指定 symbol 时，可拉取当日全部品种仓单（单次上限 1000 条）。

用法示例：
    # 1. 获取指定日期、指定品种的仓单数据并入库
    python scripts/fetch_warehouse_receipts.py --date 20250507 --symbols AU,ZN,CU

    # 2. 获取日期范围内所有活跃品种的仓单数据
    python scripts/fetch_warehouse_receipts.py --start-date 20250501 --end-date 20250507

    # 3. 仅预览，不写入数据库
    python scripts/fetch_warehouse_receipts.py --date 20250507 --symbols AU --dry-run

    # 4. 允许写入 SQLite（默认只允许 PostgreSQL）
    python scripts/fetch_warehouse_receipts.py --date 20250507 --allow-sqlite
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

# 将项目根目录加入 path，以便导入 python/ 下的模块
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from data_collector.adapters import map_tushare_fut_wsr
from data_collector.tushare_collector import TushareCollector
from data_collector.upsert import upsert_fut_wsr_bulk
from models import SessionLocal, VarietyDB


def parse_date_arg(value: str | None) -> str | None:
    if not value:
        return None
    # 允许 YYYYMMDD 或 YYYY-MM-DD
    value = value.replace("-", "")
    if len(value) != 8 or not value.isdigit():
        raise argparse.ArgumentTypeError(f"Invalid date format: {value}")
    return value


def iter_dates(start_date: str | None, end_date: str | None, single_date: str | None) -> list[str]:
    if single_date:
        return [single_date]
    if not start_date or not end_date:
        # 默认取最近一个交易日（简单处理：今天或昨天）
        today = datetime.now(timezone.utc)
        # 周末回退到周五
        weekday = today.weekday()
        if weekday >= 5:
            today -= timedelta(days=(weekday - 4))
        return [today.strftime("%Y%m%d")]

    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    if end < start:
        raise ValueError("end_date must be >= start_date")

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return dates


def fetch_warehouse_receipts(
    collector: TushareCollector,
    db,
    dates: list[str],
    symbols: list[str] | None,
    dry_run: bool = False,
) -> dict:
    stats = {"dates": len(dates), "symbols_queried": 0, "fetched": 0, "written": 0, "skipped": 0}

    for trade_date in dates:
        query_symbols = symbols if symbols else [None]
        for symbol in query_symbols:
            label = symbol or "ALL"
            print(f"[FETCH] date={trade_date} symbol={label} ...", end=" ")

            try:
                raw_rows = collector.fetch_wsr(trade_date=trade_date, symbol=symbol)
            except Exception as e:
                print(f"ERROR: {e}")
                continue

            stats["symbols_queried"] += 1
            stats["fetched"] += len(raw_rows)

            if not raw_rows:
                print("0 rows")
                continue

            rows = [map_tushare_fut_wsr(row) for row in raw_rows]
            # 过滤无效数据：必须包含 trade_date、symbol、warehouse
            rows = [row for row in rows if row.get("trade_date") and row.get("symbol") and row.get("warehouse")]
            stats["skipped"] += len(raw_rows) - len(rows)

            print(f"fetched={len(raw_rows)} valid={len(rows)}")

            if dry_run:
                # 打印前 3 条作为预览
                for row in rows[:3]:
                    print(f"  {row['trade_date'].strftime('%Y-%m-%d')} | {row['symbol']:6s} | {row['fut_name'] or '':6s} | "
                          f"{row['warehouse']:20s} | pre={row.get('pre_vol')} vol={row.get('vol')} chg={row.get('vol_chg')}")
                if len(rows) > 3:
                    print(f"  ... and {len(rows) - 3} more rows")
                continue

            try:
                written = upsert_fut_wsr_bulk(db, rows)
                db.commit()
                stats["written"] += written
                print(f"  => written={written}")
            except Exception as e:
                db.rollback()
                print(f"  => DB ERROR: {e}")

    return stats


def get_active_symbols(db) -> list[str]:
    """从 VarietyDB 读取所有活跃品种的 symbol（品种简称，如 AU、ZN）。"""
    varieties = db.query(VarietyDB).filter(VarietyDB.is_active == True).all()
    return sorted({v.symbol.upper() for v in varieties if v.symbol})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", type=parse_date_arg, help="Single trade date, YYYYMMDD")
    parser.add_argument("--start-date", type=parse_date_arg, help="Start date, YYYYMMDD")
    parser.add_argument("--end-date", type=parse_date_arg, help="End date, YYYYMMDD")
    parser.add_argument("--symbols", help="Comma-separated product codes, e.g. AU,ZN,CU. Defaults to all active varieties from DB.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and map data, but do not write to database")
    parser.add_argument("--allow-sqlite", action="store_true", help="Allow running against SQLite (no-op for this script, but keeps convention)")

    args = parser.parse_args()

    # 初始化数据库连接（SessionLocal 已经根据 DATABASE_URL 配置好了）
    db = SessionLocal()
    try:
        # 如果用户没传 symbols，从 DB 读取活跃品种列表
        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        else:
            symbols = get_active_symbols(db)
            print(f"[INFO] Loaded {len(symbols)} active varieties from DB: {', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}")

        dates = iter_dates(args.start_date, args.end_date, args.date)
        print(f"[INFO] Date range: {dates[0]} ~ {dates[-1]} ({len(dates)} day(s))")
        print(f"[INFO] Symbols: {', '.join(symbols) if symbols else 'ALL ( unspecified - Tushare full pull )'}")
        print(f"[INFO] Dry run: {args.dry_run}\n")

        collector = TushareCollector()
        stats = fetch_warehouse_receipts(
            collector=collector,
            db=db,
            dates=dates,
            symbols=symbols,
            dry_run=args.dry_run,
        )

        print("\n=== Summary ===")
        print(f"Dates queried     : {stats['dates']}")
        print(f"API calls made    : {stats['symbols_queried']}")
        print(f"Total fetched     : {stats['fetched']}")
        print(f"Total skipped     : {stats['skipped']}")
        if not args.dry_run:
            print(f"Total written     : {stats['written']}")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
