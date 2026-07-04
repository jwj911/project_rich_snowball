"""预警中心 API。"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session, joinedload

from dependencies import get_current_user_dependency, get_db
from models import AlertEventDB, AlertEventUserStateDB, UserDB
from schemas import AlertEventResponse, AlertSummaryResponse
from services.alert_events import get_or_create_user_state, visible_alert_events_query

router = APIRouter(prefix="/api/alerts", tags=["预警中心"])


def _to_response(event: AlertEventDB, state: AlertEventUserStateDB | None = None) -> AlertEventResponse:
    variety = event.related_variety
    return AlertEventResponse(
        id=event.id,
        category=event.category,
        severity=event.severity,
        title=event.title,
        summary=event.summary,
        source_type=event.source_type,
        source_id=event.source_id,
        source_url=event.source_url,
        related_variety_id=event.related_variety_id,
        related_variety_symbol=variety.symbol if variety else None,
        related_variety_name=variety.name if variety else None,
        user_id=event.user_id,
        target_scope=event.target_scope,
        triggered_at=event.triggered_at,
        created_at=event.created_at,
        read_at=state.read_at if state else None,
        dismissed_at=state.dismissed_at if state else None,
    )


def _visible_event_or_404(db: Session, user: UserDB, event_id: int) -> AlertEventDB:
    event = (
        db.query(AlertEventDB)
        .filter(
            AlertEventDB.id == event_id,
            or_(AlertEventDB.target_scope == "broadcast", AlertEventDB.user_id == user.id),
        )
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="alert_event_not_found")
    return event


@router.get("/events", response_model=list[AlertEventResponse])
def list_alert_events(
    category: str | None = Query(None, pattern=r"^(news|market|calendar)$"),
    severity: str | None = Query(None, pattern=r"^(low|medium|high|critical)$"),
    unread_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    query = visible_alert_events_query(db, current_user).options(joinedload(AlertEventDB.related_variety))
    if category:
        query = query.filter(AlertEventDB.category == category)
    if severity:
        query = query.filter(AlertEventDB.severity == severity)

    query = query.filter(
        or_(
            AlertEventUserStateDB.dismissed_at.is_(None),
            AlertEventUserStateDB.id.is_(None),
        )
    )
    if unread_only:
        query = query.filter(
            or_(
                AlertEventUserStateDB.read_at.is_(None),
                AlertEventUserStateDB.id.is_(None),
            )
        )

    rows = query.order_by(desc(AlertEventDB.triggered_at), desc(AlertEventDB.created_at)).offset(skip).limit(limit).all()
    return [_to_response(event, state) for event, state in rows]


@router.get("/summary", response_model=AlertSummaryResponse)
def get_alert_summary(
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    query = visible_alert_events_query(db, current_user).filter(
        or_(
            AlertEventUserStateDB.dismissed_at.is_(None),
            AlertEventUserStateDB.id.is_(None),
        )
    )
    rows = query.with_entities(AlertEventDB.category, AlertEventUserStateDB.read_at).all()
    unread_count = sum(1 for _category, read_at in rows if read_at is None)
    news_count = sum(1 for category, _read_at in rows if category == "news")
    market_count = sum(1 for category, _read_at in rows if category == "market")
    return AlertSummaryResponse(unread_count=unread_count, news_count=news_count, market_count=market_count)


@router.put("/events/{event_id}/read", response_model=AlertEventResponse)
def mark_alert_event_read(
    event_id: int,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    event = _visible_event_or_404(db, current_user, event_id)
    state = get_or_create_user_state(db, event.id, current_user.id)
    if state.read_at is None:
        state.read_at = datetime.now(UTC)
    db.commit()
    db.refresh(event)
    db.refresh(state)
    return _to_response(event, state)


@router.put("/events/{event_id}/dismiss", response_model=AlertEventResponse)
def dismiss_alert_event(
    event_id: int,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    event = _visible_event_or_404(db, current_user, event_id)
    state = get_or_create_user_state(db, event.id, current_user.id)
    now = datetime.now(UTC)
    if state.read_at is None:
        state.read_at = now
    state.dismissed_at = now
    db.commit()
    db.refresh(event)
    db.refresh(state)
    return _to_response(event, state)
