from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from dependencies import get_current_user_dependency, get_db
from models import CommentDB, PriceLevelDB, UserDB, WatchlistDB
from schemas import (
    CommentResponse,
    PriceLevelResponse,
    WatchlistResponse,
    WorkspaceSummary,
)

router = APIRouter(prefix="/api/workspace", tags=["工作区"])


@router.get("/me", response_model=WorkspaceSummary)
def get_workspace(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    user_id = current_user.id

    # price_levels with variety info
    price_levels_rows = (
        db.query(PriceLevelDB)
        .options(joinedload(PriceLevelDB.variety))
        .filter(PriceLevelDB.user_id == user_id)
        .order_by(PriceLevelDB.created_at.desc())
        .all()
    )
    price_levels = [
        PriceLevelResponse(
            id=pl.id,
            user_id=pl.user_id,
            variety_id=pl.variety_id,
            variety_symbol=pl.variety.symbol if pl.variety else None,
            variety_name=pl.variety.name if pl.variety else None,
            type=pl.type,
            price=pl.price,
            note=pl.note,
            source=pl.source,
            created_at=pl.created_at,
            updated_at=pl.updated_at,
        )
        for pl in price_levels_rows
    ]

    # watchlists with variety info (joinedload 避免 N+1)
    watchlist_rows = (
        db.query(WatchlistDB)
        .options(joinedload(WatchlistDB.variety))
        .filter(WatchlistDB.user_id == user_id)
        .order_by(WatchlistDB.created_at.desc())
        .all()
    )
    watchlists = []
    for w in watchlist_rows:
        watchlists.append(WatchlistResponse(
            id=w.id,
            user_id=w.user_id,
            variety_id=w.variety_id,
            variety_symbol=w.variety.symbol if w.variety else "",
            variety_name=w.variety.name if w.variety else "",
            notes=w.notes,
            is_notified=w.is_notified,
            created_at=w.created_at
        ))

    # recent comments with product info
    comments_rows = (
        db.query(CommentDB)
        .options(joinedload(CommentDB.product))
        .filter(CommentDB.user_id == user_id)
        .order_by(CommentDB.created_at.desc())
        .limit(20)
        .all()
    )
    recent_comments = [
        CommentResponse(
            id=c.id,
            product_id=c.product_id,
            product_symbol=c.product.symbol if c.product else None,
            product_name=c.product.name if c.product else None,
            user_id=c.user_id,
            username=current_user.username,
            content=c.content,
            price_level_id=c.price_level_id,
            created_at=c.created_at,
        )
        for c in comments_rows
    ]

    return WorkspaceSummary(
        price_levels=price_levels,
        watchlists=watchlists,
        recent_comments=recent_comments
    )
