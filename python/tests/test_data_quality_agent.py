"""DataQualityAgent 最小闭环测试。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from models import FutContractDB, KlineDataDB, UserDB, VarietyDB
from services.agent.context import AgentContext
from services.agent.data_quality_agent import DataQualityAgent
from services.agent.executor import AgentExecutor
from services.data_quality import DataQualityService


def _create_user(db_session) -> UserDB:
    user = UserDB(
        username="data_quality_user",
        email="data-quality@example.com",
        password_hash="x",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_variety_with_contract(db_session, symbol: str = "RB") -> tuple[VarietyDB, FutContractDB]:
    variety = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if variety is None:
        variety = VarietyDB(
            symbol=symbol,
            contract_code=f"{symbol}2501",
            name="螺纹钢" if symbol == "RB" else symbol,
            exchange="SHFE",
            category="黑色系",
            is_active=True,
        )
        db_session.add(variety)
        db_session.flush()

    ts_code = f"{symbol}2501.SHF"
    contract = db_session.query(FutContractDB).filter(FutContractDB.ts_code == ts_code).first()
    if contract is None:
        contract = FutContractDB(
            ts_code=ts_code,
            symbol=symbol,
            fut_code=symbol,
            name=variety.name,
            exchange="SHFE",
            is_active=True,
        )
        db_session.add(contract)
    db_session.commit()
    db_session.refresh(variety)
    db_session.refresh(contract)
    db_session.query(KlineDataDB).filter(KlineDataDB.variety_id == variety.id).delete()
    db_session.commit()
    return variety, contract


def _add_daily_kline(
    db_session,
    variety: VarietyDB,
    contract: FutContractDB,
    day_offset: int,
    open_price: float = 3500.0,
    high_price: float = 3520.0,
    low_price: float = 3480.0,
    close_price: float = 3510.0,
    volume: int = 10000,
) -> None:
    base = datetime(2026, 6, 1, tzinfo=UTC)
    trading_time = base + timedelta(days=day_offset)
    db_session.add(
        KlineDataDB(
            variety_id=variety.id,
            contract_id=contract.id,
            period="1d",
            trading_time=trading_time,
            trading_date=trading_time.date(),
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            volume=volume,
        )
    )


def test_data_quality_service_returns_good_for_normal_kline(db_session):
    variety, contract = _create_variety_with_contract(db_session)
    for offset in range(5):
        _add_daily_kline(db_session, variety, contract, offset)
    db_session.commit()

    report = DataQualityService(db_session).check_kline("RB", "1d").to_dict()

    assert report["status"] == "good"
    assert report["score"] == 100
    assert report["coverage"]["row_count"] == 5
    assert report["issues"] == []


def test_data_quality_service_flags_invalid_ohlc(db_session):
    variety, contract = _create_variety_with_contract(db_session)
    _add_daily_kline(
        db_session,
        variety,
        contract,
        0,
        open_price=3500.0,
        high_price=3490.0,
        low_price=3480.0,
        close_price=3510.0,
    )
    db_session.commit()

    report = DataQualityService(db_session).check_kline("RB", "1d").to_dict()

    assert report["status"] == "bad"
    assert any(issue["code"] == "KLINE_INVALID_OHLC" for issue in report["issues"])


def test_data_quality_agent_returns_clear_error_for_missing_data(db_session):
    user = _create_user(db_session)
    _create_variety_with_contract(db_session)
    executor = AgentExecutor(db_session, user.id)
    task_id = executor.create_task("data_quality", "检查 RB 日 K 数据质量")
    agent = DataQualityAgent(AgentContext(db_session, user.id, task_id))

    result = asyncio.run(executor.execute(agent, "检查 RB 日 K 数据质量", task_id=task_id))

    assert result.success is True
    assert result.data["status"] == "bad"
    assert any(issue["code"] == "KLINE_NO_DATA" for issue in result.data["issues"])
    assert "不建议直接用于回测" in result.answer


def test_data_quality_capability_available_without_llm(client, auth_headers, monkeypatch):
    import config

    monkeypatch.setattr(config, "OPENAI_API_KEY", "")

    resp = client.get("/api/agents/status", headers=auth_headers)

    assert resp.status_code == 200
    data_quality = next(item for item in resp.json()["capabilities"] if item["agent_type"] == "data_quality")
    assert data_quality["enabled"] is True
    assert data_quality["requires_llm"] is False
