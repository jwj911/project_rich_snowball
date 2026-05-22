from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import KlineDataDB, UserDB, VarietyDB
from schemas import ContinuousKlineResponse, KlineResponse
from services.continuous_kline import get_continuous_kline, get_main_contract_kline
from services.kline_period import period_candidates
from utils import ensure_naive

router = APIRouter(prefix="/api/klines", tags=["K线"])


@router.get("/{symbol}", response_model=list[KlineResponse])
def get_kline(
    symbol: str,
    period: str = Query("1h", pattern="^(1m|5m|15m|30m|1h|1d|1w)$"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    klines = []
    for candidate in period_candidates(period):
        klines = (
            db.query(KlineDataDB)
            .filter(KlineDataDB.variety_id == variety.id, KlineDataDB.period == candidate)
            .order_by(KlineDataDB.trading_time.desc())
            .limit(limit)
            .all()
        )
        if klines:
            break

    return [
        {
            "time": k.trading_time.isoformat(),
            "open": k.open_price,
            "high": k.high_price,
            "low": k.low_price,
            "close": k.close_price,
            "volume": k.volume,
        }
        for k in reversed(klines)
    ]


@router.get("/{symbol}/continuous", response_model=list[ContinuousKlineResponse])
def get_continuous_kline_api(
    symbol: str,
    period: str = Query("D", pattern=r"^(D|W|M|5|15|30|60|1m|5m|15m|30m|1h|1d|1w)$"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取连续 K 线（按主力切换拼接多合约）。"""
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    rows = get_continuous_kline(
        db, variety.id, period=period, start=ensure_naive(start), end=ensure_naive(end), limit=limit, adjustment="backward"
    )
    return [
        ContinuousKlineResponse(
            time=r["time"],
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
            contract_code=r.get("contract_code"),
        )
        for r in rows
    ]


@router.get("/{symbol}/main", response_model=list[ContinuousKlineResponse])
def get_main_contract_kline_api(
    symbol: str,
    period: str = Query("D", pattern=r"^(D|W|M|5|15|30|60|1m|5m|15m|30m|1h|1d|1w)$"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取当前主力合约的 K 线（不拼接）。"""
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    rows = get_main_contract_kline(
        db, variety.id, period=period, start=ensure_naive(start), end=ensure_naive(end), limit=limit
    )
    return [
        ContinuousKlineResponse(
            time=r["time"],
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
            contract_code=r.get("contract_code"),
        )
        for r in rows
    ]
