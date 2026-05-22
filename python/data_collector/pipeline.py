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
from models import SessionLocal, DataIngestionRunDB, VarietyDB, ContractRolloverDB, FutContractDB
from services.circuit_breaker import is_circuit_open, record_failure, record_success

logger = logging.getLogger(__name__)


CIRCUIT_FAILURE_THRESHOLD = 0.5


def _record_circuit_outcome(source_name: str, stats: dict, exc: Exception | None):
    """根据任务统计决定熔断器状态。

    规则：
    - 外层抛出异常 → 记录失败
    - 全部 skipped（无实际尝试）→ 不触碰熔断器
    - 全部失败或失败率 >= 阈值 → 记录失败
    - 否则 → 记录成功
    """
    if exc:
        record_failure(source_name)
        return

    processed = stats.get("processed", 0)
    failed = stats.get("failed", 0)
    # adapter_failed 也视为失败（扩展 pipeline 的适配器异常）
    adapter_failed = stats.get("adapter_failed", 0)
    total_attempted = processed + failed + adapter_failed

    if total_attempted == 0:
        # 无实际尝试（全部 skipped 或 circuit_open），不触碰熔断器
        return

    total_failed = failed + adapter_failed
    if total_failed == total_attempted:
        record_failure(source_name)
    elif total_failed / total_attempted >= CIRCUIT_FAILURE_THRESHOLD:
        record_failure(source_name)
    else:
        record_success(source_name)


def _symbol_from_ts_code(ts_code: str) -> str:
    base = (ts_code or "").split(".")[0]
    match = re.match(r"^([A-Za-z]+)", base)
    return match.group(1).upper() if match else base.upper()


def _record_run(job_name: str, source: str, stats: dict, exc: Exception = None, meta: dict = None):
    """记录采集批次到 data_ingestion_runs。使用独立 session，避免干扰采集事务。
    记录失败时至少记录 error 日志，不静默吞异常。"""
    run_db = SessionLocal()
    try:
        started_at = stats.get("_started_at", datetime.now(timezone.utc))
        finished_at = datetime.now(timezone.utc)
        duration_ms = None
        if isinstance(started_at, datetime):
            duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        error_sample = None
        if exc:
            error_sample = str(exc)[:500]

        window_start = None
        window_end = None
        if meta:
            window_start = meta.get("window_start")
            window_end = meta.get("window_end")

        run = DataIngestionRunDB(
            job_name=job_name,
            source=source,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            status="failed" if exc else "success",
            success_count=stats.get("processed", 0),
            failed_count=stats.get("failed", 0),
            skipped_count=stats.get("skipped", 0),
            error_message=str(exc)[:1000] if exc else None,
            error_sample=error_sample,
            window_start=window_start,
            window_end=window_end,
            metadata_json=json.dumps(meta, ensure_ascii=False, default=str) if meta else None,
        )
        run_db.add(run)
        run_db.commit()
    except Exception as e:
        logger.error(f"Failed to record ingestion run: {e}", exc_info=True)
        # OperationalError（如 database locked、连接断开）属于数据库层面问题，
        # 不应导致采集任务失败；其他异常应抛出以便排查。
        from sqlalchemy.exc import OperationalError
        if not isinstance(e, OperationalError):
            raise
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
        source_name = self.collector.__class__.__name__
        if is_circuit_open(source_name):
            logger.warning("Circuit breaker open for %s, skipping realtime", source_name)
            return {"processed": 0, "failed": 0, "skipped": len(symbols), "circuit_open": True}

        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None

        COMMIT_BATCH_SIZE = 50
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
                    if batch_counter >= COMMIT_BATCH_SIZE:
                        db.commit()
                        batch_counter = 0

                except Exception as e:
                    stats["failed"] += 1
                    logger.error(f"Pipeline failed for {symbol}: {e}", exc_info=True)
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    batch_counter = 0

            # 提交剩余未 commit 的数据
            if batch_counter > 0:
                db.commit()

            logger.info(f"Realtime pipeline completed: {stats}")
            return stats

        except Exception as e:
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

        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
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
                    except Exception as e:
                        stats["failed"] += 1
                        logger.warning(f"Kline adapter failed for {contract_code} {period}: {e}, row={row}")
                raw_rows = adapted_rows

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
                try:
                    if self.adapter:
                        mapped = self.adapter(raw, variety_id, period)
                    else:
                        mapped = raw
                except Exception as e:
                    stats["failed"] += 1
                    logger.warning(f"FutDaily adapter failed: row={raw}, error={e}")
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
            logger.info(f"FutDaily pipeline ({period}) completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            record_failure(self.collector.__class__.__name__)
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
            _record_circuit_outcome(self.collector.__class__.__name__, stats, exc)

    def run_fut_settle(self, trade_date: str, exchange: str = None) -> dict:
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None
        try:
            raw_rows = self.collector.fetch_settle(trade_date, exchange)
            if not raw_rows:
                return stats

            rows = []
            adapter_failed = 0
            if self.adapter:
                for row in raw_rows:
                    try:
                        rows.append(self.adapter(row))
                    except Exception as e:
                        adapter_failed += 1
                        logger.warning(f"FutSettle adapter failed: row={row}, error={e}")
            else:
                rows = raw_rows
            rows = [row for row in rows if row.get("ts_code") and row.get("trade_date")]
            inserted = upsert_fut_settle_bulk(db, rows)
            db.commit()
            stats["processed"] = inserted
            stats["skipped"] = len(raw_rows) - len(rows)
            stats["adapter_failed"] = adapter_failed
            if adapter_failed > 0:
                logger.warning(f"FutSettle pipeline partial: {stats}")
            else:
                logger.info(f"FutSettle pipeline completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            record_failure(self.collector.__class__.__name__)
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
            _record_circuit_outcome(self.collector.__class__.__name__, stats, exc)

    def run_fut_weekly_detail(self, start_date: str, end_date: str) -> dict:
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None
        try:
            raw_rows = self.collector.fetch_weekly_detail(start_date, end_date)
            if not raw_rows:
                return stats

            rows = []
            adapter_failed = 0
            if self.adapter:
                for row in raw_rows:
                    try:
                        rows.append(self.adapter(row))
                    except Exception as e:
                        adapter_failed += 1
                        logger.warning(f"FutWeeklyDetail adapter failed: row={row}, error={e}")
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
                logger.warning(f"FutWeeklyDetail pipeline partial: {stats}")
            else:
                logger.info(f"FutWeeklyDetail pipeline completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            record_failure(self.collector.__class__.__name__)
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
            _record_circuit_outcome(self.collector.__class__.__name__, stats, exc)

    def run_fut_wsr(self, trade_date: str, symbol: str = None) -> dict:
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None
        try:
            raw_rows = self.collector.fetch_wsr(trade_date, symbol)
            if not raw_rows:
                return stats

            rows = []
            adapter_failed = 0
            if self.adapter:
                for row in raw_rows:
                    try:
                        rows.append(self.adapter(row))
                    except Exception as e:
                        adapter_failed += 1
                        logger.warning(f"FutWsr adapter failed: row={row}, error={e}")
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
                logger.warning(f"FutWsr pipeline partial: {stats}")
            else:
                logger.info(f"FutWsr pipeline completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            record_failure(self.collector.__class__.__name__)
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
            _record_circuit_outcome(self.collector.__class__.__name__, stats, exc)

    def run_fut_holding(self, trade_date: str, symbol: str = None, exchange: str = None) -> dict:
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None
        try:
            raw_rows = self.collector.fetch_holding(trade_date, symbol, exchange)
            if not raw_rows:
                return stats

            rows = []
            adapter_failed = 0
            if self.adapter:
                for row in raw_rows:
                    try:
                        rows.append(self.adapter(row))
                    except Exception as e:
                        adapter_failed += 1
                        logger.warning(f"FutHolding adapter failed: row={row}, error={e}")
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
                logger.warning(f"FutHolding pipeline partial: {stats}")
            else:
                logger.info(f"FutHolding pipeline completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            record_failure(self.collector.__class__.__name__)
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
            _record_circuit_outcome(self.collector.__class__.__name__, stats, exc)

    def run_fut_price_limit(self, trade_date: str = None, ts_code: str = None) -> dict:
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        db = SessionLocal()
        exc = None
        try:
            raw_rows = self.collector.fetch_limit(trade_date=trade_date, ts_code=ts_code)
            if not raw_rows:
                return stats

            rows = []
            adapter_failed = 0
            if self.adapter:
                for row in raw_rows:
                    try:
                        rows.append(self.adapter(row))
                    except Exception as e:
                        adapter_failed += 1
                        logger.warning(f"FutPriceLimit adapter failed: row={row}, error={e}")
            else:
                rows = raw_rows
            rows = [row for row in rows if row.get("ts_code") and row.get("trade_date")]
            inserted = upsert_fut_price_limit_bulk(db, rows)
            db.commit()
            stats["processed"] = inserted
            stats["skipped"] = len(raw_rows) - len(rows)
            stats["adapter_failed"] = adapter_failed
            if adapter_failed > 0:
                logger.warning(f"FutPriceLimit pipeline partial: {stats}")
            else:
                logger.info(f"FutPriceLimit pipeline completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            record_failure(self.collector.__class__.__name__)
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
            _record_circuit_outcome(self.collector.__class__.__name__, stats, exc)

    def run_fut_mapping(self, trade_date: str = None, db=None) -> dict:
        """Update VarietyDB.contract_code from fut_mapping (main contract rollover).
        Also records rollover history to ContractRolloverDB when a switch is detected."""
        stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(timezone.utc)}
        close_db = db is None
        db = db if db is not None else SessionLocal()
        exc = None
        try:
            raw_rows = self.collector.fetch_mapping(trade_date=trade_date)
            if not raw_rows:
                return stats

            rows = []
            adapter_failed = 0
            if self.adapter:
                for row in raw_rows:
                    try:
                        rows.append(self.adapter(row))
                    except Exception as e:
                        adapter_failed += 1
                        logger.warning(f"FutMapping adapter failed: row={row}, error={e}")
            else:
                rows = raw_rows
            updated = 0
            skipped = 0
            for row in rows:
                ts_code = row.get("ts_code")
                mapping_ts_code = row.get("mapping_ts_code")
                if not ts_code or not mapping_ts_code:
                    skipped += 1
                    continue
                # Extract base symbol from ts_code, e.g. "AU.SHF" -> "AU"
                symbol = ts_code.split(".")[0]
                variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
                if not variety:
                    skipped += 1
                    continue
                # Extract contract_code from mapping_ts_code, e.g. "AU2506.SHF" -> "AU2506"
                contract_code = mapping_ts_code.split(".")[0]
                old_contract_code = variety.contract_code
                if old_contract_code != contract_code:
                    # Record rollover history
                    from models import ContractRolloverDB, FutContractDB
                    old_contract = (
                        db.query(FutContractDB).filter(FutContractDB.symbol == old_contract_code).first()
                        if old_contract_code else None
                    )
                    new_contract = (
                        db.query(FutContractDB).filter(FutContractDB.symbol == contract_code).first()
                    )
                    if not new_contract:
                        logger.error(
                            f"FutMapping abort: new contract {contract_code} not found for variety {variety.symbol}"
                        )
                        skipped += 1
                        continue

                    effective_date = datetime.now(timezone.utc)
                    if trade_date and len(trade_date) == 8 and trade_date.isdigit():
                        effective_date = datetime.strptime(trade_date, "%Y%m%d")

                    rollover = ContractRolloverDB(
                        variety_id=variety.id,
                        old_contract_id=old_contract.id if old_contract else None,
                        new_contract_id=new_contract.id,
                        old_contract_code=old_contract_code,
                        new_contract_code=contract_code,
                        effective_date=effective_date,
                        source="mapping_pipeline",
                    )
                    db.add(rollover)

                    variety.contract_code = contract_code
                    updated += 1
            db.commit()
            stats["processed"] = updated
            stats["skipped"] = skipped
            logger.info(f"FutMapping pipeline completed: {stats}")
            return stats
        except Exception as e:
            db.rollback()
            exc = e
            record_failure(self.collector.__class__.__name__)
            logger.critical(f"FutMapping pipeline aborted: {e}", exc_info=True)
            raise
        finally:
            if close_db:
                db.close()
            _record_run(
                job_name="sync_fut_mapping",
                source=self.collector.__class__.__name__,
                stats=stats,
                exc=exc,
                meta={"trade_date": trade_date},
            )
            _record_circuit_outcome(self.collector.__class__.__name__, stats, exc)
