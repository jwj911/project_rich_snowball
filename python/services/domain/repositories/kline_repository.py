"""K-line 数据访问层。

将 K 线相关查询从 router / service 中收敛，统一处理周期别名、
时间范围过滤、排序和合约元数据附加。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from models import FutContractDB, KlineDataDB, VarietyDB
from services.kline_period import period_candidates
from utils import ensure_utc


class KlineRepository:
    """K 线数据访问对象。"""

    def __init__(self, db: Session):
        self._db = db

    def get_variety_by_symbol(self, symbol: str) -> VarietyDB | None:
        return self._db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()

    def get_contract_by_id(self, contract_id: int) -> FutContractDB | None:
        return self._db.query(FutContractDB).filter(FutContractDB.id == contract_id).first()

    def get_contract_by_symbol(self, symbol: str) -> FutContractDB | None:
        return self._db.query(FutContractDB).filter(FutContractDB.symbol == symbol).first()

    def list_klines(
        self,
        variety_id: int | None = None,
        contract_id: int | None = None,
        period: str = "1d",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
        order_desc: bool = True,
    ) -> list[KlineDataDB]:
        """按品种或合约查询 K 线，自动处理周期别名 fallback。

        默认按 trading_time 降序返回最近的 limit 条（与原始 API 语义一致）。

        注意：调用方应至少提供 variety_id 或 contract_id 之一；
        若两者都不提供，返回空列表，避免全表扫描。
        """
        if variety_id is None and contract_id is None:
            return []

        start = ensure_utc(start)
        end = ensure_utc(end)

        base_filters = []
        if variety_id is not None:
            base_filters.append(KlineDataDB.variety_id == variety_id)
        if contract_id is not None:
            base_filters.append(KlineDataDB.contract_id == contract_id)

        for candidate in period_candidates(period):
            q = self._db.query(KlineDataDB).filter(*base_filters)
            q = q.filter(KlineDataDB.period == candidate)
            if start is not None:
                q = q.filter(KlineDataDB.trading_time >= start)
            if end is not None:
                q = q.filter(KlineDataDB.trading_time <= end)

            if order_desc:
                q = q.order_by(KlineDataDB.trading_time.desc())
            else:
                q = q.order_by(KlineDataDB.trading_time.asc())

            rows = q.limit(limit).all()
            if rows:
                return rows
        return []

    def list_klines_with_contract(
        self,
        variety_id: int | None = None,
        contract_id: int | None = None,
        period: str = "1d",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
        order_desc: bool = True,
    ) -> list[dict[str, Any]]:
        """查询 K 线并附加合约元数据，默认返回最近的 limit 条（trading_time 降序）。"""
        rows = self.list_klines(
            variety_id=variety_id,
            contract_id=contract_id,
            period=period,
            start=start,
            end=end,
            limit=limit,
            order_desc=order_desc,
        )
        if not rows:
            return []

        contract_ids = {r.contract_id for r in rows if r.contract_id is not None}
        contracts: dict[int, FutContractDB] = {}
        if contract_ids:
            contracts = {
                c.id: c
                for c in self._db.query(FutContractDB)
                .filter(FutContractDB.id.in_(contract_ids))
                .all()
            }

        result = []
        for r in rows:
            contract = contracts.get(r.contract_id) if r.contract_id is not None else None
            result.append({
                "time": r.trading_time.isoformat(),
                "open": float(r.open_price),
                "high": float(r.high_price),
                "low": float(r.low_price),
                "close": float(r.close_price),
                "volume": r.volume,
                "contract_code": contract.symbol if contract else None,
                "contract_id": contract.id if contract else r.contract_id,
            })
        return result

    def list_contracts_by_variety_symbol(
        self,
        symbol: str,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 1000,
    ) -> list[FutContractDB]:
        q = self._db.query(FutContractDB).filter(FutContractDB.fut_code == symbol)
        if active_only:
            q = q.filter(FutContractDB.is_active.is_(True))
        return q.order_by(FutContractDB.delist_date.desc()).offset(skip).limit(limit).all()
