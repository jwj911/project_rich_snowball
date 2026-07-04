"""MarketDataService 单元测试。"""

from __future__ import annotations

import datetime

import pytest

from models import RealtimeQuoteDB, VarietyDB
from services.domain.exceptions import NotFoundError
from services.domain.market_data_service import MarketDataService


@pytest.fixture
def seed_quotes(db_session, seed_varieties):
    """为部分品种创建实时行情。"""
    au = next(v for v in seed_varieties if v.symbol == "AU")
    ag = next(v for v in seed_varieties if v.symbol == "AG")
    cu = next(v for v in seed_varieties if v.symbol == "CU")

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
    quote = service.get_realtime("AU")
    assert quote["symbol"] == "AU"
    assert float(quote["current_price"]) == pytest.approx(453.2)
    assert quote["delayed"] is False


def test_get_realtime_not_found(db_session, seed_varieties):
    service = MarketDataService(db_session)
    with pytest.raises(NotFoundError):
        service.get_realtime("XX")


def test_get_realtime_no_quote(db_session, seed_varieties):
    service = MarketDataService(db_session)
    # 有品种但无行情
    with pytest.raises(NotFoundError):
        service.get_realtime("RB")


def test_get_realtime_batch(db_session, seed_quotes):
    service = MarketDataService(db_session)
    quotes, not_found = service.get_realtime_batch(["AU", "AG", "UNKNOWN"])
    assert len(quotes) == 2
    symbols = {q["symbol"] for q in quotes}
    assert symbols == {"AU", "AG"}
    assert not_found == ["UNKNOWN"]


def test_get_realtime_batch_too_many(db_session, seed_quotes):
    service = MarketDataService(db_session)
    from services.domain.exceptions import ServiceError
    with pytest.raises(ServiceError):
        service.get_realtime_batch(["AU"] * 51, max_symbols=50)


def test_get_market_comparison(db_session, seed_quotes):
    service = MarketDataService(db_session)
    result = service.get_market_comparison(["AU", "AG", "CU"])
    assert len(result) == 3
    assert result[0]["symbol"] == "AU"  # 涨幅最大
    assert result[-1]["symbol"] == "AG"  # 跌幅最大


def test_get_data_quality(db_session, seed_quotes):
    service = MarketDataService(db_session)
    result = service.get_data_quality()
    assert result["overall"] == "healthy"
    assert result["total"] >= 3
    assert result["stale_count"] == 0


def test_get_data_quality_by_symbol(db_session, seed_quotes):
    service = MarketDataService(db_session)
    result = service.get_data_quality(symbol="AU")
    assert result["overall"] == "healthy"
    assert len(result["details"]) == 1
    assert result["details"][0]["symbol"] == "AU"
