"""数据库通用查询工具。

让 Agent 能够通过受控的 SQL 直接查询 PostgreSQL/SQLite 数据库中的数据。
提供两层能力：
1. 通用 SQL 查询（query_database）—— 灵活但受安全限制
2. 预置常用查询（get_table_schema / list_tables）—— 辅助 LLM 写 SQL
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from sqlalchemy import text
from sqlglot import exp, parse
from sqlglot.errors import ParseError

from services.agent.context import AgentContext
from services.agent.tools import Tool, ToolDefinition, ToolParameter, register_tool

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 安全配置
# ------------------------------------------------------------------

# 禁止的 SQL 关键字（写操作 + 危险操作）
_FORBIDDEN_KEYWORDS: frozenset[str] = frozenset(
    {
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "create",
        "truncate",
        "grant",
        "revoke",
        "exec",
        "execute",
        "sp_",
        "xp_",
        "pragma",
        "attach",
        "detach",
        "vacuum",
        "replace",
        "merge",
        "copy",
        "load",
        "import",
    }
)

# 白名单表（Agent 可以查询的表）
# 注意：users 表被排除，避免泄露密码哈希等敏感信息
_ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        # 品种与合约
        "varieties",
        "fut_contracts",
        "contract_rollovers",
        # 行情数据
        "realtime_quotes",
        "kline_data",
        "fut_daily_data",
        "fut_index",
        # 基本面数据
        "fut_settle",
        "fut_wsr",
        "fut_holding",
        "fut_price_limits",
        "fut_weekly_detail",
        "fut_trade_fee",
        # 交易日历与监控
        "trading_calendar",
        "data_ingestion_runs",
        # 新闻
        "news_articles",
        "news_sources",
        # 用户业务数据（需通过 user_id 过滤，由查询逻辑自动注入）
        "opinions",
        "trade_records",
        "strategies",
        "backtest_runs",
        "price_levels",
        "watchlists",
        "comments",
        "price_alerts",
        "alert_events",
        "alert_event_user_states",
        # Agent 数据
        "agent_tasks",
        "agent_task_steps",
        # 其他
        "frontend_logs",
        "user_preferences",
    }
)

# 敏感字段映射：某些表的特定字段需要脱敏或排除
_SENSITIVE_FIELDS: dict[str, set[str]] = {
    "users": {"password_hash", "email"},  # users 表其实不在白名单，双重保险
}

_MAX_ROWS = 500
_QUERY_TIMEOUT_SECONDS = 5

# ------------------------------------------------------------------
# SQL 安全检查
# ------------------------------------------------------------------

# 保留旧关键字集合作为公开模块常量，实际校验由 SQL AST 完成。
_FORBIDDEN_AST_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.Command,
    exp.Copy,
    exp.Merge,
    exp.Grant,
    exp.Transaction,
    exp.Pragma,
    exp.Set,
    exp.Use,
    exp.TruncateTable,
    exp.Commit,
    exp.Rollback,
    exp.LoadData,
    exp.Describe,
    exp.Into,
    exp.Lock,
)
_READ_QUERY_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)
_FORBIDDEN_FUNCTIONS = frozenset(
    {
        "dblink_connect",
        "dblink_exec",
        "load_extension",
        "pg_ls_dir",
        "pg_read_file",
        "pg_sleep",
        "readfile",
        "writefile",
    }
)


def _validate_sql(sql: str) -> tuple[bool, str]:
    """Validate a single read-only SQL statement with its parsed AST.

    Regex checks are insufficient for nested queries, CTEs, comments, aliases,
    and multi-statement payloads. Parsing first lets the validator inspect the
    actual statement tree while preserving the existing table allowlist.
    """
    if not sql or not sql.strip():
        return False, "SQL 查询不能为空"

    try:
        statements = parse(sql)
    except ParseError as exc:
        return False, f"SQL 解析失败: {exc}"

    if len(statements) != 1:
        return False, "只允许执行单条 SELECT 查询"

    expression = statements[0]
    if not isinstance(expression, _READ_QUERY_ROOTS):
        return False, "只允许 SELECT 查询"

    for node in expression.walk():
        if isinstance(node, _FORBIDDEN_AST_NODES):
            return False, f"SQL 包含禁止的操作: {type(node).__name__}"

    for function in expression.find_all(exp.Anonymous):
        function_name = function.name.lower()
        if function_name in _FORBIDDEN_FUNCTIONS:
            return False, f"SQL 包含禁止的函数: {function_name}"

    cte_names = {cte.alias_or_name.lower() for cte in expression.find_all(exp.CTE)}
    for table in expression.find_all(exp.Table):
        table_name = table.name.lower()
        if table_name in cte_names:
            continue
        if table.catalog or (table.db and table.db.lower() != "public"):
            return False, f"表 '{table.sql()}' 不在允许查询的白名单中"
        if table_name not in _ALLOWED_TABLES:
            return False, f"表 '{table_name}' 不在允许查询的白名单中"

    return True, ""


# ------------------------------------------------------------------
# 工具实现
# ------------------------------------------------------------------


class ListTablesTool(Tool):
    """列出 Agent 可以查询的数据库表。"""

    name = "list_tables"
    description = (
        "列出数据库中所有 Agent 可以查询的表名及其简要说明。当用户要求查询数据库但你不确定表名时，先调用此工具。"
    )

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(name=self.name, description=self.description, parameters=[])

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        table_descriptions = {
            "varieties": "期货品种基础信息（symbol, name, exchange, category, contract_code等）",
            "fut_contracts": "期货合约明细（ts_code, symbol, exchange, list_date, delist_date等）",
            "contract_rollovers": "主力合约切换历史记录",
            "realtime_quotes": "实时行情快照（current_price, change_percent, volume, open_interest等）",
            "kline_data": "K线数据（分钟/小时/日/周，含OHLCV）",
            "fut_daily_data": "日线/周线/月线行情（Tushare回填，含settle/amount/oi_chg等）",
            "fut_settle": "每日结算参数（保证金率、手续费率、交割费等）",
            "fut_wsr": "仓单日报（各仓库库存、品级、年度等）",
            "fut_holding": "持仓排名（成交量/多空持仓前N券商）",
            "fut_price_limits": "涨跌停价格（up_limit, down_limit, m_ratio）",
            "fut_weekly_detail": "周度交易统计（成交量/持仓量周同比环比）",
            "fut_trade_fee": "手续费与保证金（九期网数据）",
            "trading_calendar": "交易日历",
            "news_articles": "新闻资讯",
            "opinions": "用户交易观点",
            "trade_records": "模拟持仓交易记录",
            "strategies": "用户策略",
            "backtest_runs": "策略回测记录",
            "price_levels": "用户云端价位标注（支撑/阻力）",
            "watchlists": "用户自选品种",
            "agent_tasks": "Agent任务记录",
        }
        return {
            "tables": [
                {"name": name, "description": desc}
                for name, desc in table_descriptions.items()
                if name in _ALLOWED_TABLES
            ],
            "note": f"共 {len(table_descriptions)} 张表可查询。查询用户私有数据（opinions/trade_records等）时，SQL中需包含 user_id = {context.user_id} 条件。",
        }


class GetTableSchemaTool(Tool):
    """获取指定表的结构信息。"""

    name = "get_table_schema"
    description = "获取指定数据库表的列名、类型和说明。在写 SQL 查询前调用此工具了解表结构，可避免字段名错误。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="table_name", type="string", description="表名，如 fut_wsr, fut_holding", required=True
                ),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        table_name = kwargs.get("table_name", "").strip().lower()
        if not table_name:
            return {"error": "表名不能为空"}
        if table_name not in _ALLOWED_TABLES:
            return {"error": f"表 '{table_name}' 不在允许查询的白名单中"}

        try:
            # 使用 PRAGMA（SQLite）或 information_schema（PG）获取表结构
            dialect = context.db.bind.dialect.name if context.db.bind else "unknown"

            if dialect == "sqlite":
                result = context.db.execute(text(f"PRAGMA table_info({table_name})"))
                columns = [
                    {
                        "name": row[1],
                        "type": row[2],
                        "nullable": not row[3],
                        "default": row[4],
                    }
                    for row in result
                ]
            else:
                # PostgreSQL
                schema_sql = """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = :table_name
                    ORDER BY ordinal_position
                """
                result = context.db.execute(text(schema_sql), {"table_name": table_name})
                columns = [
                    {
                        "name": row[0],
                        "type": row[1],
                        "nullable": row[2] == "YES",
                        "default": row[3],
                    }
                    for row in result
                ]

            # 补充示例数据（最近 1 条）
            sample_sql = f"SELECT * FROM {table_name} LIMIT 1"
            try:
                sample_result = context.db.execute(text(sample_sql))
                sample_row = sample_result.mappings().first()
                sample = dict(sample_row) if sample_row else None
            except Exception as e:
                sample = None
                logger.debug("Failed to get sample from %s: %s", table_name, e)

            return {
                "table_name": table_name,
                "dialect": dialect,
                "columns": columns,
                "sample_row": sample,
                "note": "查询时请注意：日期字段通常是 DateTime 类型，需用 YYYY-MM-DD 格式比较。",
            }
        except Exception as e:
            logger.warning("Failed to get schema for %s: %s", table_name, e)
            return {"error": f"获取表结构失败: {e}"}


class QueryDatabaseTool(Tool):
    """通用 SQL 查询工具 — Agent 的核心数据库访问能力。"""

    name = "query_database"
    description = (
        "执行受控的 SELECT SQL 查询，直接从数据库获取数据。"
        "支持任何已入库的期货数据表：行情、基本面、用户业务数据等。"
        "\n"
        "使用建议：\n"
        "1. 不确定表结构时，先调用 get_table_schema 工具\n"
        "2. 查询用户私有数据（opinions/trade_records等）时，必须加 user_id 条件\n"
        "3. 日期比较格式：trade_date >= '2024-01-01'\n"
        "4. 限制返回行数：SELECT ... LIMIT 100\n"
        "\n"
        "示例查询：\n"
        "- SELECT * FROM fut_wsr WHERE symbol = 'RB' AND trade_date >= '2024-01-01' ORDER BY trade_date DESC LIMIT 50\n"
        "- SELECT trade_date, vol, vol_chg FROM fut_wsr WHERE symbol = 'CU' ORDER BY trade_date DESC LIMIT 30\n"
        "- SELECT broker, long_hld, short_hld FROM fut_holding WHERE symbol = 'AU' AND trade_date = '2024-06-01' ORDER BY long_hld DESC LIMIT 20\n"
        "- SELECT * FROM fut_settle WHERE ts_code LIKE 'RB%' ORDER BY trade_date DESC LIMIT 10\n"
    )

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="sql",
                    type="string",
                    description="SELECT SQL 查询语句。必须是只读查询，禁止 INSERT/UPDATE/DELETE/DROP 等操作。",
                    required=True,
                ),
                ToolParameter(
                    name="limit",
                    type="number",
                    description="最大返回行数，默认 100，最大 500",
                    required=False,
                ),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        sql = kwargs.get("sql", "").strip()
        limit = kwargs.get("limit", 100)
        if isinstance(limit, str):
            limit = int(limit)
        limit = min(max(limit, 1), _MAX_ROWS)

        # 安全检查
        is_valid, error_msg = _validate_sql(sql)
        if not is_valid:
            return {"error": error_msg, "sql": sql}

        # 自动注入 user_id 过滤（对私有数据表）
        try:
            sql = _inject_user_filter(sql, context.user_id)
        except ValueError as exc:
            return {"error": f"SQL 安全改写失败: {exc}", "sql": sql}

        # 自动追加 LIMIT（如果用户没写）
        sql = _ensure_limit(sql, limit)

        start_time = time.time()
        try:
            result = context.db.execute(text(sql))
            rows = result.mappings().all()
            elapsed_ms = (time.time() - start_time) * 1000

            # 转换为可序列化的 dict 列表
            records = []
            for row in rows:
                record: dict[str, Any] = {}
                for key, value in dict(row).items():
                    # 处理不可序列化的类型
                    if hasattr(value, "isoformat"):  # datetime / date
                        record[key] = value.isoformat()
                    elif value.__class__.__name__ == "Decimal":
                        record[key] = float(value)
                    else:
                        record[key] = value
                records.append(record)

            return {
                "sql": sql,
                "row_count": len(records),
                "elapsed_ms": round(elapsed_ms, 2),
                "columns": list(records[0].keys()) if records else [],
                "data": records,
            }
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.warning("Database query failed: %s | sql=%s", e, sql[:200])
            return {
                "error": f"查询执行失败: {e}",
                "sql": sql,
                "elapsed_ms": round(elapsed_ms, 2),
            }


# ------------------------------------------------------------------
# SQL 辅助函数
# ------------------------------------------------------------------

_PRIVATE_TABLES: frozenset[str] = frozenset(
    {
        "opinions",
        "trade_records",
        "strategies",
        "backtest_runs",
        "price_levels",
        "watchlists",
        "comments",
        "price_alerts",
        "alert_events",
        "alert_event_user_states",
        "agent_tasks",
        "agent_task_steps",
    }
)


_USER_ID_COLUMN_MAP: dict[str, str] = {
    "opinions": "user_id",
    "trade_records": "user_id",
    "strategies": "user_id",
    "backtest_runs": "user_id",
    "price_levels": "user_id",
    "watchlists": "user_id",
    "comments": "user_id",
    "price_alerts": "user_id",
    "alert_events": "user_id",
    "alert_event_user_states": "user_id",
    "agent_tasks": "user_id",
    "agent_task_steps": "task_id",  # 通过 task 间接关联 user
}


def _inject_user_filter(sql: str, user_id: int) -> str:
    """在 SQL AST 中按查询作用域注入私有数据过滤条件。

    每个私有表都在其所属 ``SELECT`` 作用域中单独处理：

    - ``FROM`` 主表使用 ``WHERE`` 谓词；
    - JOIN 表使用 ``ON`` 谓词，避免把 LEFT JOIN 错误收紧为 INNER JOIN；
    - 已有同一表/别名的 owner 条件不会重复注入；
    - ``agent_task_steps`` 没有 ``user_id``，使用 ``EXISTS`` 关联
      ``agent_tasks.user_id``；
    - CTE 和嵌套 SELECT 各自按最近的 SELECT 作用域处理。

    SQL 已由 ``_validate_sql`` 解析过；这里仍然 fail closed，避免未来调用方
    绕过验证时执行未隔离的私有查询。
    """
    try:
        statements = parse(sql)
    except ParseError as exc:
        raise ValueError(f"SQL 解析失败: {exc}") from exc
    if len(statements) != 1:
        raise ValueError("只允许改写单条 SELECT 查询")

    expression = statements[0]
    if not isinstance(expression, _READ_QUERY_ROOTS):
        raise ValueError("只允许改写 SELECT 查询")

    try:
        owner_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("user_id 必须是整数") from exc

    selects = list(expression.find_all(exp.Select))
    if isinstance(expression, exp.Select) and expression not in selects:
        selects.insert(0, expression)
    changed = False

    for select in selects:
        cte_names = {cte.alias_or_name.lower() for cte in select.find_all(exp.CTE)}
        direct_tables = [
            table
            for table in select.find_all(exp.Table)
            if _nearest_select(table) is select
            and table.name.lower() not in cte_names
            and table.name.lower() in _PRIVATE_TABLES
        ]
        if not direct_tables:
            continue

        private_aliases = {table.alias_or_name.lower() for table in direct_tables}
        for table in direct_tables:
            table_name = table.name.lower()
            alias = table.alias_or_name
            if table_name == "agent_task_steps":
                predicate = _task_owner_predicate(alias, owner_id)
            else:
                user_column = _USER_ID_COLUMN_MAP.get(table_name, "user_id")
                if _has_owner_predicate(select, table, user_column, private_aliases, owner_id):
                    continue
                predicate = exp.EQ(
                    this=exp.column(user_column, table=alias),
                    expression=exp.Literal.number(owner_id),
                )

            if isinstance(table.parent, exp.Join):
                join = table.parent
                join.set("on", _combine_predicates(join.args.get("on"), predicate))
            else:
                select.set("where", _append_where(select.args.get("where"), predicate))
            changed = True

    return expression.sql() if changed else sql


def _nearest_select(expression: exp.Expression) -> exp.Select | None:
    """Return the closest SELECT ancestor for a table or expression node."""
    parent = expression.parent
    while parent is not None:
        if isinstance(parent, exp.Select):
            return parent
        parent = parent.parent
    return None


def _predicate_nodes(select: exp.Select) -> list[exp.Expression]:
    """Return WHERE and direct JOIN ON expressions for owner checks."""
    predicates: list[exp.Expression] = []
    where = select.args.get("where")
    if isinstance(where, exp.Where):
        predicates.append(where.this)
    for join in select.find_all(exp.Join):
        if _nearest_select(join) is select and isinstance(join.args.get("on"), exp.Expression):
            predicates.append(join.args["on"])
    return predicates


def _has_owner_predicate(
    select: exp.Select,
    table: exp.Table,
    user_column: str,
    private_aliases: set[str],
    owner_id: int,
) -> bool:
    """Check whether a predicate already equals this table to ``owner_id``."""
    alias = table.alias_or_name.lower()
    for predicate in _predicate_nodes(select):
        for equality in predicate.find_all(exp.EQ):
            sides = ((equality.this, equality.expression), (equality.expression, equality.this))
            for column_expr, value_expr in sides:
                if not isinstance(column_expr, exp.Column):
                    continue
                if column_expr.name.lower() != user_column.lower():
                    continue
                qualifier = column_expr.table.lower()
                if qualifier != alias and (qualifier or len(private_aliases) != 1):
                    continue
                if isinstance(value_expr, exp.Literal) and value_expr.is_number and int(value_expr.this) == owner_id:
                    return True
    return False


def _task_owner_predicate(task_step_alias: str, user_id: int) -> exp.Exists:
    """Build an ownership predicate for task steps via their parent task."""
    owner_alias = "_agent_owner_task"
    owner_table = exp.table_("agent_tasks", alias=owner_alias)
    owner_query = (
        exp.select(exp.Literal.number(1))
        .from_(owner_table)
        .where(
            exp.and_(
                exp.EQ(
                    this=exp.column("id", table=owner_alias),
                    expression=exp.column("task_id", table=task_step_alias),
                ),
                exp.EQ(
                    this=exp.column("user_id", table=owner_alias),
                    expression=exp.Literal.number(user_id),
                ),
            )
        )
    )
    return exp.Exists(this=owner_query)


def _combine_predicates(
    existing: exp.Expression | None,
    predicate: exp.Expression,
) -> exp.Expression:
    """Append an expression to an existing ON/WHERE predicate."""
    return exp.and_(existing, predicate) if existing is not None else predicate


def _append_where(
    where: exp.Where | None,
    predicate: exp.Expression,
) -> exp.Where:
    """Append an expression to a SELECT WHERE clause."""
    existing = where.this if isinstance(where, exp.Where) else None
    return exp.Where(this=_combine_predicates(existing, predicate))


def _ensure_limit(sql: str, limit: int) -> str:
    """确保 SQL 末尾有 LIMIT 子句。"""
    sql_stripped = sql.rstrip().rstrip(";")
    # 检查是否已有 LIMIT
    if re.search(r"\bLIMIT\s+\d+\b", sql_stripped, re.IGNORECASE):
        return sql_stripped
    return f"{sql_stripped} LIMIT {limit}"


# ------------------------------------------------------------------
# 注册工具
# ------------------------------------------------------------------

register_tool(ListTablesTool())
register_tool(GetTableSchemaTool())
register_tool(QueryDatabaseTool())
