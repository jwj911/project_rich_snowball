"""数据工具集。

为 Agent 提供查询期货数据的能力，封装对数据库的直接访问。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from models import (
    KlineDataDB,
    RealtimeQuoteDB,
    TradingCalendarDB,
    VarietyDB,
)
from services.agent.context import AgentContext
from services.agent.tools import Tool, ToolDefinition, ToolParameter, register_tool


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
                ToolParameter(name="period", type="string", description="周期，如 1d(日线)、1h(小时线)、15m(15分钟线)", required=False),
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
    description = "列出所有当前活跃的期货品种，可按类别筛选。"

    def _build_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(name="category", type="string", description="类别筛选，如有色金属、黑色系、农产品等", required=False),
            ],
        )

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        category = kwargs.get("category")
        return _list_active_varieties(context.db, category=category)


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


# 注册工具（实例化后注册到全局注册表）
register_tool(GetVarietyInfoTool())
register_tool(GetRealtimeQuoteTool())
register_tool(GetKlineDataTool())
register_tool(ListActiveVarietiesTool())
register_tool(GetMarketStatusTool())


# ---------- 服务层直接调用函数（供 DataAgent 内部使用） ----------


def _get_variety_info(db: Session, symbol: str) -> dict[str, Any] | None:
    """查询品种基础信息。"""
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol.upper(), VarietyDB.is_active == True).first()  # noqa: E712
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
    """获取实时行情。"""
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol.upper(), VarietyDB.is_active == True).first()  # noqa: E712
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
) -> list[dict[str, Any]]:
    """获取 K 线数据。"""
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol.upper(), VarietyDB.is_active == True).first()  # noqa: E712
    if not variety:
        return []

    # 周期映射：统一处理
    period_map = {"1d": "1d", "D": "1d", "1h": "1h", "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1w": "1w"}
    mapped = period_map.get(period, period)

    klines = (
        db.query(KlineDataDB)
        .filter(KlineDataDB.variety_id == variety.id, KlineDataDB.period == mapped)
        .order_by(KlineDataDB.trading_time.desc())
        .limit(min(limit, 500))
        .all()
    )

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


def _list_active_varieties(db: Session, category: str | None = None) -> list[dict[str, Any]]:
    """列出活跃品种。"""
    q = db.query(VarietyDB).filter(VarietyDB.is_active == True)  # noqa: E712
    if category:
        q = q.filter(VarietyDB.category.ilike(f"%{category}%"))
    varieties = q.order_by(VarietyDB.symbol).all()
    return [
        {
            "symbol": v.symbol,
            "name": v.name,
            "exchange": v.exchange,
            "category": v.category,
        }
        for v in varieties
    ]


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
        .filter(TradingCalendarDB.trade_date > today, TradingCalendarDB.is_trading_day == True, TradingCalendarDB.exchange == "ALL")  # noqa: E712
        .order_by(TradingCalendarDB.trade_date.asc())
        .first()
    )

    return {
        "date": today.strftime("%Y-%m-%d"),
        "is_trading_day": is_trading,
        "current_session": session_status,
        "next_trade_date": next_trade.trade_date.strftime("%Y-%m-%d") if next_trade else None,
    }
