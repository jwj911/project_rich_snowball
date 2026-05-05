"""数据采集 Pipeline：extract → map → clean → load。
Scheduler 只调用 Pipeline.run()，不直接操作 Collector/Cleaner/Upsert。
"""
import json
import logging
import re
from datetime import datetime, timezone

from data_collector.base import BaseCollector
from data_collector.upsert import (
    upsert_realtime, insert_kline_bulk,
    upsert_fut_daily_bulk, upsert_fut_settle_bulk,
    upsert_fut_weekly_detail_bulk, upsert_fut_wsr_bulk,
    upsert_fut_holding_bulk, upsert_fut_price_limit_bulk,
)
from models import SessionLocal, DataIngestionRunDB

logger = logging.getLogger(__name__)


def _symbol_from_ts_code(ts_code: str) -> str:
    base = (ts_code or "").split(".")[0]
    match = re.match(r"^([A-Za-z]+)", base)
    return match.group(1).upper() if match else base.upper()


def _record_run(job_name: str, source: str, stats: dict, exc: Exception = None, meta: dict = None):
    """记录采集批次到 data_ingestion_runs。使用独立 session，避免干扰采集事务。"""
    run_db = SessionLocal()
    try:
        run = DataIngestionRunDB(
            job_name=job_name,
            source=source,
            started_at=stats.get("_started_at", datetime.now(timezone.utc)),
            finished_at=datetime.now(timezone.utc),
            status="failed" if exc else "success",
            success_count=stats.get("processed", 0),
            failed_count=stats.get("failed", 0),
            skipped_count=stats.get("skipped", 0),
            error_message=str(exc)[:1000] if exc else None,
            metadata_json=json.dumps(meta, ensure_ascii=False, default=str) if meta else None,
        )
        run_db.add(run)
        run_db.commit()
    except Exception as e:
        logger.error(f"Failed to record ingestion run: {e}")
    finally:
        run_db.close()


class DataPipeline:
    """可配置的采集 Pipeline。"""

    def __init__(self, collector: BaseCollector, adapter=None, cleaner=None):
        self.collector = collector
        self.adapter = adapter
        self.cleaner = cleaner

    def run_realtime(self, symbols: list[str]) -> dict:
        """执行实时行情采集 Pipeline。返回统计信息。"""
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None

        try:
            for symbol in symbols:
                try:
                    raw = self.collector.fetch_realtime(symbol)
                    if raw is None:
                        stats["skipped"] += 1
                        continue

                    # Adapter 映射
                    if self.adapter:
                        raw = self.adapter(raw, symbol)

                    # Cleaner 校验
                    if self.cleaner:
                        data = self.cleaner(raw, symbol)
                        if data is None:
                            stats["skipped"] += 1
                            continue
                    else:
                        data = raw

                    upsert_realtime(db, data)
                    stats["processed"] += 1

                except Exception as e:
                    stats["failed"] += 1
                    logger.error(f"Pipeline failed for {symbol}: {e}", exc_info=True)

            db.commit()
            logger.info(f"Realtime pipeline completed: {stats}")
            return stats

        except Exception as e:
            db.rollback()
            exc = e
            logger.critical(f"Realtime pipeline aborted: {e}", exc_info=True)
            raise
        finally:
            db.close()
            _record_run(
                job_name="refresh_realtime_quotes",
                source=self.collector.__class__.__name__,
                stats=stats,
                exc=exc,
                meta={"symbols_count": len(symbols)},
            )

    def run_kline(self, contract_code: str, period: str, limit: int = 100) -> dict:
        """执行 K 线采集 Pipeline。"""
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None

        try:
            raw_rows = self.collector.fetch_kline(contract_code, period, limit=limit)
            if not raw_rows:
                return stats

            # Adapter 映射
            if self.adapter:
                raw_rows = [self.adapter(row, contract_code, period) for row in raw_rows]

            # Cleaner 校验
            if self.cleaner:
                rows = self.cleaner(raw_rows, contract_code)
            else:
                rows = raw_rows

            inserted = insert_kline_bulk(db, rows, period)
            db.commit()

            stats["processed"] = inserted
            stats["skipped"] = len(raw_rows) - inserted
            logger.info(f"K-line pipeline completed: {stats}")
            return stats

        except Exception as e:
            db.rollback()
            exc = e
            logger.critical(f"K-line pipeline aborted: {e}", exc_info=True)
            raise
        finally:
            db.close()
            _record_run(
                job_name=f"sync_kline_{period}",
                source=self.collector.__class__.__name__,
                stats=stats,
                exc=exc,
                meta={"contract_code": contract_code, "period": period, "limit": limit},
            )

    # ------------------------------------------------------------------
    # 扩展 Pipeline：期货日线 / 结算 / 周报 / 仓单 / 持仓
    # ------------------------------------------------------------------

    def run_fut_daily(self, ts_code: str, start_date: str, end_date: str, period: str = "D") -> dict:
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None
        try:
            raw_rows = self.collector.fetch_daily(ts_code, start_date, end_date) if period == "D" else \
                       self.collector.fetch_weekly(ts_code, start_date, end_date) if period == "W" else \
                       self.collector.fetch_monthly(ts_code, start_date, end_date)
            if not raw_rows:
                return stats

            # 查询 variety_id
            from models import VarietyDB
            symbol = _symbol_from_ts_code(ts_code)
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
            variety_id = variety.id if variety else None

            rows = []
            missing_variety = 0
            for raw in raw_rows:
                if self.adapter:
                    mapped = self.adapter(raw, variety_id, period)
                else:
                    mapped = raw
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
            logger.info(f"FutDaily pipeline ({period}) completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            logger.critical(f"FutDaily pipeline aborted: {e}", exc_info=True)
            raise
        finally:
            db.close()
            _record_run(
                job_name=f"sync_fut_daily_{period}",
                source=self.collector.__class__.__name__,
                stats=stats,
                exc=exc,
                meta={"ts_code": ts_code, "start_date": start_date, "end_date": end_date, "period": period},
            )

    def run_fut_settle(self, trade_date: str, exchange: str = None) -> dict:
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None
        try:
            raw_rows = self.collector.fetch_settle(trade_date, exchange)
            if not raw_rows:
                return stats

            rows = [self.adapter(row) for row in raw_rows] if self.adapter else raw_rows
            rows = [row for row in rows if row.get("ts_code") and row.get("trade_date")]
            inserted = upsert_fut_settle_bulk(db, rows)
            db.commit()
            stats["processed"] = inserted
            stats["skipped"] = len(raw_rows) - len(rows)
            logger.info(f"FutSettle pipeline completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            logger.critical(f"FutSettle pipeline aborted: {e}", exc_info=True)
            raise
        finally:
            db.close()
            _record_run(
                job_name="sync_fut_settle",
                source=self.collector.__class__.__name__,
                stats=stats,
                exc=exc,
                meta={"trade_date": trade_date, "exchange": exchange},
            )

    def run_fut_weekly_detail(self, start_date: str, end_date: str) -> dict:
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None
        try:
            raw_rows = self.collector.fetch_weekly_detail(start_date, end_date)
            if not raw_rows:
                return stats

            rows = [self.adapter(row) for row in raw_rows] if self.adapter else raw_rows
            rows = [
                row for row in rows
                if row.get("week") and row.get("prd") and row.get("exchange")
            ]
            inserted = upsert_fut_weekly_detail_bulk(db, rows)
            db.commit()
            stats["processed"] = inserted
            stats["skipped"] = len(raw_rows) - len(rows)
            logger.info(f"FutWeeklyDetail pipeline completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            logger.critical(f"FutWeeklyDetail pipeline aborted: {e}", exc_info=True)
            raise
        finally:
            db.close()
            _record_run(
                job_name="sync_fut_weekly_detail",
                source=self.collector.__class__.__name__,
                stats=stats,
                exc=exc,
                meta={"start_date": start_date, "end_date": end_date},
            )

    def run_fut_wsr(self, trade_date: str, symbol: str = None) -> dict:
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None
        try:
            raw_rows = self.collector.fetch_wsr(trade_date, symbol)
            if not raw_rows:
                return stats

            rows = [self.adapter(row) for row in raw_rows] if self.adapter else raw_rows
            rows = [
                row for row in rows
                if row.get("trade_date") and row.get("symbol") and row.get("warehouse")
            ]
            inserted = upsert_fut_wsr_bulk(db, rows)
            db.commit()
            stats["processed"] = inserted
            stats["skipped"] = len(raw_rows) - len(rows)
            logger.info(f"FutWsr pipeline completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            logger.critical(f"FutWsr pipeline aborted: {e}", exc_info=True)
            raise
        finally:
            db.close()
            _record_run(
                job_name="sync_fut_wsr",
                source=self.collector.__class__.__name__,
                stats=stats,
                exc=exc,
                meta={"trade_date": trade_date, "symbol": symbol},
            )

    def run_fut_holding(self, trade_date: str, symbol: str = None, exchange: str = None) -> dict:
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None
        try:
            raw_rows = self.collector.fetch_holding(trade_date, symbol, exchange)
            if not raw_rows:
                return stats

            rows = [self.adapter(row) for row in raw_rows] if self.adapter else raw_rows
            rows = [
                row for row in rows
                if row.get("trade_date") and row.get("symbol") and row.get("broker")
            ]
            inserted = upsert_fut_holding_bulk(db, rows)
            db.commit()
            stats["processed"] = inserted
            stats["skipped"] = len(raw_rows) - len(rows)
            logger.info(f"FutHolding pipeline completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            logger.critical(f"FutHolding pipeline aborted: {e}", exc_info=True)
            raise
        finally:
            db.close()
            _record_run(
                job_name="sync_fut_holding",
                source=self.collector.__class__.__name__,
                stats=stats,
                exc=exc,
                meta={"trade_date": trade_date, "symbol": symbol, "exchange": exchange},
            )

    def run_fut_price_limit(self, trade_date: str = None, ts_code: str = None) -> dict:
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None
        try:
            raw_rows = self.collector.fetch_limit(trade_date=trade_date, ts_code=ts_code)
            if not raw_rows:
                return stats

            rows = [self.adapter(row) for row in raw_rows] if self.adapter else raw_rows
            rows = [row for row in rows if row.get("ts_code") and row.get("trade_date")]
            inserted = upsert_fut_price_limit_bulk(db, rows)
            db.commit()
            stats["processed"] = inserted
            stats["skipped"] = len(raw_rows) - len(rows)
            logger.info(f"FutPriceLimit pipeline completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            logger.critical(f"FutPriceLimit pipeline aborted: {e}", exc_info=True)
            raise
        finally:
            db.close()
            _record_run(
                job_name="sync_fut_price_limit",
                source=self.collector.__class__.__name__,
                stats=stats,
                exc=exc,
                meta={"trade_date": trade_date, "ts_code": ts_code},
            )
