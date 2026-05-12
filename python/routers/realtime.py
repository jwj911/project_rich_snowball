from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models import RealtimeQuoteDB, VarietyDB
from schemas import RealtimeResponse
from dependencies import get_db
from services.cache import get_cached

router = APIRouter(prefix="/api/realtime", tags=["实时行情"])


@router.get("/{symbol}", response_model=RealtimeResponse)
def get_realtime(symbol: str, db: Session = Depends(get_db)):
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    def _fetch():
        q = db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
        if not q:
            return None
        # 缓存纯 dict，不存 ORM 实例，避免 detached session 风险
        return {
            "symbol": variety.symbol,
            "current_price": q.current_price,
            "change_percent": q.change_percent or 0,
            "open_price": q.open_price,
            "high": q.high,
            "low": q.low,
            "volume": q.volume,
            "updated_at": q.updated_at,
        }

    quote = get_cached(f"realtime:{symbol}", _fetch)

    if not quote:
        raise HTTPException(status_code=404, detail="暂无实时行情数据")

    return quote
