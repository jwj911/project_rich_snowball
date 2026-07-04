"""KlineService 单元测试。"""

from __future__ import annotations

import datetime

import pytest

from models import FutContractDB, KlineDataDB, VarietyDB
from services.domain.kline_service import KlineService


@pytest.fixture
def seed_contracts_and_klines(db_session, seed_varieties):
    """为 AU 品种创建合约和多根 K 线。"""
    au = next(v for v in seed_varieties if v.symbol == "AU")
    contract = FutContractDB(
        ts_code="AU2406.SHF",
        symbol="AU2406",
        name="黄金2406",
        exchange="SHFE",
        fut_code="AU",
    )
    db_session.add(contract)
    db_session.flush()

    base_time = datetime.datetime(2099, 1, 1, 10, 0, 0, tzinfo=datetime.UTC)
    for i in range(5):
        db_session.add(KlineDataDB(
            variety_id=au.id,
            contract_id=contract.id,
            period="1h",
            trading_time=base_time + datetime.timedelta(hours=i),
            open_price=500.0 + i,
            high_price=510.0 + i,
            low_price=490.0 + i,
            close_price=505.0 + i,
            volume=1000 + i * 100,
        ))

    # 主力合约 1d 数据
    for i in range(3):
        db_session.add(KlineDataDB(
            variety_id=au.id,
            contract_id=contract.id,
            period="1d",
            trading_time=base_time + datetime.timedelta(days=i),
            open_price=600.0 + i,
            high_price=610.0 + i,
            low_price=590.0 + i,
            close_price=605.0 + i,
            volume=2000 + i * 100,
        ))
    db_session.commit()
    return {"au": au, "contract": contract}


def test_get_klines_default(db_session, seed_contracts_and_klines):
    service = KlineService(db_session)
    rows = service.get_klines("AU", period="1h", limit=10)
    assert len(rows) == 5
    opens = [r["open"] for r in rows]
    assert 500.0 in opens
    assert 504.0 in opens
    assert rows[0]["time"] <= rows[-1]["time"]


def test_get_klines_by_contract(db_session, seed_contracts_and_klines):
    service = KlineService(db_session)
    contract = seed_contracts_and_klines["contract"]
    rows = service.get_klines("AU", period="1h", contract_id=contract.id, limit=10)
    assert len(rows) == 5
    assert all(r["contract_id"] == contract.id for r in rows)


def test_get_main_klines(db_session, seed_contracts_and_klines):
    service = KlineService(db_session)
    rows = service.get_main_klines("AU", period="1d", limit=10)
    assert len(rows) == 3
    opens = [r["open"] for r in rows]
    assert 600.0 in opens


def test_get_continuous_klines(db_session, seed_contracts_and_klines):
    service = KlineService(db_session)
    rows = service.get_continuous_klines("AU", period="1h", limit=10)
    assert len(rows) == 5


def test_calculate_indicators(db_session, seed_contracts_and_klines):
    service = KlineService(db_session)
    rows = service.calculate_indicators("AU", period="1h", limit=10)
    assert len(rows) == 5
    assert "sma5" in rows[-1]
    assert "rsi6" in rows[-1]

    # 指定指标
    rows = service.calculate_indicators("AU", period="1h", indicators=["sma5", "macd_dif"], limit=10)
    assert "sma5" in rows[-1]
    assert "macd_dif" in rows[-1]


def test_get_kline_summary(db_session, seed_contracts_and_klines):
    service = KlineService(db_session)
    result = service.get_kline_summary("AU", periods=["1h", "1d"], limit=10)
    assert "1h" in result
    assert "1d" in result
    assert len(result["1h"]) == 5
    assert len(result["1d"]) == 3


def test_get_klines_variety_not_found(db_session):
    service = KlineService(db_session)
    from services.domain.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        service.get_klines("UNKNOWN", period="1h")
