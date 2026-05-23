
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import UserDB
from schemas import MessageResponse, WatchlistCreate, WatchlistResponse, WatchlistUpdate
from services.domain.exceptions import ConflictError, ForbiddenError, NotFoundError
from services.domain.watchlist_service import WatchlistService

router = APIRouter(prefix="/api/watchlists", tags=["自选"])


@router.get("", response_model=list[WatchlistResponse])
def list_watchlists(
    variety_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    items = WatchlistService.list_watchlists(db, current_user.id, variety_id, skip=skip, limit=limit)
    return [
        WatchlistResponse(
            id=w.id,
            user_id=w.user_id,
            variety_id=w.variety_id,
            variety_symbol=w.variety.symbol if w.variety else "",
            variety_name=w.variety.name if w.variety else "",
            notes=w.notes,
            is_notified=w.is_notified,
            created_at=w.created_at,
        )
        for w in items
    ]


@router.post("", response_model=WatchlistResponse)
def create_watchlist(
    item: WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    try:
        w = WatchlistService.create_watchlist(db, current_user.id, item)
    except (NotFoundError, ConflictError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return WatchlistResponse(
        id=w.id,
        user_id=w.user_id,
        variety_id=w.variety_id,
        variety_symbol=w.variety.symbol if w.variety else "",
        variety_name=w.variety.name if w.variety else "",
        notes=w.notes,
        is_notified=w.is_notified,
        created_at=w.created_at,
    )


@router.put("/{watchlist_id}", response_model=WatchlistResponse)
def update_watchlist(
    watchlist_id: int,
    item: WatchlistUpdate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    try:
        w = WatchlistService.update_watchlist(db, current_user.id, watchlist_id, item)
    except (NotFoundError, ForbiddenError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return WatchlistResponse(
        id=w.id,
        user_id=w.user_id,
        variety_id=w.variety_id,
        variety_symbol=w.variety.symbol if w.variety else "",
        variety_name=w.variety.name if w.variety else "",
        notes=w.notes,
        is_notified=w.is_notified,
        created_at=w.created_at,
    )


@router.delete("/{watchlist_id}", response_model=MessageResponse)
def delete_watchlist(
    watchlist_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    try:
        WatchlistService.delete_watchlist(db, current_user.id, watchlist_id)
    except (NotFoundError, ForbiddenError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return {"detail": "已删除"}
