"""数据采集 Pipeline：extract → map → clean → load。
Scheduler 只调用 Pipeline.run()，不直接操作 Collector/Cleaner/Upsert。
"""
import contextlib
import logging
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from config import PIPELINE_COMMIT_BATCH_SIZE
from data_collector.base import BaseCollector
from data_collector.pipeline_tasks._common import (
    _record_circuit_outcome,
    _record_run,
)
from data_collector.upsert import insert_kline_bulk, upsert_realtime
from models import SessionLocal
from services.circuit_breaker import is_circuit_open, record_failure

logger = logging.getLogger(__name__)





class DataPipeline:
    """可配置的采集 Pipeline。"""

    def __init__(self, collector: BaseCollector, adapter=None, cleaner=None):
        self.collector = collector
        self.adapter = adapter
        self.cleaner = cleaner

    def run_realtime(self, symbols: list[str]) -> dict:
        """执行实时行情采集 Pipeline。返回统计信息。"""
        source_name = self.collector.__class__.__name__
        if is_circuit_open(source_name):
            logger.warning("Circuit breaker open for %s, skipping realtime", source_name)
            return {"processed": 0, "failed": 0, "skipped": len(symbols), "circuit_open": True}

        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(UTC)}
        db = SessionLocal()
        exc = None

        commit_batch_size = PIPELINE_COMMIT_BATCH_SIZE
        batch_counter = 0

        try:
            # 批量预查 symbol -> variety_id，避免 upsert_realtime 内部 N+1 查询
            from models import VarietyDB
            variety_map = {
                v.symbol: v.id
                for v in db.query(VarietyDB).filter(VarietyDB.symbol.in_(symbols)).all()
            }

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

                    variety_id = variety_map.get(symbol)
                    if not variety_id:
                        stats["skipped"] += 1
                        logger.warning(f"Variety not found for symbol: {symbol}")
                        continue
                    data["variety_id"] = variety_id
                    upsert_realtime(db, data)
                    batch_counter += 1
                    stats["processed"] += 1

                    # 批量 commit，减少事务开销
                    if batch_counter >= commit_batch_size:
                        db.commit()
                        batch_counter = 0

                except (KeyError, TypeError, ValueError, IndexError) as e:
                    stats["failed"] += 1
                    logger.error(f"Pipeline failed for {symbol}: {e}", exc_info=True)
                    with contextlib.suppress(SQLAlchemyError):
                        db.rollback()
                    batch_counter = 0

            # 提交剩余未 commit 的数据
            if batch_counter > 0:
                db.commit()

            logger.info(f"Realtime pipeline completed: {stats}")
            return stats

        except SQLAlchemyError as e:
            db.rollback()
            exc = e
            logger.critical(f"Realtime pipeline aborted: {e}", exc_info=True)
            record_failure(source_name)
            raise
        finally:
            db.close()
            _record_run(
                job_name="refresh_realtime_quotes",
                source=source_name,
                stats=stats,
                exc=exc,
                meta={"symbols_count": len(symbols)},
            )
            _record_circuit_outcome(source_name, stats, exc)

    def run_kline(self, contract_code: str, period: str, limit: int = 100) -> dict:
        """执行 K 线采集 Pipeline。"""
        source_name = self.collector.__class__.__name__
        if is_circuit_open(source_name):
            logger.warning("Circuit breaker open for %s, skipping kline", source_name)
            return {"processed": 0, "failed": 0, "skipped": 0, "circuit_open": True}

        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(UTC)}
        db = SessionLocal()
        exc = None

        try:
            raw_rows = self.collector.fetch_kline(contract_code, period, limit=limit)
            if not raw_rows:
                return stats

            # Adapter 映射（逐行容错，单条失败不丢弃整批）
            if self.adapter:
                adapted_rows = []
                for row in raw_rows:
                    try:
                        adapted_rows.append(self.adapter(row, contract_code, period))
                    except (KeyError, TypeError, ValueError, IndexError) as e:
                        stats["failed"] += 1
                        logger.warning(f"Kline adapter failed for {contract_code} {period}: {e}, row={row}")
                raw_rows = adapted_rows

            # Cleaner 校验
            rows = self.cleaner(raw_rows, contract_code) if self.cleaner else raw_rows

            inserted = insert_kline_bulk(db, rows, period)
            db.commit()

            stats["processed"] = inserted
            stats["skipped"] = len(raw_rows) - inserted
            logger.info(f"K-line pipeline completed: {stats}")
            return stats

        except SQLAlchemyError as e:
            db.rollback()
            exc = e
            logger.critical(f"K-line pipeline aborted: {e}", exc_info=True)
            record_failure(source_name)
            raise
        finally:
            db.close()
            _record_run(
                job_name=f"sync_kline_{period}",
                source=source_name,
                stats=stats,
                exc=exc,
                meta={"contract_code": contract_code, "period": period, "limit": limit},
            )
            _record_circuit_outcome(source_name, stats, exc)

    # ------------------------------------------------------------------
    # 扩展 Pipeline：期货日线 / 结算 / 周报 / 仓单 / 持仓
    # ------------------------------------------------------------------

    def run_fut_daily(self, ts_code: str, start_date: str, end_date: str, period: str = "D") -> dict:
        from data_collector.pipeline_tasks.tushare_batch_tasks import run_fut_daily
        return run_fut_daily(self.collector, self.adapter, ts_code, start_date, end_date, period)

    def run_fut_settle(self, trade_date: str, exchange: str = None) -> dict:
        from data_collector.pipeline_tasks.tushare_batch_tasks import run_fut_settle
        return run_fut_settle(self.collector, self.adapter, trade_date, exchange)

    def run_fut_weekly_detail(self, start_date: str, end_date: str) -> dict:
        from data_collector.pipeline_tasks.tushare_batch_tasks import run_fut_weekly_detail
        return run_fut_weekly_detail(self.collector, self.adapter, start_date, end_date)

    def run_fut_wsr(self, trade_date: str, symbol: str = None) -> dict:
        from data_collector.pipeline_tasks.tushare_batch_tasks import run_fut_wsr
        return run_fut_wsr(self.collector, self.adapter, trade_date, symbol)

    def run_fut_holding(self, trade_date: str, symbol: str = None, exchange: str = None) -> dict:
        from data_collector.pipeline_tasks.tushare_batch_tasks import run_fut_holding
        return run_fut_holding(self.collector, self.adapter, trade_date, symbol, exchange)

    def run_fut_price_limit(self, trade_date: str = None, ts_code: str = None) -> dict:
        from data_collector.pipeline_tasks.tushare_batch_tasks import run_fut_price_limit
        return run_fut_price_limit(self.collector, self.adapter, trade_date, ts_code)

    def run_fut_mapping(self, trade_date: str = None, db=None) -> dict:
        """Update VarietyDB.contract_code from fut_mapping (main contract rollover).
        Also records rollover history to ContractRolloverDB when a switch is detected.

        内部实现已下沉到 pipeline_tasks.fut_mapping_task，此处保留为兼容代理。
        """
        from data_collector.pipeline_tasks.fut_mapping_task import run_fut_mapping_task
        return run_fut_mapping_task(self.collector, self.adapter, trade_date=trade_date, db=db)
