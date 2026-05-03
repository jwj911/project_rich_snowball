from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from models import RealtimeQuoteDB, KlineDataDB, VarietyDB


def upsert_realtime(db: Session, data: dict):
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == data["symbol"]).first()
    if not variety:
        return

    stmt = insert(RealtimeQuoteDB).values(
        variety_id=variety.id,
        current_price=data["current_price"],
        change_percent=data.get("change_percent"),
        open_price=data.get("open_price"),
        high=data.get("high"),
        low=data.get("low"),
        volume=data.get("volume"),
        open_interest=data.get("open_interest"),
        updated_at=data["updated_at"],
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["variety_id"],
        set_={
            "current_price": data["current_price"],
            "change_percent": data.get("change_percent"),
            "high": data.get("high"),
            "low": data.get("low"),
            "volume": data.get("volume"),
            "open_interest": data.get("open_interest"),
            "updated_at": data["updated_at"],
        }
    )
    db.execute(stmt)
    db.commit()


def insert_kline_bulk(db: Session, rows: list, period: str):
    if not rows:
        return

    values = []
    for r in rows:
        variety = db.query(VarietyDB).filter(VarietyDB.symbol == r["symbol"]).first()
        if not variety:
            continue
        values.append({
            "variety_id": variety.id,
            "period": period,
            "trading_time": r["trading_time"],
            "open_price": r["open_price"],
            "high_price": r["high_price"],
            "low_price": r["low_price"],
            "close_price": r["close_price"],
            "volume": r["volume"],
            "open_interest": r.get("open_interest"),
        })

    if not values:
        return

    stmt = insert(KlineDataDB).values(values)
    stmt = stmt.on_conflict_do_nothing(index_elements=["variety_id", "period", "trading_time"])
    db.execute(stmt)
    db.commit()
