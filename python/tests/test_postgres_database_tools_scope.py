"""PostgreSQL 专项回归：验证 Agent 私有数据 AST 改写的执行语义。"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (
    AgentTaskDB,
    AgentTaskStepDB,
    FrontendLogDB,
    OpinionDB,
    StrategyDB,
    UserDB,
    UserPreferenceDB,
    VarietyDB,
)
from services.agent.context import AgentContext
from services.agent.database_tools import QueryDatabaseTool

_PG_URL = os.environ.get("_PYTEST_ORIGINAL_DATABASE_URL", "")
_IS_PG = _PG_URL.startswith("postgresql")

if _IS_PG:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    _pg_engine = create_engine(_PG_URL)
    _PgSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_pg_engine)
else:
    _pg_engine = None
    _PgSessionLocal = None


@pytest.fixture(scope="module")
def pg_scope_data():
    """创建唯一测试数据；没有 PostgreSQL 时明确跳过。"""
    if not _IS_PG or _PgSessionLocal is None:
        pytest.skip("PostgreSQL owner-scope regression requires PostgreSQL DATABASE_URL")

    db = _PgSessionLocal()
    suffix = uuid.uuid4().hex[:10]
    symbol = f"PGS{suffix.upper()}"
    contract_code = f"{symbol}2401"

    owner = UserDB(
        username=f"pg_scope_owner_{suffix}",
        email=f"pg_scope_owner_{suffix}@example.com",
        password_hash="test-only",
    )
    other = UserDB(
        username=f"pg_scope_other_{suffix}",
        email=f"pg_scope_other_{suffix}@example.com",
        password_hash="test-only",
    )
    variety = VarietyDB(
        symbol=symbol,
        contract_code=contract_code,
        name="PostgreSQL scope regression",
        exchange="SHFE",
        category="test",
        is_active=True,
    )
    db.add_all([owner, other, variety])
    db.flush()

    owner_opinion = OpinionDB(user_id=owner.id, variety_id=variety.id, type="long", reason="owner-only-opinion")
    other_opinion = OpinionDB(user_id=other.id, variety_id=variety.id, type="short", reason="other-only-opinion")
    owner_strategy = StrategyDB(
        user_id=owner.id,
        name="owner strategy",
        description="owner-only-strategy",
        symbol=symbol,
        dsl_json="{}",
        timeframe="1d",
        direction="long",
    )
    other_strategy = StrategyDB(
        user_id=other.id,
        name="other strategy",
        description="other-only-strategy",
        symbol=symbol,
        dsl_json="{}",
        timeframe="1d",
        direction="short",
    )
    owner_task = AgentTaskDB(user_id=owner.id, agent_type="data", query="owner task", status="completed")
    other_task = AgentTaskDB(user_id=other.id, agent_type="data", query="other task", status="completed")
    owner_preference = UserPreferenceDB(user_id=owner.id, theme="dark", language="zh-CN")
    other_preference = UserPreferenceDB(user_id=other.id, theme="light", language="en-US")
    owner_log = FrontendLogDB(
        user_id=owner.id,
        log_type="exception",
        level="error",
        payload_json='{"scope":"owner"}',
    )
    other_log = FrontendLogDB(
        user_id=other.id,
        log_type="exception",
        level="error",
        payload_json='{"scope":"other"}',
    )
    anonymous_log = FrontendLogDB(
        user_id=None,
        log_type="exception",
        level="error",
        payload_json='{"scope":"anonymous"}',
    )
    db.add_all(
        [
            owner_opinion,
            other_opinion,
            owner_strategy,
            other_strategy,
            owner_task,
            other_task,
            owner_preference,
            other_preference,
            owner_log,
            other_log,
            anonymous_log,
        ]
    )
    db.flush()
    db.add_all(
        [
            AgentTaskStepDB(task_id=owner_task.id, step_number=1, role="thought", content="owner-only-step"),
            AgentTaskStepDB(task_id=other_task.id, step_number=1, role="thought", content="other-only-step"),
        ]
    )
    db.commit()

    try:
        yield db, owner.id, variety.id, symbol
    finally:
        task_ids = [owner_task.id, other_task.id]
        user_ids = [owner.id, other.id]
        log_ids = [owner_log.id, other_log.id, anonymous_log.id]
        db.rollback()
        db.query(FrontendLogDB).filter(FrontendLogDB.id.in_(log_ids)).delete(synchronize_session=False)
        db.query(AgentTaskStepDB).filter(AgentTaskStepDB.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(AgentTaskDB).filter(AgentTaskDB.id.in_(task_ids)).delete(synchronize_session=False)
        db.query(UserPreferenceDB).filter(UserPreferenceDB.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(OpinionDB).filter(OpinionDB.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(StrategyDB).filter(StrategyDB.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(VarietyDB).filter(VarietyDB.id == variety.id).delete(synchronize_session=False)
        db.query(UserDB).filter(UserDB.id.in_(user_ids)).delete(synchronize_session=False)
        db.commit()
        db.close()


def _query(db, user_id: int, sql: str) -> dict:
    tool = QueryDatabaseTool()
    context = AgentContext(db, user_id=user_id)
    return asyncio.run(tool.execute(context, sql=sql))


def test_postgres_left_join_keeps_private_filter_in_on_clause(pg_scope_data):
    db, owner_id, variety_id, symbol = pg_scope_data

    result = _query(
        db,
        owner_id,
        f"""
        SELECT v.symbol, o.reason
        FROM varieties v
        LEFT JOIN opinions o ON o.variety_id = v.id
        WHERE v.id = {variety_id}
        """,
    )

    assert "error" not in result
    assert result["data"] == [{"symbol": symbol, "reason": "owner-only-opinion"}]
    assert "LEFT JOIN opinions AS o" in result["sql"]
    assert f"o.user_id = {owner_id}" in result["sql"]
    assert "WHERE o.user_id" not in result["sql"]


def test_postgres_cte_union_isolated_per_select_scope(pg_scope_data):
    db, owner_id, variety_id, symbol = pg_scope_data

    result = _query(
        db,
        owner_id,
        f"""
        WITH opinion_rows AS (
            SELECT id, reason
            FROM opinions
            WHERE variety_id = {variety_id}
        ),
        strategy_rows AS (
            SELECT id, description AS reason
            FROM strategies
            WHERE symbol = '{symbol}'
        )
        SELECT reason FROM opinion_rows
        UNION ALL
        SELECT reason FROM strategy_rows
        """,
    )

    assert "error" not in result
    reasons = {row["reason"] for row in result["data"]}
    assert reasons == {"owner-only-opinion", "owner-only-strategy"}
    assert "other-only-opinion" not in reasons
    assert "other-only-strategy" not in reasons


def test_postgres_task_steps_use_parent_task_owner_scope(pg_scope_data):
    db, owner_id, _, _ = pg_scope_data

    result = _query(
        db,
        owner_id,
        """
        SELECT ats.step_number, ats.content
        FROM agent_task_steps ats
        JOIN agent_tasks t ON t.id = ats.task_id
        WHERE t.agent_type = 'data'
        ORDER BY ats.step_number
        """,
    )

    assert "error" not in result
    assert result["data"] == [{"step_number": 1, "content": "owner-only-step"}]
    assert "EXISTS" in result["sql"]
    assert f"t.user_id = {owner_id}" in result["sql"]


def test_postgres_preferences_and_frontend_logs_are_owner_scoped(pg_scope_data):
    db, owner_id, _, _ = pg_scope_data

    preferences = _query(db, owner_id, "SELECT user_id, theme FROM user_preferences")
    logs = _query(db, owner_id, "SELECT user_id, type, payload_json FROM frontend_logs")

    assert "error" not in preferences
    assert preferences["data"] == [{"user_id": owner_id, "theme": "dark"}]
    assert f"user_preferences.user_id = {owner_id}" in preferences["sql"]

    assert "error" not in logs
    assert logs["data"] == [{"user_id": owner_id, "type": "exception", "payload_json": '{"scope":"owner"}'}]
    assert f"frontend_logs.user_id = {owner_id}" in logs["sql"]
