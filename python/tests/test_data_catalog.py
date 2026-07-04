"""Data Catalog 服务与 Agent 工具测试。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import services.agent.data_tools  # noqa: F401 触发工具注册
from models import FutContractDB, KlineDataDB, RealtimeQuoteDB, VarietyDB
from services.agent.context import AgentContext
from services.agent.data_agent import DataAgent
from services.agent.tools import get_tool_registry
from services.data_catalog import DataCatalogService


def _seed_catalog_market_data(db_session) -> tuple[VarietyDB, FutContractDB]:
    symbol = "ZZ"
    variety = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if variety is None:
        variety = VarietyDB(
            symbol=symbol,
            contract_code="ZZ2501",
            name="测试锌指",
            exchange="TEST",
            category="测试",
            is_active=True,
        )
        db_session.add(variety)
        db_session.flush()

    contract = db_session.query(FutContractDB).filter(FutContractDB.ts_code == "ZZ2501.TEST").first()
    if contract is None:
        contract = FutContractDB(
            ts_code="ZZ2501.TEST",
            symbol=symbol,
            fut_code=symbol,
            name=variety.name,
            exchange="TEST",
            is_active=True,
        )
        db_session.add(contract)
        db_session.flush()

    db_session.query(KlineDataDB).filter(KlineDataDB.variety_id == variety.id).delete()
    db_session.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).delete()

    quote = RealtimeQuoteDB(
        variety_id=variety.id,
        current_price=100.0,
        change_percent=1.2,
        open_price=99.0,
        high=101.0,
        low=98.0,
        volume=1000,
        updated_at=datetime.now(UTC),
    )
    db_session.add(quote)

    base = datetime(2026, 6, 1, tzinfo=UTC)
    for offset in range(3):
        ts = base + timedelta(days=offset)
        db_session.add(
            KlineDataDB(
                variety_id=variety.id,
                contract_id=contract.id,
                period="1d",
                trading_time=ts,
                trading_date=ts.date(),
                open_price=100 + offset,
                high_price=102 + offset,
                low_price=99 + offset,
                close_price=101 + offset,
                volume=1000 + offset,
            )
        )

    db_session.commit()
    db_session.refresh(variety)
    db_session.refresh(contract)
    return variety, contract


def test_data_catalog_lists_core_datasets(db_session):
    _seed_catalog_market_data(db_session)

    datasets = DataCatalogService(db_session).list_available_datasets()
    names = {item["dataset_name"] for item in datasets}

    assert "varieties" in names
    assert "kline_data" in names
    assert "realtime_quotes" in names
    assert "backtest_runs" in names
    assert all("quality_status" in item for item in datasets)


def test_data_catalog_profile_contains_coverage_and_columns(db_session):
    _seed_catalog_market_data(db_session)

    profile = DataCatalogService(db_session).get_dataset_profile("kline_data")

    assert profile["dataset_name"] == "kline_data"
    assert profile["row_count"] >= 3
    assert profile["date_coverage"]["first_date"] is not None
    assert profile["symbol_coverage"]["symbol_count"] >= 1
    assert "open_price" in profile["columns"]


def test_data_catalog_symbol_coverage(db_session):
    _seed_catalog_market_data(db_session)

    coverage = DataCatalogService(db_session).get_symbol_data_coverage("ZZ", period="1d")

    assert coverage["symbol"] == "ZZ"
    assert coverage["datasets"]["varieties"]["available"] is True
    assert coverage["datasets"]["realtime_quotes"]["available"] is True
    assert coverage["datasets"]["kline_data"]["row_count"] == 3


def test_data_catalog_tools_are_registered_and_executable(db_session, seed_user):
    _seed_catalog_market_data(db_session)
    registry = get_tool_registry()
    context = AgentContext(db_session, seed_user.id)

    list_result = asyncio.run(registry.execute("list_available_datasets", context, {}))
    profile_result = asyncio.run(registry.execute("get_dataset_profile", context, {"dataset_name": "kline_data"}))
    coverage_result = asyncio.run(
        registry.execute("get_symbol_data_coverage", context, {"symbol": "ZZ", "period": "1d"})
    )

    assert any(item["dataset_name"] == "kline_data" for item in list_result)
    assert profile_result["dataset_name"] == "kline_data"
    assert coverage_result["datasets"]["kline_data"]["available"] is True


def test_data_agent_fallback_answers_available_datasets(db_session, seed_user, monkeypatch):
    import config

    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    _seed_catalog_market_data(db_session)

    result = asyncio.run(DataAgent(AgentContext(db_session, seed_user.id)).run("现在库里有哪些可用数据"))

    assert result.success is True
    assert "当前可用数据集" in result.answer
    assert "kline_data" in result.answer
    assert result.data["result"][0]["dataset_name"] == "varieties"
