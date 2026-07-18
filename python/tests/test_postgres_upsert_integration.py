"""
PostgreSQL upsert 集成测试
=========================
验证：第一阶段修复后的 PostgreSQL dialect insert 能真实执行。

运行方式：
    cd python
    $env:SECRET_KEY="test-secret-key-for-local-development-123456"
    $env:ENABLE_SCHEDULER="0"
    $env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
    pytest tests/test_postgres_upsert_integration.py -v

说明：
- 该测试只在 PostgreSQL 环境下执行；SQLite 环境会 skip。
- 使用可控样本，不依赖 Tushare 网络、token、积分或交易日状态。
"""

import datetime
import os
import sys

import pytest
from sqlalchemy import inspect

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-local-development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_collector.upsert import (
    insert_kline_bulk,
    upsert_fut_daily_bulk,
    upsert_fut_main_daily_bulk,
    upsert_fut_price_limit_bulk,
    upsert_fut_settle_bulk,
    upsert_realtime,
)
from models import (
    FutContractDB,
    FutDailyDataDB,
    FutMainDailyDataDB,
    FutPriceLimitDB,
    FutSettleDB,
    KlineDataDB,
    RealtimeQuoteDB,
    VarietyDB,
    init_db,
)

# 动态判断是否需要 PostgreSQL session。
# 注意：不能依赖 models.engine（conftest 会强制设为 SQLite），
# 所以根据原始 DATABASE_URL 环境变量重新创建 PG engine。
_PG_URL = os.environ.get("_PYTEST_ORIGINAL_DATABASE_URL", "")
_IS_PG = "postgresql" in _PG_URL

if _IS_PG:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    _pg_engine = create_engine(_PG_URL)
    PgSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_pg_engine)
else:
    _pg_engine = None
    PgSessionLocal = None


SYMBOL = "TSTPG"
CONTRACT = "TSTPG9901"
TS_CODE = "TSTPG.SHF"
TRADE_DATE = datetime.datetime(2099, 1, 2)


def _cleanup(db):
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == SYMBOL).first()
    if variety:
        db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).delete(synchronize_session=False)
        db.query(KlineDataDB).filter(KlineDataDB.variety_id == variety.id).delete(synchronize_session=False)
        db.query(FutDailyDataDB).filter(FutDailyDataDB.variety_id == variety.id).delete(synchronize_session=False)
        db.query(FutMainDailyDataDB).filter(FutMainDailyDataDB.variety_id == variety.id).delete(
            synchronize_session=False
        )
        db.delete(variety)

    db.query(FutContractDB).filter(FutContractDB.ts_code == TS_CODE).delete(synchronize_session=False)
    db.query(FutSettleDB).filter(FutSettleDB.ts_code == TS_CODE).delete(synchronize_session=False)
    db.query(FutPriceLimitDB).filter(FutPriceLimitDB.ts_code == TS_CODE).delete(synchronize_session=False)
    db.commit()


@pytest.fixture(scope="module")
def pg_db():
    if not _IS_PG or _pg_engine is None:
        pytest.skip("PostgreSQL upsert integration test requires PostgreSQL DATABASE_URL")
    init_db()
    session = PgSessionLocal()
    _cleanup(session)
    variety = VarietyDB(
        symbol=SYMBOL,
        contract_code=CONTRACT,
        name="PostgreSQL Upsert Test",
        exchange="SHFE",
        category="测试",
    )
    session.add(variety)
    session.commit()
    session.refresh(variety)

    contract = FutContractDB(
        ts_code=TS_CODE,
        symbol=CONTRACT,
        name="测试合约",
        fut_code=SYMBOL,
        exchange="SHFE",
        is_active=True,
    )
    session.add(contract)
    session.commit()
    try:
        yield session
    finally:
        _cleanup(session)
        session.close()


def test_postgres_fut_main_daily_schema_matches_upsert_contract(pg_db):
    inspector = inspect(_pg_engine)

    assert "fut_main_daily_data" in inspector.get_table_names()
    unique_constraints = inspector.get_unique_constraints("fut_main_daily_data")
    assert any(
        constraint["name"] == "uix_fut_main_daily"
        and constraint["column_names"] == ["variety_id", "ts_code", "period", "trade_date"]
        for constraint in unique_constraints
    )

    indexes = inspector.get_indexes("fut_main_daily_data")
    assert any(
        index["name"] == "idx_fut_main_daily_lookup"
        and index["column_names"] == ["variety_id", "period", "trade_date"]
        for index in indexes
    )


def test_postgres_realtime_upsert_updates_existing_row(pg_db):
    db = pg_db
    upsert_realtime(
        db,
        {
            "symbol": SYMBOL,
            "current_price": 100.0,
            "pre_settlement": 98.0,
            "change_percent": 1.0,
            "open_price": 99.0,
            "high": 101.0,
            "low": 97.0,
            "volume": 1000,
            "open_interest": 2000,
            "updated_at": TRADE_DATE,
        },
    )
    db.commit()

    upsert_realtime(
        db,
        {
            "symbol": SYMBOL,
            "current_price": 105.0,
            "pre_settlement": 100.0,
            "change_percent": 5.0,
            "open_price": 101.0,
            "high": 106.0,
            "low": 100.0,
            "volume": 1200,
            "open_interest": 2200,
            "updated_at": TRADE_DATE + datetime.timedelta(minutes=1),
        },
    )
    db.commit()

    variety = db.query(VarietyDB).filter(VarietyDB.symbol == SYMBOL).one()
    quotes = db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).all()
    assert len(quotes) == 1
    assert quotes[0].current_price == 105.0
    assert quotes[0].volume == 1200


def test_postgres_kline_insert_conflict_does_nothing(pg_db):
    db = pg_db
    rows = [
        {
            "symbol": SYMBOL,
            "contract_code": CONTRACT,
            "trading_time": TRADE_DATE,
            "open_price": 100.0,
            "high_price": 110.0,
            "low_price": 90.0,
            "close_price": 105.0,
            "volume": 100,
        }
    ]

    inserted = insert_kline_bulk(db, rows, period="1d")
    db.commit()
    duplicate_inserted = insert_kline_bulk(db, rows, period="1d")
    db.commit()

    variety = db.query(VarietyDB).filter(VarietyDB.symbol == SYMBOL).one()
    count = db.query(KlineDataDB).filter(
        KlineDataDB.variety_id == variety.id,
        KlineDataDB.period == "1d",
        KlineDataDB.trading_time == TRADE_DATE,
    ).count()
    assert inserted == 1
    assert duplicate_inserted == 0
    assert count == 1


def test_postgres_fut_daily_upsert_updates_existing_row(pg_db):
    db = pg_db
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == SYMBOL).one()
    base = {
        "variety_id": variety.id,
        "ts_code": TS_CODE,
        "trade_date": TRADE_DATE,
        "pre_close": 99.0,
        "pre_settle": 98.0,
        "open_price": 100.0,
        "high_price": 110.0,
        "low_price": 90.0,
        "close_price": 105.0,
        "settle": 104.0,
        "change1": 6.0,
        "change2": 7.0,
        "volume": 1000,
        "amount": 12345.0,
        "open_interest": 2000,
        "oi_chg": 10,
        "period": "D",
    }

    assert upsert_fut_daily_bulk(db, [base]) == 1
    db.commit()
    updated = dict(base, close_price=108.0, volume=1300)
    assert upsert_fut_daily_bulk(db, [updated]) == 1
    db.commit()

    row = db.query(FutDailyDataDB).filter(
        FutDailyDataDB.variety_id == variety.id,
        FutDailyDataDB.period == "D",
        FutDailyDataDB.trade_date == TRADE_DATE,
    ).one()
    assert row.close_price == 108.0
    assert row.volume == 1300


def test_postgres_fut_main_daily_upsert_updates_existing_row(pg_db):
    db = pg_db
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == SYMBOL).one()
    base = {
        "variety_id": variety.id,
        "ts_code": TS_CODE,
        "trade_date": TRADE_DATE,
        "pre_close": 99.0,
        "pre_settle": 98.0,
        "open_price": 100.0,
        "high_price": 110.0,
        "low_price": 90.0,
        "close_price": 105.0,
        "settle": 104.0,
        "change1": 6.0,
        "change2": 7.0,
        "volume": 1000,
        "amount": 12345.0,
        "open_interest": 2000,
        "oi_chg": 10,
        "period": "D",
    }

    assert upsert_fut_main_daily_bulk(db, [base]) == 1
    db.commit()
    updated = dict(base, close_price=108.0, settle=107.0, volume=1300)
    assert upsert_fut_main_daily_bulk(db, [updated]) == 1
    db.commit()

    row = db.query(FutMainDailyDataDB).filter(
        FutMainDailyDataDB.variety_id == variety.id,
        FutMainDailyDataDB.period == "D",
        FutMainDailyDataDB.trade_date == TRADE_DATE,
    ).one()
    assert row.close_price == 108.0
    assert row.settle == 107.0
    assert row.volume == 1300


def test_postgres_fut_settle_upsert_updates_existing_row(pg_db):
    db = pg_db
    base = {
        "ts_code": TS_CODE,
        "trade_date": TRADE_DATE,
        "settle": 100.0,
        "trading_fee_rate": 0.01,
        "trading_fee": 2.0,
        "delivery_fee": 3.0,
        "b_hedging_margin_rate": 0.1,
        "s_hedging_margin_rate": 0.1,
        "long_margin_rate": 0.2,
        "short_margin_rate": 0.2,
        "offset_today_fee": 1.0,
        "exchange": "SHFE",
    }

    assert upsert_fut_settle_bulk(db, [base]) == 1
    db.commit()
    assert upsert_fut_settle_bulk(db, [dict(base, settle=101.5, trading_fee=2.5)]) == 1
    db.commit()

    row = db.query(FutSettleDB).filter(FutSettleDB.ts_code == TS_CODE, FutSettleDB.trade_date == TRADE_DATE).one()
    assert float(row.settle) == 101.5
    assert row.trading_fee == 2.5


def test_postgres_fut_price_limit_upsert_updates_existing_row(pg_db):
    db = pg_db
    base = {
        "ts_code": TS_CODE,
        "trade_date": TRADE_DATE,
        "name": "测试合约",
        "up_limit": 120.0,
        "down_limit": 80.0,
        "m_ratio": 0.1,
        "cont": "主力",
        "exchange": "SHFE",
    }

    assert upsert_fut_price_limit_bulk(db, [base]) == 1
    db.commit()
    assert upsert_fut_price_limit_bulk(db, [dict(base, up_limit=125.0, down_limit=85.0)]) == 1
    db.commit()

    row = db.query(FutPriceLimitDB).filter(
        FutPriceLimitDB.ts_code == TS_CODE,
        FutPriceLimitDB.trade_date == TRADE_DATE,
    ).one()
    assert row.up_limit == 125.0
    assert row.down_limit == 85.0
