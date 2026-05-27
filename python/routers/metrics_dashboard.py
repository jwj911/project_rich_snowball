"""业务指标面板路由
==================
提供平台级聚合统计数据，支撑运营指标面板。
所有接口均为只读，不触碰核心业务写路径。
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import (
    CommentDB,
    DataIngestionRunDB,
    PriceLevelDB,
    UserDB,
    VarietyDB,
    WatchlistDB,
)
from services.circuit_breaker import get_circuit_status

router = APIRouter(prefix="/metrics", tags=["指标面板"])


def _today_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _week_start() -> datetime:
    now = datetime.now(UTC)
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


@router.get("/dashboard")
def get_dashboard_overview(
    _=Depends(get_current_user_dependency),
    db: Session = Depends(get_db),  # noqa: B008
):
    """平台总体统计。"""
    today = _today_start()
    week_start = _week_start()

    total_users = db.query(func.count(UserDB.id)).scalar() or 0
    users_today = db.query(func.count(UserDB.id)).filter(UserDB.created_at >= today).scalar() or 0
    users_this_week = (
        db.query(func.count(UserDB.id)).filter(UserDB.created_at >= week_start).scalar() or 0
    )

    total_comments = db.query(func.count(CommentDB.id)).scalar() or 0
    comments_today = (
        db.query(func.count(CommentDB.id)).filter(CommentDB.created_at >= today).scalar() or 0
    )

    total_price_levels = db.query(func.count(PriceLevelDB.id)).scalar() or 0
    total_watchlists = db.query(func.count(WatchlistDB.id)).scalar() or 0
    total_varieties = db.query(func.count(VarietyDB.id)).scalar() or 0
    active_varieties = (
        db.query(func.count(VarietyDB.id)).filter(VarietyDB.is_active.is_(True)).scalar() or 0
    )

    return {
        "users": {
            "total": total_users,
            "today": users_today,
            "this_week": users_this_week,
        },
        "comments": {
            "total": total_comments,
            "today": comments_today,
        },
        "engagement": {
            "price_levels": total_price_levels,
            "watchlists": total_watchlists,
        },
        "market": {
            "total_varieties": total_varieties,
            "active_varieties": active_varieties,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/dashboard/activity")
def get_dashboard_activity(
    _=Depends(get_current_user_dependency),
    db: Session = Depends(get_db),  # noqa: B008
):
    """最近 7 天活跃度趋势。"""
    since = datetime.now(UTC) - timedelta(days=6)
    since = since.replace(hour=0, minute=0, second=0, microsecond=0)

    # 每日新增用户
    user_rows = (
        db.query(
            func.date(UserDB.created_at).label("day"),
            func.count(UserDB.id).label("cnt"),
        )
        .filter(UserDB.created_at >= since)
        .group_by(func.date(UserDB.created_at))
        .order_by(func.date(UserDB.created_at))
        .all()
    )

    # 每日评论数
    comment_rows = (
        db.query(
            func.date(CommentDB.created_at).label("day"),
            func.count(CommentDB.id).label("cnt"),
        )
        .filter(CommentDB.created_at >= since)
        .group_by(func.date(CommentDB.created_at))
        .order_by(func.date(CommentDB.created_at))
        .all()
    )

    def _fill_days(rows):
        data = {str(r.day): r.cnt for r in rows}
        result = []
        for i in range(7):
            day = (since + timedelta(days=i)).date().isoformat()
            result.append({"date": day, "count": data.get(day, 0)})
        return result

    return {
        "new_users": _fill_days(user_rows),
        "comments": _fill_days(comment_rows),
        "since": since.date().isoformat(),
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/dashboard/collection")
def get_dashboard_collection(
    _=Depends(get_current_user_dependency),
    db: Session = Depends(get_db),  # noqa: B008
):
    """数据采集健康度。"""
    since = datetime.now(UTC) - timedelta(hours=24)

    agg = (
        db.query(
            func.count(DataIngestionRunDB.id).label("total"),
            func.sum(case((DataIngestionRunDB.status == "success", 1), else_=0)).label(
                "success"
            ),
            func.sum(case((DataIngestionRunDB.status == "failed", 1), else_=0)).label(
                "failed"
            ),
            func.avg(DataIngestionRunDB.duration_ms).label("avg_duration"),
        )
        .filter(DataIngestionRunDB.started_at >= since)
        .first()
    )

    total = agg.total or 0
    success = agg.success or 0
    failed = agg.failed or 0
    avg_duration_ms = int(agg.avg_duration) if agg.avg_duration is not None else None

    recent_runs = (
        db.query(DataIngestionRunDB)
        .filter(DataIngestionRunDB.started_at >= since)
        .order_by(DataIngestionRunDB.started_at.desc())
        .limit(10)
        .all()
    )

    circuit_status = get_circuit_status()

    return {
        "last_24h": {
            "total": total,
            "success": success,
            "failed": failed,
            "success_rate": round(success / total, 2) if total > 0 else None,
            "avg_duration_ms": avg_duration_ms,
        },
        "recent_runs": [
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
