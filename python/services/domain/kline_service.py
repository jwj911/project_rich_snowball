"""K-line 领域服务。

统一封装 K 线查询、连续 K 线、主力合约 K 线、合约 K 线、技术指标计算等能力，
供 router 和 Agent 工具调用。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from errors import ErrorCode
from lib.technical_indicators import calculate_all_indicators
from models import FutContractDB, VarietyDB
from services.cache import get_cached, invalidate_cache_pattern
from services.continuous_kline import get_fut_daily_main_kline, get_fut_daily_contract_kline, get_continuous_kline, get_main_contract_kline
from services.domain.exceptions import NotFoundError, ValidationError
from services.domain.repositories.kline_repository import KlineRepository
from services.kline_period import period_candidates
from utils import ensure_utc

logger = logging.getLogger(__name__)

# 缓存 TTL（秒），与典型采集周期对齐
_KLINE_TTL_SECONDS = 60
_CONTINUOUS_KLINE_TTL_SECONDS = 300
_INDICATOR_TTL_SECONDS = 300
_SUMMARY_TTL_SECONDS = 60


def _kline_cache_key(prefix: str, symbol: str, period: str, **kwargs) -> str:
    """生成稳定的缓存 key。kwargs 中只包含可哈希的简单值。"""
    parts = [prefix, symbol, period]
    for k in sorted(kwargs):
        parts.append(f"{k}={kwargs[k]}")
    return "futures:kline:" + ":".join(parts)


class KlineService:
    """K 线领域服务。"""

    def __init__(self, db: Session, repository: KlineRepository | None = None):
        self._db = db
        self._repo = repository or KlineRepository(db)

    def _get_variety(self, symbol: str) -> VarietyDB:
        variety = self._repo.get_variety_by_symbol(symbol)
        if not variety:
            raise NotFoundError(f"品种不存在: {symbol}", code=ErrorCode.SYMBOL_NOT_FOUND)
        return variety

    def _get_contract(self, contract_id: int) -> FutContractDB:
        contract = self._repo.get_contract_by_id(contract_id)
        if not contract:
            raise NotFoundError("合约不存在", code=ErrorCode.NOT_FOUND)
        return contract

    def _normalize_period(self, period: str) -> str:
        candidates = period_candidates(period)
        if candidates[0] != period and period not in candidates:
            raise ValidationError(f"不支持的 K 线周期: {period}", code=ErrorCode.VALIDATION_ERROR)
        return candidates[0]

    def get_klines(
        self,
        symbol: str,
        period: str = "1h",
        limit: int = 1000,
        contract_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """获取品种 K 线。

        - 当 contract_id 显式传入时，返回该合约数据；
        - 当 contract_id 未传入时，返回该品种下所有合约的 K 线（保持与原接口兼容）。
          注意：若品种下存在多个活跃合约，可能返回混合数据；需要连续序列请使用
          `/api/klines/{symbol}/main` 或 `/api/klines/{symbol}/continuous`。
        """
        variety = self._get_variety(symbol)
        period = self._normalize_period(period)

        if period in ("D", "1d"):
            return get_fut_daily_main_kline(self._db, variety.id, limit=limit)

        if contract_id is None:
            cache_key = _kline_cache_key("variety", symbol, period, limit=limit)

            def _fetch():
                rows = self._repo.list_klines_with_contract(
                    variety_id=variety.id,
                    period=period,
                    limit=limit,
                )
                if rows:
                    rows.reverse()
                return rows or None

            return get_cached(cache_key, _fetch, ttl=_KLINE_TTL_SECONDS) or []

        cache_key = _kline_cache_key("contract", symbol, period, contract_id=contract_id, limit=limit)

        def _fetch():
            rows = self._repo.list_klines_with_contract(
                contract_id=contract_id,
                period=period,
                limit=limit,
            )
            if rows:
                rows.reverse()
            return rows or None

        return get_cached(cache_key, _fetch, ttl=_KLINE_TTL_SECONDS) or []

    def get_continuous_klines(
        self,
        symbol: str,
        period: str = "D",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 5000,
        adjustment: str = "backward",
    ) -> list[dict[str, Any]]:
        """获取连续 K 线（主力切换拼接）。"""
        variety = self._get_variety(symbol)
        period = self._normalize_period(period)
        start = ensure_utc(start)
        end = ensure_utc(end)

        cache_key = _kline_cache_key(
            "continuous",
            symbol,
            period,
            start=start.isoformat() if start else "",
            end=end.isoformat() if end else "",
            limit=limit,
            adjustment=adjustment,
        )

        def _fetch():
            rows = get_continuous_kline(
                self._db,
                variety.id,
                period=period,
                start=start,
                end=end,
                limit=limit,
                adjustment=adjustment,
            )
            return rows or None

        return get_cached(cache_key, _fetch, ttl=_CONTINUOUS_KLINE_TTL_SECONDS) or []

    def get_main_klines(
        self,
        symbol: str,
        period: str = "D",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """获取当前主力合约 K 线。"""
        variety = self._get_variety(symbol)
        period = self._normalize_period(period)
        return self._get_cached_main_klines(variety, period, limit, start, end)

    def _get_cached_main_klines(
        self,
        variety: VarietyDB,
        period: str,
        limit: int,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        start = ensure_utc(start)
        end = ensure_utc(end)
        cache_key = _kline_cache_key(
            "main",
            variety.symbol,
            period,
            start=start.isoformat() if start else "",
            end=end.isoformat() if end else "",
            limit=limit,
        )

        def _fetch():
            rows = get_main_contract_kline(
                self._db,
                variety.id,
                period=period,
                start=start,
                end=end,
                limit=limit,
            )
            return rows or None

        return get_cached(cache_key, _fetch, ttl=_KLINE_TTL_SECONDS) or []

    def get_contract_klines(
        self,
        contract_id: int,
        period: str = "D",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """获取单个合约 K 线。"""
        contract = self._get_contract(contract_id)
        period = self._normalize_period(period)
        start = ensure_utc(start)
        end = ensure_utc(end)

        cache_key = _kline_cache_key(
            "contract",
            contract.symbol,
            period,
            contract_id=contract_id,
            start=start.isoformat() if start else "",
            end=end.isoformat() if end else "",
            limit=limit,
        )

        def _fetch():
            if period in ("D", "1d"):
                rows = get_fut_daily_contract_kline(self._db, contract_id, start, end, limit)
            else:
                rows = self._repo.list_klines_with_contract(
                    contract_id=contract_id,
                    period=period,
                    start=start,
                    end=end,
                    limit=limit,
                )
            return rows or None

        return get_cached(cache_key, _fetch, ttl=_KLINE_TTL_SECONDS) or []

    def calculate_indicators(
        self,
        symbol: str,
        period: str = "1d",
        indicators: list[str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """基于 K 线计算技术指标。

        若 indicators 为空，默认计算全部指标；
        若指定指标名，仅返回指定列。
        """
        variety = self._get_variety(symbol)
        period = self._normalize_period(period)

        cache_key = _kline_cache_key(
            "indicators",
            symbol,
            period,
            indicators=",".join(sorted(indicators)) if indicators else "all",
            limit=limit,
        )

        def _fetch():
            if period in ("D", "1d"):
                rows = get_fut_daily_main_kline(self._db, variety.id, limit=limit)
            else:
                rows = self._repo.list_klines(
                    variety_id=variety.id,
                    period=period,
                    limit=limit,
                )
                if rows:
                    rows.reverse()
            if not rows:
                return None

            df = pd.DataFrame(
                [
                    {
                        "open": float(r.open_price),
                        "high": float(r.high_price),
                        "low": float(r.low_price),
                        "close": float(r.close_price),
                        "volume": r.volume,
                        "time": r.trading_time.isoformat(),
                    }
                    for r in rows
                ]
            )

            df = calculate_all_indicators(df)

            # 选择需要返回的列
            keep = {"time", "open", "high", "low", "close", "volume"}
            if indicators:
                requested = {i.lower().strip() for i in indicators}
                available = {c.lower().strip() for c in df.columns}
                invalid = requested - available
                if invalid:
                    raise ValidationError(
                        f"未知指标: {', '.join(sorted(invalid))}",
                        code=ErrorCode.VALIDATION_ERROR,
                    )
                keep.update(requested)
            else:
                keep.update({c.lower().strip() for c in df.columns})

            df.columns = [c.lower().strip() for c in df.columns]
            df = df[[c for c in df.columns if c in keep]]
            # 处理 NaN/inf，序列化为 None
            df = df.replace([float("inf"), float("-inf")], None)
            return df.where(pd.notnull(df), None).to_dict(orient="records")

        return get_cached(cache_key, _fetch, ttl=_INDICATOR_TTL_SECONDS) or []

    def get_kline_summary(
        self,
        symbol: str,
        periods: list[str],
        limit: int = 100,
    ) -> dict[str, list[dict[str, Any]]]:
        """返回多个周期的最近 K 线汇总。"""
        if not periods:
            raise ValidationError("periods 不能为空", code=ErrorCode.VALIDATION_ERROR)

        variety = self._get_variety(symbol)
        normalized_periods = [self._normalize_period(p) for p in periods]
        cache_key = _kline_cache_key(
            "summary",
            symbol,
            "multi",
            periods=",".join(sorted(normalized_periods)),
            limit=limit,
        )

        def _fetch():
            result: dict[str, list[dict[str, Any]]] = {}
            for period in normalized_periods:
                if period in ("D", "1d"):
                    rows = get_fut_daily_main_kline(self._db, variety.id, limit=limit)
                else:
                    rows = self._repo.list_klines_with_contract(
                        variety_id=variety.id,
                        period=period,
                        limit=limit,
                    )
                    if rows:
                        rows.reverse()
                result[period] = rows
            return result

        return get_cached(cache_key, _fetch, ttl=_SUMMARY_TTL_SECONDS) or {}

    @staticmethod
    def invalidate_kline_cache(symbol: str | None = None):
        """失效 K 线相关缓存。

        若 symbol 为 None，则清理所有 futures:kline:* 前缀缓存（慎用）。
        """
        if symbol:
            invalidate_cache_pattern(f"futures:kline:*:{symbol}:")
        else:
            invalidate_cache_pattern("futures:kline:")
