"""Pipeline task 公共辅助函数。

提取 _record_run、_record_circuit_outcome、_symbol_from_ts_code，
避免在 pipeline.py 与各个 task 模块间重复定义。
"""

import json
import logging
import re
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, OperationalError

from config import CIRCUIT_FAILURE_THRESHOLD
from models import DataIngestionRunDB, SessionLocal
from services.circuit_breaker import record_failure, record_success

logger = logging.getLogger(__name__)


def _symbol_from_ts_code(ts_code: str) -> str:
    base = (ts_code or "").split(".")[0]
    match = re.match(r"^([A-Za-z]+)", base)
    return match.group(1).upper() if match else base.upper()


def _record_run(job_name: str, source: str, stats: dict, exc: Exception = None, meta: dict = None):
    """记录采集批次到 data_ingestion_runs。使用独立 session，避免干扰采集事务。
    记录失败时至少记录 error 日志，不静默吞异常。"""
    run_db = SessionLocal()
    try:
        started_at = stats.get("_started_at", datetime.now(UTC))
        finished_at = datetime.now(UTC)
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
    except (OperationalError, IntegrityError, TypeError, ValueError) as e:
        logger.error("Failed to record ingestion run: %s", e, exc_info=True)
        if not isinstance(e, OperationalError):
            raise
    finally:
        run_db.close()


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
    adapter_failed = stats.get("adapter_failed", 0)
    total_attempted = processed + failed + adapter_failed

    if total_attempted == 0:
        return

    total_failed = failed + adapter_failed
    if total_failed == total_attempted or total_failed / total_attempted >= CIRCUIT_FAILURE_THRESHOLD:
        record_failure(source_name)
    else:
        record_success(source_name)
