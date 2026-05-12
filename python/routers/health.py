from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone

from dependencies import get_db
from models import get_engine_info
from services.cache import get_cache_stats
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
def scheduler_check():
    """返回调度器状态。API 进程本身不运行 scheduler 时也返回信息。"""
    try:
        from data_collector.scheduler import scheduler
        scheduler_running = scheduler.running
    except Exception:
        scheduler_running = False

    return {
        "scheduler_enabled": ENABLE_SCHEDULER,
        "scheduler_running": scheduler_running,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
