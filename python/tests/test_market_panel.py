"""raw_contract 日频研究宽表构建与数据目录回归。"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import AgentMarketPanelDailyDB, Base, FutContractDB, FutDailyDataDB, KlineDataDB, VarietyDB
from scripts import rebuild_raw_contract_panel
from services.data_catalog import DataCatalogService
from services.data_quality import DataQualityService
from services.market_panel import rebuild_raw_contract_daily_panel


def _seed_raw_contract_sources(db_session) -> tuple[VarietyDB, FutContractDB]:
    variety = VarietyDB(
        symbol="PANEL",
        contract_code="PANEL2501",
        name="研究宽表测试",
        exchange="TEST",
        category="测试",
        is_active=True,
    )
    contract = FutContractDB(
        ts_code="PANEL2501.TEST",
        symbol="PANEL2501",
        fut_code="PANEL",
        name="研究宽表测试合约",
        exchange="TEST",
        is_active=True,
    )
    db_session.add_all([variety, contract])
    db_session.flush()

    start = datetime(2026, 6, 1, tzinfo=UTC)
    source_rows = [
        (100, 105, 98, 100, 10, None),
        (108, 112, 106, 110, 20, 400),
        (109, 115, 107, 114, 30, 450),
    ]
    for offset, (open_price, high_price, low_price, close_price, volume, open_interest) in enumerate(source_rows):
        timestamp = start + timedelta(days=offset)
        db_session.add(
            KlineDataDB(
                variety_id=variety.id,
                contract_id=contract.id,
                period="1d",
                trading_time=timestamp,
                trading_date=timestamp.date(),
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                open_interest=open_interest,
            )
        )

    db_session.add(
        FutDailyDataDB(
            variety_id=variety.id,
            ts_code=contract.ts_code,
            trade_date=start,
            open_price=100,
            high_price=105,
            low_price=98,
            close_price=100,
            settle=101,
            volume=10,
            amount=1000,
            open_interest=300,
            period="D",
        )
    )
    db_session.commit()
    return variety, contract


def test_rebuild_raw_contract_panel_merges_sources_and_tracks_lineage(db_session):
    variety, contract = _seed_raw_contract_sources(db_session)

    stats = rebuild_raw_contract_daily_panel(db_session, variety_id=variety.id)
    db_session.commit()

    rows = (
        db_session.query(AgentMarketPanelDailyDB)
        .filter(AgentMarketPanelDailyDB.variety_id == variety.id)
        .order_by(AgentMarketPanelDailyDB.trading_date.asc())
        .all()
    )
    assert stats == {"source_rows": 3, "written_rows": 3, "deleted_rows": 0}
    assert len(rows) == 3
    assert rows[0].data_view == "raw_contract"
    assert rows[0].contract_id == contract.id
    assert rows[0].amount == 1000
    assert rows[0].open_interest == 300
    assert rows[0].settlement == 101
    assert rows[0].quality_status == "good"
    assert json.loads(rows[0].source_flags) == {
        "amount": "fut_daily_data",
        "ohlcv": "kline_data",
        "open_interest": "fut_daily_data",
        "settlement": "fut_daily_data",
    }

    assert float(rows[1].amount) == pytest.approx(2200.0)
    assert float(rows[1].ret_1) == pytest.approx(0.1)
    assert float(rows[1].gap) == pytest.approx(0.08)
    assert float(rows[1].volume_ratio_20) == pytest.approx(20 / 15)
    assert rows[1].quality_status == "warning"
    assert json.loads(rows[1].source_flags)["amount"] == "estimated_close_volume"
    assert json.loads(rows[1].source_flags)["open_interest"] == "kline_data"


def test_rebuild_raw_contract_panel_is_idempotent_and_removes_stale_rows(db_session):
    variety, _ = _seed_raw_contract_sources(db_session)
    rebuild_raw_contract_daily_panel(db_session, variety_id=variety.id)
    db_session.commit()

    source_to_remove = (
        db_session.query(KlineDataDB)
        .filter(KlineDataDB.variety_id == variety.id)
        .order_by(KlineDataDB.trading_date.desc())
        .first()
    )
    db_session.delete(source_to_remove)
    db_session.commit()

    stats = rebuild_raw_contract_daily_panel(db_session, variety_id=variety.id)
    db_session.commit()
    row_count = db_session.query(AgentMarketPanelDailyDB).filter_by(variety_id=variety.id).count()

    assert stats == {"source_rows": 2, "written_rows": 2, "deleted_rows": 3}
    assert row_count == 2

    stats = rebuild_raw_contract_daily_panel(db_session, variety_id=variety.id)
    db_session.commit()
    assert stats == {"source_rows": 2, "written_rows": 2, "deleted_rows": 2}
    assert db_session.query(AgentMarketPanelDailyDB).filter_by(variety_id=variety.id).count() == 2


def test_market_panel_is_visible_to_catalog_and_data_quality(db_session):
    variety, _ = _seed_raw_contract_sources(db_session)
    rebuild_raw_contract_daily_panel(db_session, variety_id=variety.id)
    db_session.commit()

    catalog = DataCatalogService(db_session)
    profile = catalog.get_dataset_profile("agent_market_panel_daily")
    coverage = catalog.get_symbol_data_coverage("PANEL")["datasets"]["agent_market_panel_daily"]
    quality = DataQualityService(db_session).check_market_panel("PANEL").to_dict()

    assert profile["row_count"] == 3
    assert profile["quality_status"] == "warning"
    assert "source_flags" in profile["columns"]
    assert coverage == {
        "available": True,
        "row_count": 3,
        "first_date": "2026-06-01",
        "last_date": "2026-06-03",
        "contract_count": 1,
    }
    assert quality["status"] == "warning"
    assert quality["coverage"]["warning_row_count"] == 2


def test_rebuild_script_dry_run_rolls_back(monkeypatch, capsys):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        variety, _ = _seed_raw_contract_sources(session)
        variety_id = variety.id
        monkeypatch.setattr(rebuild_raw_contract_panel, "SessionLocal", lambda: session)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                str(Path(rebuild_raw_contract_panel.__file__)),
                "--symbol",
                variety.symbol,
                "--dry-run",
            ],
        )

        assert rebuild_raw_contract_panel.main() == 0
        output = json.loads(capsys.readouterr().out)

        assert output == {"source_rows": 3, "written_rows": 3, "deleted_rows": 0, "dry_run": True}
        assert session.query(AgentMarketPanelDailyDB).filter_by(variety_id=variety_id).count() == 0
    finally:
        session.close()
        engine.dispose()
