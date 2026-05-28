"""前端监控日志接收端点。

接收 sentry-lite 和 web-vitals 的上报数据，写入 frontend_logs 表供后续查询和告警。
"""

import json
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from dependencies import get_db
from models import FrontendLogDB
from schemas import FrontendLogCreate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/log", tags=["前端监控"])


@router.post("/frontend", status_code=202)
def create_frontend_log(data: FrontendLogCreate, db: Session = Depends(get_db)):
    """接收前端错误、日志和 Web Vitals 数据。

    该端点不返回业务数据，仅确认接收（202 Accepted）。
    写入失败时降级为结构化日志，不向前端抛错。
    """
    meta = data.meta or {}
    try:
        db.add(
            FrontendLogDB(
                log_type=data.type,
                level=data.level,
                url=meta.get("url"),
                user_agent=meta.get("ua"),
                release=meta.get("release"),
                environment=meta.get("environment"),
                payload_json=json.dumps(data.payload, ensure_ascii=False, default=str),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        # 降级：写入失败时记录到服务端日志，避免丢失关键前端错误
        logger.warning(
            "frontend_log_persist_failed",
            extra={
                "log_type": data.type,
                "level": data.level,
                "url": meta.get("url"),
                "payload": data.payload,
            },
        )
    return {"ok": True}
