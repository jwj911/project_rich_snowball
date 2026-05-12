from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from models import WatchlistDB, VarietyDB, UserDB
from schemas import WatchlistCreate, WatchlistUpdate, WatchlistResponse
from dependencies import get_db, get_current_user_dependency

router = APIRouter(prefix="/api/watchlists", tags=["自选"])


@router.get("", response_model=List[WatchlistResponse])
def list_watchlists(
    variety_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    query = db.query(WatchlistDB).filter(WatchlistDB.user_id == current_user.id)
    if variety_id:
        query = query.filter(WatchlistDB.variety_id == variety_id)
    items = query.order_by(WatchlistDB.created_at.desc()).all()

    result = []
    for w in items:
        variety = db.query(VarietyDB).filter(VarietyDB.id == w.variety_id).first()
        result.append(WatchlistResponse(
            id=w.id,
            user_id=w.user_id,
            variety_id=w.variety_id,
            variety_symbol=variety.symbol if variety else "",
            variety_name=variety.name if variety else "",
            notes=w.notes,
            is_notified=w.is_notified,
            created_at=w.created_at
        ))
    return result


@router.post("", response_model=WatchlistResponse)
def create_watchlist(
    item: WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    variety = db.query(VarietyDB).filter(VarietyDB.id == item.variety_id).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    existing = db.query(WatchlistDB).filter(
        WatchlistDB.user_id == current_user.id,
        WatchlistDB.variety_id == item.variety_id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="该品种已在自选列表中")

    w = WatchlistDB(
        user_id=current_user.id,
        variety_id=item.variety_id,
        notes=item.notes,
        is_notified=False
    )
    db.add(w)
    db.commit()
    db.refresh(w)

    return WatchlistResponse(
        id=w.id,
        user_id=w.user_id,
        variety_id=w.variety_id,
        variety_symbol=variety.symbol,
        variety_name=variety.name,
        notes=w.notes,
        is_notified=w.is_notified,
        created_at=w.created_at
    )


@router.put("/{watchlist_id}", response_model=WatchlistResponse)
def update_watchlist(
    watchlist_id: int,
    item: WatchlistUpdate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    w = db.query(WatchlistDB).filter(WatchlistDB.id == watchlist_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="自选记录不存在")
    if w.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    if item.notes is not None:
        w.notes = item.notes
    if item.is_notified is not None:
        w.is_notified = item.is_notified

    db.commit()
    db.refresh(w)

    variety = db.query(VarietyDB).filter(VarietyDB.id == w.variety_id).first()
    return WatchlistResponse(
        id=w.id,
        user_id=w.user_id,
        variety_id=w.variety_id,
        variety_symbol=variety.symbol if variety else "",
        variety_name=variety.name if variety else "",
        notes=w.notes,
        is_notified=w.is_notified,
        created_at=w.created_at
    )


@router.delete("/{watchlist_id}")
def delete_watchlist(
    watchlist_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    w = db.query(WatchlistDB).filter(WatchlistDB.id == watchlist_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="自选记录不存在")
    if w.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    db.delete(w)
    db.commit()
    return {"detail": "已删除"}
