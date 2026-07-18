"""市场数据领域服务。

统一封装实时行情、批量行情、品种聚合、跨品种对比、数据质量等能力。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, asc, case, desc, func, or_
from sqlalchemy.orm import Session, aliased

from config import REALTIME_REFRESH_INTERVAL_SECONDS
from errors import ErrorCode
from models import FutMainDailyDataDB, RealtimeQuoteDB, VarietyDB
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
            "pre_settlement": float(quote.pre_settlement) if quote.pre_settlement is not None else None,
            "open_interest": quote.open_interest,
            "bid1": float(quote.bid1) if quote.bid1 is not None else None,
            "ask1": float(quote.ask1) if quote.ask1 is not None else None,
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
            quote = self._db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
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
                v.symbol: v for v in self._db.query(VarietyDB).filter(VarietyDB.symbol.in_(unique_symbols)).all()
            }
            if not varieties:
                return {"quotes": [], "not_found": unique_symbols}

            variety_ids = [v.id for v in varieties.values()]
            quotes_rows = self._db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id.in_(variety_ids)).all()
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
        """获取品种列表并附加行情，返回 ``(items, summary)``。

        主力日线优先用于列表展示；主力日线缺失时回退到实时快照，
        这样 Mock、真实日线和盘中行情都遵循同一套读模型契约。
        """
        if sort_by not in {"change_percent", "volume", "current_price", "symbol"}:
            raise ValidationError(f"不支持的排序字段: {sort_by}", code=ErrorCode.VALIDATION_ERROR)
        if sort_order not in {"asc", "desc"}:
            raise ValidationError(f"不支持的排序方向: {sort_order}", code=ErrorCode.VALIDATION_ERROR)

        ranked_main = (
            self._db.query(
                FutMainDailyDataDB,
                func.row_number()
                .over(
                    partition_by=FutMainDailyDataDB.variety_id,
                    order_by=[
                        desc(FutMainDailyDataDB.trade_date),
                        asc(FutMainDailyDataDB.ts_code),
                    ],
                )
                .label("rn"),
            )
            .filter(FutMainDailyDataDB.period == "D")
            .subquery()
        )
        main = aliased(FutMainDailyDataDB, ranked_main)

        q = (
            self._db.query(VarietyDB, main, RealtimeQuoteDB)
            .outerjoin(
                main,
                and_(
                    main.variety_id == VarietyDB.id,
                    ranked_main.c.rn == 1,
                ),
            )
            .outerjoin(RealtimeQuoteDB, RealtimeQuoteDB.variety_id == VarietyDB.id)
            .filter(VarietyDB.is_active.is_(True))
        )
        if search:
            search = search.strip()
            q = q.filter(
                or_(
                    VarietyDB.symbol.ilike(f"%{search}%"),
                    VarietyDB.name.ilike(f"%{search}%"),
                    VarietyDB.category.ilike(f"%{search}%"),
                )
            )
        if category and category != "all":
            q = q.filter(VarietyDB.category == category)

        main_current = func.coalesce(main.settle, main.close_price)
        main_change = case(
            (
                and_(
                    main.pre_settle.isnot(None),
                    main.pre_settle != 0,
                    main_current.isnot(None),
                ),
                (main_current - main.pre_settle) / main.pre_settle * 100,
            ),
            else_=None,
        )
        effective_current = func.coalesce(main_current, RealtimeQuoteDB.current_price)
        effective_change = func.coalesce(main_change, RealtimeQuoteDB.change_percent)
        effective_volume = func.coalesce(main.volume, RealtimeQuoteDB.volume, 0)
        has_data = or_(main.id.isnot(None), RealtimeQuoteDB.id.isnot(None))

        # 方向筛选只作用于有行情的数据，避免无行情品种被视为上涨。
        if direction == "up":
            q = q.filter(has_data, effective_change >= 0)
        elif direction == "down":
            q = q.filter(has_data, effective_change < 0)
        elif direction not in {"all", None, ""}:
            raise ValidationError(f"不支持的涨跌方向: {direction}", code=ErrorCode.VALIDATION_ERROR)

        total_count, total_volume, up_count, down_count = q.with_entities(
            func.count(VarietyDB.id),
            func.coalesce(func.sum(effective_volume), 0),
            func.coalesce(
                func.sum(case((and_(has_data, effective_change >= 0), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((and_(has_data, effective_change < 0), 1), else_=0)),
                0,
            ),
        ).one()

        order_func = desc if sort_order == "desc" else asc
        sort_columns = {
            "symbol": VarietyDB.symbol,
            "change_percent": effective_change,
            "volume": effective_volume,
            "current_price": effective_current,
        }
        items = (
            q.order_by(order_func(func.coalesce(sort_columns[sort_by], 0)), VarietyDB.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        categories = [
            row[0]
            for row in self._db.query(VarietyDB.category)
            .filter(
                VarietyDB.is_active.is_(True),
                VarietyDB.category.isnot(None),
                VarietyDB.category != "",
            )
            .distinct()
            .order_by(VarietyDB.category.asc())
            .all()
        ]

        def _to_float(value: Any) -> float | None:
            return float(value) if value is not None else None

        def _isoformat(value: Any) -> str | None:
            return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)

        def _freshness(updated_at: Any, source: str | None) -> str:
            if updated_at is None or source is None:
                return "unavailable"
            if getattr(updated_at, "tzinfo", None) is None:
                updated_at = updated_at.replace(tzinfo=UTC)
            age = datetime.now(UTC) - updated_at
            threshold = 3 * REALTIME_REFRESH_INTERVAL_SECONDS if source == "realtime_quotes" else 3 * 86400
            return "fresh" if age.total_seconds() <= threshold else "stale"

        def _price_precision(tick_size: Any) -> int:
            if not tick_size:
                return 2
            text = f"{float(tick_size):.10f}".rstrip("0")
            return len(text.split(".")[1]) if "." in text else 0

        result: list[dict[str, Any]] = []
        for variety, main_row, quote in items:
            if main_row is not None:
                current_price = main_row.settle if main_row.settle is not None else main_row.close_price
                change_percent = None
                if main_row.pre_settle is not None and float(main_row.pre_settle) != 0 and current_price is not None:
                    change_percent = round(
                        (float(current_price) - float(main_row.pre_settle)) / float(main_row.pre_settle) * 100,
                        2,
                    )
                source = "fut_main_daily_data"
                updated_at = main_row.trade_date
                open_price = main_row.open_price
                high = main_row.high_price
                low = main_row.low_price
                volume = main_row.volume
                limit_up = None
                limit_down = None
            elif quote is not None:
                current_price = quote.current_price
                change_percent = quote.change_percent
                source = quote.data_source or "realtime_quotes"
                updated_at = quote.updated_at
                open_price = quote.open_price
                high = quote.high
                low = quote.low
                volume = quote.volume
                limit_up = quote.limit_up
                limit_down = quote.limit_down
            else:
                current_price = change_percent = open_price = high = low = volume = None
                limit_up = limit_down = None
                source = None
                updated_at = None

            result.append(
                {
                    "id": variety.id,
                    "symbol": variety.symbol,
                    "name": variety.name,
                    "category": variety.category,
                    "current_price": _to_float(current_price),
                    "change_percent": _to_float(change_percent),
                    "open_price": _to_float(open_price),
                    "high": _to_float(high),
                    "low": _to_float(low),
                    "volume": int(volume) if volume is not None else None,
                    "limit_up": _to_float(limit_up),
                    "limit_down": _to_float(limit_down),
                    "price_precision": _price_precision(variety.tick_size),
                    "margin_rate": _to_float(variety.margin_rate),
                    "commission": _to_float(variety.commission),
                    "updated_at": _isoformat(updated_at),
                    "data_source": source,
                    "data_freshness": _freshness(updated_at, source),
                }
            )

        summary = {
            "total": int(total_count or 0),
            "total_volume": int(total_volume or 0),
            "up_count": int(up_count or 0),
            "down_count": int(down_count or 0),
            "categories": categories,
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
            result.append(
                {
                    "symbol": q["symbol"],
                    "current_price": q["current_price"],
                    "change_percent": change,
                    "direction": "up" if change > 0 else ("down" if change < 0 else "flat"),
                }
            )

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
            details.append(
                {
                    "symbol": variety.symbol,
                    "data_source": quote.data_source,
                    "updated_at": quote.updated_at.isoformat() if quote.updated_at else None,
                    "stale": is_stale,
                }
            )

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
