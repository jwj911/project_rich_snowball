"""TechAnalysisAgent 输出结构测试。

验证技术分析报告必须包含任务要求的所有字段。
"""

from __future__ import annotations

import asyncio
from datetime import timezone, timedelta, datetime

import numpy as np
import pytest

from models import AgentTaskDB, FutContractDB, KlineDataDB, RealtimeQuoteDB, UserDB, VarietyDB
from services.agent.context import AgentContext
from services.agent.executor import AgentExecutor
from services.agent.tech_analysis_agent import TechAnalysisAgent


@pytest.fixture
def _seed_tech_analysis_data(db_session):
    """创建测试品种、行情和 K 线数据。"""
    user = UserDB(username="tech_output_user", email="tech-output@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    symbol = "RB"
    variety = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if variety is None:
        variety = VarietyDB(
            symbol=symbol,
            contract_code=symbol + "2501",
            name="螺纹钢",
            exchange="SHFE",
            category="黑色系",
            margin_rate=8.0,
            is_active=True,
        )
        db_session.add(variety)
    else:
        variety.name = "螺纹钢"
        variety.exchange = "SHFE"
        variety.category = "黑色系"
        variety.is_active = True
    db_session.commit()
    db_session.refresh(variety)

    contract = FutContractDB(
        ts_code=symbol + "2501.SHF",
        symbol=symbol,
        name="螺纹钢",
        exchange="SHFE",
        fut_code=symbol,
        is_active=True,
    )
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(contract)

    quote = db_session.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
    if quote is None:
        quote = RealtimeQuoteDB(variety_id=variety.id)
        db_session.add(quote)
    quote.current_price = 3500.0
    quote.change_percent = 1.5
    quote.open_price = 3450.0
    quote.high = 3550.0
    quote.low = 3440.0
    quote.volume = 150000
    db_session.commit()

    base_prices = np.linspace(3300, 3600, 60)
    for i in range(60):
        close = base_prices[i] + np.random.normal(0, 20)
        open_p = close + np.random.normal(0, 15)
        high = max(open_p, close) + np.random.uniform(10, 30)
        low = min(open_p, close) - np.random.uniform(10, 30)
        kline = KlineDataDB(
            variety_id=variety.id,
            contract_id=contract.id,
            period="1d",
            trading_time=datetime.now(timezone.utc) - timedelta(days=60 - i),
            trading_date=(datetime.now(timezone.utc) - timedelta(days=60 - i)).date(),
            open_price=round(open_p, 2),
            high_price=round(high, 2),
            low_price=round(low, 2),
            close_price=round(close, 2),
            volume=int(np.random.uniform(10000, 50000)),
        )
        db_session.add(kline)
    db_session.commit()

    return user


class TestTechAnalysisOutput:
    REQUIRED_FIELDS = {
        "direction",
        "bias",
        "money_flow",
        "kline_trend",
        "score",
        "rating",
        "key_levels",
        "risk_note",
    }

    def test_output_contains_all_required_fields(self, db_session, _seed_tech_analysis_data):
        user = _seed_tech_analysis_data
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("tech_analysis", "分析螺纹钢日线")
        agent = TechAnalysisAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "分析螺纹钢日线", task_id=task_id))

        task = db_session.get(AgentTaskDB, task_id)
        assert result.success is True
        assert task.status == "completed"
        data = result.data
        assert data is not None
        missing = self.REQUIRED_FIELDS - set(data.keys())
        assert not missing, f"缺少必需字段: {missing}"

    def test_direction_values(self, db_session, _seed_tech_analysis_data):
        user = _seed_tech_analysis_data
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("tech_analysis", "分析螺纹钢日线")
        agent = TechAnalysisAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "分析螺纹钢日线", task_id=task_id))

        assert result.data["direction"] in {"向上", "向下", "震荡"}
        assert result.data["bias"] in {"偏多", "偏空", "震荡"}

    def test_key_levels_structure(self, db_session, _seed_tech_analysis_data):
        user = _seed_tech_analysis_data
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("tech_analysis", "分析螺纹钢日线")
        agent = TechAnalysisAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "分析螺纹钢日线", task_id=task_id))

        key_levels = result.data["key_levels"]
        assert "support" in key_levels
        assert "resistance" in key_levels
        assert "ma5" in key_levels
        assert "ma10" in key_levels
        assert "ma20" in key_levels

    def test_indicators_include_required(self, db_session, _seed_tech_analysis_data):
        user = _seed_tech_analysis_data
        executor = AgentExecutor(db_session, user.id)
        task_id = executor.create_task("tech_analysis", "分析螺纹钢日线")
        agent = TechAnalysisAgent(AgentContext(db_session, user.id, task_id))

        result = asyncio.run(executor.execute(agent, "分析螺纹钢日线", task_id=task_id))

        indicators = result.data["indicators"]
        assert "atr14" in indicators
        assert "sma5" in indicators
        assert "sma10" in indicators
        assert "sma20" in indicators
        assert "volume_change" in indicators
