"""RSS 新闻抓取服务。

基于 feedparser 解析 RSS/Atom 订阅源，将文章写入 news_articles 表。
去重策略：同一 source_id + url 不重复入库。

安全加固：
- 禁止非 HTTP(S) scheme 和内网地址
- 使用 httpx 带显式超时抓取，避免慢源阻塞
- 重定向也经过安全检查
"""

import ipaddress
import logging
from datetime import UTC, datetime
from time import mktime
from urllib.parse import urlparse

import feedparser
import httpx
from sqlalchemy.orm import Session

from models import NewsArticleDB, NewsSourceDB, SessionLocal
from services.alert_events import create_news_alert_for_article

logger = logging.getLogger(__name__)

# RSS 抓取超时（秒）
_RSS_FETCH_TIMEOUT = 10.0
_RSS_MAX_REDIRECTS = 3


def _is_safe_url(url: str) -> bool:
    """检查 URL 是否安全：禁止非 HTTP(S) scheme 和内网/本地地址。"""
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    hostname_lower = hostname.lower()
    if hostname_lower in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # 不是 IP 地址，是域名，放行
        pass
    else:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False

    return True


def _raise_on_unsafe_redirect(request: httpx.Request) -> None:
    """httpx 事件钩子：重定向目标不安全时阻断。"""
    if not _is_safe_url(str(request.url)):
        raise httpx.RequestError(f"Redirect to unsafe URL blocked: {request.url}")


def _fetch_rss_content(url: str) -> str:
    """使用 httpx 安全抓取 RSS 内容，返回 XML 字符串。"""
    with httpx.Client(
        timeout=_RSS_FETCH_TIMEOUT,
        follow_redirects=True,
        max_redirects=_RSS_MAX_REDIRECTS,
        event_hooks={"request": [_raise_on_unsafe_redirect]},
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


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
    # SSRF 防护：拒绝不安全 URL
    if not _is_safe_url(source.url):
        logger.warning(
            "rss_url_unsafe",
            extra={"source_id": source.id, "url": source.url},
        )
        source.fetch_error_count += 1
        db.commit()
        return 0

    try:
        content = _fetch_rss_content(source.url)
        parsed = feedparser.parse(content)
    except Exception as exc:
        logger.warning(
            "rss_fetch_failed",
            extra={"source_id": source.id, "url": source.url, "error": str(exc)},
        )
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
            db.query(NewsArticleDB.id).filter(NewsArticleDB.source_id == source.id, NewsArticleDB.url == url).first()
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
        db.flush()
        create_news_alert_for_article(db, article)
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


def fetch_source_background(source_id: int) -> None:
    """在后台执行单个 RSS 源抓取。

    供 API 端点通过 FastAPI BackgroundTasks 调用，避免阻塞 HTTP 响应。
    函数内部自行创建数据库会话，不继承调用方 session。
    """
    db = SessionLocal()
    try:
        source = db.get(NewsSourceDB, source_id)
        if source is None:
            logger.warning("rss_background_source_not_found", extra={"source_id": source_id})
            return
        if not source.is_enabled:
            logger.info("rss_background_source_disabled", extra={"source_id": source_id})
            return
        fetch_source(source, db)
    except Exception:
        logger.exception("rss_background_source_failed", extra={"source_id": source_id})
    finally:
        db.close()


def fetch_all_enabled_sources_background() -> None:
    """在后台执行所有启用 RSS 源的抓取。

    供 API 端点通过 FastAPI BackgroundTasks 调用，避免阻塞 HTTP 响应。
    函数内部自行创建数据库会话，不继承调用方 session。
    """
    db = SessionLocal()
    try:
        fetch_all_enabled_sources(db)
    except Exception:
        logger.exception("rss_background_fetch_all_failed")
    finally:
        db.close()
