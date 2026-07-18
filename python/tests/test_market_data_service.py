"""MarketDataService 单元测试。"""

from __future__ import annotations

import datetime

import pytest

from models import FutMainDailyDataDB, RealtimeQuoteDB, VarietyDB
from services.domain.exceptions import NotFoundError
from services.domain.market_data_service import MarketDataService


@pytest.fixture
def seed_quotes(db_session):
    """为独立测试品种创建实时行情，避免与 seed_varieties 互相污染。"""
    au = VarietyDB(symbol="TESTAU", contract_code="TESTAU2406", name="测试黄金", exchange="SHFE", category="贵金属")
    ag = VarietyDB(symbol="TESTAG", contract_code="TESTAG2406", name="测试白银", exchange="SHFE", category="贵金属")
    cu = VarietyDB(symbol="TESTCU", contract_code="TESTCU2406", name="测试铜", exchange="SHFE", category="有色金属")
    db_session.add_all([au, ag, cu])
    db_session.flush()

    now = datetime.datetime.now(datetime.UTC)
    for v, price, change in [(au, 453.2, 1.25), (ag, 5420.0, -0.85), (cu, 68000.0, 0.0)]:
        db_session.add(RealtimeQuoteDB(
            variety_id=v.id,
            current_price=price,
            change_percent=change,
            open_price=price - 1,
            high=price + 2,
            low=price - 2,
            volume=100000,
            data_source="mock",
            updated_at=now,
        ))
    db_session.flush()
    return {"au": au, "ag": ag, "cu": cu}


def test_get_realtime(db_session, seed_quotes):
    service = MarketDataService(db_session)
    quote = service.get_realtime("TESTAU")
    assert quote["symbol"] == "TESTAU"
    assert float(quote["current_price"]) == pytest.approx(453.2)
    assert quote["delayed"] is False


def test_get_realtime_not_found(db_session):
    service = MarketDataService(db_session)
    with pytest.raises(NotFoundError):
        service.get_realtime("UNKNOWN")


def test_get_realtime_no_quote(db_session):
    service = MarketDataService(db_session)
    # 先创建一个无行情的品种
    variety = VarietyDB(symbol="TESTNOQ", contract_code="TESTNOQ2406", name="无行情", exchange="SHFE", category="测试")
    db_session.add(variety)
    db_session.flush()
    with pytest.raises(NotFoundError):
        service.get_realtime("TESTNOQ")


def test_get_realtime_batch(db_session, seed_quotes):
    service = MarketDataService(db_session)
    quotes, not_found = service.get_realtime_batch(["TESTAU", "TESTAG", "UNKNOWN"])
    assert len(quotes) == 2
    symbols = {q["symbol"] for q in quotes}
    assert symbols == {"TESTAU", "TESTAG"}
    assert not_found == ["UNKNOWN"]


def test_get_realtime_batch_too_many(db_session, seed_quotes):
    service = MarketDataService(db_session)
    from services.domain.exceptions import ServiceError
    with pytest.raises(ServiceError):
        service.get_realtime_batch(["TESTAU"] * 51, max_symbols=50)


def test_get_market_comparison(db_session, seed_quotes):
    service = MarketDataService(db_session)
    result = service.get_market_comparison(["TESTAU", "TESTAG", "TESTCU"])
    assert len(result) == 3
    assert result[0]["symbol"] == "TESTAU"  # 涨幅最大
    assert result[-1]["symbol"] == "TESTAG"  # 跌幅最大


def test_get_varieties_prefers_main_daily_over_realtime(db_session, seed_quotes):
    variety = seed_quotes["au"]
    db_session.add(
        FutMainDailyDataDB(
            variety_id=variety.id,
            ts_code="TESTAU.SHF",
            trade_date=datetime.datetime.now(datetime.UTC),
            pre_settle=450.0,
            settle=460.0,
            open_price=451.0,
            high_price=465.0,
            low_price=448.0,
            close_price=459.0,
            volume=200000,
            period="D",
        )
    )
    db_session.flush()

    items, summary = MarketDataService(db_session).get_varieties_with_realtime(
        search="TESTAU",
        sort_by="change_percent",
        sort_order="desc",
    )

    assert summary["total"] == 1
    assert len(items) == 1
    assert items[0]["current_price"] == pytest.approx(460.0)
    assert items[0]["data_source"] == "fut_main_daily_data"
    assert items[0]["data_freshness"] == "fresh"


def test_get_varieties_falls_back_to_realtime(db_session, seed_quotes):
    items, summary = MarketDataService(db_session).get_varieties_with_realtime(
        search="TESTAG",
        sort_by="change_percent",
        sort_order="desc",
    )

    assert summary["total"] == 1
    assert items[0]["current_price"] == pytest.approx(5420.0)
    assert items[0]["data_source"] == "mock"
    assert items[0]["data_freshness"] == "fresh"


def test_get_varieties_reports_unavailable_data(db_session):
    db_session.add(
        VarietyDB(
            symbol="TESTNO DATA",
            contract_code="TESTNO2406",
            name="无行情",
            exchange="SHFE",
            category="测试",
        )
    )
    db_session.flush()

    items, _ = MarketDataService(db_session).get_varieties_with_realtime(search="TESTNO DATA")

    assert len(items) == 1
    assert items[0]["current_price"] is None
    assert items[0]["data_source"] is None
    assert items[0]["data_freshness"] == "unavailable"


def test_get_data_quality(db_session, seed_quotes):
    service = MarketDataService(db_session)
    result = service.get_data_quality()
    assert result["overall"] == "healthy"
    assert result["total"] >= 3
    assert result["stale_count"] == 0


def test_get_data_quality_by_symbol(db_session, seed_quotes):
    service = MarketDataService(db_session)
    result = service.get_data_quality(symbol="TESTAU")
    assert result["overall"] == "healthy"
    assert len(result["details"]) == 1
    assert result["details"][0]["symbol"] == "TESTAU"
