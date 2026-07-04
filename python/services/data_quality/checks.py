"""数据质量单项检查规则。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models import KlineDataDB
from services.data_quality.types import DataQualityIssue


def check_kline_ohlc(db: Session, variety_id: int, period: str) -> DataQualityIssue | None:
    """检查 K 线 OHLC 价格合法性和成交量非负。"""
    invalid_rows = (
        db.query(KlineDataDB)
        .filter(
            KlineDataDB.variety_id == variety_id,
            KlineDataDB.period == period,
            or_(
                KlineDataDB.open_price <= 0,
                KlineDataDB.high_price <= 0,
                KlineDataDB.low_price <= 0,
                KlineDataDB.close_price <= 0,
                KlineDataDB.volume < 0,
                KlineDataDB.high_price < KlineDataDB.open_price,
                KlineDataDB.high_price < KlineDataDB.close_price,
                KlineDataDB.high_price < KlineDataDB.low_price,
                KlineDataDB.low_price > KlineDataDB.open_price,
                KlineDataDB.low_price > KlineDataDB.close_price,
                KlineDataDB.low_price > KlineDataDB.high_price,
            ),
        )
        .order_by(KlineDataDB.trading_time.asc())
        .limit(5)
        .all()
    )
    if not invalid_rows:
        return None

    sample = [
        {
            "trading_time": row.trading_time.isoformat() if row.trading_time else None,
            "open": float(row.open_price),
            "high": float(row.high_price),
            "low": float(row.low_price),
            "close": float(row.close_price),
            "volume": row.volume,
        }
        for row in invalid_rows
    ]
    return DataQualityIssue(
        severity="bad",
        code="KLINE_INVALID_OHLC",
        message=f"发现 {len(invalid_rows)} 条样例存在 OHLC 或成交量异常",
        sample=sample,
    )


def check_kline_duplicates(db: Session, variety_id: int, period: str) -> DataQualityIssue | None:
    """检查同一品种、合约、周期、时间是否有重复 K 线。"""
    duplicate_rows = (
        db.query(
            KlineDataDB.contract_id,
            KlineDataDB.trading_time,
            func.count(KlineDataDB.id).label("row_count"),
        )
        .filter(KlineDataDB.variety_id == variety_id, KlineDataDB.period == period)
        .group_by(KlineDataDB.contract_id, KlineDataDB.trading_time)
        .having(func.count(KlineDataDB.id) > 1)
        .limit(5)
        .all()
    )
    if not duplicate_rows:
        return None

    sample: list[dict[str, Any]] = [
        {
            "contract_id": row.contract_id,
            "trading_time": row.trading_time.isoformat() if row.trading_time else None,
            "row_count": row.row_count,
        }
        for row in duplicate_rows
    ]
    return DataQualityIssue(
        severity="bad",
        code="KLINE_DUPLICATE_ROWS",
        message="发现重复 K 线记录",
        sample=sample,
    )


def check_daily_date_gaps(trading_dates: list[date]) -> DataQualityIssue | None:
    """按自然日粗检日 K 日期缺口，周末不计入缺口。"""
    if len(trading_dates) < 2:
        return None

    date_set = set(trading_dates)
    missing: list[str] = []
    current = min(trading_dates)
    end = max(trading_dates)
    while current <= end:
        if current.weekday() < 5 and current not in date_set:
            missing.append(current.isoformat())
            if len(missing) >= 10:
                break
        current = date.fromordinal(current.toordinal() + 1)

    if not missing:
        return None

    return DataQualityIssue(
        severity="warning",
        code="KLINE_MISSING_DATES",
        message=f"发现 {len(missing)} 个疑似缺失交易日样例",
        sample=missing,
    )
