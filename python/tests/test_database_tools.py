"""database_tools.py 测试 — SQL 查询 + 注入防护 + 基础功能。"""

from __future__ import annotations

import asyncio

from models import VarietyDB
from services.agent.database_tools import (
    GetTableSchemaTool,
    ListTablesTool,
    QueryDatabaseTool,
    _ensure_limit,
    _inject_user_filter,
    _validate_sql,
)


class TestSQLValidation:
    """SQL 安全检查测试。"""

    def test_valid_select_passes(self):
        ok, msg = _validate_sql("SELECT * FROM varieties WHERE is_active = 1")
        assert ok, msg

    def test_select_with_aggregate_passes(self):
        ok, msg = _validate_sql("SELECT symbol, COUNT(*) FROM fut_wsr GROUP BY symbol")
        assert ok, msg

    def test_empty_sql_fails(self):
        ok, msg = _validate_sql("")
        assert not ok
        assert "不能为空" in msg

    def test_non_select_fails(self):
        ok, msg = _validate_sql("INSERT INTO varieties VALUES (1)")
        assert not ok
        assert "只允许 SELECT" in msg

    def test_forbidden_keyword_delete_fails(self):
        ok, msg = _validate_sql("DELETE FROM varieties")
        assert not ok
        # DELETE is caught as non-SELECT (stricter check kicks in first)
        assert ("只允许 SELECT" in msg or "禁止关键字" in msg)

    def test_forbidden_keyword_drop_fails(self):
        ok, msg = _validate_sql("DROP TABLE varieties")
        assert not ok
        assert ("只允许 SELECT" in msg or "禁止关键字" in msg)

    def test_forbidden_keyword_truncate_fails(self):
        ok, msg = _validate_sql("TRUNCATE TABLE varieties")
        assert not ok
        assert ("只允许 SELECT" in msg or "禁止关键字" in msg)

    def test_forbidden_keyword_in_string_not_blocked(self):
        """字符串字面量中的 DROP 不触发误判（单引号内是安全的）。"""
        ok, msg = _validate_sql("SELECT * FROM varieties WHERE name = 'DROP'")
        assert ok, msg

    def test_non_whitelist_table_fails(self):
        ok, msg = _validate_sql("SELECT * FROM users WHERE id = 1")
        assert not ok
        assert "不在允许查询" in msg

    def test_whitelist_varieties_table_ok(self):
        ok, msg = _validate_sql("SELECT * FROM varieties LIMIT 1")
        assert ok, msg

    def test_whitelist_fut_wsr_table_ok(self):
        ok, msg = _validate_sql("SELECT * FROM fut_wsr LIMIT 1")
        assert ok, msg

    def test_whitelist_kline_data_table_ok(self):
        ok, msg = _validate_sql("SELECT * FROM kline_data LIMIT 1")
        assert ok, msg

    def test_whitelist_trading_calendar_table_ok(self):
        ok, msg = _validate_sql("SELECT * FROM trading_calendar LIMIT 1")
        assert ok, msg

    def test_update_fails(self):
        ok, msg = _validate_sql("UPDATE varieties SET name='x'")
        assert not ok

    def test_mixed_case_select_passes(self):
        ok, msg = _validate_sql("select * from varieties limit 1")
        assert ok, msg

    def test_select_in_join_query_passes(self):
        ok, msg = _validate_sql(
            "SELECT v.symbol, r.current_price FROM varieties v JOIN realtime_quotes r ON v.id = r.variety_id LIMIT 10"
        )
        assert ok, msg

    def test_cte_and_nested_subquery_pass(self):
        ok, msg = _validate_sql(
            "WITH recent AS ("
            "SELECT variety_id FROM kline_data WHERE trading_time >= '2026-01-01'"
            ") "
            "SELECT v.symbol FROM varieties v "
            "WHERE v.id IN (SELECT variety_id FROM recent)"
        )
        assert ok, msg

    def test_multiple_statements_fail(self):
        ok, msg = _validate_sql("SELECT * FROM varieties; SELECT * FROM fut_wsr")
        assert not ok
        assert "单条" in msg

    def test_dangerous_function_fails(self):
        ok, msg = _validate_sql("SELECT pg_sleep(10) FROM varieties")
        assert not ok
        assert "禁止的函数" in msg

    def test_schema_qualified_non_public_table_fails(self):
        ok, msg = _validate_sql("SELECT * FROM private.varieties")
        assert not ok
        assert "不在允许查询" in msg

    def test_block_comment_strips_keywords(self):
        """Block comment removal: /* DROP TABLE some_table */ exposes a non-whitelist table."""
        # After stripping the comment: "SELECT * FROM varieties   LIMIT 1"
        # — still valid because varieties is whitelisted. So test with a non-whitelist table.
        ok, msg = _validate_sql("SELECT * FROM varieties /* DROP */ JOIN users")
        assert not ok, f"Expected failure but got: {msg}"


class TestSQLHelpers:
    """辅助函数测试。"""

    def test_injects_filter_for_unqualified_private_table(self):
        result = _inject_user_filter("SELECT * FROM opinions", 7)
        assert result == "SELECT * FROM opinions WHERE opinions.user_id = 7"

    def test_does_not_duplicate_qualified_owner_filter(self):
        result = _inject_user_filter("SELECT * FROM opinions o WHERE o.user_id = 7", 7)
        assert result == "SELECT * FROM opinions o WHERE o.user_id = 7"

    def test_overrides_mismatched_qualified_owner_filter(self):
        result = _inject_user_filter("SELECT * FROM opinions o WHERE o.user_id = 2", 7)
        assert "o.user_id = 2" in result
        assert "o.user_id = 7" in result

    def test_injects_each_private_table_by_alias(self):
        result = _inject_user_filter(
            "SELECT o.id, s.id FROM opinions o JOIN strategies s ON s.symbol = o.symbol",
            7,
        )
        assert "o.user_id = 7" in result
        assert "s.user_id = 7" in result
        assert result.count("user_id = 7") == 2

    def test_puts_join_filter_in_on_clause_for_outer_join(self):
        result = _inject_user_filter(
            "SELECT v.symbol, o.id FROM varieties v "
            "LEFT JOIN opinions o ON o.variety_id = v.id",
            7,
        )
        assert "LEFT JOIN opinions AS o" in result
        assert "ON o.variety_id = v.id AND o.user_id = 7" in result
        assert "WHERE o.user_id = 7" not in result

    def test_rewrites_private_table_inside_cte_and_subquery(self):
        cte_result = _inject_user_filter(
            "WITH mine AS (SELECT * FROM opinions) SELECT * FROM mine",
            7,
        )
        subquery_result = _inject_user_filter(
            "SELECT * FROM varieties WHERE id IN (SELECT variety_id FROM opinions)",
            7,
        )
        assert "FROM opinions WHERE opinions.user_id = 7" in cte_result
        assert "FROM opinions WHERE opinions.user_id = 7" in subquery_result

    def test_rewrites_task_steps_through_parent_task(self):
        result = _inject_user_filter("SELECT * FROM agent_task_steps ats", 7)
        assert result.count("EXISTS") == 1
        assert "_agent_owner_task.user_id = 7" in result
        assert "_agent_owner_task.id = ats.task_id" in result

    def test_rewrites_each_side_of_union(self):
        result = _inject_user_filter(
            "SELECT * FROM opinions UNION ALL SELECT * FROM trade_records",
            7,
        )
        assert result.count("user_id = 7") == 2

    def test_ensure_limit_adds_limit(self):
        sql = "SELECT * FROM varieties"
        result = _ensure_limit(sql, 100)
        assert "LIMIT 100" in result

    def test_ensure_limit_does_not_double_limit(self):
        sql = "SELECT * FROM varieties LIMIT 50"
        result = _ensure_limit(sql, 100)
        assert result.count("LIMIT") <= 1

    def test_ensure_limit_strips_trailing_semicolon(self):
        sql = "SELECT * FROM varieties;"
        result = _ensure_limit(sql, 100)
        assert not result.endswith(";")


class TestListTablesTool:
    """list_tables 工具测试。"""

    def test_returns_table_list(self, db_session):
        from services.agent.context import AgentContext

        tool = ListTablesTool()
        ctx = AgentContext(db_session, user_id=1)
        result = asyncio.run(tool.execute(ctx))
        assert "tables" in result
        assert isinstance(result["tables"], list)
        assert len(result["tables"]) > 0
        table_names = [t["name"] for t in result["tables"]]
        assert "varieties" in table_names
        assert "fut_wsr" in table_names
        assert "trade_records" in table_names


class TestGetTableSchemaTool:
    """get_table_schema 工具测试。"""

    def test_returns_schema_for_valid_table(self, db_session):
        from services.agent.context import AgentContext

        tool = GetTableSchemaTool()
        ctx = AgentContext(db_session, user_id=1)
        result = asyncio.run(tool.execute(ctx, table_name="varieties"))
        assert "columns" in result
        assert isinstance(result["columns"], list)
        assert len(result["columns"]) > 0

    def test_empty_table_name_fails(self, db_session):
        from services.agent.context import AgentContext

        tool = GetTableSchemaTool()
        ctx = AgentContext(db_session, user_id=1)
        result = asyncio.run(tool.execute(ctx, table_name=""))
        assert "error" in result

    def test_non_whitelist_table_fails(self, db_session):
        from services.agent.context import AgentContext

        tool = GetTableSchemaTool()
        ctx = AgentContext(db_session, user_id=1)
        result = asyncio.run(tool.execute(ctx, table_name="users"))
        assert "error" in result


class TestQueryDatabaseTool:
    """query_database 工具测试。"""

    def test_valid_query_returns_data(self, db_session):
        from services.agent.context import AgentContext

        # 确保有测试数据
        variety = db_session.query(VarietyDB).filter(VarietyDB.is_active).first()
        if variety is None:
            variety = VarietyDB(
                symbol="DBTEST",
                contract_code="DBTEST2501",
                name="测试品种",
                exchange="SHFE",
                category="黑色系",
                is_active=True,
            )
            db_session.add(variety)
            db_session.commit()
            db_session.refresh(variety)

        tool = QueryDatabaseTool()
        ctx = AgentContext(db_session, user_id=1)
        result = asyncio.run(tool.execute(ctx, sql="SELECT symbol, name FROM varieties WHERE is_active = 1 LIMIT 5"))
        assert "data" in result
        assert "row_count" in result
        assert result["row_count"] >= 1
        assert isinstance(result["data"], list)

    def test_forbidden_sql_returns_error(self, db_session):
        from services.agent.context import AgentContext

        tool = QueryDatabaseTool()
        ctx = AgentContext(db_session, user_id=1)
        result = asyncio.run(tool.execute(ctx, sql="DROP TABLE varieties"))
        assert "error" in result

    def test_empty_sql_returns_error(self, db_session):
        from services.agent.context import AgentContext

        tool = QueryDatabaseTool()
        ctx = AgentContext(db_session, user_id=1)
        result = asyncio.run(tool.execute(ctx, sql=""))
        assert "error" in result

    def test_private_query_executes_with_ast_owner_filter(self, db_session):
        from services.agent.context import AgentContext

        tool = QueryDatabaseTool()
        ctx = AgentContext(db_session, user_id=1)
        result = asyncio.run(tool.execute(ctx, sql="SELECT id FROM opinions"))

        assert "error" not in result
        assert "opinions.user_id = 1" in result["sql"]
