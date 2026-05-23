
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import UserDB
from schemas import (
    MessageResponse,
    PriceLevelBatchCreate,
    PriceLevelBatchResponse,
    PriceLevelCreate,
    PriceLevelResponse,
    PriceLevelUpdate,
)
from services.domain.exceptions import ConflictError, ForbiddenError, NotFoundError
from services.domain.price_level_service import PriceLevelService

router = APIRouter(prefix="/api/price-levels", tags=["价位标注"])


@router.get("", response_model=list[PriceLevelResponse])
def list_price_levels(
    variety_id: int | None = Query(None),
    type: str | None = Query(None, pattern=r"^(support|resistance)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    items = PriceLevelService.list_price_levels(db, current_user.id, variety_id, type, skip=skip, limit=limit)
    return [PriceLevelResponse.model_validate(i) for i in items]


@router.post("", response_model=PriceLevelResponse)
def create_price_level(
    item: PriceLevelCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    try:
        pl = PriceLevelService.create_price_level(db, current_user.id, item)
    except (NotFoundError, ConflictError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return PriceLevelResponse.model_validate(pl)


@router.put("/{price_level_id}", response_model=PriceLevelResponse)
def update_price_level(
    price_level_id: int,
    item: PriceLevelUpdate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    try:
        pl = PriceLevelService.update_price_level(db, current_user.id, price_level_id, item)
    except (NotFoundError, ForbiddenError, ConflictError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return PriceLevelResponse.model_validate(pl)


@router.delete("/{price_level_id}", response_model=MessageResponse)
def delete_price_level(
    price_level_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    try:
        PriceLevelService.delete_price_level(db, current_user.id, price_level_id)
    except (NotFoundError, ForbiddenError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return {"detail": "已删除"}


@router.post("/batch", response_model=PriceLevelBatchResponse)
def create_price_levels_batch(
    body: PriceLevelBatchCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    success_orm, failed = PriceLevelService.create_price_levels_batch(
        db, current_user.id, body
    )
    success = [PriceLevelResponse.model_validate(pl) for pl in success_orm]
    return PriceLevelBatchResponse(
        success=success,
        failed=failed,
        created_count=len(success),
        failed_count=len(failed),
    )
