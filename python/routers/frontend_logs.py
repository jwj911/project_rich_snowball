"""前端监控日志端点。

接收 sentry-lite 和 web-vitals 的上报数据，写入 frontend_logs 表供后续查询和告警。
同时提供查询接口，支持 admin 全量查询和普通用户仅查询自己的日志。
"""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import FrontendLogDB, UserDB
from schemas import FrontendLogCreate, FrontendLogResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/log", tags=["前端监控"])


@router.post("/frontend", status_code=202)
def create_frontend_log(data: FrontendLogCreate, db: Session = Depends(get_db)):  # noqa: B008
    """接收前端错误、日志和 Web Vitals 数据。

    该端点不返回业务数据，仅确认接收（202 Accepted）。
    写入失败时降级为结构化日志，不向前端抛错。
    """
    meta = data.meta or {}
    try:
        db.add(
            FrontendLogDB(
                user_id=data.user_id,
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


@router.get("/frontend", response_model=list[FrontendLogResponse])
def list_frontend_logs(
    response: Response,
    type: str | None = Query(None, max_length=20, description="日志类型筛选"),
    level: str | None = Query(None, max_length=20, description="日志级别筛选"),
    start_time: str | None = Query(None, description="起始时间（ISO 8601）"),
    end_time: str | None = Query(None, description="结束时间（ISO 8601）"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """查询前端日志。

    权限策略：
    - admin 用户可查询全部日志
    - 普通用户只能查询与自己 user_id 关联的日志
    """
    q = db.query(FrontendLogDB)

    # 权限过滤
    if current_user.role != "admin":
        q = q.filter(FrontendLogDB.user_id == current_user.id)

    if type:
        q = q.filter(FrontendLogDB.log_type == type)
    if level:
        q = q.filter(FrontendLogDB.level == level)
    if start_time:
        try:
            # URL 查询参数中的 + 可能被解码为空格，先还原
            start_time = start_time.replace(" ", "+")
            parsed = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            q = q.filter(FrontendLogDB.created_at >= parsed)
        except ValueError:
            pass
    if end_time:
        try:
            # URL 查询参数中的 + 可能被解码为空格，先还原
            end_time = end_time.replace(" ", "+")
            parsed = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            q = q.filter(FrontendLogDB.created_at <= parsed)
        except ValueError:
            pass

    total = q.with_entities(func.count(FrontendLogDB.id)).scalar() or 0

    results = (
        q.order_by(desc(FrontendLogDB.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )

    response.headers["X-Total-Count"] = str(total)
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "type": r.log_type,
            "level": r.level,
            "url": r.url,
            "user_agent": r.user_agent,
            "release": r.release,
            "environment": r.environment,
            "payload": json.loads(r.payload_json) if r.payload_json else {},
            "created_at": r.created_at,
        }
        for r in results
    ]
