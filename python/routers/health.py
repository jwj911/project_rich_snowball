import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, text
from sqlalchemy.orm import Session

from config import ENABLE_SCHEDULER
from dependencies import get_db
from models import DataIngestionRunDB, get_engine_info
from services.cache import get_cache_stats
from services.circuit_breaker import get_circuit_status

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get("")
def health_check():
    return {
        "status": "ok",
        "version": "2.0.0",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    """返回系统就绪状态。DB 可连接即 ready；若配置了 Redis，也检查 Redis 连通性。"""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        # 数据库连接异常视为未就绪（不暴露具体错误给客户端）
        db_ok = False

    redis_ok = True
    if os.getenv("REDIS_URL"):
        from services.redis_client import get_redis_client
        try:
            client = get_redis_client()
            redis_ok = client is not None and client.ping()
        except Exception:
            redis_ok = False

    cache_stats = get_cache_stats()

    ready = db_ok and redis_ok

    if not ready:
        raise HTTPException(
            status_code=503,
            detail=f"Service not ready: db={db_ok}, cache={cache_stats}",
        )

    return {
        "ready": True,
        "db": db_ok,
        "cache": cache_stats,
        "engine": get_engine_info(),
    }


@router.get("/scheduler")
def scheduler_check(db: Session = Depends(get_db)):
    """返回调度器状态与最近任务历史。API 进程本身不运行 scheduler 时也返回信息。"""
    try:
        from data_collector.scheduler import scheduler
        scheduler_running = scheduler.running
    except (ImportError, AttributeError):
        scheduler_running = False

    # 最近 24 小时的任务统计（聚合全量，避免 limit 导致失真）
    since = datetime.now(UTC) - timedelta(hours=24)

    agg = (
        db.query(
            func.count(DataIngestionRunDB.id).label("total"),
            func.sum(case((DataIngestionRunDB.status == "success", 1), else_=0)).label("success"),
            func.sum(case((DataIngestionRunDB.status == "failed", 1), else_=0)).label("failed"),
            func.avg(DataIngestionRunDB.duration_ms).label("avg_duration"),
        )
        .filter(DataIngestionRunDB.started_at >= since)
        .first()
    )

    total = agg.total or 0
    success = agg.success or 0
    failed = agg.failed or 0
    avg_duration_ms = int(agg.avg_duration) if agg.avg_duration is not None else None

    last_success = None
    if total > 0:
        last_success_row = (
            db.query(DataIngestionRunDB)
            .filter(DataIngestionRunDB.started_at >= since)
            .filter(DataIngestionRunDB.status == "success")
            .order_by(DataIngestionRunDB.started_at.desc())
            .first()
        )
        if last_success_row and last_success_row.started_at:
            last_success = last_success_row.started_at.isoformat()

    # 列表展示：最近 10 条（独立查询，不影响聚合统计）
    recent_runs = (
        db.query(DataIngestionRunDB)
        .filter(DataIngestionRunDB.started_at >= since)
        .order_by(DataIngestionRunDB.started_at.desc())
        .limit(10)
        .all()
    )

    # 熔断器状态
    circuit_status = get_circuit_status()

    return {
        "scheduler_enabled": ENABLE_SCHEDULER,
        "scheduler_running": scheduler_running,
        "recent_runs": {
            "total": total,
            "success": success,
            "failed": failed,
            "success_rate": round(success / total, 2) if total > 0 else None,
            "last_success": last_success,
            "avg_duration_ms": avg_duration_ms,
        },
        "runs": [
            {
                "job_name": r.job_name,
                "source": r.source,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "duration_ms": r.duration_ms,
                "success_count": r.success_count,
                "failed_count": r.failed_count,
            }
            for r in recent_runs
        ],
        "circuit_breakers": circuit_status,
        "timestamp": datetime.now(UTC).isoformat(),
    }
