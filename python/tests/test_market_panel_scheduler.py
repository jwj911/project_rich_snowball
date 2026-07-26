"""日频研究宽表的 worker 调度与重建窗口回归。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from data_collector import scheduler as market_scheduler
from data_collector.job_registry import build_job_configs
from models import ContractRolloverDB, DataIngestionRunDB, FutContractDB, VarietyDB
from services.market_panel import PANEL_BUILD_JOB_NAME, PANEL_BUILD_SOURCE


def _noop():
    return None


def _seed_rollover(db_session, *, effective_date: datetime, created_at: datetime) -> ContractRolloverDB:
    variety = VarietyDB(
        symbol="SCHEDPANEL",
        contract_code="SCHED2505",
        name="调度换月测试",
        exchange="TEST",
        category="测试",
        is_active=True,
    )
    old_contract = FutContractDB(
        ts_code="SCHED2501.TEST",
        symbol="SCHED2501",
        fut_code="SCHEDPANEL",
        exchange="TEST",
        is_active=True,
    )
    new_contract = FutContractDB(
        ts_code="SCHED2505.TEST",
        symbol="SCHED2505",
        fut_code="SCHEDPANEL",
        exchange="TEST",
        is_active=True,
    )
    db_session.add_all([variety, old_contract, new_contract])
    db_session.flush()
    rollover = ContractRolloverDB(
        variety_id=variety.id,
        old_contract_id=old_contract.id,
        new_contract_id=new_contract.id,
        old_contract_code=old_contract.symbol,
        new_contract_code=new_contract.symbol,
        effective_date=effective_date,
        created_at=created_at,
        source="test",
    )
    db_session.add(rollover)
    db_session.commit()
    return rollover


def test_market_panel_window_expands_to_late_rollover_effective_date(db_session, monkeypatch):
    today = date(2026, 7, 31)
    trading_days = [today - timedelta(days=29 - index) for index in range(30)]
    latest_finished_at = datetime(2026, 7, 30, 12, tzinfo=UTC)
    db_session.add(
        DataIngestionRunDB(
            job_name=PANEL_BUILD_JOB_NAME,
            source=PANEL_BUILD_SOURCE,
            started_at=latest_finished_at - timedelta(minutes=5),
            finished_at=latest_finished_at,
            duration_ms=100,
            status="success",
            success_count=1,
            failed_count=0,
            skipped_count=0,
        )
    )
    _seed_rollover(
        db_session,
        effective_date=datetime(2026, 6, 15, tzinfo=UTC),
        created_at=latest_finished_at + timedelta(minutes=1),
    )
    monkeypatch.setattr(market_scheduler, "get_trading_days", lambda start, end: trading_days)

    start_date, end_date, reason = market_scheduler.market_panel_rebuild_window(db_session, today)

    assert start_date == date(2026, 6, 15)
    assert end_date == today
    assert reason == "late_rollover_from_effective_date"


def test_market_panel_window_uses_twenty_day_warmup_without_late_rollover(db_session, monkeypatch):
    today = date(2026, 7, 31)
    trading_days = [today - timedelta(days=29 - index) for index in range(30)]
    monkeypatch.setattr(market_scheduler, "get_trading_days", lambda start, end: trading_days)

    start_date, end_date, reason = market_scheduler.market_panel_rebuild_window(db_session, today)

    assert start_date == trading_days[-20]
    assert end_date == today
    assert reason == "warmup_20_trading_days"


def test_market_panel_job_is_registered_only_when_worker_function_is_supplied():
    common_args = {
        "refresh_realtime_quotes_func": _noop,
        "sync_daily_kline_func": _noop,
        "sync_minute_kline_func": _noop,
        "sync_trading_calendar_func": _noop,
        "sync_variety_metadata_func": _noop,
        "sync_news_func": _noop,
    }
    api_jobs = build_job_configs(**common_args)
    worker_jobs = build_job_configs(**common_args, sync_market_panel_daily_func=_noop)
    panel_job = next(job for job in worker_jobs if job.id == "market_panel_daily")

    assert "market_panel_daily" not in {job.id for job in api_jobs}
    assert panel_job.func is _noop
    assert panel_job.max_instances == 1
    assert panel_job.coalesce is True
    assert "hour='16'" in str(panel_job.trigger)
    assert "minute='18'" in str(panel_job.trigger)


def test_worker_sync_passes_the_computed_window_to_market_panel_builder(db_session, monkeypatch):
    start_date = date(2026, 7, 1)
    end_date = date(2026, 7, 31)
    captured = {}

    monkeypatch.setattr(market_scheduler, "_cn_date", lambda: end_date)
    monkeypatch.setattr(market_scheduler, "is_trading_day", lambda value: True)
    monkeypatch.setattr(market_scheduler, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(
        market_scheduler,
        "market_panel_rebuild_window",
        lambda db: (start_date, end_date, "test_window"),
    )

    from services import market_panel

    def fake_build(db, **kwargs):
        captured.update(kwargs)
        return {"run_id": 99, "written_rows": 12}

    monkeypatch.setattr(market_panel, "run_market_panel_daily_build", fake_build)

    market_scheduler.sync_market_panel_daily()

    assert captured == {
        "start_date": start_date,
        "end_date": end_date,
        "max_attempts": 3,
    }
