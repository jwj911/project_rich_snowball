"""Walk-forward window planning and execution regressions."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from models import FutContractDB, KlineDataDB, RealtimeQuoteDB, VarietyDB
from services.backtest.walk_forward import (
    WalkForwardConfig,
    build_walk_forward_windows,
    run_walk_forward_validation,
)


def _seed_daily_history(db_session, symbol: str = "WF", bars: int = 210) -> VarietyDB:
    variety = VarietyDB(
        symbol=symbol,
        contract_code=f"{symbol}2601",
        name="Walk-forward 测试品种",
        exchange="SHFE",
        category="测试",
        margin_rate=Decimal("0.10"),
        multiplier=Decimal("10"),
        tick_size=Decimal("1"),
        commission=Decimal("0.0001"),
        is_active=True,
    )
    db_session.add(variety)
    db_session.flush()
    contract = FutContractDB(
        ts_code=f"{symbol}2601.SHF",
        symbol=symbol,
        name="Walk-forward 测试合约",
        fut_code=symbol,
        exchange="SHFE",
        is_active=True,
    )
    db_session.add(contract)
    db_session.add(RealtimeQuoteDB(variety_id=variety.id, current_price=Decimal("100")))
    db_session.flush()

    start = datetime(2025, 1, 1, tzinfo=UTC)
    for index in range(bars):
        close = Decimal("100") + Decimal(index % 25)
        trading_time = start + timedelta(days=index)
        db_session.add(
            KlineDataDB(
                variety_id=variety.id,
                contract_id=contract.id,
                period="1d",
                trading_time=trading_time,
                trading_date=trading_time.date(),
                open_price=close - Decimal("0.5"),
                high_price=close + Decimal("1"),
                low_price=close - Decimal("1"),
                close_price=close,
                volume=1000 + index,
            )
        )
    db_session.commit()
    return variety


def _conditions() -> tuple[list[dict], list[dict]]:
    return (
        [{"indicator": "close", "operator": "greater_than", "value": 0}],
        [{"indicator": "close", "operator": "less_than", "value": 0}],
    )


def test_build_expanding_windows_is_chronological():
    dates = [date(2025, 1, 1) + timedelta(days=index) for index in range(210)]
    windows = build_walk_forward_windows(
        dates,
        WalkForwardConfig(train_bars=90, test_bars=30, step_bars=30, window_mode="expanding", min_windows=2),
    )

    assert len(windows) == 4
    assert windows[0].train_start == dates[0]
    assert windows[0].train_end == dates[89]
    assert windows[0].test_start == dates[90]
    assert windows[0].test_end == dates[119]
    assert windows[1].train_start == dates[0]
    assert windows[1].train_end == dates[119]
    assert windows[1].test_start == dates[120]


def test_build_rolling_windows_keeps_fixed_training_size():
    dates = [date(2025, 1, 1) + timedelta(days=index) for index in range(180)]
    windows = build_walk_forward_windows(
        dates,
        WalkForwardConfig(train_bars=90, test_bars=30, step_bars=30, window_mode="rolling", min_windows=2),
    )

    assert len(windows) == 3
    assert windows[1].train_start == dates[30]
    assert (windows[1].train_end - windows[1].train_start).days == 89


def test_walk_forward_runs_and_captures_window_metrics(db_session):
    variety = _seed_daily_history(db_session)
    entry_conditions, exit_conditions = _conditions()

    result = run_walk_forward_validation(
        db_session,
        symbol=variety.symbol,
        period="1d",
        direction="long",
        entry_conditions=entry_conditions,
        exit_conditions=exit_conditions,
        config=WalkForwardConfig(train_bars=90, test_bars=30, step_bars=30, min_windows=2),
    )

    assert result["status"] == "completed"
    assert result["validation_status"] in {"stable", "unstable"}
    assert result["completed_window_count"] == 4
    assert result["failed_window_count"] == 0
    assert result["data_coverage"]["row_count"] == 210
    assert all(window["train_end"] < window["test_start"] for window in result["windows"])
    assert "metrics" in result["windows"][0]["in_sample"]
    assert "metrics" in result["windows"][0]["out_of_sample"]


def test_insufficient_windows_is_not_a_validation_pass(db_session):
    variety = _seed_daily_history(db_session, symbol="WI", bars=140)
    entry_conditions, exit_conditions = _conditions()

    result = run_walk_forward_validation(
        db_session,
        symbol=variety.symbol,
        period="1d",
        direction="long",
        entry_conditions=entry_conditions,
        exit_conditions=exit_conditions,
        config=WalkForwardConfig(train_bars=90, test_bars=30, step_bars=30, min_windows=2),
    )

    assert result["status"] == "not_run"
    assert result["validation_status"] == "not_run"
    assert result["reason"] == "insufficient_windows"
    assert "未将样本外验证视为通过" in result["warnings"][0]
