"""市场数据领域服务。

统一封装实时行情、批量行情、品种聚合、跨品种对比、数据质量等能力。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from config import REALTIME_REFRESH_INTERVAL_SECONDS
from errors import ErrorCode
from models import RealtimeQuoteDB, VarietyDB
from services.cache import get_cached, invalidate_cache_pattern
from services.domain.exceptions import NotFoundError, ServiceError, ValidationError

logger = logging.getLogger(__name__)

_REALTIME_TTL_SECONDS = max(5, REALTIME_REFRESH_INTERVAL_SECONDS // 2)
_BATCH_REALTIME_TTL_SECONDS = max(3, REALTIME_REFRESH_INTERVAL_SECONDS // 3)
_MARKET_STATUS_TTL_SECONDS = 60


def _realtime_cache_key(symbol: str) -> str:
    return f"futures:realtime:{symbol}"


def _batch_realtime_cache_key(symbols: tuple[str, ...]) -> str:
    return "futures:realtime:batch:" + ",".join(symbols)


class MarketDataService:
    """市场数据领域服务。"""

    def __init__(self, db: Session):
        self._db = db

    def _get_variety(self, symbol: str) -> VarietyDB:
        variety = self._db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        if not variety:
            raise NotFoundError(f"品种不存在: {symbol}", code=ErrorCode.SYMBOL_NOT_FOUND)
        return variety

    @staticmethod
    def _quote_to_dict(variety: VarietyDB, quote: RealtimeQuoteDB | None) -> dict[str, Any] | None:
        if not quote:
            return None
        return {
            "symbol": variety.symbol,
            "current_price": float(quote.current_price) if quote.current_price is not None else None,
            "change_percent": float(quote.change_percent) if quote.change_percent is not None else 0.0,
            "open_price": float(quote.open_price) if quote.open_price is not None else None,
            "high": float(quote.high) if quote.high is not None else None,
            "low": float(quote.low) if quote.low is not None else None,
            "volume": quote.volume,
            "updated_at": quote.updated_at,
            "delayed": quote.data_source == "akshare",
            "data_source": quote.data_source,
            "limit_up": float(quote.limit_up) if quote.limit_up is not None else None,
            "limit_down": float(quote.limit_down) if quote.limit_down is not None else None,
        }

    def get_realtime(self, symbol: str) -> dict[str, Any]:
        """获取单个品种实时行情，带缓存。"""
        variety = self._get_variety(symbol)
        cache_key = _realtime_cache_key(symbol)

        def _fetch():
            quote = (
                self._db.query(RealtimeQuoteDB)
                .filter(RealtimeQuoteDB.variety_id == variety.id)
                .first()
            )
            return self._quote_to_dict(variety, quote)

        quote = get_cached(cache_key, _fetch, ttl=_REALTIME_TTL_SECONDS)
        if not quote:
            raise NotFoundError("暂无实时行情数据", code=ErrorCode.REALTIME_DATA_UNAVAILABLE)
        return quote

    def get_realtime_batch(self, symbols: list[str], max_symbols: int = 50) -> tuple[list[dict[str, Any]], list[str]]:
        """批量获取实时行情。

        返回 (quotes, not_found)。
        为保持数据新鲜，batch 使用较短 TTL 缓存（或根据场景不缓存）。
        """
        if len(symbols) > max_symbols:
            raise ServiceError(
                message=f"查询品种数超过上限 {max_symbols}",
                status_code=400,
                code=ErrorCode.TOO_MANY_SYMBOLS,
            )

        unique_symbols = list(dict.fromkeys(symbols))  # 保持顺序去重
        cache_key = _batch_realtime_cache_key(tuple(sorted(unique_symbols)))

        def _fetch():
            varieties = {
                v.symbol: v
                for v in self._db.query(VarietyDB)
                .filter(VarietyDB.symbol.in_(unique_symbols))
                .all()
            }
            if not varieties:
                return {"quotes": [], "not_found": unique_symbols}

            variety_ids = [v.id for v in varieties.values()]
            quotes_rows = (
                self._db.query(RealtimeQuoteDB)
                .filter(RealtimeQuoteDB.variety_id.in_(variety_ids))
                .all()
            )
            quotes_map = {q.variety_id: q for q in quotes_rows}

            quotes: list[dict[str, Any]] = []
            not_found: list[str] = []
            for symbol in unique_symbols:
                variety = varieties.get(symbol)
                if not variety:
                    not_found.append(symbol)
                    continue
                q = quotes_map.get(variety.id)
                if not q:
                    not_found.append(symbol)
                    continue
                quote = self._quote_to_dict(variety, q)
                if quote:
                    quotes.append(quote)

            return {"quotes": quotes, "not_found": not_found}

        result = get_cached(cache_key, _fetch, ttl=_BATCH_REALTIME_TTL_SECONDS)
        return result["quotes"], result["not_found"]

    def get_varieties_with_realtime(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        category: str | None = None,
        direction: str | None = None,
        sort_by: str = "symbol",
        sort_order: str = "asc",
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """获取品种列表并附加实时行情，返回 (items, summary)。

        当前保留原 router 中的查询语义；后续可进一步下沉聚合逻辑。
        """
        from sqlalchemy import asc, desc, or_

        q = self._db.query(VarietyDB)
        if search:
            q = q.filter(
                or_(
                    VarietyDB.symbol.ilike(f"%{search}%"),
                    VarietyDB.name.ilike(f"%{search}%"),
                )
            )
        if category:
            q = q.filter(VarietyDB.category == category)

        # 统计查询
        stats_query = self._db.query(VarietyDB)
        if search:
            stats_query = stats_query.filter(
                or_(
                    VarietyDB.symbol.ilike(f"%{search}%"),
                    VarietyDB.name.ilike(f"%{search}%"),
                )
            )
        if category:
            stats_query = stats_query.filter(VarietyDB.category == category)

        total = stats_query.count()

        # 涨跌筛选
        if direction == "up":
            q = q.join(RealtimeQuoteDB).filter(RealtimeQuoteDB.change_percent > 0)
            stats_query = stats_query.join(RealtimeQuoteDB).filter(RealtimeQuoteDB.change_percent > 0)
        elif direction == "down":
            q = q.join(RealtimeQuoteDB).filter(RealtimeQuoteDB.change_percent < 0)
            stats_query = stats_query.join(RealtimeQuoteDB).filter(RealtimeQuoteDB.change_percent < 0)
        elif direction == "all" or not direction:
            q = q.outerjoin(RealtimeQuoteDB)
            stats_query = stats_query.outerjoin(RealtimeQuoteDB)

        total_after_direction = stats_query.count()
        up_count = stats_query.filter(RealtimeQuoteDB.change_percent > 0).count()
        down_count = stats_query.filter(RealtimeQuoteDB.change_percent < 0).count()

        sort_column = getattr(VarietyDB, sort_by, VarietyDB.symbol)
        order_func = desc if sort_order == "desc" else asc
        items = q.order_by(order_func(sort_column)).offset(skip).limit(limit).all()

        variety_ids = [v.id for v in items]
        quotes_map = {}
        if variety_ids:
            quotes = (
                self._db.query(RealtimeQuoteDB)
                .filter(RealtimeQuoteDB.variety_id.in_(variety_ids))
                .all()
            )
            quotes_map = {q.variety_id: q for q in quotes}

        result = []
        for v in items:
            quote = quotes_map.get(v.id)
            result.append({
                "symbol": v.symbol,
                "name": v.name,
                "exchange": v.exchange,
                "category": v.category,
                "current_price": quote.current_price if quote else None,
                "change_percent": quote.change_percent if quote else None,
                "volume": quote.volume if quote else None,
                "updated_at": quote.updated_at if quote else None,
            })

        summary = {
            "total": total,
            "filtered_total": total_after_direction,
            "up_count": up_count,
            "down_count": down_count,
        }
        return result, summary

    def get_market_comparison(
        self,
        symbols: list[str],
    ) -> list[dict[str, Any]]:
        """跨品种对比：返回涨跌幅、波动率等聚合指标。"""
        if len(symbols) > 50:
            raise ValidationError("对比品种数超过上限 50", code=ErrorCode.TOO_MANY_SYMBOLS)
        if not symbols:
            raise ValidationError("symbols 不能为空", code=ErrorCode.VALIDATION_ERROR)

        quotes, not_found = self.get_realtime_batch(symbols)
        if not quotes:
            raise NotFoundError("暂无对比数据", code=ErrorCode.REALTIME_DATA_UNAVAILABLE)

        result = []
        for q in quotes:
            change = q.get("change_percent") or 0.0
            result.append({
                "symbol": q["symbol"],
                "current_price": q["current_price"],
                "change_percent": change,
                "direction": "up" if change > 0 else ("down" if change < 0 else "flat"),
            })

        # 按涨跌幅排序
        result.sort(key=lambda x: x["change_percent"], reverse=True)
        return result

    def get_data_quality(self, symbol: str | None = None) -> dict[str, Any]:
        """获取数据质量状态。"""
        now = datetime.now(UTC)
        q = self._db.query(RealtimeQuoteDB, VarietyDB).join(VarietyDB)
        if symbol:
            q = q.filter(VarietyDB.symbol == symbol)

        rows = q.all()
        if not rows:
            if symbol:
                raise NotFoundError("暂无该品种数据质量信息", code=ErrorCode.REALTIME_DATA_UNAVAILABLE)
            return {"overall": "unknown", "details": []}

        stale_threshold = timedelta(seconds=REALTIME_REFRESH_INTERVAL_SECONDS * 3)
        details = []
        stale_count = 0
        for quote, variety in rows:
            updated_at = quote.updated_at
            if updated_at is None:
                is_stale = True
            else:
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=UTC)
                is_stale = (now - updated_at) > stale_threshold
            if is_stale:
                stale_count += 1
            details.append({
                "symbol": variety.symbol,
                "data_source": quote.data_source,
                "updated_at": quote.updated_at.isoformat() if quote.updated_at else None,
                "stale": is_stale,
            })

        overall = "healthy" if stale_count == 0 else ("degraded" if stale_count <= len(rows) * 0.2 else "unhealthy")
        return {
            "overall": overall,
            "total": len(rows),
            "stale_count": stale_count,
            "stale_threshold_seconds": stale_threshold.total_seconds(),
            "details": details if symbol else [],
        }

    @staticmethod
    def invalidate_realtime_cache(symbol: str | None = None):
        """失效实时行情缓存。"""
        if symbol:
            invalidate_cache_pattern(_realtime_cache_key(symbol))
        else:
            invalidate_cache_pattern("futures:realtime:")
