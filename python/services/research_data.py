"""研究宽表的显式数据视图选择与加载器。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from models import AgentMarketPanelDailyDB, VarietyDB

RAW_CONTRACT_VIEW = "raw_contract"
MAIN_CONTINUOUS_VIEW = "main_continuous"
MAIN_BACK_ADJUSTED_VIEW = "main_back_adjusted"
MAIN_FORWARD_ADJUSTED_VIEW = "main_forward_adjusted"
MARKET_PANEL_DATA_VIEWS = frozenset(
    {
        RAW_CONTRACT_VIEW,
        MAIN_CONTINUOUS_VIEW,
        MAIN_BACK_ADJUSTED_VIEW,
        MAIN_FORWARD_ADJUSTED_VIEW,
    }
)


@dataclass(frozen=True)
class ResearchDataSelection:
    """调用方显式选择的研究数据口径。``None`` 保留既有 K 线默认链路。"""

    data_view: str | None = None
    contract_code: str | None = None

    @property
    def uses_market_panel(self) -> bool:
        return self.data_view is not None


@dataclass(frozen=True)
class ResearchDataSlice:
    """用于因子或回测的标准化研究数据及可审计元数据。"""

    rows: list[dict[str, Any]]
    metadata: dict[str, Any]


def parse_research_data_selection(query: str) -> ResearchDataSelection:
    """从自然语言中提取显式的宽表视图和 raw-contract 合约代码。"""
    text = query.lower()
    data_view = _explicit_data_view(text)
    contract_code = _extract_contract_code(query)
    return ResearchDataSelection(data_view=data_view, contract_code=contract_code)


def validate_research_data_selection(
    selection: ResearchDataSelection,
    *,
    period: str = "1d",
) -> None:
    """校验宽表视图的周期和原始合约选择约束。"""
    if not selection.uses_market_panel:
        return
    if selection.data_view not in MARKET_PANEL_DATA_VIEWS:
        raise ValueError(f"不支持的 data_view：{selection.data_view}")
    if _normalize_period(period) != "1d":
        raise ValueError("研究宽表当前仅支持 1d 周期")
    if selection.data_view == RAW_CONTRACT_VIEW and not selection.contract_code:
        raise ValueError("raw_contract 视图必须显式指定 contract_code，例如：合约 RB2501")


def load_market_panel_data(
    db: Session,
    *,
    symbol: str,
    data_view: str,
    period: str = "1d",
    contract_code: str | None = None,
    limit: int = 500,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ResearchDataSlice:
    """从日频研究宽表加载一个明确数据口径的时间序列。"""
    selection = ResearchDataSelection(data_view=data_view, contract_code=contract_code)
    validate_research_data_selection(selection, period=period)

    query = (
        db.query(AgentMarketPanelDailyDB)
        .join(VarietyDB, AgentMarketPanelDailyDB.variety_id == VarietyDB.id)
        .filter(
            VarietyDB.symbol == symbol.upper().strip(),
            AgentMarketPanelDailyDB.data_view == data_view,
            AgentMarketPanelDailyDB.period == _normalize_period(period),
        )
    )
    if contract_code:
        query = query.filter(AgentMarketPanelDailyDB.contract_code == contract_code.upper().strip())
    if start_date is not None:
        query = query.filter(AgentMarketPanelDailyDB.trading_date >= start_date)
    if end_date is not None:
        query = query.filter(AgentMarketPanelDailyDB.trading_date <= end_date)

    rows = query.order_by(AgentMarketPanelDailyDB.trading_date.desc()).limit(min(limit, 5000)).all()
    rows.reverse()
    result_rows = [
        {
            "time": row.trading_date.isoformat(),
            "open": float(row.open_price),
            "high": float(row.high_price),
            "low": float(row.low_price),
            "close": float(row.close_price),
            "volume": int(row.volume),
            "amount": float(row.amount) if row.amount is not None else None,
            "open_interest": row.open_interest,
            "settlement": float(row.settlement) if row.settlement is not None else None,
            "contract_code": row.contract_code,
        }
        for row in rows
    ]
    metadata = {
        "dataset_name": "agent_market_panel_daily",
        "data_view": data_view,
        "period": _normalize_period(period),
        "contract_code": contract_code.upper().strip() if contract_code else None,
        "build_trace_ids": sorted({row.build_trace_id for row in rows if row.build_trace_id}),
        "quality_statuses": sorted({row.quality_status for row in rows}),
        "first_date": rows[0].trading_date.isoformat() if rows else None,
        "last_date": rows[-1].trading_date.isoformat() if rows else None,
        "row_count": len(rows),
    }
    return ResearchDataSlice(rows=result_rows, metadata=metadata)


def _explicit_data_view(text: str) -> str | None:
    match = re.search(
        r"(?:data_view|data-view)\s*[:=]\s*(raw_contract|main_continuous|main_back_adjusted|main_forward_adjusted)",
        text,
    )
    if match:
        return match.group(1)
    if "raw_contract" in text or "原始合约宽表" in text:
        return RAW_CONTRACT_VIEW
    if "main_forward_adjusted" in text or "前复权" in text:
        return MAIN_FORWARD_ADJUSTED_VIEW
    if "main_back_adjusted" in text or "后复权" in text:
        return MAIN_BACK_ADJUSTED_VIEW
    if "main_continuous" in text or any(term in text for term in ("主力连续", "主连", "连续合约")):
        return MAIN_CONTINUOUS_VIEW
    return None


def _extract_contract_code(query: str) -> str | None:
    """仅接受被 contract/合约关键词明确标注的代码，避免误把品种代码当作合约。"""
    match = re.search(
        r"(?:contract(?:_code)?|合约(?:代码)?)\s*[:=：]?\s*([A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z]+)?)",
        query,
        flags=re.IGNORECASE,
    )
    return match.group(1).upper() if match else None


def _normalize_period(period: str) -> str:
    return {"d": "1d", "day": "1d", "1d": "1d"}.get(period.lower(), period.lower())
