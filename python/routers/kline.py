from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from models import KlineDataDB, VarietyDB
from schemas import KlineResponse
from dependencies import get_db

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
