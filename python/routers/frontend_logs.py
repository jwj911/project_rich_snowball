"""前端监控日志端点。

接收 sentry-lite 和 web-vitals 的上报数据，写入 frontend_logs 表供后续查询和告警。
同时提供查询接口，支持 admin 全量查询和普通用户仅查询自己的日志。
"""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from dependencies import (
    get_current_user_dependency,
    get_db,
    get_optional_current_user,
)
from models import FrontendLogDB, UserDB
from schemas import FrontendLogCreate, FrontendLogResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/log", tags=["前端监控"])

# payload JSON 序列化后的最大字节数
_MAX_PAYLOAD_BYTES = 8 * 1024


def _payload_size_bytes(data: FrontendLogCreate) -> int:
    """估算 payload + meta 序列化后的字节数。"""
    try:
        return len(
            json.dumps(
                {"payload": data.payload, "meta": data.meta},
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
        )
    except (TypeError, ValueError):
        return 0


@router.post("/frontend", status_code=202)
def create_frontend_log(
    request: Request,
    data: FrontendLogCreate,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: UserDB | None = Depends(get_optional_current_user),  # noqa: B008
):
    """接收前端错误、日志和 Web Vitals 数据。

    鉴权策略：
    - 该端点允许匿名访问（未登录用户也能上报）
    - 如果请求携带有效 Authorization: Bearer token，user_id 从 token 解析
    - 客户端传入的 user_id 字段被忽略，防止伪造

    该端点不返回业务数据，仅确认接收（202 Accepted）。
    写入失败时降级为结构化日志，不向前端抛错。
    """
    # payload 大小硬限制
    if _payload_size_bytes(data) > _MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=422, detail="payload 大小超过 8KB 限制")

    # 身份归属：优先从 token 解析，忽略客户端 user_id
    effective_user_id = current_user.id if current_user else None

    meta = data.meta or {}
    try:
        db.add(
            FrontendLogDB(
                user_id=effective_user_id,
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
        # 不记录完整 payload，防止日志污染
        logger.warning(
            "frontend_log_persist_failed",
            extra={
                "log_type": data.type,
                "level": data.level,
                "url": meta.get("url"),
                "payload_size": _payload_size_bytes(data),
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
