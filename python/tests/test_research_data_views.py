"""研究宽表视图在因子和回测链路中的回归。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from models import FutContractDB, KlineDataDB, VarietyDB
from services.agent.factor_engine.data_loader import load_panel_data
from services.backtest.service import _backtest_cache_key, run_dsl_backtest
from services.market_panel import MAIN_CONTINUOUS_VIEW, run_market_panel_daily_build
from services.research_data import ResearchDataSelection, parse_research_data_selection


def _seed_research_view_sources(db_session) -> tuple[VarietyDB, FutContractDB]:
    variety = VarietyDB(
        symbol="VIEWBT",
        contract_code="VIEWBT2501",
        name="研究视图回测",
        exchange="TEST",
        category="测试",
        is_active=True,
    )
    contract = FutContractDB(
        ts_code="VIEWBT2501.TEST",
        symbol="VIEWBT2501",
        fut_code="VIEWBT",
        name="研究视图合约",
        exchange="TEST",
        is_active=True,
    )
    db_session.add_all([variety, contract])
    db_session.flush()

    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(35):
        timestamp = start + timedelta(days=index)
        close_price = 100 + index
        db_session.add(
            KlineDataDB(
                variety_id=variety.id,
                contract_id=contract.id,
                period="1d",
                trading_time=timestamp,
                trading_date=timestamp.date(),
                open_price=close_price - 1,
                high_price=close_price + 1,
                low_price=close_price - 2,
                close_price=close_price,
                volume=1000 + index,
                open_interest=5000 + index,
            )
        )
    db_session.commit()
    return variety, contract


def test_market_panel_view_drives_factor_loader_and_dsl_backtest(db_session):
    variety, _ = _seed_research_view_sources(db_session)
    run_market_panel_daily_build(
        db_session,
        variety_id=variety.id,
        data_views=(MAIN_CONTINUOUS_VIEW,),
        max_attempts=1,
    )

    panel = load_panel_data(
        db_session,
        symbols=[variety.symbol],
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 2, 4, tzinfo=UTC),
        min_bars=30,
        data_selection=ResearchDataSelection(data_view=MAIN_CONTINUOUS_VIEW),
    )
    result = run_dsl_backtest(
        db_session,
        symbol=variety.symbol,
        period="1d",
        direction="long",
        entry_conditions=[{"indicator": "close", "operator": "greater_than", "value": 0}],
        exit_conditions=[{"indicator": "close", "operator": "less_than", "value": 0}],
        data_view=MAIN_CONTINUOUS_VIEW,
    )

    assert len(panel.close) == 35
    assert panel.metadata["data_view"] == MAIN_CONTINUOUS_VIEW
    assert result["config"]["data_view"] == MAIN_CONTINUOUS_VIEW
    assert result["data_source"]["dataset_name"] == "agent_market_panel_daily"
    assert result["data_source"]["data_view"] == MAIN_CONTINUOUS_VIEW
    assert result["data_source"]["row_count"] == 35
    assert len(result["data_source"]["build_trace_ids"]) == 1


def test_raw_contract_view_requires_an_explicit_contract_code(db_session):
    variety, contract = _seed_research_view_sources(db_session)
    run_market_panel_daily_build(
        db_session,
        variety_id=variety.id,
        data_views=("raw_contract",),
        max_attempts=1,
    )

    with pytest.raises(ValueError, match="contract_code"):
        run_dsl_backtest(
            db_session,
            symbol=variety.symbol,
            period="1d",
            direction="long",
            entry_conditions=[{"indicator": "close", "operator": "greater_than", "value": 0}],
            exit_conditions=[{"indicator": "close", "operator": "less_than", "value": 0}],
            data_view="raw_contract",
        )

    result = run_dsl_backtest(
        db_session,
        symbol=variety.symbol,
        period="1d",
        direction="long",
        entry_conditions=[{"indicator": "close", "operator": "greater_than", "value": 0}],
        exit_conditions=[{"indicator": "close", "operator": "less_than", "value": 0}],
        data_view="raw_contract",
        contract_code=contract.symbol,
    )
    assert result["data_source"]["contract_code"] == contract.symbol
    assert result["data_source"]["row_count"] == 35


def test_raw_contract_catalog_quality_is_scoped_to_the_selected_contract(db_session):
    variety, contract = _seed_research_view_sources(db_session)
    run_market_panel_daily_build(
        db_session,
        variety_id=variety.id,
        data_views=("raw_contract",),
        max_attempts=1,
    )

    from services.data_catalog import DataCatalogService

    catalog = DataCatalogService(db_session)
    coverage = catalog.get_symbol_data_coverage(
        variety.symbol,
        data_view="raw_contract",
        contract_code="VIEWBT9999",
    )["datasets"]["agent_market_panel_daily"]
    quality = catalog.get_data_quality_summary(
        symbol=variety.symbol,
        dataset_name="agent_market_panel_daily",
        data_view="raw_contract",
        contract_code=contract.symbol,
    )

    assert coverage["row_count"] == 0
    assert quality["scope"]["contract_code"] == contract.symbol
    assert quality["coverage"]["row_count"] == 35


def test_explicit_data_view_selection_and_cache_key_are_distinct():
    selection = parse_research_data_selection("回测 data_view=raw_contract 合约 VIEWBT2501")
    base_args = (
        "VIEWBT",
        "1d",
        "long",
        [{"indicator": "close", "operator": "greater_than", "value": 0}],
        [{"indicator": "close", "operator": "less_than", "value": 0}],
        500,
    )
    legacy_key = _backtest_cache_key(*base_args)
    panel_key = _backtest_cache_key(*base_args, data_view=MAIN_CONTINUOUS_VIEW)

    assert selection == ResearchDataSelection(data_view="raw_contract", contract_code="VIEWBT2501")
    assert legacy_key != panel_key
