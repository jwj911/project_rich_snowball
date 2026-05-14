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
    """返回系统就绪状态。任一依赖异常返回 503。"""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    cache_stats = get_cache_stats()
    scheduler_ok = ENABLE_SCHEDULER

    # API 进程和 worker 进程分离：数据库可用即 ready，scheduler 仅作为信息状态
    ready = db_ok

    if not ready:
        raise HTTPException(
            status_code=503,
            detail={
                "ready": False,
                "db": db_ok,
                "cache": cache_stats,
                "scheduler": scheduler_ok,
            },
        )

    return {
        "ready": True,
        "db": db_ok,
        "cache": cache_stats,
        "scheduler": scheduler_ok,
        "engine": get_engine_info(),
    }
