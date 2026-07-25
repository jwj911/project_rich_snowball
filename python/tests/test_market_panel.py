"""raw_contract 日频研究宽表构建与数据目录回归。"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

import services.market_panel as market_panel
from models import (
    AgentMarketPanelDailyDB,
    Base,
    DataIngestionRunDB,
    FutContractDB,
    FutDailyDataDB,
    KlineDataDB,
    VarietyDB,
)
from scripts import rebuild_raw_contract_panel
from services.data_catalog import DataCatalogService
from services.data_quality import DataQualityService
from services.market_panel import MarketPanelBuildError, rebuild_raw_contract_daily_panel, run_raw_contract_daily_panel_build


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


def test_panel_build_records_quality_snapshot(db_session):
    variety, _ = _seed_raw_contract_sources(db_session)
    variety_id = variety.id

    result = run_raw_contract_daily_panel_build(db_session, variety_id=variety_id, max_attempts=1)
    run = db_session.get(DataIngestionRunDB, result["run_id"])
    assert run is not None
    metadata = json.loads(run.metadata_json)

    assert result["run_id"] == run.id
    assert result["attempt_count"] == 1
    assert run.source == market_panel.PANEL_BUILD_SOURCE
    assert run.status == "success"
    assert run.success_count == 3
    assert run.failed_count == 0
    assert metadata["data_view"] == "raw_contract"
    assert metadata["period"] == "1d"
    assert metadata["variety_id"] == variety_id
    assert metadata["build_stats"] == {"deleted_rows": 0, "source_rows": 3, "written_rows": 3}
    assert metadata["quality_snapshot"]["status"] == "warning"
    assert metadata["quality_snapshot"]["coverage"]["warning_row_count"] == 2
    assert metadata["quality_snapshot"]["issue_codes"] == ["MARKET_PANEL_WARNING_ROWS"]


def test_panel_build_retries_retryable_failure_and_records_each_attempt(db_session, monkeypatch):
    variety, _ = _seed_raw_contract_sources(db_session)
    variety_id = variety.id
    original_rebuild = market_panel.rebuild_raw_contract_daily_panel
    previous_run_id = db_session.query(DataIngestionRunDB.id).order_by(DataIngestionRunDB.id.desc()).scalar() or 0
    call_count = 0

    def transient_rebuild(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OperationalError("SELECT 1", {}, ConnectionError("temporary database connection failure"))
        return original_rebuild(*args, **kwargs)

    monkeypatch.setattr(market_panel, "rebuild_raw_contract_daily_panel", transient_rebuild)

    result = market_panel.run_raw_contract_daily_panel_build(
        db_session,
        variety_id=variety_id,
        max_attempts=2,
        retry_delay_seconds=0,
    )
    runs = (
        db_session.query(DataIngestionRunDB)
        .filter(
            DataIngestionRunDB.job_name == market_panel.PANEL_BUILD_JOB_NAME,
            DataIngestionRunDB.id > previous_run_id,
        )
        .order_by(DataIngestionRunDB.id.asc())
        .all()
    )
    failed_metadata = json.loads(runs[0].metadata_json)
    success_metadata = json.loads(runs[1].metadata_json)

    assert result["attempt_count"] == 2
    assert call_count == 2
    assert [run.status for run in runs] == ["failed", "success"]
    assert runs[0].failed_count == 1
    assert "temporary database connection failure" not in (runs[0].error_message or "")
    assert failed_metadata["error_type"] == "OperationalError"
    assert failed_metadata["retryable"] is True
    assert failed_metadata["retry_delay_seconds"] == 0
    assert success_metadata["attempt"] == 2
    assert success_metadata["quality_snapshot"]["status"] == "warning"


def test_panel_build_persists_nonretryable_failure_without_raw_error_details(db_session, monkeypatch):
    variety, _ = _seed_raw_contract_sources(db_session)
    variety_id = variety.id
    previous_run_id = db_session.query(DataIngestionRunDB.id).order_by(DataIngestionRunDB.id.desc()).scalar() or 0

    def invalid_rebuild(*args, **kwargs):
        raise ValueError("unexpected raw market value 12345")

    monkeypatch.setattr(market_panel, "rebuild_raw_contract_daily_panel", invalid_rebuild)

    with pytest.raises(MarketPanelBuildError) as error:
        market_panel.run_raw_contract_daily_panel_build(
            db_session,
            variety_id=variety_id,
            max_attempts=3,
            retry_delay_seconds=0,
        )

    run = (
        db_session.query(DataIngestionRunDB)
        .filter(
            DataIngestionRunDB.job_name == market_panel.PANEL_BUILD_JOB_NAME,
            DataIngestionRunDB.id > previous_run_id,
        )
        .one()
    )
    metadata = json.loads(run.metadata_json)

    assert error.value.attempt_count == 1
    assert run.status == "failed"
    assert run.failed_count == 1
    assert "12345" not in (run.error_message or "")
    assert "12345" not in str(error.value)
    assert metadata["error_type"] == "ValueError"
    assert metadata["retryable"] is False


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

        assert output["source_rows"] == 3
        assert output["written_rows"] == 3
        assert output["deleted_rows"] == 0
        assert output["attempt_count"] == 1
        assert output["run_id"] is None
        assert output["quality_snapshot"]["status"] == "warning"
        assert output["dry_run"] is True
        assert session.query(AgentMarketPanelDailyDB).filter_by(variety_id=variety_id).count() == 0
        assert session.query(DataIngestionRunDB).count() == 0
    finally:
        session.close()
        engine.dispose()


def test_rebuild_script_returns_sanitized_build_failure(monkeypatch, capsys):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        variety, _ = _seed_raw_contract_sources(session)

        def fail_build(*args, **kwargs):
            raise MarketPanelBuildError("trace_for_test", "ValueError", 1)

        monkeypatch.setattr(rebuild_raw_contract_panel, "SessionLocal", lambda: session)
        monkeypatch.setattr(rebuild_raw_contract_panel, "run_raw_contract_daily_panel_build", fail_build)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                str(Path(rebuild_raw_contract_panel.__file__)),
                "--symbol",
                variety.symbol,
            ],
        )

        assert rebuild_raw_contract_panel.main() == 1
        assert json.loads(capsys.readouterr().out) == {
            "error": "market_panel_build_failed",
            "error_type": "ValueError",
            "trace_id": "trace_for_test",
        }
    finally:
        session.close()
        engine.dispose()
