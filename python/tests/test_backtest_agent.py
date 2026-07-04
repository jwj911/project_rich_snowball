"""Backtest framework and Agent tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd

from models import FutContractDB, KlineDataDB, VarietyDB
from services.backtest.engine import BacktestConfig, run_backtest


def _sample_bars(count: int = 80) -> pd.DataFrame:
    rows = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(count):
        if i < 25:
            close = 100 - i * 0.3
        elif i < 55:
            close = 92.5 + (i - 25) * 0.8
        else:
            close = 116.5 - (i - 55) * 0.9
        rows.append({
            "time": start + timedelta(days=i),
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000 + i,
        })
    return pd.DataFrame(rows)


def test_backtest_engine_returns_metrics_and_trades():
    result = run_backtest(
        _sample_bars(),
        BacktestConfig(symbol="RB", short_window=5, long_window=20, initial_cash=100_000, quantity=1),
    )

    data = result.to_dict()
    assert data["metrics"]["trade_count"] >= 1
    assert 0 <= data["metrics"]["score"] <= 100
    assert data["equity_curve"]
    assert data["signals"]


def test_backtest_agent_task_runs_from_natural_language(client, auth_headers, db_session):
    variety = db_session.query(VarietyDB).filter(VarietyDB.symbol == "RB").first()
    if variety is None:
        variety = VarietyDB(
            symbol="RB",
            contract_code="RB2601",
            name="螺纹钢",
            exchange="SHFE",
            category="黑色系",
            multiplier=Decimal("10"),
            commission=Decimal("0.0001"),
            is_active=True,
        )
        db_session.add(variety)
        db_session.flush()
    else:
        variety.multiplier = Decimal("10")
        variety.commission = Decimal("0.0001")
        variety.is_active = True
    contract = FutContractDB(
        ts_code="RB2601.SHFE",
        symbol="RB2601",
        name="螺纹钢2601",
        fut_code="RB",
        exchange="SHFE",
        is_active=True,
    )
    db_session.add(contract)
    db_session.flush()

    for i, row in _sample_bars(90).iterrows():
        trade_time = row["time"].to_pydatetime()
        db_session.add(
            KlineDataDB(
                variety_id=variety.id,
                contract_id=contract.id,
                period="1d",
                trading_time=trade_time,
                trading_date=trade_time.date(),
                open_price=Decimal(str(row["open"])),
                high_price=Decimal(str(row["high"])),
                low_price=Decimal(str(row["low"])),
                close_price=Decimal(str(row["close"])),
                volume=int(row["volume"]),
            )
        )
    db_session.commit()

    resp = client.post(
        "/api/agents/tasks",
        json={"agent_type": "backtest", "query": "RB 5/20 均线回测"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "completed"
    assert payload["result"]["data"]["metrics"]["trade_count"] >= 1
    assert "策略回测" in payload["result"]["answer"]
