"""批量写入。本模块不执行 commit，commit 由 Pipeline/Scheduler 控制。"""
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import (
    RealtimeQuoteDB, KlineDataDB, VarietyDB,
    FutDailyDataDB, FutSettleDB, FutWeeklyDetailDB,
    FutWsrDB, FutHoldingDB, FutPriceLimitDB,
    FutContractDB,
    engine,
)

import logging

logger = logging.getLogger(__name__)


def _dialect_insert(model):
    """根据数据库方言选择正确的 insert 构造器。"""
    if engine.dialect.name == "postgresql":
        return pg_insert(model)
    return sqlite_insert(model)


def upsert_realtime(db: Session, data: dict) -> None:
    """写入或更新实时行情。调用方负责 commit。"""
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == data["symbol"]).first()
    if not variety:
        logger.warning(f"Variety not found: {data['symbol']}")
        return

    stmt = _dialect_insert(RealtimeQuoteDB).values(
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
    """批量写入 K 线。返回实际写入条数。调用方负责 commit。
    如果 row 中包含 contract_code，会尝试匹配 fut_contracts.id 写入 contract_id。"""
    if not rows:
        return 0

    # 收集所有涉及的 symbol 和 contract_code
    symbols = set()
    contract_codes = set()
    for row in rows:
        sym = row.get("symbol")
        if sym:
            symbols.add(sym)
        cc = row.get("contract_code")
        if cc:
            contract_codes.add(cc)

    # 单次查询：symbol -> variety_id
    varieties = {
        v.symbol: v.id
        for v in db.query(VarietyDB).filter(VarietyDB.symbol.in_(symbols)).all()
    }

    # 单次查询：contract_code -> contract_id
    # contract_code 通常不含交易所后缀（如 "AU2506"），对应 FutContractDB.symbol
    contracts = {}
    if contract_codes:
        from models import FutContractDB
        contracts = {
            c.symbol: c.id
            for c in db.query(FutContractDB).filter(FutContractDB.symbol.in_(contract_codes)).all()
        }
        # 也尝试用 ts_code 匹配（有些 contract_code 可能带后缀如 "AU2506.SHF"）
        if len(contracts) < len(contract_codes):
            missing = contract_codes - set(contracts.keys())
            by_ts_code = {
                c.ts_code: c.id
                for c in db.query(FutContractDB).filter(FutContractDB.ts_code.in_(missing)).all()
            }
            contracts.update(by_ts_code)

    values = []
    skipped = 0
    for row in rows:
        variety_id = varieties.get(row.get("symbol"))
        if not variety_id:
            skipped += 1
            continue
        contract_id = contracts.get(row.get("contract_code")) if row.get("contract_code") else None
        values.append({
            "variety_id": variety_id,
            "contract_id": contract_id,
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

    stmt = _dialect_insert(KlineDataDB).values(values)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["variety_id", "contract_id", "period", "trading_time"]
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
    stmt = _dialect_insert(FutDailyDataDB).values(rows)
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
    stmt = _dialect_insert(FutSettleDB).values(rows)
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
    stmt = _dialect_insert(FutWeeklyDetailDB).values(rows)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["week", "prd", "exchange"]
    )
    result = db.execute(stmt)
    return result.rowcount if hasattr(result, "rowcount") else len(rows)


def upsert_fut_wsr_bulk(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = _dialect_insert(FutWsrDB).values(rows)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["trade_date", "symbol", "warehouse", "wh_id"]
    )
    result = db.execute(stmt)
    return result.rowcount if hasattr(result, "rowcount") else len(rows)


def upsert_fut_holding_bulk(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = _dialect_insert(FutHoldingDB).values(rows)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["trade_date", "symbol", "broker"]
    )
    result = db.execute(stmt)
    return result.rowcount if hasattr(result, "rowcount") else len(rows)


def upsert_fut_contract_bulk(db: Session, rows: list[dict]) -> int:
    """批量写入或更新期货合约元数据。"""
    if not rows:
        return 0
    stmt = _dialect_insert(FutContractDB).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts_code"],
        set_={
            "symbol": stmt.excluded.symbol,
            "name": stmt.excluded.name,
            "fut_code": stmt.excluded.fut_code,
            "exchange": stmt.excluded.exchange,
            "list_date": stmt.excluded.list_date,
            "delist_date": stmt.excluded.delist_date,
            "multiplier": stmt.excluded.multiplier,
            "trade_unit": stmt.excluded.trade_unit,
            "per_unit": stmt.excluded.per_unit,
            "quote_unit": stmt.excluded.quote_unit,
            "d_month": stmt.excluded.d_month,
            "contract_type": stmt.excluded.contract_type,
            "is_active": stmt.excluded.is_active,
            "updated_at": func.now(),
        },
    )
    result = db.execute(stmt)
    return result.rowcount if hasattr(result, "rowcount") else len(rows)


def upsert_fut_price_limit_bulk(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = _dialect_insert(FutPriceLimitDB).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ts_code", "trade_date"],
        set_={
            "name": stmt.excluded.name,
            "up_limit": stmt.excluded.up_limit,
            "down_limit": stmt.excluded.down_limit,
            "m_ratio": stmt.excluded.m_ratio,
            "cont": stmt.excluded.cont,
            "exchange": stmt.excluded.exchange,
        },
    )
    result = db.execute(stmt)
    return result.rowcount if hasattr(result, "rowcount") else len(rows)
