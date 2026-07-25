"""PostgreSQL 专项回归：验证 raw_contract 日频研究宽表迁移与幂等重建。"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (
    AgentMarketPanelDailyDB,
    FutContractDB,
    FutDailyDataDB,
    KlineDataDB,
    VarietyDB,
)
from services.market_panel import rebuild_raw_contract_daily_panel

_PG_URL = os.environ.get("_PYTEST_ORIGINAL_DATABASE_URL", "")
_IS_PG = _PG_URL.startswith("postgresql")

if _IS_PG:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    _pg_engine = create_engine(_PG_URL)
    _PgSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_pg_engine)
else:
    _pg_engine = None
    _PgSessionLocal = None


@pytest.fixture(scope="module")
def pg_market_panel_data():
    """创建仅供 PostgreSQL 宽表回归使用的唯一合约数据。"""
    if not _IS_PG or _PgSessionLocal is None:
        pytest.skip("PostgreSQL market-panel regression requires PostgreSQL DATABASE_URL")

    db = _PgSessionLocal()
    suffix = uuid.uuid4().hex[:5].upper()
    symbol = f"PM{suffix}"
    contract_code = f"{symbol}01"
    ts_code = f"{contract_code}.TST"
    start = datetime(2099, 1, 2, tzinfo=UTC)

    variety = VarietyDB(
        symbol=symbol,
        contract_code=contract_code,
        name="PostgreSQL market panel regression",
        exchange="TEST",
        category="test",
        is_active=True,
    )
    contract = FutContractDB(
        ts_code=ts_code,
        symbol=contract_code,
        fut_code=symbol,
        name="PostgreSQL market panel contract",
        exchange="TEST",
        is_active=True,
    )
    db.add_all([variety, contract])
    db.flush()

    for offset, close_price in enumerate((100, 110)):
        timestamp = start + timedelta(days=offset)
        db.add(
            KlineDataDB(
                variety_id=variety.id,
                contract_id=contract.id,
                period="1d",
                trading_time=timestamp,
                trading_date=timestamp.date(),
                open_price=100 + offset,
                high_price=112 + offset,
                low_price=99 + offset,
                close_price=close_price,
                volume=100 * (offset + 1),
                open_interest=1000 + offset,
            )
        )
    db.add(
        FutDailyDataDB(
            variety_id=variety.id,
            ts_code=ts_code,
            trade_date=start,
            open_price=100,
            high_price=112,
            low_price=99,
            close_price=100,
            settle=101,
            volume=100,
            amount=10000,
            open_interest=900,
            period="D",
        )
    )
    db.commit()

    try:
        yield db, variety, contract
    finally:
        db.rollback()
        db.query(AgentMarketPanelDailyDB).filter(AgentMarketPanelDailyDB.variety_id == variety.id).delete(
            synchronize_session=False
        )
        db.query(FutDailyDataDB).filter(FutDailyDataDB.variety_id == variety.id).delete(synchronize_session=False)
        db.query(KlineDataDB).filter(KlineDataDB.variety_id == variety.id).delete(synchronize_session=False)
        db.query(FutContractDB).filter(FutContractDB.id == contract.id).delete(synchronize_session=False)
        db.query(VarietyDB).filter(VarietyDB.id == variety.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_postgres_market_panel_schema_and_rebuild(pg_market_panel_data):
    db, variety, contract = pg_market_panel_data

    inspector = inspect(_pg_engine)
    assert "agent_market_panel_daily" in inspector.get_table_names()
    assert any(
        constraint["name"] == "uix_agent_market_panel_daily"
        and constraint["column_names"] == ["data_view", "variety_id", "contract_id", "period", "trading_date"]
        for constraint in inspector.get_unique_constraints("agent_market_panel_daily")
    )

    assert rebuild_raw_contract_daily_panel(db, variety_id=variety.id)["written_rows"] == 2
    db.commit()
    assert rebuild_raw_contract_daily_panel(db, variety_id=variety.id)["written_rows"] == 2
    db.commit()

    rows = (
        db.query(AgentMarketPanelDailyDB)
        .filter(AgentMarketPanelDailyDB.variety_id == variety.id)
        .order_by(AgentMarketPanelDailyDB.trading_date.asc())
        .all()
    )
    assert len(rows) == 2
    assert rows[0].contract_id == contract.id
    assert float(rows[0].amount) == 10000.0
    assert float(rows[1].ret_1) == pytest.approx(0.1)
    assert rows[1].quality_status == "warning"
