"""因子数据加载器。

从 K 线数据构建面板数据结构（日期 × 品种），供因子 DSL 和评估器使用。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from models import KlineDataDB, VarietyDB
from services.agent.utils import resolve_symbol

logger = logging.getLogger(__name__)


def load_panel_data(
    db: Session,
    symbols: list[str] | None = None,
    category: str | None = None,
    start_date: date | datetime | None = None,
    end_date: date | datetime | None = None,
    period: str = "1d",
    min_bars: int = 30,
) -> "PanelData":
    """加载因子面板数据。

    Args:
        db: 数据库会话。
        symbols: 品种代码列表。若为空则按 category 筛选或加载全部活跃品种。
        category: 品种类别筛选，如 "黑色系"、"有色金属"。
        start_date: 起始日期（包含）。
        end_date: 结束日期（包含），默认今天。
        period: K 线周期，默认 1d。
        min_bars: 单个品种至少需要的 K 线数量，不足则丢弃。

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

    # 为每个品种加载 K 线
    symbol_frames: dict[str, pd.DataFrame] = {}
    for v in varieties:
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
        if len(klines) < min_bars:
            logger.debug("品种 %s K 线数量 %d 不足 %d，跳过", v.symbol, len(klines), min_bars)
            continue

        df = pd.DataFrame(
            [
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
        )
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
    )


def extract_factor_universe(query: str, db: Session) -> tuple[list[str] | None, str | None]:
    """从用户查询中提取因子评估的品种池。

    返回 (symbols, category)。
    若用户给出具体品种列表，返回 symbols；否则尝试返回 category。
    """
    # 尝试解析单个品种
    single_symbol = resolve_symbol(db, query)
    if single_symbol:
        return [single_symbol], None

    # 类别关键词兜底
    category_keywords = {
        "黑色系": ["黑色", "螺纹", "铁矿", "焦煤", "焦炭", "热卷"],
        "有色金属": ["有色", "铜", "铝", "锌", "铅", "镍", "锡", "黄金", "白银"],
        "农产品": ["农产品", "豆粕", "菜粕", "豆油", "棕榈", "棉花", "白糖", "玉米"],
        "能源化工": ["能源", "化工", "原油", "沥青", "燃油", "甲醇", "PTA", "PP"],
    }
    for category, keywords in category_keywords.items():
        if any(kw in query for kw in keywords):
            return None, category

    return None, None
