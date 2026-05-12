from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from models import PriceLevelDB, VarietyDB, UserDB
from schemas import PriceLevelCreate, PriceLevelUpdate, PriceLevelResponse
from dependencies import get_db, get_current_user_dependency

router = APIRouter(prefix="/api/price-levels", tags=["价位标注"])


@router.get("", response_model=List[PriceLevelResponse])
def list_price_levels(
    variety_id: Optional[int] = Query(None),
    type: Optional[str] = Query(None, pattern=r"^(support|resistance)$"),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    query = db.query(PriceLevelDB).filter(PriceLevelDB.user_id == current_user.id)
    if variety_id:
        query = query.filter(PriceLevelDB.variety_id == variety_id)
    if type:
        query = query.filter(PriceLevelDB.type == type)
    items = query.order_by(PriceLevelDB.created_at.desc()).all()
    return [PriceLevelResponse.model_validate(i) for i in items]


@router.post("", response_model=PriceLevelResponse)
def create_price_level(
    item: PriceLevelCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    variety = db.query(VarietyDB).filter(VarietyDB.id == item.variety_id).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    existing = db.query(PriceLevelDB).filter(
        PriceLevelDB.user_id == current_user.id,
        PriceLevelDB.variety_id == item.variety_id,
        PriceLevelDB.type == item.type,
        PriceLevelDB.price == item.price
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="该价位标注已存在")

    pl = PriceLevelDB(
        user_id=current_user.id,
        variety_id=item.variety_id,
        type=item.type,
        price=item.price,
        note=item.note,
        source="manual"
    )
    db.add(pl)
    db.commit()
    db.refresh(pl)
    return PriceLevelResponse.model_validate(pl)


@router.put("/{price_level_id}", response_model=PriceLevelResponse)
def update_price_level(
    price_level_id: int,
    item: PriceLevelUpdate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    pl = db.query(PriceLevelDB).filter(PriceLevelDB.id == price_level_id).first()
    if not pl:
        raise HTTPException(status_code=404, detail="价位标注不存在")
    if pl.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    if item.price is not None:
        existing = db.query(PriceLevelDB).filter(
            PriceLevelDB.user_id == current_user.id,
            PriceLevelDB.variety_id == pl.variety_id,
            PriceLevelDB.type == pl.type,
            PriceLevelDB.price == item.price,
            PriceLevelDB.id != price_level_id
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="该价位标注已存在")
        pl.price = item.price
    if item.note is not None:
        pl.note = item.note

    db.commit()
    db.refresh(pl)
    return PriceLevelResponse.model_validate(pl)


@router.delete("/{price_level_id}")
def delete_price_level(
    price_level_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    pl = db.query(PriceLevelDB).filter(PriceLevelDB.id == price_level_id).first()
    if not pl:
        raise HTTPException(status_code=404, detail="价位标注不存在")
    if pl.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    db.delete(pl)
    db.commit()
    return {"detail": "已删除"}
