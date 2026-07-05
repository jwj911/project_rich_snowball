"""数据工具集。

为 Agent 提供查询期货数据的能力，封装对数据库的直接访问。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.orm import Session

from models import (
    FutHoldingDB,
    FutMainDailyDataDB,
    FutPriceLimitDB,
    FutSettleDB,
    FutWsrDB,
    KlineDataDB,
    RealtimeQuoteDB,
    TradingCalendarDB,
    VarietyDB,
)
from services.agent.context import AgentContext
from services.agent.tools import Tool, ToolDefinition, ToolParameter, register_tool
from services.agent.utils import resolve_symbol
from services.data_catalog import DataCatalogService

logger = logging.getLogger(__name__)


class GetVarietyInfoTool(Tool):
    """查询品种基础信息。"""

    name = "get_variety_info"
    description = "查询期货品种的基础信息，包括名称、交易所、类别、合约代码、手续费、保证金等。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(name="symbol", type="string", description="品种代码，如 RB、AU、CU", required=True),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        symbol = kwargs.get("symbol", "").upper().strip()
        result = _get_variety_info(context.db, symbol)
        return result or {"error": f"未找到品种 {symbol}"}


class GetRealtimeQuoteTool(Tool):
    """获取实时行情。"""

    name = "get_realtime_quote"
    description = "获取期货品种的实时行情数据，包括最新价、涨跌幅、开盘价、最高价、最低价、成交量等。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(name="symbol", type="string", description="品种代码，如 RB、AU", required=True),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        symbol = kwargs.get("symbol", "").upper().strip()
        result = _get_realtime_quote(context.db, symbol)
        return result or {"error": f"未找到品种 {symbol} 的实时行情"}


class GetKlineDataTool(Tool):
    """获取 K 线数据。"""

    name = "get_kline_data"
    description = "获取期货品种的历史 K 线数据。支持日线、小时线、分钟线等周期。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(name="symbol", type="string", description="品种代码", required=True),
                ToolParameter(
                    name="period",
                    type="string",
                    description="周期，如 1d(日线)、1h(小时线)、15m(15分钟线)",
                    required=False,
                ),
                ToolParameter(name="limit", type="number", description="返回条数，默认 100，最大 500", required=False),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        symbol = kwargs.get("symbol", "").upper().strip()
        period = kwargs.get("period", "1d")
        limit = kwargs.get("limit", 100)
        if isinstance(limit, str):
            limit = int(limit)
        return _get_kline_data(context.db, symbol, period=period, limit=limit)


class ListActiveVarietiesTool(Tool):
    """列出活跃品种。"""

    name = "list_active_varieties"
    description = "列出所有当前活跃的期货品种，可按类别筛选并排序。注意：查询『涨幅前 N』时使用 sort_order='desc'，查询『跌幅前 N』时使用 sort_order='asc'。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="category", type="string", description="类别筛选，如有色金属、黑色系、农产品等", required=False
                ),
                ToolParameter(
                    name="sort_by",
                    type="string",
                    description="排序字段：change_percent（涨跌幅）、volume（成交量）、current_price（最新价）、symbol（品种代码）",
                    required=False,
                ),
                ToolParameter(
                    name="sort_order",
                    type="string",
                    description="排序方向：asc（升序）或 desc（降序），默认 asc",
                    required=False,
                ),
                ToolParameter(
                    name="limit", type="number", description="返回数量上限，默认 50，最大 200", required=False
                ),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        category = kwargs.get("category")
        sort_by = kwargs.get("sort_by")
        sort_order = kwargs.get("sort_order", "asc")
        limit = kwargs.get("limit", 50)
        if isinstance(limit, str):
            limit = int(limit)
        return _list_active_varieties(
            context.db,
            category=category,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
        )


class GetMarketStatusTool(Tool):
    """获取市场状态。"""

    name = "get_market_status"
    description = "获取当前期货市场状态，包括是否交易日、当前交易时段、下一交易日等。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        return _get_market_status(context.db)


class ListAvailableDatasetsTool(Tool):
    """列出 Agent 可用数据集。"""

    name = "list_available_datasets"
    description = "列出当前系统可供 Agent 使用的数据集，包括业务含义、粒度、行数、日期覆盖、品种覆盖和质量状态。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(name=self.name, description=self.description, parameters=[])

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        return DataCatalogService(context.db).list_available_datasets()


class GetDatasetProfileTool(Tool):
    """查询数据集 profile。"""

    name = "get_dataset_profile"
    description = "查询指定数据集的 profile，包括字段列表、业务含义、粒度、覆盖范围和可用 Agent。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="dataset_name",
                    type="string",
                    description="数据集名称，如 kline_data、realtime_quotes、fut_daily_data",
                    required=True,
                ),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        dataset_name = kwargs.get("dataset_name", "")
        try:
            return DataCatalogService(context.db).get_dataset_profile(dataset_name)
        except ValueError as exc:
            return {"error": str(exc)}


class GetSymbolDataCoverageTool(Tool):
    """查询品种数据覆盖。"""

    name = "get_symbol_data_coverage"
    description = "查询某个品种在品种表、实时行情、K 线和扩展日线中的覆盖范围。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="symbol", type="string", description="品种代码或中文名称，如 RB、螺纹钢", required=True
                ),
                ToolParameter(name="period", type="string", description="K 线周期，默认 1d", required=False),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        symbol = kwargs.get("symbol", "")
        period = kwargs.get("period")
        return DataCatalogService(context.db).get_symbol_data_coverage(symbol, period=period)


class GetDataQualitySummaryTool(Tool):
    """查询数据质量摘要。"""

    name = "get_data_quality_summary"
    description = "查询数据质量摘要。可指定 symbol 和 dataset_name；kline_data 会执行 OHLC、重复和缺口检查。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(name="symbol", type="string", description="品种代码或中文名称，可选", required=False),
                ToolParameter(
                    name="dataset_name",
                    type="string",
                    description="数据集名称，如 kline_data、realtime_quotes，可选",
                    required=False,
                ),
                ToolParameter(name="period", type="string", description="K 线周期，默认 1d", required=False),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        return DataCatalogService(context.db).get_data_quality_summary(
            symbol=kwargs.get("symbol"),
            dataset_name=kwargs.get("dataset_name"),
            period=kwargs.get("period"),
        )


# 注册基础工具（实例化后注册到全局注册表）
register_tool(GetVarietyInfoTool())
register_tool(GetRealtimeQuoteTool())
register_tool(GetKlineDataTool())
register_tool(ListActiveVarietiesTool())
register_tool(GetMarketStatusTool())
register_tool(ListAvailableDatasetsTool())
register_tool(GetDatasetProfileTool())
register_tool(GetSymbolDataCoverageTool())
register_tool(GetDataQualitySummaryTool())


# ---------- 服务层直接调用函数（供 DataAgent 内部使用） ----------


def _get_variety_info(db: Session, symbol: str) -> dict[str, Any] | None:
    """查询品种基础信息，支持品种代码或中文别名。"""
    symbol = symbol.upper().strip()
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol, VarietyDB.is_active == True).first()  # noqa: E712
    if not variety:
        resolved = resolve_symbol(db, symbol)
        if resolved and resolved != symbol:
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == resolved, VarietyDB.is_active == True).first()  # noqa: E712
    if not variety:
        return None
    return {
        "symbol": variety.symbol,
        "name": variety.name,
        "exchange": variety.exchange,
        "category": variety.category,
        "contract_code": variety.contract_code,
        "tick_size": float(variety.tick_size) if variety.tick_size else None,
        "multiplier": float(variety.multiplier) if variety.multiplier else None,
        "margin_rate": float(variety.margin_rate) if variety.margin_rate else None,
        "commission": float(variety.commission) if variety.commission else None,
    }


def _get_realtime_quote(db: Session, symbol: str) -> dict[str, Any] | None:
    """获取实时行情，支持品种代码或中文别名。"""
    symbol = symbol.upper().strip()
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol, VarietyDB.is_active == True).first()  # noqa: E712
    if not variety:
        resolved = resolve_symbol(db, symbol)
        if resolved and resolved != symbol:
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == resolved, VarietyDB.is_active == True).first()  # noqa: E712
    if not variety:
        return None
    quote = db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
    if not quote:
        return None
    return {
        "symbol": variety.symbol,
        "name": variety.name,
        "current_price": float(quote.current_price) if quote.current_price else None,
        "change_percent": float(quote.change_percent) if quote.change_percent else None,
        "open_price": float(quote.open_price) if quote.open_price else None,
        "high": float(quote.high) if quote.high else None,
        "low": float(quote.low) if quote.low else None,
        "volume": quote.volume,
        "open_interest": quote.open_interest,
        "bid1": float(quote.bid1) if quote.bid1 else None,
        "ask1": float(quote.ask1) if quote.ask1 else None,
        "limit_up": float(quote.limit_up) if quote.limit_up else None,
        "limit_down": float(quote.limit_down) if quote.limit_down else None,
        "updated_at": quote.updated_at.isoformat() if quote.updated_at else None,
    }


def _get_kline_data(
    db: Session,
    symbol: str,
    period: str = "1d",
    limit: int = 100,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    """获取 K 线数据，支持品种代码或中文别名，可选日期区间过滤。

    日线（1d/D）优先从 fut_main_daily_data 读取 Tushare 回填数据（覆盖全、数据量大），
    日线以下的日内周期（1h/5m/15m 等）从 kline_data 读取。
    """
    symbol = symbol.upper().strip()
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol, VarietyDB.is_active == True).first()  # noqa: E712
    if not variety:
        resolved = resolve_symbol(db, symbol)
        if resolved and resolved != symbol:
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == resolved, VarietyDB.is_active == True).first()  # noqa: E712
    if not variety:
        return []

    limit = min(limit, 500)

    # 周期映射：kline_data 使用前端周期，fut_daily_data 使用 Tushare D/W/M 周期。
    kline_period_map = {
        "1d": "1d",
        "D": "1d",
        "d": "1d",
        "1h": "1h",
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1w": "1w",
        "W": "1w",
        "w": "1w",
    }
    fut_daily_period_map = {
        "1d": "D",
        "D": "D",
        "d": "D",
        "1w": "W",
        "W": "W",
        "w": "W",
        "1M": "M",
        "1mo": "M",
        "M": "M",
        "mth": "M",
    }
    mapped = kline_period_map.get(period, period)

    # 日线优先从 fut_main_daily_data 获取，指定优先级：主力连续 > 下季度合约 > 所有。
    # 避免多种 ts_code 混入 K 线数据导致价格不连贯。
    if period in fut_daily_period_map:
        fut_period = fut_daily_period_map[period]
        ts_code_priority = [f"{symbol}.SHF", f"{symbol}.DCE", f"{symbol}.CZC", f"{symbol}.INE", f"{symbol}.GFE"]

        daily_rows: list[FutMainDailyDataDB] = []
        for preferred_ts in ts_code_priority:
            q = db.query(FutMainDailyDataDB).filter(
                FutMainDailyDataDB.variety_id == variety.id,
                FutMainDailyDataDB.period == fut_period,
                FutMainDailyDataDB.ts_code == preferred_ts,
            )
            if start_date is not None:
                q = q.filter(FutMainDailyDataDB.trade_date >= start_date)
            if end_date is not None:
                q = q.filter(FutMainDailyDataDB.trade_date <= end_date)
            daily_rows = q.order_by(FutMainDailyDataDB.trade_date.desc()).limit(limit).all()
            if daily_rows:
                break

        if not daily_rows:
            # Fallback: no ts_code filter (backward-compatible for other exchanges)
            daily_fallback = db.query(FutMainDailyDataDB).filter(
                FutMainDailyDataDB.variety_id == variety.id, FutMainDailyDataDB.period == fut_period
            )
            if start_date is not None:
                daily_fallback = daily_fallback.filter(FutMainDailyDataDB.trade_date >= start_date)
            if end_date is not None:
                daily_fallback = daily_fallback.filter(FutMainDailyDataDB.trade_date <= end_date)
            daily_rows = daily_fallback.order_by(FutMainDailyDataDB.trade_date.desc()).limit(limit).all()

        daily_result = [
            {
                "time": row.trade_date.isoformat(),
                "open": float(row.open_price),
                "high": float(row.high_price),
                "low": float(row.low_price),
                "close": float(row.close_price),
                "volume": row.volume,
            }
            for row in reversed(daily_rows)
            if row.open_price is not None
            and row.high_price is not None
            and row.low_price is not None
            and row.close_price is not None
        ]
        if daily_result:
            return daily_result

    # 日内周期或无日线数据时的 fallback
    klines_query = db.query(KlineDataDB).filter(KlineDataDB.variety_id == variety.id, KlineDataDB.period == mapped)
    if start_date is not None:
        klines_query = klines_query.filter(KlineDataDB.trading_time >= start_date)
    if end_date is not None:
        klines_query = klines_query.filter(KlineDataDB.trading_time <= end_date)
    klines = klines_query.order_by(KlineDataDB.trading_time.desc()).limit(limit).all()

    return [
        {
            "time": k.trading_time.isoformat(),
            "open": float(k.open_price),
            "high": float(k.high_price),
            "low": float(k.low_price),
            "close": float(k.close_price),
            "volume": k.volume,
        }
        for k in reversed(klines)
    ]


def _list_active_varieties(
    db: Session,
    category: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """列出活跃品种。

    Args:
        category: 类别筛选。
        sort_by: 排序字段，支持 change_percent / volume / current_price / symbol。
        sort_order: asc 或 desc。
        limit: 返回数量上限。
    """
    from sqlalchemy import desc

    q = db.query(VarietyDB).filter(VarietyDB.is_active == True)  # noqa: E712
    if category:
        q = q.filter(VarietyDB.category.ilike(f"%{category}%"))

    sort_by = (sort_by or "").lower().strip()
    sort_order = (sort_order or "asc").lower().strip()

    # 需要按行情字段排序时，外联 realtime_quotes
    if sort_by in ("change_percent", "volume", "current_price"):
        q = q.outerjoin(RealtimeQuoteDB, VarietyDB.id == RealtimeQuoteDB.variety_id)
        sort_column = {
            "change_percent": RealtimeQuoteDB.change_percent,
            "volume": RealtimeQuoteDB.volume,
            "current_price": RealtimeQuoteDB.current_price,
        }.get(sort_by)
        if sort_column is not None:
            if sort_order == "desc":
                q = q.order_by(desc(sort_column), VarietyDB.symbol)
            else:
                q = q.order_by(sort_column, VarietyDB.symbol)
    else:
        # 默认按品种代码排序
        q = q.order_by(desc(VarietyDB.symbol)) if sort_order == "desc" else q.order_by(VarietyDB.symbol)

    varieties = q.limit(min(limit, 200)).all()

    # 组装结果，包含行情数据（如有）
    result = []
    for v in varieties:
        item: dict[str, Any] = {
            "symbol": v.symbol,
            "name": v.name,
            "exchange": v.exchange,
            "category": v.category,
        }
        if v.realtime:
            item["current_price"] = float(v.realtime.current_price) if v.realtime.current_price else None
            item["change_percent"] = float(v.realtime.change_percent) if v.realtime.change_percent else None
            item["volume"] = v.realtime.volume
        result.append(item)
    return result


def _get_market_status(db: Session) -> dict[str, Any]:
    """获取市场状态。"""
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    entry = (
        db.query(TradingCalendarDB)
        .filter(TradingCalendarDB.trade_date == today, TradingCalendarDB.exchange == "ALL")
        .first()
    )
    is_trading = entry.is_trading_day if entry else True
    session_status = "unknown"
    if entry and entry.is_trading_day:
        time_str = datetime.now(UTC).strftime("%H:%M")
        day_start = entry.day_session_start or "09:00"
        day_end = entry.day_session_end or "15:00"
        if day_start <= time_str <= day_end:
            session_status = "day"
        else:
            night_start = entry.night_session_start
            night_end = entry.night_session_end
            if night_start and night_end:
                if night_start < night_end:
                    if night_start <= time_str <= night_end:
                        session_status = "night"
                else:
                    if time_str >= night_start or time_str <= night_end:
                        session_status = "night"
            if session_status == "unknown":
                session_status = "closed"
    else:
        session_status = "closed"

    next_trade = (
        db.query(TradingCalendarDB)
        .filter(
            TradingCalendarDB.trade_date > today,
            TradingCalendarDB.is_trading_day,
            TradingCalendarDB.exchange == "ALL",
        )  # noqa: E712
        .order_by(TradingCalendarDB.trade_date.asc())
        .first()
    )

    return {
        "date": today.strftime("%Y-%m-%d"),
        "is_trading_day": is_trading,
        "current_session": session_status,
        "next_trade_date": next_trade.trade_date.strftime("%Y-%m-%d") if next_trade else None,
    }


# =====================================================================
# 扩展专用数据工具 — 覆盖 Tushare 回填的仓单/持仓/结算/涨跌停等数据
# =====================================================================


class GetWarehouseReceiptsTool(Tool):
    """查询仓单日报数据。"""

    name = "get_warehouse_receipts"
    description = "查询期货品种的仓单日报数据（仓库库存、品级、年度等）。可分析库存压力、交割博弈和基差变化。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(name="symbol", type="string", description="品种代码，如 RB、CU、AU", required=True),
                ToolParameter(
                    name="days", type="number", description="查询最近 N 天，默认 30，最大 365", required=False
                ),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        symbol = kwargs.get("symbol", "").upper().strip()
        days = kwargs.get("days", 30)
        if isinstance(days, str):
            days = int(days)
        days = min(max(days, 1), 365)
        return _get_warehouse_receipts(context.db, symbol, days=days)


class GetHoldingRankingsTool(Tool):
    """查询持仓排名数据。"""

    name = "get_holding_rankings"
    description = "查询期货品种的成交持仓排名数据（成交量/多空持仓前 N 券商）。可分析资金流向、多空博弈和主力动向。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(name="symbol", type="string", description="品种代码，如 RB、AU", required=True),
                ToolParameter(
                    name="trade_date",
                    type="string",
                    description="交易日，格式 YYYY-MM-DD。不填则取最新",
                    required=False,
                ),
                ToolParameter(name="top_n", type="number", description="返回前 N 名，默认 20，最大 50", required=False),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        symbol = kwargs.get("symbol", "").upper().strip()
        trade_date = kwargs.get("trade_date")
        top_n = kwargs.get("top_n", 20)
        if isinstance(top_n, str):
            top_n = int(top_n)
        top_n = min(max(top_n, 1), 50)
        return _get_holding_rankings(context.db, symbol, trade_date=trade_date, top_n=top_n)


class GetSettlementParamsTool(Tool):
    """查询结算参数数据。"""

    name = "get_settlement_params"
    description = "查询期货品种的每日结算参数（保证金率、手续费率、交割结算价等）。可分析保证金变化对杠杆和风控的影响。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(name="symbol", type="string", description="品种代码，如 RB、AU", required=True),
                ToolParameter(
                    name="days", type="number", description="查询最近 N 天，默认 30，最大 365", required=False
                ),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        symbol = kwargs.get("symbol", "").upper().strip()
        days = kwargs.get("days", 30)
        if isinstance(days, str):
            days = int(days)
        days = min(max(days, 1), 365)
        return _get_settlement_params(context.db, symbol, days=days)


class GetPriceLimitsTool(Tool):
    """查询涨跌停价格数据。"""

    name = "get_price_limits"
    description = "查询期货品种的涨跌停价格数据（涨停价、跌停价、保证金比例）。可分析当日交易边界和波动率预期。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(name="symbol", type="string", description="品种代码，如 RB、AU", required=True),
                ToolParameter(
                    name="days", type="number", description="查询最近 N 天，默认 10，最大 90", required=False
                ),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        symbol = kwargs.get("symbol", "").upper().strip()
        days = kwargs.get("days", 10)
        if isinstance(days, str):
            days = int(days)
        days = min(max(days, 1), 90)
        return _get_price_limits(context.db, symbol, days=days)


class GetContinuousKlinesTool(Tool):
    """查询连续 K 线（主力切换拼接）。"""

    name = "get_continuous_klines"
    description = (
        "获取期货品种的连续 K 线数据（主力合约切换时自动拼接）。适合长期趋势分析和策略回测，避免换月跳空影响。"
    )

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(name="symbol", type="string", description="品种代码，如 RB、AU", required=True),
                ToolParameter(
                    name="period", type="string", description="周期，如 1d(日线)、1h(小时线)。默认 1d", required=False
                ),
                ToolParameter(name="limit", type="number", description="返回条数，默认 120，最大 500", required=False),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        symbol = kwargs.get("symbol", "").upper().strip()
        period = kwargs.get("period", "1d")
        limit = kwargs.get("limit", 120)
        if isinstance(limit, str):
            limit = int(limit)
        limit = min(max(limit, 1), 500)
        return _get_continuous_klines(context.db, symbol, period=period, limit=limit)


class GetMainKlinesTool(Tool):
    """查询当前主力合约 K 线。"""

    name = "get_main_klines"
    description = "获取期货品种当前主力合约的 K 线数据（不拼接历史合约）。适合分析当前主力合约的独立走势。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(name="symbol", type="string", description="品种代码，如 RB、AU", required=True),
                ToolParameter(
                    name="period", type="string", description="周期，如 1d(日线)、1h(小时线)。默认 1d", required=False
                ),
                ToolParameter(name="limit", type="number", description="返回条数，默认 120，最大 500", required=False),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        symbol = kwargs.get("symbol", "").upper().strip()
        period = kwargs.get("period", "1d")
        limit = kwargs.get("limit", 120)
        if isinstance(limit, str):
            limit = int(limit)
        limit = min(max(limit, 1), 500)
        return _get_main_klines(context.db, symbol, period=period, limit=limit)


# ---------- 专用工具的服务层实现 ----------


def _get_warehouse_receipts(
    db: Session,
    symbol: str,
    days: int = 30,
) -> dict[str, Any]:
    """查询仓单日报数据。"""
    symbol = symbol.upper().strip()
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol, VarietyDB.is_active == True).first()  # noqa: E712
    if not variety:
        resolved = resolve_symbol(db, symbol)
        if resolved and resolved != symbol:
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == resolved, VarietyDB.is_active == True).first()  # noqa: E712
            symbol = resolved
    if not variety:
        return {"error": f"未找到品种 {symbol}"}

    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(days=days)

    rows = (
        db.query(FutWsrDB)
        .filter(FutWsrDB.symbol == symbol, FutWsrDB.trade_date >= cutoff)
        .order_by(FutWsrDB.trade_date.desc(), FutWsrDB.warehouse)
        .limit(500)
        .all()
    )

    if not rows:
        return {"symbol": symbol, "days": days, "data": [], "note": "该品种暂无仓单数据"}

    # 按日期聚合汇总
    daily_summary: dict[str, dict[str, Any]] = {}
    detail_records = []
    for r in rows:
        date_key = r.trade_date.strftime("%Y-%m-%d") if r.trade_date else ""
        if date_key and date_key not in daily_summary:
            daily_summary[date_key] = {"date": date_key, "total_vol": 0, "warehouse_count": 0}
        if date_key:
            daily_summary[date_key]["total_vol"] += r.vol or 0
            daily_summary[date_key]["warehouse_count"] += 1
        detail_records.append(
            {
                "date": date_key,
                "warehouse": r.warehouse,
                "vol": r.vol,
                "vol_chg": r.vol_chg,
                "area": r.area,
                "year": r.year,
                "grade": r.grade,
            }
        )

    return {
        "symbol": symbol,
        "name": variety.name,
        "days": days,
        "summary": list(daily_summary.values())[:days],
        "latest_detail": detail_records[:20],
        "total_records": len(rows),
    }


def _get_holding_rankings(
    db: Session,
    symbol: str,
    trade_date: str | None = None,
    top_n: int = 20,
) -> dict[str, Any]:
    """查询持仓排名数据。"""
    symbol = symbol.upper().strip()
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol, VarietyDB.is_active == True).first()  # noqa: E712
    if not variety:
        resolved = resolve_symbol(db, symbol)
        if resolved and resolved != symbol:
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == resolved, VarietyDB.is_active == True).first()  # noqa: E712
            symbol = resolved
    if not variety:
        return {"error": f"未找到品种 {symbol}"}

    query = db.query(FutHoldingDB).filter(FutHoldingDB.symbol == symbol)
    if trade_date:
        from datetime import datetime as _dt

        try:
            dt = _dt.strptime(trade_date, "%Y-%m-%d")
            query = query.filter(FutHoldingDB.trade_date >= dt.replace(hour=0, minute=0))
            query = query.filter(FutHoldingDB.trade_date < dt.replace(hour=23, minute=59))
        except ValueError:
            return {"error": f"日期格式错误: {trade_date}，应为 YYYY-MM-DD"}
    else:
        # 取最新一天
        latest = (
            db.query(FutHoldingDB)
            .filter(FutHoldingDB.symbol == symbol)
            .order_by(FutHoldingDB.trade_date.desc())
            .first()
        )
        if latest and latest.trade_date:
            dt = latest.trade_date
            query = query.filter(FutHoldingDB.trade_date >= dt.replace(hour=0, minute=0))
            query = query.filter(FutHoldingDB.trade_date < dt.replace(hour=23, minute=59))

    # 多头排名
    longs = query.order_by(FutHoldingDB.long_hld.desc()).limit(top_n).all()
    # 空头排名（重新查，因为 order_by 不能复用）
    query2 = db.query(FutHoldingDB).filter(FutHoldingDB.symbol == symbol)
    if trade_date:
        from datetime import datetime as _dt

        dt = _dt.strptime(trade_date, "%Y-%m-%d")
        query2 = query2.filter(FutHoldingDB.trade_date >= dt.replace(hour=0, minute=0))
        query2 = query2.filter(FutHoldingDB.trade_date < dt.replace(hour=23, minute=59))
    else:
        if latest and latest.trade_date:
            dt = latest.trade_date
            query2 = query2.filter(FutHoldingDB.trade_date >= dt.replace(hour=0, minute=0))
            query2 = query2.filter(FutHoldingDB.trade_date < dt.replace(hour=23, minute=59))

    shorts = query2.order_by(FutHoldingDB.short_hld.desc()).limit(top_n).all()

    actual_date = longs[0].trade_date.strftime("%Y-%m-%d") if longs and longs[0].trade_date else trade_date or ""

    return {
        "symbol": symbol,
        "name": variety.name,
        "trade_date": actual_date,
        "long_rankings": [
            {
                "broker": r.broker,
                "long_hld": r.long_hld,
                "long_chg": r.long_chg,
                "vol": r.vol,
            }
            for r in longs
        ],
        "short_rankings": [
            {
                "broker": r.broker,
                "short_hld": r.short_hld,
                "short_chg": r.short_chg,
                "vol": r.vol,
            }
            for r in shorts
        ],
    }


def _get_settlement_params(
    db: Session,
    symbol: str,
    days: int = 30,
) -> dict[str, Any]:
    """查询结算参数数据。"""
    symbol = symbol.upper().strip()
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol, VarietyDB.is_active == True).first()  # noqa: E712
    if not variety:
        resolved = resolve_symbol(db, symbol)
        if resolved and resolved != symbol:
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == resolved, VarietyDB.is_active == True).first()  # noqa: E712
            symbol = resolved
    if not variety:
        return {"error": f"未找到品种 {symbol}"}

    contract_code = variety.contract_code
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(days=days)

    rows = (
        db.query(FutSettleDB)
        .filter(FutSettleDB.ts_code.like(f"{contract_code}%"), FutSettleDB.trade_date >= cutoff)
        .order_by(FutSettleDB.trade_date.desc())
        .limit(200)
        .all()
    )

    if not rows:
        # 尝试用 symbol 直接匹配
        rows = (
            db.query(FutSettleDB)
            .filter(FutSettleDB.ts_code.like(f"{symbol}%"), FutSettleDB.trade_date >= cutoff)
            .order_by(FutSettleDB.trade_date.desc())
            .limit(200)
            .all()
        )

    if not rows:
        return {
            "symbol": symbol,
            "contract_code": contract_code,
            "days": days,
            "data": [],
            "note": "该品种暂无结算参数数据（SHFE/INE 覆盖较好，其他交易所可能缺失）",
        }

    return {
        "symbol": symbol,
        "name": variety.name,
        "contract_code": contract_code,
        "days": days,
        "data": [
            {
                "trade_date": r.trade_date.strftime("%Y-%m-%d") if r.trade_date else "",
                "ts_code": r.ts_code,
                "settle": float(r.settle) if r.settle else None,
                "long_margin_rate": float(r.long_margin_rate) if r.long_margin_rate else None,
                "short_margin_rate": float(r.short_margin_rate) if r.short_margin_rate else None,
                "trading_fee_rate": float(r.trading_fee_rate) if r.trading_fee_rate else None,
                "trading_fee": float(r.trading_fee) if r.trading_fee else None,
                "offset_today_fee": float(r.offset_today_fee) if r.offset_today_fee else None,
            }
            for r in rows
        ],
    }


def _get_price_limits(
    db: Session,
    symbol: str,
    days: int = 10,
) -> dict[str, Any]:
    """查询涨跌停价格数据。"""
    symbol = symbol.upper().strip()
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol, VarietyDB.is_active == True).first()  # noqa: E712
    if not variety:
        resolved = resolve_symbol(db, symbol)
        if resolved and resolved != symbol:
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == resolved, VarietyDB.is_active == True).first()  # noqa: E712
            symbol = resolved
    if not variety:
        return {"error": f"未找到品种 {symbol}"}

    contract_code = variety.contract_code
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(days=days)

    rows = (
        db.query(FutPriceLimitDB)
        .filter(FutPriceLimitDB.ts_code.like(f"{contract_code}%"), FutPriceLimitDB.trade_date >= cutoff)
        .order_by(FutPriceLimitDB.trade_date.desc())
        .limit(200)
        .all()
    )

    if not rows:
        rows = (
            db.query(FutPriceLimitDB)
            .filter(FutPriceLimitDB.ts_code.like(f"{symbol}%"), FutPriceLimitDB.trade_date >= cutoff)
            .order_by(FutPriceLimitDB.trade_date.desc())
            .limit(200)
            .all()
        )

    if not rows:
        return {
            "symbol": symbol,
            "contract_code": contract_code,
            "days": days,
            "data": [],
            "note": "该品种暂无涨跌停数据",
        }

    return {
        "symbol": symbol,
        "name": variety.name,
        "contract_code": contract_code,
        "days": days,
        "data": [
            {
                "trade_date": r.trade_date.strftime("%Y-%m-%d") if r.trade_date else "",
                "ts_code": r.ts_code,
                "name": r.name,
                "up_limit": float(r.up_limit) if r.up_limit else None,
                "down_limit": float(r.down_limit) if r.down_limit else None,
                "m_ratio": float(r.m_ratio) if r.m_ratio else None,
            }
            for r in rows
        ],
    }


def _get_continuous_klines(
    db: Session,
    symbol: str,
    period: str = "1d",
    limit: int = 120,
) -> list[dict[str, Any]] | dict[str, Any]:
    """获取连续 K 线（主力切换拼接）。"""
    symbol = symbol.upper().strip()
    try:
        from services.domain.kline_service import KlineService

        svc = KlineService(db)
        # 将前端周期映射为 KlineService 格式
        period_map = {"1d": "D", "1w": "W", "1h": "1h", "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m"}
        svc_period = period_map.get(period, period)
        rows = svc.get_continuous_klines(symbol, period=svc_period, limit=limit)
        return rows
    except Exception as e:
        logger.warning("Get continuous klines failed for %s: %s", symbol, e)
        return {"error": f"获取连续 K 线失败: {e}"}


def _get_main_klines(
    db: Session,
    symbol: str,
    period: str = "1d",
    limit: int = 120,
) -> list[dict[str, Any]] | dict[str, Any]:
    """获取当前主力合约 K 线。"""
    symbol = symbol.upper().strip()
    try:
        from services.domain.kline_service import KlineService

        svc = KlineService(db)
        period_map = {"1d": "D", "1w": "W", "1h": "1h", "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m"}
        svc_period = period_map.get(period, period)
        rows = svc.get_main_klines(symbol, period=svc_period, limit=limit)
        return rows
    except Exception as e:
        logger.warning("Get main klines failed for %s: %s", symbol, e)
        return {"error": f"获取主力合约 K 线失败: {e}"}


# 注册扩展专用工具
register_tool(GetWarehouseReceiptsTool())
register_tool(GetHoldingRankingsTool())
register_tool(GetSettlementParamsTool())
register_tool(GetPriceLimitsTool())
register_tool(GetContinuousKlinesTool())
register_tool(GetMainKlinesTool())
