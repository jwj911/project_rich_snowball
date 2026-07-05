"""Agent 可用的数据目录服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    BacktestRunDB,
    ContractRolloverDB,
    FutContractDB,
    FutDailyDataDB,
    FutHoldingDB,
    FutMainDailyDataDB,
    FutPriceLimitDB,
    FutSettleDB,
    FutWeeklyDetailDB,
    FutWsrDB,
    KlineDataDB,
    RealtimeQuoteDB,
    StrategyDB,
    TradeRecordDB,
    VarietyDB,
)
from services.agent.utils import resolve_symbol
from services.data_quality import DataQualityService


@dataclass(frozen=True)
class DatasetDefinition:
    """数据目录中的静态业务定义。"""

    name: str
    label: str
    description: str
    grain: str
    model: type
    date_field: str | None = None
    symbol_field: str | None = None
    agents: tuple[str, ...] = ()


DATASET_DEFINITIONS: dict[str, DatasetDefinition] = {
    "varieties": DatasetDefinition(
        "varieties",
        "期货品种",
        "品种主数据，包含品种代码、名称、交易所、类别和当前主力合约。",
        "one row per variety",
        VarietyDB,
        date_field="updated_at",
        symbol_field="symbol",
        agents=("data", "data_quality", "tech_analysis", "backtest", "factor_mining"),
    ),
    "fut_contracts": DatasetDefinition(
        "fut_contracts",
        "期货合约",
        "具体合约元数据，包含合约代码、上市/摘牌日期和交易所。",
        "one row per contract",
        FutContractDB,
        date_field="updated_at",
        symbol_field="fut_code",
        agents=("data", "data_quality", "backtest"),
    ),
    "realtime_quotes": DatasetDefinition(
        "realtime_quotes",
        "实时行情",
        "品种级实时行情快照，用于当前价格、涨跌幅、盘口和成交量查询。",
        "one row per variety",
        RealtimeQuoteDB,
        date_field="updated_at",
        agents=("data", "data_quality", "risk_management"),
    ),
    "kline_data": DatasetDefinition(
        "kline_data",
        "K 线数据",
        "合约级历史 K 线，是技术分析、回测和因子评估的基础数据。",
        "variety + contract + period + trading_time",
        KlineDataDB,
        date_field="trading_date",
        agents=("data", "data_quality", "tech_analysis", "backtest", "factor_mining"),
    ),
    "contract_rollovers": DatasetDefinition(
        "contract_rollovers",
        "主力换月",
        "主力合约切换历史，用于连续合约拼接和换月解释。",
        "variety + effective_date",
        ContractRolloverDB,
        date_field="effective_date",
        agents=("data", "data_quality", "backtest"),
    ),
    "fut_main_daily_data": DatasetDefinition(
        "fut_main_daily_data",
        "Tushare 主力日/周/月线",
        "从 fut_daily_data 筛选的 43 个核心品种主力合约数据，供前端展示和策略回测。",
        "variety + period + trade_date",
        FutMainDailyDataDB,
        date_field="trade_date",
        symbol_field="ts_code",
        agents=("data", "data_quality", "tech_analysis", "backtest", "factor_mining"),
    ),
    "fut_daily_data": DatasetDefinition(
        "fut_daily_data",
        "Tushare 日/周/月线",
        "Tushare fut_daily/pro_bar 全量数据，包含结算价、成交额、持仓等扩展行情。",
        "variety + period + trade_date",
        FutDailyDataDB,
        date_field="trade_date",
        symbol_field="ts_code",
        agents=("data", "data_quality", "factor_mining"),
    ),
    "fut_settle": DatasetDefinition(
        "fut_settle",
        "结算参数",
        "合约每日结算、手续费、保证金参数。",
        "contract + trade_date",
        FutSettleDB,
        date_field="trade_date",
        symbol_field="ts_code",
        agents=("data", "risk_management", "factor_mining"),
    ),
    "fut_wsr": DatasetDefinition(
        "fut_wsr",
        "仓单日报",
        "仓单数量与变化，用于供需和库存侧分析。",
        "symbol + warehouse + trade_date",
        FutWsrDB,
        date_field="trade_date",
        symbol_field="symbol",
        agents=("data", "factor_mining"),
    ),
    "fut_holding": DatasetDefinition(
        "fut_holding",
        "持仓排名",
        "会员成交、持多、持空排名数据。",
        "symbol + broker + trade_date",
        FutHoldingDB,
        date_field="trade_date",
        symbol_field="symbol",
        agents=("data", "factor_mining"),
    ),
    "fut_price_limits": DatasetDefinition(
        "fut_price_limits",
        "涨跌停价格",
        "合约每日涨跌停价格和保证金比例。",
        "contract + trade_date",
        FutPriceLimitDB,
        date_field="trade_date",
        symbol_field="ts_code",
        agents=("data", "risk_management"),
    ),
    "fut_weekly_detail": DatasetDefinition(
        "fut_weekly_detail",
        "交易周报",
        "交易所主要品种周度成交、成交额、持仓和同比环比数据。",
        "exchange + product + week",
        FutWeeklyDetailDB,
        date_field="week_date",
        symbol_field="prd",
        agents=("data", "factor_mining"),
    ),
    "trade_records": DatasetDefinition(
        "trade_records",
        "模拟持仓",
        "用户模拟交易记录，关联观点、策略和回测。",
        "user + variety + trade",
        TradeRecordDB,
        date_field="created_at",
        agents=("risk_management", "backtest"),
    ),
    "strategies": DatasetDefinition(
        "strategies",
        "策略库",
        "用户保存的结构化策略 DSL。",
        "user + strategy",
        StrategyDB,
        date_field="created_at",
        symbol_field="symbol",
        agents=("strategy_compiler", "backtest"),
    ),
    "backtest_runs": DatasetDefinition(
        "backtest_runs",
        "回测运行",
        "策略或一次性查询的回测结果快照。",
        "user + run",
        BacktestRunDB,
        date_field="created_at",
        agents=("backtest", "factor_mining"),
    ),
}


class DataCatalogService:
    """动态数据目录，供 Agent 查询当前可用数据资产。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_available_datasets(self) -> list[dict[str, Any]]:
        """列出第一版纳入目录的所有数据集。"""
        return [self.get_dataset_profile(name, include_columns=False) for name in DATASET_DEFINITIONS]

    def get_dataset_profile(self, dataset_name: str, include_columns: bool = True) -> dict[str, Any]:
        """返回单个数据集的业务定义、覆盖范围和质量摘要。"""
        definition = self._get_definition(dataset_name)
        row_count = self.db.query(definition.model).count()
        coverage = self._date_coverage(definition)
        symbols = self._symbol_coverage(definition)
        quality_status = self._quality_status(definition.name, row_count)
        result = {
            "dataset_name": definition.name,
            "label": definition.label,
            "description": definition.description,
            "grain": definition.grain,
            "row_count": row_count,
            "date_coverage": coverage,
            "symbol_coverage": symbols,
            "quality_status": quality_status,
            "agents": list(definition.agents),
        }
        if include_columns:
            result["columns"] = [column.name for column in definition.model.__table__.columns]
        return result

    def get_symbol_data_coverage(self, symbol: str, period: str | None = None) -> dict[str, Any]:
        """查询指定品种在核心行情数据集中的覆盖情况。"""
        resolved_symbol = resolve_symbol(self.db, symbol) or symbol.upper().strip()
        kline_period = period or "1d"
        return {
            "symbol": resolved_symbol,
            "period": kline_period,
            "datasets": {
                "varieties": self._variety_coverage(resolved_symbol),
                "realtime_quotes": self._realtime_symbol_coverage(resolved_symbol),
                "kline_data": self._kline_symbol_coverage(resolved_symbol, kline_period),
                "fut_main_daily_data": self._fut_main_daily_symbol_coverage(resolved_symbol),
                "fut_daily_data": self._fut_daily_symbol_coverage(resolved_symbol),
            },
        }

    def get_data_quality_summary(
        self,
        symbol: str | None = None,
        dataset_name: str | None = None,
        period: str | None = None,
    ) -> dict[str, Any]:
        """返回目录维度的质量摘要，优先复用 DataQualityService 的确定性规则。"""
        quality = DataQualityService(self.db)
        if dataset_name == "realtime_quotes":
            return quality.check_realtime(symbol.upper() if symbol else None).to_dict()
        if dataset_name in (None, "kline_data") and symbol:
            return quality.check_kline(symbol.upper(), period or "1d").to_dict()
        return quality.inventory().to_dict()

    def _get_definition(self, dataset_name: str) -> DatasetDefinition:
        normalized = dataset_name.strip()
        if normalized not in DATASET_DEFINITIONS:
            known = ", ".join(DATASET_DEFINITIONS)
            raise ValueError(f"未知数据集 {dataset_name}，可选值：{known}")
        return DATASET_DEFINITIONS[normalized]

    def _date_coverage(self, definition: DatasetDefinition) -> dict[str, Any]:
        if not definition.date_field:
            return {"first_date": None, "last_date": None}
        column = getattr(definition.model, definition.date_field)
        first_value, last_value = self.db.query(func.min(column), func.max(column)).one()
        return {
            "first_date": _serialize_date(first_value),
            "last_date": _serialize_date(last_value),
        }

    def _symbol_coverage(self, definition: DatasetDefinition) -> dict[str, Any]:
        if definition.name == "realtime_quotes":
            count = self.db.query(func.count(RealtimeQuoteDB.id)).join(VarietyDB).scalar() or 0
            return {"symbol_count": int(count), "sample": self._sample_realtime_symbols()}
        if definition.name == "kline_data":
            count = (
                self.db.query(func.count(func.distinct(VarietyDB.symbol)))
                .join(KlineDataDB, KlineDataDB.variety_id == VarietyDB.id)
                .scalar()
                or 0
            )
            return {"symbol_count": int(count), "sample": self._sample_kline_symbols()}
        if not definition.symbol_field:
            return {"symbol_count": None, "sample": []}
        column = getattr(definition.model, definition.symbol_field)
        rows = self.db.query(column).filter(column.isnot(None)).distinct().limit(10).all()
        count = self.db.query(func.count(func.distinct(column))).scalar() or 0
        return {"symbol_count": int(count), "sample": [row[0] for row in rows if row[0]]}

    def _quality_status(self, dataset_name: str, row_count: int) -> str:
        if row_count <= 0:
            return "empty"
        if dataset_name in {"kline_data", "realtime_quotes"}:
            summary = self.get_data_quality_summary(dataset_name=dataset_name)
            return summary["status"]
        return "available"

    def _variety_coverage(self, symbol: str) -> dict[str, Any]:
        variety = self.db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        return {
            "available": variety is not None,
            "row_count": 1 if variety else 0,
            "name": variety.name if variety else None,
            "exchange": variety.exchange if variety else None,
        }

    def _realtime_symbol_coverage(self, symbol: str) -> dict[str, Any]:
        row = (
            self.db.query(RealtimeQuoteDB)
            .join(VarietyDB, RealtimeQuoteDB.variety_id == VarietyDB.id)
            .filter(VarietyDB.symbol == symbol)
            .first()
        )
        return {
            "available": row is not None,
            "row_count": 1 if row else 0,
            "last_updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        }

    def _kline_symbol_coverage(self, symbol: str, period: str) -> dict[str, Any]:
        row = (
            self.db.query(
                func.count(KlineDataDB.id),
                func.min(KlineDataDB.trading_date),
                func.max(KlineDataDB.trading_date),
                func.count(func.distinct(KlineDataDB.contract_id)),
            )
            .join(VarietyDB, KlineDataDB.variety_id == VarietyDB.id)
            .filter(VarietyDB.symbol == symbol, KlineDataDB.period == period)
            .one()
        )
        row_count, first_date, last_date, contract_count = row
        return {
            "available": int(row_count or 0) > 0,
            "row_count": int(row_count or 0),
            "first_date": _serialize_date(first_date),
            "last_date": _serialize_date(last_date),
            "contract_count": int(contract_count or 0),
        }

    def _fut_main_daily_symbol_coverage(self, symbol: str) -> dict[str, Any]:
        variety = self.db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        if not variety:
            return {"available": False, "row_count": 0, "first_date": None, "last_date": None}
        row_count, first_date, last_date = (
            self.db.query(
                func.count(FutMainDailyDataDB.id),
                func.min(FutMainDailyDataDB.trade_date),
                func.max(FutMainDailyDataDB.trade_date),
            )
            .filter(FutMainDailyDataDB.variety_id == variety.id)
            .one()
        )
        return {
            "available": int(row_count or 0) > 0,
            "row_count": int(row_count or 0),
            "first_date": _serialize_date(first_date),
            "last_date": _serialize_date(last_date),
        }

    def _fut_daily_symbol_coverage(self, symbol: str) -> dict[str, Any]:
        variety = self.db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        if not variety:
            return {"available": False, "row_count": 0, "first_date": None, "last_date": None}
        row_count, first_date, last_date = (
            self.db.query(
                func.count(FutDailyDataDB.id),
                func.min(FutDailyDataDB.trade_date),
                func.max(FutDailyDataDB.trade_date),
            )
            .filter(FutDailyDataDB.variety_id == variety.id)
            .one()
        )
        return {
            "available": int(row_count or 0) > 0,
            "row_count": int(row_count or 0),
            "first_date": _serialize_date(first_date),
            "last_date": _serialize_date(last_date),
        }

    def _sample_realtime_symbols(self) -> list[str]:
        rows = (
            self.db.query(VarietyDB.symbol)
            .join(RealtimeQuoteDB, RealtimeQuoteDB.variety_id == VarietyDB.id)
            .order_by(VarietyDB.symbol.asc())
            .limit(10)
            .all()
        )
        return [row[0] for row in rows]

    def _sample_kline_symbols(self) -> list[str]:
        rows = (
            self.db.query(VarietyDB.symbol)
            .join(KlineDataDB, KlineDataDB.variety_id == VarietyDB.id)
            .distinct()
            .order_by(VarietyDB.symbol.asc())
            .limit(10)
            .all()
        )
        return [row[0] for row in rows]


def _serialize_date(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()
