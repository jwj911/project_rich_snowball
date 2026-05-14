from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from datetime import datetime, timezone, timedelta

from dependencies import get_db
from models import get_engine_info, DataIngestionRunDB
from services.cache import get_cache_stats
from services.circuit_breaker import get_circuit_status
from config import ENABLE_SCHEDULER

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get("")
def health_check():
    return {
        "status": "ok",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    """返回系统就绪状态。DB 可连接即 ready。scheduler 状态单独检查。"""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    cache_stats = get_cache_stats()

    ready = db_ok

    if not ready:
        raise HTTPException(
            status_code=503,
            detail={
                "ready": False,
                "db": db_ok,
                "cache": cache_stats,
            },
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
    except Exception:
        scheduler_running = False

    # 最近 24 小时的任务统计
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_runs = (
        db.query(DataIngestionRunDB)
        .filter(DataIngestionRunDB.started_at >= since)
        .order_by(DataIngestionRunDB.started_at.desc())
        .limit(20)
        .all()
    )

    total = len(recent_runs)
    success = sum(1 for r in recent_runs if r.status == "success")
    failed = sum(1 for r in recent_runs if r.status == "failed")

    last_success = None
    for r in recent_runs:
        if r.status == "success":
            last_success = r.started_at.isoformat() if r.started_at else None
            break

    # 平均执行时长
    durations = [r.duration_ms for r in recent_runs if r.duration_ms is not None]
    avg_duration_ms = int(sum(durations) / len(durations)) if durations else None

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
            for r in recent_runs[:10]
        ],
        "circuit_breakers": circuit_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
