"""数据覆盖范围统计。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import KlineDataDB, RealtimeQuoteDB, VarietyDB


def get_kline_coverage(db: Session, variety_id: int, period: str) -> dict[str, Any]:
    """统计指定品种和周期的 K 线覆盖范围。"""
    row = (
        db.query(
            func.min(KlineDataDB.trading_date),
            func.max(KlineDataDB.trading_date),
            func.count(KlineDataDB.id),
            func.count(func.distinct(KlineDataDB.contract_id)),
            func.max(KlineDataDB.created_at),
        )
        .filter(KlineDataDB.variety_id == variety_id, KlineDataDB.period == period)
        .one()
    )
    first_date, last_date, row_count, contract_count, last_updated_at = row
    return {
        "first_date": first_date.isoformat() if first_date else None,
        "last_date": last_date.isoformat() if last_date else None,
        "row_count": int(row_count or 0),
        "contract_count": int(contract_count or 0),
        "last_updated_at": last_updated_at.isoformat() if last_updated_at else None,
    }


def get_realtime_coverage(db: Session, symbol: str | None = None) -> dict[str, Any]:
    """统计实时行情覆盖范围。"""
    query = db.query(
        func.count(RealtimeQuoteDB.id),
        func.max(RealtimeQuoteDB.updated_at),
    ).join(VarietyDB, RealtimeQuoteDB.variety_id == VarietyDB.id)
    if symbol:
        query = query.filter(VarietyDB.symbol == symbol.upper())
    row_count, last_updated_at = query.one()
    return {
        "row_count": int(row_count or 0),
        "last_updated_at": last_updated_at.isoformat() if last_updated_at else None,
    }
