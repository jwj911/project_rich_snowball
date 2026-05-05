"""批量写入。本模块不执行 commit，commit 由 Pipeline/Scheduler 控制。"""
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from models import (
    RealtimeQuoteDB, KlineDataDB, VarietyDB,
    FutDailyDataDB, FutSettleDB, FutWeeklyDetailDB,
    FutWsrDB, FutHoldingDB, FutPriceLimitDB,
)

import logging

logger = logging.getLogger(__name__)


def upsert_realtime(db: Session, data: dict) -> None:
    """写入或更新实时行情。调用方负责 commit。"""
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == data["symbol"]).first()
    if not variety:
        logger.warning(f"Variety not found: {data['symbol']}")
        return

    stmt = insert(RealtimeQuoteDB).values(
        variety_id=variety.id,
        current_price=data["current_price"],
        pre_settlement=data.get("pre_settlement"),
        change_percent=data.get("change_percent"),
        open_price=data.get("open_price"),
        high=data.get("high"),
        low=data.get("low"),
        volume=data.get("volume"),
        open_interest=data.get("open_interest"),
        bid1=data.get("bid1"),
        ask1=data.get("ask1"),
        updated_at=data["updated_at"],
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["variety_id"],
        set_={
            "current_price": data["current_price"],
            "pre_settlement": data.get("pre_settlement"),
            "change_percent": data.get("change_percent"),
            "open_price": data.get("open_price"),
            "high": data.get("high"),
            "low": data.get("low"),
            "volume": data.get("volume"),
            "open_interest": data.get("open_interest"),
            "bid1": data.get("bid1"),
            "ask1": data.get("ask1"),
            "updated_at": data["updated_at"],
        },
    )
    db.execute(stmt)


def insert_kline_bulk(db: Session, rows: list[dict], period: str) -> int:
    """批量写入 K 线。返回实际写入条数。调用方负责 commit。"""
    if not rows:
        return 0

    # 收集所有涉及的 symbol
    symbols = set()
    for row in rows:
        sym = row.get("symbol")
        if sym:
            symbols.add(sym)

    # 单次查询：symbol -> variety_id
    varieties = {
        v.symbol: v.id
        for v in db.query(VarietyDB).filter(VarietyDB.symbol.in_(symbols)).all()
    }

    values = []
    skipped = 0
    for row in rows:
        variety_id = varieties.get(row.get("symbol"))
        if not variety_id:
            skipped += 1
            continue
        values.append({
            "variety_id": variety_id,
            "period": period,
            "trading_time": row["trading_time"],
            "open_price": row["open_price"],
            "high_price": row["high_price"],
            "low_price": row["low_price"],
            "close_price": row["close_price"],
            "volume": row["volume"],
            "open_interest": row.get("open_interest"),
        })

    if not values:
        return 0

    stmt = insert(KlineDataDB).values(values)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["variety_id", "period", "trading_time"]
    )
    result = db.execute(stmt)

    inserted = result.rowcount if hasattr(result, "rowcount") else len(values)
    if skipped:
        logger.warning(f"K-line bulk insert skipped {skipped} rows (variety not found)")
    return inserted


def upsert_fut_daily_bulk(db: Session, rows: list[dict]) -> int:
    """批量写入期货日线/周线/月线数据。"""
    if not rows:
        return 0
    stmt = insert(FutDailyDataDB).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["variety_id", "period", "trade_date"],
        set_={
            "pre_close": stmt.excluded.pre_close,
            "pre_settle": stmt.excluded.pre_settle,
            "open_price": stmt.excluded.open_price,
            "high_price": stmt.excluded.high_price,
            "low_price": stmt.excluded.low_price,
            "close_price": stmt.excluded.close_price,
            "settle": stmt.excluded.settle,
            "change1": stmt.excluded.change1,
            "change2": stmt.excluded.change2,
            "volume": stmt.excluded.volume,
            "amount": stmt.excluded.amount,
            "open_interest": stmt.excluded.open_interest,
            "oi_chg": stmt.excluded.oi_chg,
        },
    )
    result = db.execute(stmt)
    return result.rowcount if hasattr(result, "rowcount") else len(rows)


def upsert_fut_settle_bulk(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = insert(FutSettleDB).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts_code", "trade_date"],
        set_={
            "settle": stmt.excluded.settle,
            "trading_fee_rate": stmt.excluded.trading_fee_rate,
            "trading_fee": stmt.excluded.trading_fee,
            "delivery_fee": stmt.excluded.delivery_fee,
            "b_hedging_margin_rate": stmt.excluded.b_hedging_margin_rate,
            "s_hedging_margin_rate": stmt.excluded.s_hedging_margin_rate,
            "long_margin_rate": stmt.excluded.long_margin_rate,
            "short_margin_rate": stmt.excluded.short_margin_rate,
            "offset_today_fee": stmt.excluded.offset_today_fee,
            "exchange": stmt.excluded.exchange,
        },
    )
    result = db.execute(stmt)
    return result.rowcount if hasattr(result, "rowcount") else len(rows)


def upsert_fut_weekly_detail_bulk(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    inserted = 0
    for row in rows:
        exists = db.query(FutWeeklyDetailDB).filter(
            FutWeeklyDetailDB.week == row.get("week"),
            FutWeeklyDetailDB.prd == row.get("prd"),
            FutWeeklyDetailDB.exchange == row.get("exchange"),
        ).first()
        if exists:
            continue
        db.add(FutWeeklyDetailDB(**row))
        inserted += 1
    return inserted


def upsert_fut_wsr_bulk(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    inserted = 0
    for row in rows:
        exists = db.query(FutWsrDB).filter(
            FutWsrDB.trade_date == row.get("trade_date"),
            FutWsrDB.symbol == row.get("symbol"),
            FutWsrDB.warehouse == row.get("warehouse"),
            FutWsrDB.wh_id == row.get("wh_id"),
        ).first()
        if exists:
            continue
        db.add(FutWsrDB(**row))
        inserted += 1
    return inserted


def upsert_fut_holding_bulk(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    inserted = 0
    for row in rows:
        exists = db.query(FutHoldingDB).filter(
            FutHoldingDB.trade_date == row.get("trade_date"),
            FutHoldingDB.symbol == row.get("symbol"),
            FutHoldingDB.broker == row.get("broker"),
        ).first()
        if exists:
            continue
        db.add(FutHoldingDB(**row))
        inserted += 1
    return inserted


def upsert_fut_price_limit_bulk(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = insert(FutPriceLimitDB).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts_code", "trade_date"],
        set_={
            "up_limit": stmt.excluded.up_limit,
            "down_limit": stmt.excluded.down_limit,
            "exchange": stmt.excluded.exchange,
        },
    )
    result = db.execute(stmt)
    return result.rowcount if hasattr(result, "rowcount") else len(rows)
