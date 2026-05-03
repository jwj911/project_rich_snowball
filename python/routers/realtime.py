from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models import RealtimeQuoteDB, VarietyDB
from schemas import RealtimeResponse
from dependencies import get_db

router = APIRouter(prefix="/api/realtime", tags=["实时行情"])


@router.get("/{symbol}", response_model=RealtimeResponse)
def get_realtime(symbol: str, db: Session = Depends(get_db)):
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    quote = db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="暂无实时行情数据")

    return {
        "symbol": variety.symbol,
        "current_price": quote.current_price,
        "change_percent": quote.change_percent or 0,
        "open_price": quote.open_price,
        "high": quote.high,
        "low": quote.low,
        "volume": quote.volume,
        "updated_at": quote.updated_at,
    }
