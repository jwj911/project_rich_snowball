"""可重建的合约级日频研究宽表。"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from models import AgentMarketPanelDailyDB, FutContractDB, FutDailyDataDB, KlineDataDB, VarietyDB

RAW_CONTRACT_VIEW = "raw_contract"
PANEL_PERIOD = "1d"
_SOURCE_DAILY_PERIODS = ("1d", "D")
_DECIMAL_ONE = Decimal("1")
_DECIMAL_ZERO = Decimal("0")


def rebuild_raw_contract_daily_panel(
    db: Session,
    *,
    variety_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, int]:
    """从原始合约 K 线重建 ``raw_contract`` 日频研究宽表。

    本函数在调用方事务中执行，不自行 commit。即使指定了日期范围，也会读取同一
    合约的完整日线历史，以保证收益率和滚动成交量比与全量重建结果一致。
    """
    source_query = (
        db.query(KlineDataDB, VarietyDB, FutContractDB)
        .join(VarietyDB, KlineDataDB.variety_id == VarietyDB.id)
        .join(FutContractDB, KlineDataDB.contract_id == FutContractDB.id)
        .filter(
            KlineDataDB.period.in_(_SOURCE_DAILY_PERIODS),
            KlineDataDB.trading_date.isnot(None),
        )
    )
    if variety_id is not None:
        source_query = source_query.filter(KlineDataDB.variety_id == variety_id)

    source_rows = source_query.order_by(
        KlineDataDB.variety_id.asc(),
        KlineDataDB.contract_id.asc(),
        KlineDataDB.trading_date.asc(),
    ).all()

    source_keys = {(contract.ts_code, kline.trading_date) for kline, _, contract in source_rows}
    daily_rows = _load_daily_rows(db, source_keys)
    values = _build_panel_rows(source_rows, daily_rows, start_date=start_date, end_date=end_date)

    delete_query = db.query(AgentMarketPanelDailyDB).filter(
        AgentMarketPanelDailyDB.data_view == RAW_CONTRACT_VIEW,
        AgentMarketPanelDailyDB.period == PANEL_PERIOD,
    )
    if variety_id is not None:
        delete_query = delete_query.filter(AgentMarketPanelDailyDB.variety_id == variety_id)
    if start_date is not None:
        delete_query = delete_query.filter(AgentMarketPanelDailyDB.trading_date >= start_date)
    if end_date is not None:
        delete_query = delete_query.filter(AgentMarketPanelDailyDB.trading_date <= end_date)
    deleted = delete_query.delete(synchronize_session=False)

    written = _upsert_panel_rows(db, values)
    return {
        "source_rows": len(source_rows),
        "written_rows": written,
        "deleted_rows": deleted,
    }


def _load_daily_rows(
    db: Session,
    source_keys: set[tuple[str, date]],
) -> dict[tuple[str, date], FutDailyDataDB]:
    """载入与 K 线匹配的 Tushare 日线补充字段。"""
    if not source_keys:
        return {}

    ts_codes = {ts_code for ts_code, _ in source_keys}
    rows = (
        db.query(FutDailyDataDB)
        .filter(
            FutDailyDataDB.ts_code.in_(ts_codes),
            FutDailyDataDB.period == "D",
        )
        .all()
    )
    return {
        (row.ts_code, row.trade_date.date()): row
        for row in rows
        if row.trade_date is not None and (row.ts_code, row.trade_date.date()) in source_keys
    }


def _build_panel_rows(
    source_rows: list[tuple[KlineDataDB, VarietyDB, FutContractDB]],
    daily_rows: dict[tuple[str, date], FutDailyDataDB],
    *,
    start_date: date | None,
    end_date: date | None,
) -> list[dict[str, Any]]:
    """将同一合约的 K 线转换为宽表记录并计算确定性派生字段。"""
    grouped: dict[tuple[int, int], dict[date, tuple[KlineDataDB, VarietyDB, FutContractDB]]] = defaultdict(dict)
    for kline, variety, contract in source_rows:
        group = grouped[(kline.variety_id, kline.contract_id)]
        existing = group.get(kline.trading_date)
        if existing is None or (existing[0].period != PANEL_PERIOD and kline.period == PANEL_PERIOD):
            group[kline.trading_date] = (kline, variety, contract)

    values: list[dict[str, Any]] = []
    for rows_by_date in grouped.values():
        ordered_rows = [rows_by_date[current_date] for current_date in sorted(rows_by_date)]
        closes = [_decimal(kline.close_price) for kline, _, _ in ordered_rows]
        volumes = [_decimal(kline.volume) for kline, _, _ in ordered_rows]

        for index, (kline, variety, contract) in enumerate(ordered_rows):
            if start_date is not None and kline.trading_date < start_date:
                continue
            if end_date is not None and kline.trading_date > end_date:
                continue

            supplement = daily_rows.get((contract.ts_code, kline.trading_date))
            amount, amount_source = _amount(kline, supplement)
            open_interest, open_interest_source = _open_interest(kline, supplement)
            previous_close = closes[index - 1] if index > 0 else None
            flags = {
                "amount": amount_source,
                "ohlcv": "kline_data",
                "open_interest": open_interest_source,
                "settlement": "fut_daily_data" if supplement and supplement.settle is not None else "unavailable",
            }
            values.append(
                {
                    "data_view": RAW_CONTRACT_VIEW,
                    "variety_id": variety.id,
                    "contract_id": contract.id,
                    "symbol": variety.symbol,
                    "contract_code": contract.symbol or contract.ts_code,
                    "trading_date": kline.trading_date,
                    "period": PANEL_PERIOD,
                    "open_price": kline.open_price,
                    "high_price": kline.high_price,
                    "low_price": kline.low_price,
                    "close_price": kline.close_price,
                    "volume": kline.volume,
                    "amount": amount,
                    "open_interest": open_interest,
                    "settlement": supplement.settle if supplement else None,
                    "ret_1": _return(closes, index, 1),
                    "ret_5": _return(closes, index, 5),
                    "ret_20": _return(closes, index, 20),
                    "gap": _ratio(_decimal(kline.open_price), previous_close),
                    "amplitude": _ratio(
                        _decimal(kline.high_price) - _decimal(kline.low_price), _decimal(kline.close_price)
                    ),
                    "intraday_range": _ratio(
                        _decimal(kline.close_price) - _decimal(kline.open_price),
                        _decimal(kline.open_price),
                    ),
                    "volume_ratio_20": _volume_ratio(volumes, index),
                    "source_flags": json.dumps(flags, ensure_ascii=True, sort_keys=True),
                    "quality_status": _quality_status(kline, amount_source, open_interest),
                }
            )
    return values


def _upsert_panel_rows(db: Session, values: list[dict[str, Any]]) -> int:
    """按研究宽表业务键幂等写入。"""
    if not values:
        return 0

    dialect_name = db.bind.dialect.name if db.bind is not None else "sqlite"
    insert = pg_insert if dialect_name == "postgresql" else sqlite_insert
    stmt = insert(AgentMarketPanelDailyDB).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["data_view", "variety_id", "contract_id", "period", "trading_date"],
        set_={
            "symbol": stmt.excluded.symbol,
            "contract_code": stmt.excluded.contract_code,
            "open_price": stmt.excluded.open_price,
            "high_price": stmt.excluded.high_price,
            "low_price": stmt.excluded.low_price,
            "close_price": stmt.excluded.close_price,
            "volume": stmt.excluded.volume,
            "amount": stmt.excluded.amount,
            "open_interest": stmt.excluded.open_interest,
            "settlement": stmt.excluded.settlement,
            "ret_1": stmt.excluded.ret_1,
            "ret_5": stmt.excluded.ret_5,
            "ret_20": stmt.excluded.ret_20,
            "gap": stmt.excluded.gap,
            "amplitude": stmt.excluded.amplitude,
            "intraday_range": stmt.excluded.intraday_range,
            "volume_ratio_20": stmt.excluded.volume_ratio_20,
            "source_flags": stmt.excluded.source_flags,
            "quality_status": stmt.excluded.quality_status,
            "updated_at": func.now(),
        },
    )
    result = db.execute(stmt)
    return result.rowcount if hasattr(result, "rowcount") else len(values)


def _amount(kline: KlineDataDB, supplement: FutDailyDataDB | None) -> tuple[Decimal, str]:
    if supplement is not None and supplement.amount is not None:
        return _decimal(supplement.amount), "fut_daily_data"
    return _decimal(kline.close_price) * _decimal(kline.volume), "estimated_close_volume"


def _open_interest(kline: KlineDataDB, supplement: FutDailyDataDB | None) -> tuple[int | None, str]:
    if kline.open_interest is not None:
        return int(kline.open_interest), "kline_data"
    if supplement is not None and supplement.open_interest is not None:
        return int(supplement.open_interest), "fut_daily_data"
    return None, "unavailable"


def _return(closes: list[Decimal], index: int, offset: int) -> Decimal | None:
    if index < offset:
        return None
    return _ratio(closes[index], closes[index - offset])


def _volume_ratio(volumes: list[Decimal], index: int) -> Decimal | None:
    window = volumes[max(0, index - 19) : index + 1]
    if not window:
        return None
    average = sum(window, _DECIMAL_ZERO) / Decimal(len(window))
    return _ratio(volumes[index], average, subtract_one=False)


def _ratio(numerator: Decimal, denominator: Decimal | None, *, subtract_one: bool = True) -> Decimal | None:
    if denominator is None or denominator == _DECIMAL_ZERO:
        return None
    ratio = numerator / denominator
    return ratio - _DECIMAL_ONE if subtract_one else ratio


def _quality_status(kline: KlineDataDB, amount_source: str, open_interest: int | None) -> str:
    open_price = _decimal(kline.open_price)
    high_price = _decimal(kline.high_price)
    low_price = _decimal(kline.low_price)
    close_price = _decimal(kline.close_price)
    if (
        open_price <= _DECIMAL_ZERO
        or high_price <= _DECIMAL_ZERO
        or low_price <= _DECIMAL_ZERO
        or close_price <= _DECIMAL_ZERO
        or _decimal(kline.volume) < _DECIMAL_ZERO
        or high_price < max(open_price, close_price, low_price)
        or low_price > min(open_price, close_price, high_price)
    ):
        return "bad"
    if amount_source == "estimated_close_volume" or open_interest is None:
        return "warning"
    return "good"


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))
