"""数据工具测试。

验证 list_active_varieties 排序、品种别名解析和 Tushare 日线回退。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from models import FutMainDailyDataDB, RealtimeQuoteDB, VarietyDB
from services.agent.data_tools import _get_kline_data, _get_realtime_quote, _get_variety_info, _list_active_varieties


@pytest.fixture
def _seed_varieties_and_quotes(db_session):
    """初始化测试品种与行情，用于排序测试。"""
    category = "测试排序"
    specs = [
        ("CU", "铜", category, 5.0),
        ("AL", "铝", category, 3.0),
        ("ZN", "锌", category, 4.0),
        ("RB", "螺纹钢", category, 2.0),
    ]
    for symbol, name, variety_category, change in specs:
        variety = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        if variety is None:
            variety = VarietyDB(
                symbol=symbol,
                contract_code=symbol + "2501",
                name=name,
                exchange="SHFE",
                category=variety_category,
                is_active=True,
            )
            db_session.add(variety)
            db_session.commit()
            db_session.refresh(variety)
        else:
            variety.name = name
            variety.category = variety_category
            variety.is_active = True
            db_session.commit()

        quote = db_session.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
        if quote is None:
            quote = RealtimeQuoteDB(variety_id=variety.id)
            db_session.add(quote)
        quote.current_price = 1000.0
        quote.change_percent = Decimal(str(change))
        quote.volume = int(change * 10000)
        db_session.commit()


class TestListActiveVarieties:
    def test_sort_by_change_percent_desc(self, db_session, _seed_varieties_and_quotes):
        result = _list_active_varieties(
            db_session,
            category="测试排序",
            sort_by="change_percent",
            sort_order="desc",
            limit=5,
        )
        symbols = [r["symbol"] for r in result]
        assert symbols[0] == "CU"

    def test_sort_by_change_percent_asc(self, db_session, _seed_varieties_and_quotes):
        result = _list_active_varieties(
            db_session,
            category="测试排序",
            sort_by="change_percent",
            sort_order="asc",
            limit=5,
        )
        symbols = [r["symbol"] for r in result]
        assert symbols[0] == "RB"

    def test_sort_by_volume_desc(self, db_session, _seed_varieties_and_quotes):
        result = _list_active_varieties(
            db_session,
            category="测试排序",
            sort_by="volume",
            sort_order="desc",
            limit=5,
        )
        symbols = [r["symbol"] for r in result]
        assert symbols[0] == "CU"

    def test_default_sort_by_symbol(self, db_session, _seed_varieties_and_quotes):
        result = _list_active_varieties(db_session, category="测试排序", limit=10)
        symbols = [r["symbol"] for r in result]
        assert symbols == sorted(symbols)


class TestDataToolSymbolResolution:
    def test_get_variety_info_resolves_alias(self, db_session, _seed_varieties_and_quotes):
        info = _get_variety_info(db_session, "铜")
        assert info is not None
        assert info["symbol"] == "CU"

    def test_get_realtime_quote_resolves_alias(self, db_session, _seed_varieties_and_quotes):
        quote = _get_realtime_quote(db_session, "铜")
        assert quote is not None
        assert quote["symbol"] == "CU"

    def test_get_kline_data_resolves_alias(self, db_session, _seed_varieties_and_quotes):
        # 使用一个没有 K 线数据的品种测试别名解析
        variety = VarietyDB(
            symbol="TS99",
            contract_code="TS992501",
            name="测试无数据品种",
            exchange="SHFE",
            category="测试",
            is_active=True,
        )
        db_session.add(variety)
        db_session.commit()
        data = _get_kline_data(db_session, "测试无数据品种")
        assert data == []


class TestDataToolFutMainDailyFallback:
    def test_get_kline_data_reads_fut_main_daily_data_when_kline_table_empty(
        self,
        db_session,
        _seed_varieties_and_quotes,
    ):
        variety = VarietyDB(symbol="FD", contract_code="FD2501", name=" FutMainDaily 测试", exchange="SHFE", category="测试", is_active=True)
        db_session.add(variety)
        db_session.commit()
        db_session.refresh(variety)
        start = datetime(2026, 7, 1, tzinfo=UTC)
        for i in range(3):
            db_session.add(
                FutMainDailyDataDB(
                    variety_id=variety.id,
                    ts_code="FD.SHF",
                    trade_date=start + timedelta(days=i),
                    period="D",
                    open_price=100 + i,
                    high_price=105 + i,
                    low_price=95 + i,
                    close_price=102 + i,
                    volume=1000 + i,
                )
            )
        db_session.commit()

        data = _get_kline_data(db_session, "FD", period="1d", limit=5)

        assert len(data) == 3
        assert data[0]["open"] == 100.0
        assert data[-1]["close"] == 104.0
