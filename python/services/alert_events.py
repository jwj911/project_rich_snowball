"""Alert event generation and user-state helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from models import AlertEventDB, AlertEventUserStateDB, NewsArticleDB, PriceAlertDB, UserDB

NEWS_SOURCE_TYPE = "news_article"
PRICE_ALERT_SOURCE_TYPE = "price_alert"

_CRITICAL_NEWS_KEYWORDS = (
    "矿山坍塌",
    "矿难",
    "坍塌",
    "爆炸",
    "事故",
    "罢工",
    "出口禁令",
    "制裁",
    "战争",
    "冲突升级",
    "极端天气",
)

_HIGH_NEWS_KEYWORDS = (
    "fomc",
    "fed",
    "美联储",
    "利率决议",
    "议息",
    "cpi",
    "非农",
    "opec",
    "eia",
    "库存",
    "原油库存",
    "降息",
    "加息",
    "暂停出口",
    "限产",
    "减产",
)


def classify_news_alert(title: str, summary: str | None = None) -> str | None:
    """Return alert severity for a news article, or None when it is not major."""
    text = f"{title} {summary or ''}".lower()
    if any(keyword.lower() in text for keyword in _CRITICAL_NEWS_KEYWORDS):
        return "critical"
    if any(keyword.lower() in text for keyword in _HIGH_NEWS_KEYWORDS):
        return "high"
    return None


def create_news_alert_for_article(db: Session, article: NewsArticleDB) -> AlertEventDB | None:
    """Create one broadcast alert for a major news article."""
    severity = classify_news_alert(article.title, article.summary)
    if severity is None:
        return None

    existing = (
        db.query(AlertEventDB)
        .filter(
            AlertEventDB.source_type == NEWS_SOURCE_TYPE,
            AlertEventDB.source_id == article.id,
            AlertEventDB.target_scope == "broadcast",
        )
        .first()
    )
    if existing:
        return existing

    event = AlertEventDB(
        category="news",
        severity=severity,
        title=article.title,
        summary=article.summary,
        source_type=NEWS_SOURCE_TYPE,
        source_id=article.id,
        source_url=article.url,
        target_scope="broadcast",
        triggered_at=article.published_at or datetime.now(UTC),
    )
    db.add(event)
    return event


def create_market_alert_for_price_alert(
    db: Session,
    alert: PriceAlertDB,
    current_price: Decimal | float | int | None,
) -> AlertEventDB | None:
    """Create one personal market event when a price alert is triggered."""
    existing = (
        db.query(AlertEventDB)
        .filter(
            AlertEventDB.source_type == PRICE_ALERT_SOURCE_TYPE,
            AlertEventDB.source_id == alert.id,
            AlertEventDB.user_id == alert.user_id,
            AlertEventDB.target_scope == "personal",
        )
        .first()
    )
    if existing:
        return existing

    variety_name = alert.variety.name if alert.variety else f"品种 {alert.variety_id}"
    variety_symbol = alert.variety.symbol if alert.variety else ""
    direction = "高于" if alert.alert_type == "above" else "低于"
    current_text = f"，当前价 {current_price}" if current_price is not None else ""
    event = AlertEventDB(
        category="market",
        severity="high",
        title=f"{variety_name} 价格预警已触发",
        summary=f"{variety_symbol} 价格已{direction} {alert.target_price}{current_text}。",
        source_type=PRICE_ALERT_SOURCE_TYPE,
        source_id=alert.id,
        source_url=f"/products/{variety_symbol}" if variety_symbol else None,
        related_variety_id=alert.variety_id,
        user_id=alert.user_id,
        target_scope="personal",
        triggered_at=alert.triggered_at or datetime.now(UTC),
    )
    db.add(event)
    return event


def visible_alert_events_query(db: Session, user: UserDB):
    """Base query for events visible to a user with that user's state outer-joined."""
    return (
        db.query(AlertEventDB, AlertEventUserStateDB)
        .outerjoin(
            AlertEventUserStateDB,
            and_(
                AlertEventUserStateDB.event_id == AlertEventDB.id,
                AlertEventUserStateDB.user_id == user.id,
            ),
        )
        .filter(
            or_(
                AlertEventDB.target_scope == "broadcast",
                AlertEventDB.user_id == user.id,
            )
        )
    )


def get_or_create_user_state(db: Session, event_id: int, user_id: int) -> AlertEventUserStateDB:
    state = (
        db.query(AlertEventUserStateDB)
        .filter(AlertEventUserStateDB.event_id == event_id, AlertEventUserStateDB.user_id == user_id)
        .first()
    )
    if state is None:
        state = AlertEventUserStateDB(event_id=event_id, user_id=user_id)
        db.add(state)
        db.flush()
    return state
