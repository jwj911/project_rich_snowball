from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models import PriceLevelDB, WatchlistDB, CommentDB, VarietyDB, UserDB
from schemas import WorkspaceSummary, PriceLevelResponse, WatchlistResponse, CommentResponse
from dependencies import get_db, get_current_user_dependency

router = APIRouter(prefix="/api/workspace", tags=["工作区"])


@router.get("/me", response_model=WorkspaceSummary)
def get_workspace(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    user_id = current_user.id

    # price_levels
    price_levels = (
        db.query(PriceLevelDB)
        .filter(PriceLevelDB.user_id == user_id)
        .order_by(PriceLevelDB.created_at.desc())
        .all()
    )

    # watchlists with variety info
    watchlist_rows = (
        db.query(WatchlistDB)
        .filter(WatchlistDB.user_id == user_id)
        .order_by(WatchlistDB.created_at.desc())
        .all()
    )
    watchlists = []
    for w in watchlist_rows:
        variety = db.query(VarietyDB).filter(VarietyDB.id == w.variety_id).first()
        watchlists.append(WatchlistResponse(
            id=w.id,
            user_id=w.user_id,
            variety_id=w.variety_id,
            variety_symbol=variety.symbol if variety else "",
            variety_name=variety.name if variety else "",
            notes=w.notes,
            is_notified=w.is_notified,
            created_at=w.created_at
        ))

    # recent comments
    comments_rows = (
        db.query(CommentDB)
        .filter(CommentDB.user_id == user_id)
        .order_by(CommentDB.created_at.desc())
        .limit(20)
        .all()
    )
    recent_comments = []
    for c in comments_rows:
        recent_comments.append(CommentResponse(
            id=c.id,
            product_id=c.product_id,
            user_id=c.user_id,
            username=current_user.username,
            content=c.content,
            price_level_id=c.price_level_id,
            created_at=c.created_at
        ))

    return WorkspaceSummary(
        price_levels=[PriceLevelResponse.model_validate(pl) for pl in price_levels],
        watchlists=watchlists,
        recent_comments=recent_comments
    )
