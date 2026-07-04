"""批量写入。本模块不执行 commit，commit 由 Pipeline/Scheduler 控制。"""
import logging

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from models import (
    FutContractDB,
    FutDailyDataDB,
    FutHoldingDB,
    FutPriceLimitDB,
    FutSettleDB,
    FutWeeklyDetailDB,
    FutWsrDB,
    KlineDataDB,
    RealtimeQuoteDB,
    VarietyDB,
    engine,
)

logger = logging.getLogger(__name__)


def _dialect_insert(model):
    """根据数据库方言选择正确的 insert 构造器。"""
    if engine.dialect.name == "postgresql":
        return pg_insert(model)
    return sqlite_insert(model)


def upsert_realtime(db: Session, data: dict) -> None:
    """写入或更新实时行情。调用方负责 commit。
    如果 data 中已包含 variety_id，则跳过品种查询（避免 N+1）。
    """
    variety_id = data.get("variety_id")
    if not variety_id:
        variety = db.query(VarietyDB).filter(VarietyDB.symbol == data["symbol"]).first()
        if not variety:
            logger.warning(f"Variety not found: {data['symbol']}")
            return
        variety_id = variety.id

    stmt = _dialect_insert(RealtimeQuoteDB).values(
        variety_id=variety_id,
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
        data_source=data.get("data_source"),
        limit_up=data.get("limit_up"),
        limit_down=data.get("limit_down"),
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
            "data_source": data.get("data_source"),
            "limit_up": data.get("limit_up"),
            "limit_down": data.get("limit_down"),
            "updated_at": data["updated_at"],
        },
    )
    db.execute(stmt)


def insert_kline_bulk(db: Session, rows: list[dict], period: str) -> int:
    """批量写入 K 线。返回实际写入条数。调用方负责 commit。
    如果 row 中包含 contract_code，会尝试匹配 fut_contracts.id 写入 contract_id。
    无法解析 contract_id 的行会被跳过，防止 contract_id=NULL 导致唯一约束失效和重复数据。"""
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
    varieties: dict[str, int] = {
        v.symbol: v.id
        for v in db.query(VarietyDB).filter(VarietyDB.symbol.in_(symbols)).all()
    }

    # 单次查询：contract_code -> contract_id
    # contract_code 通常不含交易所后缀（如 "AU2506"），对应 FutContractDB.symbol
    contracts: dict[str, int] = {}
    if contract_codes:
        from models import FutContractDB
        contracts = {
            c.symbol: c.id
            for c in db.query(FutContractDB).filter(FutContractDB.symbol.in_(contract_codes)).all()
        }
        # 也尝试用 ts_code 匹配（有些 contract_code 可能带后缀如 "AU2506.SHFE"）
        if len(contracts) < len(contract_codes):
            missing = contract_codes - set(contracts.keys())
            by_ts_code = {
                c.ts_code: c.id
                for c in db.query(FutContractDB).filter(FutContractDB.ts_code.in_(missing)).all()
            }
            contracts.update(by_ts_code)

    values = []
    skipped = 0
    unmatched_contracts = set()
    for row in rows:
        variety_id = varieties.get(str(row.get("symbol") or ""))
        if not variety_id:
            skipped += 1
            continue

        contract_code = row.get("contract_code")
        if not contract_code:
            skipped += 1
            continue

        contract_id = contracts.get(contract_code)
        if contract_id is None:
            skipped += 1
            unmatched_contracts.add(contract_code)
            continue

        values.append({
            "variety_id": variety_id,
            "contract_id": contract_id,
            "period": period,
            "trading_time": row["trading_time"],
            "trading_date": row.get("trading_date"),
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
        logger.warning(f"K-line bulk insert skipped {skipped} rows (variety not found or contract unmatched)")
    if unmatched_contracts:
        logger.warning(f"K-line unmatched contracts: {sorted(unmatched_contracts)}")
    return inserted


def upsert_fut_daily_bulk(db: Session, rows: list[dict]) -> int:
    """批量写入期货日线/周线/月线数据。自动拆批避免 PostgreSQL 参数上限。

    同一批次中若存在重复的唯一键 (variety_id, ts_code, period, trade_date)——例如同一
    品种的不同合约被映射到同一品种——会触发 PostgreSQL 的
    "ON CONFLICT DO UPDATE command cannot affect row a second time" 错误。
    此处按唯一键保留最后一条记录，避免批量插入失败。
    """
    if not rows:
        return 0

    # Deduplicate within the whole buffer before splitting into batches.
    seen: dict[tuple[int, str, str, object], dict] = {}
    for row in rows:
        key = (row.get("variety_id"), row.get("ts_code"), row.get("period"), row.get("trade_date"))
        seen[key] = row
    unique_rows = list(seen.values())
    dropped = len(rows) - len(unique_rows)
    if dropped:
        logger.warning(
            f"upsert_fut_daily_bulk dropped {dropped} duplicate rows "
            "(same variety_id/ts_code/period/trade_date within batch)"
        )

    # PostgreSQL 协议参数上限 32767；FutDailyDataDB 每条约 18 个字段，
    # 300 条 ≈ 5400 个参数，留足安全余量。
    batch_size = 300
    total = 0
    for i in range(0, len(unique_rows), batch_size):
        batch = unique_rows[i:i + batch_size]
        stmt = _dialect_insert(FutDailyDataDB).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["variety_id", "ts_code", "period", "trade_date"],
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
        total += result.rowcount if hasattr(result, "rowcount") else len(batch)
    return total


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
