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

_SQL_COMMENT_RE = re.compile(r"--.*?$|/\*.*?\*/", re.MULTILINE | re.DOTALL)
_SQL_STRING_RE = re.compile(r"'(?:[^']|'')*'")


def _strip_comments(sql: str) -> str:
    """移除 SQL 中的注释，避免注释中隐藏恶意关键字。"""
    return _SQL_COMMENT_RE.sub(" ", sql)


def _extract_non_string_parts(sql: str) -> str:
    """将 SQL 字符串字面量替换为占位符，只保留非字符串部分用于关键字检查。"""
    return _SQL_STRING_RE.sub(" ? ", sql)


def _validate_sql(sql: str) -> tuple[bool, str]:
    """验证 SQL 是否安全。

    Returns:
        (is_valid, error_message)
    """
    if not sql or not sql.strip():
        return False, "SQL 查询不能为空"

    stripped = _strip_comments(sql)
    check_text = _extract_non_string_parts(stripped).lower()

    # 1. 必须是 SELECT 开头
    first_token = check_text.strip().split()[0] if check_text.strip() else ""
    if first_token != "select":
        return False, f"只允许 SELECT 查询，当前以 '{first_token}' 开头"

    # 2. 检查禁止关键字
    for keyword in _FORBIDDEN_KEYWORDS:
        # 使用正则匹配单词边界，避免 "selection" 被误拦截
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, check_text):
            return False, f"SQL 中包含禁止关键字: {keyword}"

    # 3. 检查表名是否在白名单
    # 提取 FROM 和 JOIN 后的表名
    table_pattern = r"\b(from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)"
    for match in re.finditer(table_pattern, check_text):
        table_name = match.group(2)
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
        sql = _inject_user_filter(sql, context.user_id)

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
    """对私有数据表自动注入 user_id 过滤条件。

    如果 SQL 已经包含 user_id 条件，则不重复注入。
    """
    sql_lower = sql.lower()
    for table in _PRIVATE_TABLES:
        if table not in sql_lower:
            continue
        user_col = _USER_ID_COLUMN_MAP.get(table, "user_id")
        # 检查是否已有 user_id 条件
        if f"{user_col}" in sql_lower:
            continue
        # 在 WHERE 子句中注入，或在末尾添加 WHERE
        if " where " in sql_lower:
            # 在 WHERE 后注入
            # 简单处理：找到 WHERE 位置，在其后追加 AND 条件
            where_idx = sql_lower.find(" where ")
            insert_pos = where_idx + len(" where ")
            sql = sql[:insert_pos] + f"{user_col} = {user_id} AND " + sql[insert_pos:]
        else:
            # 在 ORDER BY / LIMIT 之前添加 WHERE
            order_idx = sql_lower.find(" order by ")
            limit_idx = sql_lower.find(" limit ")
            insert_pos = len(sql)
            if order_idx > 0:
                insert_pos = order_idx
            elif limit_idx > 0:
                insert_pos = limit_idx
            sql = sql[:insert_pos] + f" WHERE {user_col} = {user_id}" + sql[insert_pos:]
    return sql


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
