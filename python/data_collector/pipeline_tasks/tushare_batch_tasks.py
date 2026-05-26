"""Tushare 扩展批量采集任务。

将 run_fut_daily / run_fut_settle / run_fut_weekly_detail /
run_fut_wsr / run_fut_holding / run_fut_price_limit 从 DataPipeline 下沉至此，
降低 pipeline.py 复杂度，新增同类任务时无需修改 DataPipeline 主体。
"""

import logging
from datetime import UTC, datetime

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


def run_fut_daily(collector, adapter, ts_code: str, start_date: str, end_date: str, period: str = "D") -> dict:
    """Sync recent futures daily/weekly/monthly bars."""
    source_name = collector.__class__.__name__
    if is_circuit_open(source_name):
        logger.warning("Circuit breaker open for %s, skipping fut_daily", source_name)
        return {"processed": 0, "failed": 0, "skipped": 0, "circuit_open": True}

    stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(UTC)}
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
    source_name = collector.__class__.__name__
    if is_circuit_open(source_name):
        logger.warning("Circuit breaker open for %s, skipping fut_settle", source_name)
        return {"processed": 0, "failed": 0, "skipped": 0, "circuit_open": True}

    stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(UTC)}
    db = SessionLocal()
    exc = None
    try:
        raw_rows = collector.fetch_settle(trade_date, exchange)
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
                    logger.warning("FutSettle adapter failed: row=%s, error=%s", row, e)
        else:
            rows = raw_rows
        rows = [row for row in rows if row.get("ts_code") and row.get("trade_date")]
        inserted = upsert_fut_settle_bulk(db, rows)
        db.commit()
        stats["processed"] = inserted
        stats["skipped"] = len(raw_rows) - len(rows)
        stats["adapter_failed"] = adapter_failed
        if adapter_failed > 0:
            logger.warning("FutSettle pipeline partial: %s", stats)
        else:
            logger.info("FutSettle pipeline completed: %s", stats)
        return stats
    except SQLAlchemyError as e:
        db.rollback()
        exc = e
        record_failure(source_name)
        logger.critical("FutSettle pipeline aborted: %s", e, exc_info=True)
        raise
    finally:
        db.close()
        _record_run(
            job_name="sync_fut_settle",
            source=source_name,
            stats=stats,
            exc=exc,
            meta={"trade_date": trade_date, "exchange": exchange},
        )
        _record_circuit_outcome(source_name, stats, exc)


def run_fut_weekly_detail(collector, adapter, start_date: str, end_date: str) -> dict:
    """Sync futures weekly trading detail."""
    source_name = collector.__class__.__name__
    if is_circuit_open(source_name):
        logger.warning("Circuit breaker open for %s, skipping fut_weekly_detail", source_name)
        return {"processed": 0, "failed": 0, "skipped": 0, "circuit_open": True}

    stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(UTC)}
    db = SessionLocal()
    exc = None
    try:
        raw_rows = collector.fetch_weekly_detail(start_date, end_date)
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
                    logger.warning("FutWeeklyDetail adapter failed: row=%s, error=%s", row, e)
        else:
            rows = raw_rows
        rows = [
            row for row in rows
            if row.get("week") and row.get("prd") and row.get("exchange")
        ]
        inserted = upsert_fut_weekly_detail_bulk(db, rows)
        db.commit()
        stats["processed"] = inserted
        stats["skipped"] = len(raw_rows) - len(rows)
        stats["adapter_failed"] = adapter_failed
        if adapter_failed > 0:
            logger.warning("FutWeeklyDetail pipeline partial: %s", stats)
        else:
            logger.info("FutWeeklyDetail pipeline completed: %s", stats)
        return stats
    except SQLAlchemyError as e:
        db.rollback()
        exc = e
        record_failure(source_name)
        logger.critical("FutWeeklyDetail pipeline aborted: %s", e, exc_info=True)
        raise
    finally:
        db.close()
        _record_run(
            job_name="sync_fut_weekly_detail",
            source=source_name,
            stats=stats,
            exc=exc,
            meta={"start_date": start_date, "end_date": end_date},
        )
        _record_circuit_outcome(source_name, stats, exc)


def run_fut_wsr(collector, adapter, trade_date: str, symbol: str = None) -> dict:
    """Sync futures warehouse receipt data."""
    source_name = collector.__class__.__name__
    if is_circuit_open(source_name):
        logger.warning("Circuit breaker open for %s, skipping fut_wsr", source_name)
        return {"processed": 0, "failed": 0, "skipped": 0, "circuit_open": True}

    stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(UTC)}
    db = SessionLocal()
    exc = None
    try:
        raw_rows = collector.fetch_wsr(trade_date, symbol)
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
                    logger.warning("FutWsr adapter failed: row=%s, error=%s", row, e)
        else:
            rows = raw_rows
        rows = [
            row for row in rows
            if row.get("trade_date") and row.get("symbol") and row.get("warehouse")
        ]
        inserted = upsert_fut_wsr_bulk(db, rows)
        db.commit()
        stats["processed"] = inserted
        stats["skipped"] = len(raw_rows) - len(rows)
        stats["adapter_failed"] = adapter_failed
        if adapter_failed > 0:
            logger.warning("FutWsr pipeline partial: %s", stats)
        else:
            logger.info("FutWsr pipeline completed: %s", stats)
        return stats
    except SQLAlchemyError as e:
        db.rollback()
        exc = e
        record_failure(source_name)
        logger.critical("FutWsr pipeline aborted: %s", e, exc_info=True)
        raise
    finally:
        db.close()
        _record_run(
            job_name="sync_fut_wsr",
            source=source_name,
            stats=stats,
            exc=exc,
            meta={"trade_date": trade_date, "symbol": symbol},
        )
        _record_circuit_outcome(source_name, stats, exc)


def run_fut_holding(collector, adapter, trade_date: str, symbol: str = None, exchange: str = None) -> dict:
    """Sync futures holding rankings."""
    source_name = collector.__class__.__name__
    if is_circuit_open(source_name):
        logger.warning("Circuit breaker open for %s, skipping fut_holding", source_name)
        return {"processed": 0, "failed": 0, "skipped": 0, "circuit_open": True}

    stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(UTC)}
    db = SessionLocal()
    exc = None
    try:
        raw_rows = collector.fetch_holding(trade_date, symbol, exchange)
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
                    logger.warning("FutHolding adapter failed: row=%s, error=%s", row, e)
        else:
            rows = raw_rows
        rows = [
            row for row in rows
            if row.get("trade_date") and row.get("symbol") and row.get("broker")
        ]
        inserted = upsert_fut_holding_bulk(db, rows)
        db.commit()
        stats["processed"] = inserted
        stats["skipped"] = len(raw_rows) - len(rows)
        stats["adapter_failed"] = adapter_failed
        if adapter_failed > 0:
            logger.warning("FutHolding pipeline partial: %s", stats)
        else:
            logger.info("FutHolding pipeline completed: %s", stats)
        return stats
    except SQLAlchemyError as e:
        db.rollback()
        exc = e
        record_failure(source_name)
        logger.critical("FutHolding pipeline aborted: %s", e, exc_info=True)
        raise
    finally:
        db.close()
        _record_run(
            job_name="sync_fut_holding",
            source=source_name,
            stats=stats,
            exc=exc,
            meta={"trade_date": trade_date, "symbol": symbol, "exchange": exchange},
        )
        _record_circuit_outcome(source_name, stats, exc)


def run_fut_price_limit(collector, adapter, trade_date: str = None, ts_code: str = None) -> dict:
    """Daily sync for futures price limit data."""
    source_name = collector.__class__.__name__
    if is_circuit_open(source_name):
        logger.warning("Circuit breaker open for %s, skipping fut_price_limit", source_name)
        return {"processed": 0, "failed": 0, "skipped": 0, "circuit_open": True}

    stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(UTC)}
    db = SessionLocal()
    exc = None
    try:
        raw_rows = collector.fetch_limit(trade_date=trade_date, ts_code=ts_code)
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
                    logger.warning("FutPriceLimit adapter failed: row=%s, error=%s", row, e)
        else:
            rows = raw_rows
        rows = [row for row in rows if row.get("ts_code") and row.get("trade_date")]
        inserted = upsert_fut_price_limit_bulk(db, rows)
        db.commit()
        stats["processed"] = inserted
        stats["skipped"] = len(raw_rows) - len(rows)
        stats["adapter_failed"] = adapter_failed
        if adapter_failed > 0:
            logger.warning("FutPriceLimit pipeline partial: %s", stats)
        else:
            logger.info("FutPriceLimit pipeline completed: %s", stats)
        return stats
    except SQLAlchemyError as e:
        db.rollback()
        exc = e
        record_failure(source_name)
        logger.critical("FutPriceLimit pipeline aborted: %s", e, exc_info=True)
        raise
    finally:
        db.close()
        _record_run(
            job_name="sync_fut_price_limit",
            source=source_name,
            stats=stats,
            exc=exc,
            meta={"trade_date": trade_date, "ts_code": ts_code},
        )
        _record_circuit_outcome(source_name, stats, exc)
