"""市场状态与交易日历接口。"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from dependencies import get_db
from models import TradingCalendarDB
from schemas import MarketStatusResponse

router = APIRouter(prefix="/api/market", tags=["市场状态"])

_CN_TZ = timezone(timedelta(hours=8))


def _cn_now() -> datetime:
    return datetime.now(_CN_TZ)


def _get_session_status(calendar_entry: TradingCalendarDB | None) -> str:
    """根据当前时间判断交易时段。"""
    now = _cn_now()
    time_str = now.strftime("%H:%M")

    if not calendar_entry or not calendar_entry.is_trading_day:
        return "closed"

    day_start = calendar_entry.day_session_start or "09:00"
    day_end = calendar_entry.day_session_end or "15:00"
    if day_start <= time_str <= day_end:
        return "day"

    night_start = calendar_entry.night_session_start
    night_end = calendar_entry.night_session_end
    if night_start and night_end:
        if night_start < night_end:
            if night_start <= time_str <= night_end:
                return "night"
        else:
            if time_str >= night_start or time_str <= night_end:
                return "night"

    return "closed"


@router.get("/status", response_model=MarketStatusResponse)
def get_market_status(db: Session = Depends(get_db)):
    today = _cn_now().replace(hour=0, minute=0, second=0, microsecond=0)

    today_entry = (
        db.query(TradingCalendarDB)
        .filter(
            TradingCalendarDB.trade_date == today,
            TradingCalendarDB.exchange == "ALL",
        )
        .first()
    )

    is_trading = today_entry.is_trading_day if today_entry else True
    session = _get_session_status(today_entry)
    remark = today_entry.remark if today_entry else None

    next_trade = (
        db.query(TradingCalendarDB)
        .filter(
            TradingCalendarDB.trade_date > today,
            TradingCalendarDB.is_trading_day == True,
            TradingCalendarDB.exchange == "ALL",
        )
        .order_by(TradingCalendarDB.trade_date.asc())
        .first()
    )

    return MarketStatusResponse(
        date=today.strftime("%Y-%m-%d"),
        is_trading_day=is_trading,
        current_session=session,
        next_trade_date=next_trade.trade_date.strftime("%Y-%m-%d") if next_trade else None,
        remark=remark,
    )
