"""重建一个或多个日频研究宽表视图。"""

from __future__ import annotations

import argparse
import json
from datetime import date

from models import SessionLocal, VarietyDB
from services.market_panel import (
    PANEL_DATA_VIEWS,
    MarketPanelBuildError,
    run_market_panel_daily_build,
)


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def main() -> int:
    parser = argparse.ArgumentParser(description="重建日频研究宽表视图")
    parser.add_argument("--symbol", help="仅重建指定品种代码")
    parser.add_argument("--start-date", help="重建起始日，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", help="重建结束日，格式 YYYY-MM-DD")
    parser.add_argument(
        "--data-view",
        action="append",
        choices=PANEL_DATA_VIEWS,
        help="要物化的视图；可重复指定，默认构建全部视图",
    )
    parser.add_argument("--dry-run", action="store_true", help="执行构建后回滚事务，不写入数据库")
    parser.add_argument("--max-attempts", type=int, default=3, help="最大构建尝试次数，默认 3")
    parser.add_argument("--retry-delay-seconds", type=float, default=1.0, help="重试初始等待秒数，默认 1")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        variety_id = None
        if args.symbol:
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == args.symbol.upper().strip()).first()
            if variety is None:
                raise ValueError(f"未找到品种 {args.symbol}")
            variety_id = variety.id

        stats = run_market_panel_daily_build(
            db,
            variety_id=variety_id,
            start_date=_parse_date(args.start_date),
            end_date=_parse_date(args.end_date),
            data_views=tuple(args.data_view or PANEL_DATA_VIEWS),
            max_attempts=args.max_attempts,
            retry_delay_seconds=args.retry_delay_seconds,
            dry_run=args.dry_run,
        )
        print(json.dumps({**stats, "dry_run": args.dry_run}, ensure_ascii=True))
        return 0
    except MarketPanelBuildError as exc:
        db.rollback()
        print(
            json.dumps(
                {
                    "error": "market_panel_build_failed",
                    "error_type": exc.error_type,
                    "trace_id": exc.trace_id,
                },
                ensure_ascii=True,
            )
        )
        return 1
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
