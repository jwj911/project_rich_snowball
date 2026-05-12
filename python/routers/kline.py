from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from models import KlineDataDB, VarietyDB
from schemas import KlineResponse, ContinuousKlineResponse
from dependencies import get_db
from services.continuous_kline import get_continuous_kline, get_main_contract_kline

router = APIRouter(prefix="/api/kline", tags=["K线"])


@router.get("/{symbol}", response_model=List[KlineResponse])
def get_kline(
    symbol: str,
    period: str = Query("1h", pattern="^(1m|5m|15m|30m|1h|1d|1w)$"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    klines = (
        db.query(KlineDataDB)
        .filter(KlineDataDB.variety_id == variety.id, KlineDataDB.period == period)
        .order_by(KlineDataDB.trading_time.desc())
        .limit(limit)
        .all()
    )

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


@router.get("/{symbol}/continuous", response_model=List[ContinuousKlineResponse])
def get_continuous_kline_api(
    symbol: str,
    period: str = Query("D", pattern=r"^(D|W|M|5|15|30|60|1m|5m|15m|30m|1h|1d|1w)$"),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db)
):
    """获取连续 K 线（按主力切换拼接多合约）。"""
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    rows = get_continuous_kline(
        db, variety.id, period=period, start=start, end=end, limit=limit
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


@router.get("/{symbol}/main", response_model=List[ContinuousKlineResponse])
def get_main_contract_kline_api(
    symbol: str,
    period: str = Query("D", pattern=r"^(D|W|M|5|15|30|60|1m|5m|15m|30m|1h|1d|1w)$"),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db)
):
    """获取当前主力合约的 K 线（不拼接）。"""
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    rows = get_main_contract_kline(
        db, variety.id, period=period, start=start, end=end, limit=limit
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
