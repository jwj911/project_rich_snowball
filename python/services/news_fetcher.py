"""RSS 新闻抓取服务。

基于 feedparser 解析 RSS/Atom 订阅源，将文章写入 news_articles 表。
去重策略：同一 source_id + url 不重复入库。
"""

import logging
from datetime import UTC, datetime
from time import mktime

import feedparser
from sqlalchemy.orm import Session

from models import NewsArticleDB, NewsSourceDB

logger = logging.getLogger(__name__)


def _parse_published(entry) -> datetime | None:
    """从 feedparser entry 中提取发布时间。"""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime.fromtimestamp(mktime(parsed), tz=UTC)
        except (ValueError, TypeError, OverflowError):
            pass
    return None


def _extract_summary(entry) -> str | None:
    """从 entry 中提取摘要，优先 summary，其次 description。"""
    for key in ("summary", "description", "subtitle"):
        value = entry.get(key)
        if value and isinstance(value, str) and value.strip():
            # RSS 摘要常带 HTML 标签，简单截断即可；前端展示时再做清洗
            return value.strip()[:2000]
    return None


def fetch_source(source: NewsSourceDB, db: Session) -> int:
    """抓取单个 RSS 源，返回新增文章数。

    失败时递增 source.fetch_error_count，不抛出异常（调用方决定是否上报）。
    """
    try:
        parsed = feedparser.parse(source.url)
    except Exception as exc:
        logger.warning("rss_fetch_failed", extra={"source_id": source.id, "url": source.url, "error": str(exc)})
        source.fetch_error_count += 1
        db.commit()
        return 0

    if hasattr(parsed, "bozo_exception") and parsed.bozo_exception:
        logger.warning(
            "rss_parse_warning",
            extra={"source_id": source.id, "url": source.url, "warning": str(parsed.bozo_exception)},
        )

    new_count = 0
    seen_urls: set[str] = set()
    for entry in parsed.entries:
        url = entry.get("link", "").strip()
        title = entry.get("title", "").strip()
        if not url or not title:
            continue

        # 同一批次内去重
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # 数据库去重：同一 source + url 已存在则跳过
        exists = (
            db.query(NewsArticleDB.id)
            .filter(NewsArticleDB.source_id == source.id, NewsArticleDB.url == url)
            .first()
        )
        if exists:
            continue

        article = NewsArticleDB(
            source_id=source.id,
            title=title[:300],
            summary=_extract_summary(entry),
            url=url[:500],
            published_at=_parse_published(entry),
        )
        db.add(article)
        new_count += 1

    source.last_fetched_at = datetime.now(UTC)
    if new_count > 0:
        # 成功抓取后重置错误计数
        source.fetch_error_count = 0
    db.commit()

    logger.info(
        "rss_fetch_completed",
        extra={"source_id": source.id, "url": source.url, "new_articles": new_count},
    )
    return new_count


def fetch_all_enabled_sources(db: Session) -> dict[int, int]:
    """抓取所有启用的 RSS 源，返回 {source_id: new_count}。"""
    sources = db.query(NewsSourceDB).filter(NewsSourceDB.is_enabled.is_(True)).all()
    results = {}
    for source in sources:
        results[source.id] = fetch_source(source, db)
    return results
