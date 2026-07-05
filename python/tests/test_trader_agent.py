"""交易员 Agent 集成测试。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import numpy as np

from models import FutContractDB, KlineDataDB, RealtimeQuoteDB, UserDB, VarietyDB
from services.agent.context import AgentContext
from services.agent.core import AgentResult, AgentStatus
from services.agent.executor import AgentExecutor
from services.agent.trader_agent import TraderAgent


def _create_user(db_session) -> UserDB:
    user = UserDB(
        username="trader_test_user",
        email="trader-test@example.com",
        password_hash="x",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _seed_variety_and_contracts(db_session) -> tuple[VarietyDB, FutContractDB]:
    # 使用唯一标识避免与其他测试的品种数据冲突
    symbol = "TRB"
    contract_code = "TRB2501"

    existing = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if existing:
        contract = db_session.query(FutContractDB).filter(FutContractDB.symbol == symbol).first()
        return existing, contract

    variety = VarietyDB(
        symbol=symbol,
        contract_code=contract_code,
        name="测试螺纹钢",
        exchange="SHFE",
        category="黑色系",
        tick_size=1.0,
        multiplier=10.0,
        margin_rate=0.1,
        is_active=True,
    )
    db_session.add(variety)
    db_session.commit()
    db_session.refresh(variety)

    contract = FutContractDB(
        ts_code=f"{contract_code}.SHF",
        symbol=symbol,
        name="测试螺纹钢2501",
        fut_code=symbol,
        exchange="SHFE",
        multiplier=10.0,
    )
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(contract)

    return variety, contract


def _seed_klines(
    db_session,
    variety: VarietyDB,
    contract: FutContractDB,
    period: str,
    n: int,
    start_price: float = 3000.0,
    trend: float = 1.0,
) -> None:
    """生成并写入 K 线数据。"""
    np.random.seed(hash(period) % 2**32)
    base = np.linspace(start_price, start_price + trend * n * 5, n)
    noise = np.random.normal(0, 3, n)
    close = base + noise
    high = close + np.abs(np.random.normal(1, 0.5, n))
    low = close - np.abs(np.random.normal(1, 0.5, n))
    open_ = close + np.random.normal(0, 1, n)

    if period == "1d":
        start_time = datetime(2026, 1, 1, tzinfo=UTC)
        delta = timedelta(days=1)
    elif period == "4h":
        start_time = datetime(2026, 1, 1, tzinfo=UTC)
        delta = timedelta(hours=4)
    elif period == "1h":
        start_time = datetime(2026, 1, 1, tzinfo=UTC)
        delta = timedelta(hours=1)
    elif period == "15m":
        start_time = datetime(2026, 1, 1, tzinfo=UTC)
        delta = timedelta(minutes=15)
    else:
        start_time = datetime(2026, 1, 1, tzinfo=UTC)
        delta = timedelta(minutes=5)

    for i in range(n):
        kline = KlineDataDB(
            variety_id=variety.id,
            contract_id=contract.id,
            period=period,
            trading_time=start_time + i * delta,
            trading_date=(start_time + i * delta).date(),
            open_price=float(open_[i]),
            high_price=float(high[i]),
            low_price=float(low[i]),
            close_price=float(close[i]),
            volume=int(np.random.randint(10000, 50000)),
            open_interest=int(np.random.randint(100000, 200000)),
        )
        db_session.add(kline)
    db_session.commit()


def _seed_realtime_quote(db_session, variety: VarietyDB, price: float) -> None:
    quote = RealtimeQuoteDB(
        variety_id=variety.id,
        current_price=price,
        pre_settlement=price - 10,
        change_percent=0.5,
        open_price=price - 5,
        high=price + 10,
        low=price - 10,
        volume=100000,
        open_interest=150000,
        updated_at=datetime.now(UTC),
    )
    db_session.add(quote)
    db_session.commit()


class TestTraderAgent:
    """交易员 Agent 集成测试。"""

    def test_run_with_uptrend_generates_long_plan(self, db_session):
        user = _create_user(db_session)
        variety, contract = _seed_variety_and_contracts(db_session)

        for period, n in [("1d", 80), ("4h", 80), ("1h", 80), ("15m", 80)]:
            _seed_klines(db_session, variety, contract, period, n, start_price=3000.0, trend=1.0)

        _seed_realtime_quote(db_session, variety, 3400.0)

        # resolve_symbol 会优先匹配大写字母代码，query 中需包含品种代码 TRB
        query = "帮我看看 TRB 今天的日内波段机会"

        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("trader", "帮我看看螺纹钢今天的日内波段机会")
        agent = TraderAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, query, task_id=task_id))

        assert isinstance(result, AgentResult)
        assert result.status == AgentStatus.COMPLETED
        assert result.success is True
        assert "交易研判" in result.answer
        assert result.data["symbol"] == "TRB"
        assert result.data["trade_plan"] is not None
        assert result.data["trade_plan"]["direction"] == "long"
        assert result.data["risk_validation"]["valid"] is True

    def test_run_with_insufficient_data_fails_gracefully(self, db_session):
        user = _create_user(db_session)
        variety, contract = _seed_variety_and_contracts(db_session)

        # 只写入少量数据
        _seed_klines(db_session, variety, contract, "1d", 5)
        _seed_realtime_quote(db_session, variety, 3400.0)

        query = "帮我看看 TRB 今天的日内波段机会"
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("trader", query)
        agent = TraderAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, query, task_id=task_id))

        assert isinstance(result, AgentResult)
        assert result.status == AgentStatus.FAILED
        assert "K 线数据" in result.error_message or "数据" in result.error_message

    def test_run_without_symbol_fails(self, db_session):
        user = _create_user(db_session)
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("trader", "今天有什么交易机会")
        agent = TraderAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "今天有什么交易机会", task_id=task_id))

        assert result.status == AgentStatus.FAILED
        assert "品种" in result.error_message or "识别" in result.error_message


class TestTraderAgentRouter:
    """交易员 Agent 路由集成测试。"""

    def test_create_task_with_trader_type(self, client, auth_headers):
        resp = client.post(
            "/api/agents/tasks",
            json={"agent_type": "trader", "query": "帮我看看螺纹钢日内波段机会"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_type"] == "trader"
        assert data["status"] in ("pending", "running", "completed", "failed")

    def test_status_includes_trader_capability(self, client, auth_headers):
        resp = client.get("/api/agents/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        types = [c["agent_type"] for c in data["capabilities"]]
        assert "trader" in types
        trader_cap = next(c for c in data["capabilities"] if c["agent_type"] == "trader")
        assert trader_cap["label"] == "交易员"
        assert trader_cap["enabled"] is True

    def test_permission_heartbeat_includes_trader(self, client, auth_headers):
        resp = client.get("/api/agents/permission-heartbeat", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "trader" in data["allowed_agent_types"]
