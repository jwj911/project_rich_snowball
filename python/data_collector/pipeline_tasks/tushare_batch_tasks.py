"""Tushare 扩展批量采集任务。

将 run_fut_daily / run_fut_settle / run_fut_weekly_detail /
run_fut_wsr / run_fut_holding / run_fut_price_limit 从 DataPipeline 下沉至此，
降低 pipeline.py 复杂度，新增同类任务时无需修改 DataPipeline 主体。
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from data_collector.pipeline_tasks._common import (
    _record_circuit_outcome,
    _record_run,
    _symbol_from_ts_code,
)
from data_collector.upsert import (
    upsert_fut_daily_bulk,
    upsert_fut_holding_bulk,
    upsert_fut_price_limit_bulk,
    upsert_fut_settle_bulk,
    upsert_fut_weekly_detail_bulk,
    upsert_fut_wsr_bulk,
)
from models import SessionLocal, VarietyDB
from services.circuit_breaker import is_circuit_open, record_failure

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 通用批量采集 runner
# ------------------------------------------------------------------

def _run_simple_batch_pipeline(
    job_name: str,
    collector,
    fetch_fn: Callable[[], list],
    adapter: Callable | None,
    filter_fn: Callable[[dict], bool],
    upsert_fn: Callable,
    meta: dict | None = None,
) -> dict:
    """通用 Tushare 批量采集流水线。

    覆盖：熔断检查 → 采集 → adapter → 过滤 → upsert → commit → 记录。
    异常时回滚、记录熔断、抛出。
    """
    source_name = collector.__class__.__name__
    if is_circuit_open(source_name):
        logger.warning("Circuit breaker open for %s, skipping %s", source_name, job_name)
        return {"processed": 0, "failed": 0, "skipped": 0, "circuit_open": True}

    stats: dict[str, Any] = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(UTC)}
    db = SessionLocal()
    exc = None
    try:
        raw_rows = fetch_fn()
        if not raw_rows:
            return stats

        rows = []
        adapter_failed = 0
        if adapter:
            for row in raw_rows:
                try:
                    rows.append(adapter(row))
                except (KeyError, TypeError, ValueError, IndexError) as e:
                    adapter_failed += 1
                    logger.warning("%s adapter failed: row=%s, error=%s", job_name, row, e)
        else:
            rows = raw_rows

        rows = [row for row in rows if filter_fn(row)]
        inserted = upsert_fn(db, rows)
        db.commit()
        stats["processed"] = inserted
        stats["skipped"] = len(raw_rows) - len(rows)
        stats["adapter_failed"] = adapter_failed
        if adapter_failed > 0:
            logger.warning("%s pipeline partial: %s", job_name, stats)
        else:
            logger.info("%s pipeline completed: %s", job_name, stats)
        return stats
    except SQLAlchemyError as e:
        db.rollback()
        exc = e
        record_failure(source_name)
        logger.critical("%s pipeline aborted: %s", job_name, e, exc_info=True)
        raise
    finally:
        db.close()
        _record_run(
            job_name=job_name,
            source=source_name,
            stats=stats,
            exc=exc,
            meta=meta,
        )
        _record_circuit_outcome(source_name, stats, exc)


# ------------------------------------------------------------------
# 具体任务
# ------------------------------------------------------------------

def run_fut_daily(collector, adapter, ts_code: str, start_date: str, end_date: str, period: str = "D") -> dict:
    """Sync recent futures daily/weekly/monthly bars.

    该任务需要预查 variety_id 并注入 adapter，逻辑较特殊，不直接使用 _run_simple_batch_pipeline。
    """
    source_name = collector.__class__.__name__
    if is_circuit_open(source_name):
        logger.warning("Circuit breaker open for %s, skipping fut_daily", source_name)
        return {"processed": 0, "failed": 0, "skipped": 0, "circuit_open": True}

    stats: dict[str, Any] = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(UTC)}
    db = SessionLocal()
    exc = None
    try:
        raw_rows = (
            collector.fetch_daily(ts_code, start_date, end_date) if period == "D" else
            collector.fetch_weekly(ts_code, start_date, end_date) if period == "W" else
            collector.fetch_monthly(ts_code, start_date, end_date)
        )
        if not raw_rows:
            return stats

        symbol = _symbol_from_ts_code(ts_code)
        variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        variety_id = variety.id if variety else None

        rows = []
        missing_variety = 0
        for raw in raw_rows:
            try:
                mapped = adapter(raw, variety_id, period) if adapter else raw
            except (KeyError, TypeError, ValueError, IndexError) as e:
                stats["failed"] += 1
                logger.warning("FutDaily adapter failed: row=%s, error=%s", raw, e)
                continue
            if mapped.get("variety_id") is None:
                missing_variety += 1
                continue
            if mapped.get("trade_date") is None:
                stats["skipped"] += 1
                continue
            rows.append(mapped)

        inserted = upsert_fut_daily_bulk(db, rows)
        db.commit()
        stats["processed"] = inserted
        stats["skipped"] += missing_variety + (len(rows) - inserted)
        logger.info("FutDaily pipeline (%s) completed: %s", period, stats)
        return stats
    except SQLAlchemyError as e:
        db.rollback()
        exc = e
        record_failure(source_name)
        logger.critical("FutDaily pipeline aborted: %s", e, exc_info=True)
        raise
    finally:
        db.close()
        _record_run(
            job_name=f"sync_fut_daily_{period}",
            source=source_name,
            stats=stats,
            exc=exc,
            meta={"ts_code": ts_code, "start_date": start_date, "end_date": end_date, "period": period},
        )
        _record_circuit_outcome(source_name, stats, exc)


def run_fut_settle(collector, adapter, trade_date: str, exchange: str = None) -> dict:
    """Sync futures settlement parameters."""
    return _run_simple_batch_pipeline(
        job_name="sync_fut_settle",
        collector=collector,
        fetch_fn=lambda: collector.fetch_settle(trade_date, exchange),
        adapter=adapter,
        filter_fn=lambda row: bool(row.get("ts_code") and row.get("trade_date")),
        upsert_fn=upsert_fut_settle_bulk,
        meta={"trade_date": trade_date, "exchange": exchange},
    )


def run_fut_weekly_detail(collector, adapter, start_date: str, end_date: str) -> dict:
    """Sync futures weekly trading detail."""
    return _run_simple_batch_pipeline(
        job_name="sync_fut_weekly_detail",
        collector=collector,
        fetch_fn=lambda: collector.fetch_weekly_detail(start_date, end_date),
        adapter=adapter,
        filter_fn=lambda row: bool(row.get("week") and row.get("prd") and row.get("exchange")),
        upsert_fn=upsert_fut_weekly_detail_bulk,
        meta={"start_date": start_date, "end_date": end_date},
    )


def run_fut_wsr(collector, adapter, trade_date: str, symbol: str = None) -> dict:
    """Sync futures warehouse receipt data."""
    return _run_simple_batch_pipeline(
        job_name="sync_fut_wsr",
        collector=collector,
        fetch_fn=lambda: collector.fetch_wsr(trade_date, symbol),
        adapter=adapter,
        filter_fn=lambda row: bool(row.get("trade_date") and row.get("symbol") and row.get("warehouse")),
        upsert_fn=upsert_fut_wsr_bulk,
        meta={"trade_date": trade_date, "symbol": symbol},
    )


def run_fut_holding(collector, adapter, trade_date: str, symbol: str = None, exchange: str = None) -> dict:
    """Sync futures holding rankings."""
    return _run_simple_batch_pipeline(
        job_name="sync_fut_holding",
        collector=collector,
        fetch_fn=lambda: collector.fetch_holding(trade_date, symbol, exchange),
        adapter=adapter,
        filter_fn=lambda row: bool(row.get("trade_date") and row.get("symbol") and row.get("broker")),
        upsert_fn=upsert_fut_holding_bulk,
        meta={"trade_date": trade_date, "symbol": symbol, "exchange": exchange},
    )


def run_fut_price_limit(collector, adapter, trade_date: str = None, ts_code: str = None) -> dict:
    """Daily sync for futures price limit data."""
    return _run_simple_batch_pipeline(
        job_name="sync_fut_price_limit",
        collector=collector,
        fetch_fn=lambda: collector.fetch_limit(trade_date=trade_date, ts_code=ts_code),
        adapter=adapter,
        filter_fn=lambda row: bool(row.get("ts_code") and row.get("trade_date")),
        upsert_fn=upsert_fut_price_limit_bulk,
        meta={"trade_date": trade_date, "ts_code": ts_code},
    )
