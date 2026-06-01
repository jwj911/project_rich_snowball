"""新闻资讯端点。

提供 RSS 源管理、新闻条目查询和手动触发抓取功能。
源管理为 admin 权限；新闻阅读为所有登录用户。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query  # noqa: F401
from sqlalchemy import desc
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db, require_admin_user
from models import NewsArticleDB, NewsSourceDB
from schemas import NewsArticleResponse, NewsSourceCreate, NewsSourceResponse
from services.news_fetcher import fetch_all_enabled_sources, fetch_source

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/news", tags=["新闻资讯"])


# ---------------------------------------------------------------------------
# 公开/用户端点
# ---------------------------------------------------------------------------

@router.get("/sources", response_model=list[NewsSourceResponse])
def list_news_sources(
    current_user=Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """列出所有启用的新闻源。"""
    return (
        db.query(NewsSourceDB)
        .filter(NewsSourceDB.is_enabled.is_(True))
        .order_by(NewsSourceDB.created_at.desc())
        .all()
    )


@router.get("/articles", response_model=list[NewsArticleResponse])
def list_news_articles(
    source_id: int | None = Query(None, description="按来源筛选"),
    q: str | None = Query(None, max_length=100, description="标题搜索关键词"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """查询新闻条目，按发布时间倒序。"""
    query = db.query(NewsArticleDB)
    if source_id:
        query = query.filter(NewsArticleDB.source_id == source_id)
    if q:
        query = query.filter(NewsArticleDB.title.ilike(f"%{q}%"))
    return (
        query.order_by(desc(NewsArticleDB.published_at))
        .offset(skip)
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Admin 端点
# ---------------------------------------------------------------------------

@router.post("/sources", response_model=NewsSourceResponse, status_code=201)
def create_news_source(
    data: NewsSourceCreate,
    _admin=Depends(require_admin_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """添加 RSS 新闻源（admin）。"""
    source = NewsSourceDB(**data.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.delete("/sources/{source_id}", status_code=204)
def delete_news_source(
    source_id: int,
    _admin=Depends(require_admin_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """删除 RSS 新闻源及其关联文章（admin）。"""
    source = db.get(NewsSourceDB, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="source_not_found")
    db.delete(source)
    db.commit()
    return None


@router.post("/fetch", response_model=dict[int, int])
def trigger_news_fetch(
    _admin=Depends(require_admin_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """手动触发所有启用源的 RSS 抓取（admin），返回 {source_id: new_count}。"""
    return fetch_all_enabled_sources(db)


@router.post("/sources/{source_id}/fetch", response_model=int)
def trigger_single_source_fetch(
    source_id: int,
    _admin=Depends(require_admin_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """手动触发单个源的 RSS 抓取（admin），返回新增文章数。"""
    source = db.get(NewsSourceDB, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="source_not_found")
    return fetch_source(source, db)
