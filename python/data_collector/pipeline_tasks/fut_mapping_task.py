"""主力合约映射任务（Fut Mapping Task）
==============================
从 Tushare fut_mapping 接口更新 VarietyDB.contract_code，
并在检测到主力合约切换时自动记录 ContractRolloverDB。

原位于 data_collector.pipeline.DataPipeline.run_fut_mapping，
因承担映射、合约、rollover、事务等多重职责，圈复杂度高，故独立为任务模块。
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from data_collector.pipeline_tasks._common import (
    _record_circuit_outcome,
    _record_run,
)
from models import ContractRolloverDB, FutContractDB, SessionLocal, VarietyDB
from services.circuit_breaker import record_failure

logger = logging.getLogger(__name__)


def _preload_maps(db, rows: list[dict]) -> tuple[dict, dict]:
    """批量预查 variety 和 contract，消除 N+1。"""
    symbols = set()
    contract_codes = set()
    for row in rows:
        ts_code = row.get("ts_code", "")
        mapping_ts_code = row.get("mapping_ts_code", "")
        symbols.add(ts_code.split(".")[0])
        contract_codes.add(mapping_ts_code.split(".")[0])

    variety_map = {
        v.symbol: v
        for v in db.query(VarietyDB).filter(VarietyDB.symbol.in_(symbols)).all()
    }
    # 旧合约代码也需要参与预查
    for v in variety_map.values():
        if v.contract_code:
            contract_codes.add(v.contract_code)

    contract_map = {
        c.symbol: c
        for c in db.query(FutContractDB).filter(FutContractDB.symbol.in_(contract_codes)).all()
    }
    return variety_map, contract_map


def _is_valid_contract_month(contract_code: str) -> bool:
    """校验合约代码中的月份是否有效（非00）。"""
    if len(contract_code) < 4:
        return False
    month_str = contract_code[-2:]
    if not month_str.isdigit():
        return False
    return month_str != "00"


def _detect_rollovers(rows, variety_map, contract_map, trade_date: str | None):
    """遍历 mapping 行，检测合约切换，生成 rollover 记录。"""
    rollovers = []
    updated = 0
    skipped = 0

    for row in rows:
        ts_code = row.get("ts_code")
        mapping_ts_code = row.get("mapping_ts_code")
        if not ts_code or not mapping_ts_code:
            skipped += 1
            continue

        symbol = ts_code.split(".")[0]
        variety = variety_map.get(symbol)
        if not variety:
            skipped += 1
            continue

        contract_code = mapping_ts_code.split(".")[0]
        if not _is_valid_contract_month(contract_code):
            logger.warning(
                "Invalid contract month in mapping: %s for variety %s, skipping",
                contract_code, variety.symbol
            )
            skipped += 1
            continue

        old_contract_code = variety.contract_code
        if old_contract_code != contract_code:
            old_contract = contract_map.get(old_contract_code) if old_contract_code else None
            new_contract = contract_map.get(contract_code)
            if not new_contract:
                logger.error(
                    "FutMapping abort: new contract %s not found for variety %s",
                    contract_code, variety.symbol
                )
                skipped += 1
                continue

            effective_date = datetime.now(UTC)
            if trade_date and len(trade_date) == 8 and trade_date.isdigit():
                effective_date = datetime.strptime(trade_date, "%Y%m%d")

            rollovers.append(ContractRolloverDB(
                variety_id=variety.id,
                old_contract_id=old_contract.id if old_contract else None,
                new_contract_id=new_contract.id,
                old_contract_code=old_contract_code,
                new_contract_code=contract_code,
                effective_date=effective_date,
                source="mapping_pipeline",
            ))
            logger.info(
                "contract_rollover_detected",
                extra={
                    "variety_id": variety.id,
                    "variety_symbol": variety.symbol,
                    "old_contract_id": old_contract.id if old_contract else None,
                    "old_contract_code": old_contract_code,
                    "new_contract_id": new_contract.id,
                    "new_contract_code": contract_code,
                    "effective_date": effective_date.isoformat(),
                },
            )
            variety.contract_code = contract_code
            updated += 1

    return rollovers, updated, skipped


def run_fut_mapping_task(collector, adapter, trade_date: str = None, db=None) -> dict:
    """执行主力合约映射更新任务。

    参数:
        collector: 具备 fetch_mapping(trade_date=...) 方法的采集器
        adapter: 行级适配器函数，接受 raw row 返回 dict
        trade_date: 交易日期（YYYYMMDD），None 表示当前日期
        db: 可选的外部 session；None 时内部创建并关闭

    返回:
        stats dict，包含 processed / failed / skipped 计数
    """
    stats = {"processed": 0, "failed": 0, "skipped": 0, "_started_at": datetime.now(UTC)}
    close_db = db is None
    db = db if db is not None else SessionLocal()
    exc = None

    try:
        raw_rows = collector.fetch_mapping(trade_date=trade_date)
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
                    logger.warning("FutMapping adapter failed: row=%s, error=%s", row, e)
        else:
            rows = raw_rows

        variety_map, contract_map = _preload_maps(db, rows)
        rollovers, updated, skipped = _detect_rollovers(rows, variety_map, contract_map, trade_date)

        for r in rollovers:
            db.add(r)

        # 幂等性说明：ContractRolloverDB 有唯一约束
        #   (variety_id, effective_date, new_contract_code)
        # 同一天重复跑 mapping 时，相同 rollover 会因约束冲突被数据库拒绝，
        # 不会重复插入。若需显式忽略冲突，可改用 PostgreSQL ON CONFLICT DO NOTHING。
        db.commit()
        stats["processed"] = updated
        stats["skipped"] = skipped
        stats["adapter_failed"] = adapter_failed
        logger.info("FutMapping task completed: %s", stats)
        return stats

    except SQLAlchemyError as e:
        db.rollback()
        exc = e
        record_failure(collector.__class__.__name__)
        logger.critical("FutMapping task aborted: %s", e, exc_info=True)
        raise
    finally:
        if close_db:
            db.close()
        _record_run(
            job_name="sync_fut_mapping",
            source=collector.__class__.__name__,
            stats=stats,
            exc=exc,
            meta={"trade_date": trade_date},
        )
        _record_circuit_outcome(collector.__class__.__name__, stats, exc)
