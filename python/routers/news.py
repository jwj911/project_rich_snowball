"""新闻资讯端点。

提供 RSS 源管理、新闻条目查询和手动触发抓取功能。
源管理开放给普通用户（可创建/删除自己的源），内置源由系统维护。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query  # noqa: F401
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db, require_admin_user
from models import NewsArticleDB, NewsSourceDB, UserDB
from schemas import NewsArticleResponse, NewsSourceCreate, NewsSourceResponse, NewsSourceUserCreate
from services.ai_chat import summarize_article_sync
from services.news_fetcher import fetch_all_enabled_sources, fetch_source

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/news", tags=["新闻资讯"])


# ---------------------------------------------------------------------------
# 公开/用户端点
# ---------------------------------------------------------------------------

@router.get("/sources", response_model=list[NewsSourceResponse])
def list_news_sources(
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """列出所有启用的新闻源（内置源 + 当前用户自定义源）。"""
    return (
        db.query(NewsSourceDB)
        .filter(
            NewsSourceDB.is_enabled.is_(True),
            or_(
                NewsSourceDB.is_builtin.is_(True),
                NewsSourceDB.user_id == current_user.id,
            ),
        )
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


@router.post("/sources", response_model=NewsSourceResponse, status_code=201)
def create_user_news_source(
    data: NewsSourceUserCreate,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """添加自定义 RSS 新闻源（普通用户）。"""
    source = NewsSourceDB(
        name=data.name,
        url=data.url,
        category=data.category,
        user_id=current_user.id,
        is_builtin=False,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.delete("/sources/{source_id}", status_code=204)
def delete_user_news_source(
    source_id: int,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """删除 RSS 新闻源。用户只能删除自己添加的源；admin 可删除所有。"""
    source = db.get(NewsSourceDB, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="source_not_found")
    if source.is_builtin and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="builtin_source_cannot_delete")
    if source.user_id is not None and source.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="not_owner")
    db.delete(source)
    db.commit()
    return None


@router.post("/articles/{article_id}/summarize", response_model=NewsArticleResponse)
def summarize_article(
    article_id: int,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """手动为单篇文章触发 AI 摘要。"""
    article = db.get(NewsArticleDB, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="article_not_found")

    summary = summarize_article_sync(article.title, article.summary or "")
    article.ai_summary = summary
    db.commit()
    db.refresh(article)
    return article


# ---------------------------------------------------------------------------
# Admin 端点
# ---------------------------------------------------------------------------

@router.post("/sources/admin", response_model=NewsSourceResponse, status_code=201)
def create_admin_news_source(
    data: NewsSourceCreate,
    _admin=Depends(require_admin_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """添加系统内置 RSS 新闻源（admin）。"""
    source = NewsSourceDB(**data.model_dump(), is_builtin=True)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


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
