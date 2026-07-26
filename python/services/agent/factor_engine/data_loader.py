"""因子数据加载器。

从 K 线数据构建面板数据结构（日期 × 品种），供因子 DSL 和评估器使用。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import pandas as pd
from sqlalchemy.orm import Session

from models import KlineDataDB, VarietyDB
from services.agent.utils import resolve_symbol, resolve_symbols
from services.research_data import (
    RAW_CONTRACT_VIEW,
    ResearchDataSelection,
    load_market_panel_data,
    validate_research_data_selection,
)

if TYPE_CHECKING:
    from services.agent.factor_engine.dsl import PanelData

logger = logging.getLogger(__name__)


def load_panel_data(
    db: Session,
    symbols: list[str] | None = None,
    category: str | None = None,
    start_date: date | datetime | None = None,
    end_date: date | datetime | None = None,
    period: str = "1d",
    min_bars: int = 30,
    data_selection: ResearchDataSelection | None = None,
) -> PanelData:
    """加载因子面板数据。

    Args:
        db: 数据库会话。
        symbols: 品种代码列表。若为空则按 category 筛选或加载全部活跃品种。
        category: 品种类别筛选，如 "黑色系"、"有色金属"。
        start_date: 起始日期（包含）。
        end_date: 结束日期（包含），默认今天。
        period: K 线周期，默认 1d。
        min_bars: 单个品种至少需要的 K 线数量，不足则丢弃。
        data_selection: 显式研究宽表视图；为空时保留既有 ``kline_data`` 路径。

    Returns:
        PanelData 对象，包含 open/high/low/close/volume 五个 DataFrame。
    """
    from services.agent.factor_engine.dsl import PanelData

    if end_date is None:
        end_date = datetime.now().date()
    elif isinstance(end_date, datetime):
        end_date = end_date.date()

    if start_date is None:
        # 默认取 1 年数据
        start_date = end_date - timedelta(days=365)
    elif isinstance(start_date, datetime):
        start_date = start_date.date()

    # 确定品种列表
    if not symbols:
        q = db.query(VarietyDB).filter(VarietyDB.is_active == True)  # noqa: E712
        if category:
            q = q.filter(VarietyDB.category.ilike(f"%{category}%"))
        varieties = q.all()
    else:
        varieties = (
            db.query(VarietyDB)
            .filter(VarietyDB.symbol.in_([s.upper() for s in symbols]), VarietyDB.is_active == True)  # noqa: E712
            .all()
        )

    if not varieties:
        raise ValueError("未找到匹配的品种")

    # 周期标准化
    period_map = {"1d": "1d", "D": "1d", "1h": "1h", "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1w": "1w"}
    mapped_period = period_map.get(period, period)
    selection = data_selection or ResearchDataSelection()
    validate_research_data_selection(selection, period=mapped_period)
    if selection.data_view == RAW_CONTRACT_VIEW and len(varieties) != 1:
        raise ValueError("raw_contract 因子研究一次只能评估一个明确品种和合约")

    # 为每个品种加载 K 线
    symbol_frames: dict[str, pd.DataFrame] = {}
    source_metadata: dict[str, dict] = {}
    for v in varieties:
        if selection.uses_market_panel:
            research_slice = load_market_panel_data(
                db,
                symbol=v.symbol,
                data_view=selection.data_view or "",
                period=mapped_period,
                contract_code=selection.contract_code,
                start_date=start_date,
                end_date=end_date,
                limit=5000,
            )
            records = [
                {
                    "date": row["time"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                }
                for row in research_slice.rows
            ]
            source_metadata[v.symbol] = research_slice.metadata
        else:
            klines = (
                db.query(KlineDataDB)
                .filter(
                    KlineDataDB.variety_id == v.id,
                    KlineDataDB.period == mapped_period,
                    KlineDataDB.trading_date >= start_date,
                    KlineDataDB.trading_date <= end_date,
                )
                .order_by(KlineDataDB.trading_date.asc())
                .all()
            )
            records = [
                {
                    "date": k.trading_date,
                    "open": float(k.open_price),
                    "high": float(k.high_price),
                    "low": float(k.low_price),
                    "close": float(k.close_price),
                    "volume": int(k.volume) if k.volume else 0,
                }
                for k in klines
            ]
            source_metadata[v.symbol] = {
                "dataset_name": "kline_data",
                "data_view": None,
                "period": mapped_period,
                "contract_code": None,
                "build_trace_ids": [],
                "quality_statuses": [],
                "first_date": records[0]["date"].isoformat() if records else None,
                "last_date": records[-1]["date"].isoformat() if records else None,
                "row_count": len(records),
            }

        if len(records) < min_bars:
            logger.debug("品种 %s 行情数量 %d 不足 %d，跳过", v.symbol, len(records), min_bars)
            source_metadata.pop(v.symbol, None)
            continue

        df = pd.DataFrame(records)
        df = df.set_index("date").sort_index()
        symbol_frames[v.symbol] = df

    if not symbol_frames:
        raise ValueError("未找到足够 K 线数据的品种")

    # 构建面板：对齐日期，合并各品种
    all_dates = sorted(set().union(*[df.index for df in symbol_frames.values()]))
    panel_index = pd.Index(all_dates, name="date")

    def _build_field(field: str) -> pd.DataFrame:
        data: dict[str, pd.Series] = {}
        for symbol, df in symbol_frames.items():
            series = df[field].reindex(panel_index)
            data[symbol] = series
        return pd.DataFrame(data, index=panel_index)

    return PanelData(
        open=_build_field("open"),
        high=_build_field("high"),
        low=_build_field("low"),
        close=_build_field("close"),
        volume=_build_field("volume"),
        metadata={
            "dataset_name": "agent_market_panel_daily" if selection.uses_market_panel else "kline_data",
            "data_view": selection.data_view,
            "period": mapped_period,
            "contract_code": selection.contract_code,
            "symbols": source_metadata,
        },
    )


def extract_factor_universe(query: str, db: Session) -> tuple[list[str] | None, str | None]:
    """从用户查询中提取因子评估的品种池。

    返回 (symbols, category)。
    若用户给出具体品种列表，返回 symbols；否则尝试返回 category。

    支持：
    - 精确代码 + 分隔符：RB, HC, I 或 螺纹钢、热卷
    - 排除语法：除螺纹钢外的黑色系
    - 类别关键词：黑色系 / 有色金属 / 农产品 / 能源化工 / 贵金属
    """
    # 1. 尝试多品种解析（使用 resolve_symbols）
    symbols = resolve_symbols(db, query)
    if symbols and len(symbols) >= 1:
        # 如果只有一个品种，检查是否来自类别匹配（类别匹配应返回 category）
        # 区分精确指定 vs 类别兜底
        if len(symbols) >= 2:
            return symbols, None
        # 单个品种：确认是否用户精确指定的
        single = resolve_symbol(db, query)
        if single:
            return [single], None

    # 2. 类别关键词兜底
    category_keywords = {
        "黑色系": ["黑色", "螺纹", "铁矿", "焦煤", "焦炭", "热卷"],
        "有色金属": ["有色", "铜", "铝", "锌", "铅", "镍", "锡", "黄金", "白银"],
        "农产品": ["农产品", "豆粕", "菜粕", "豆油", "棕榈", "棉花", "白糖", "玉米"],
        "能源化工": ["能源", "化工", "原油", "沥青", "燃油", "甲醇", "PTA", "PP"],
        "贵金属": ["贵金属", "黄金", "白银"],
    }
    for category, keywords in category_keywords.items():
        if any(kw in query for kw in keywords):
            return None, category

    return None, None
