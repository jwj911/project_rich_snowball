
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
from services.metrics import price_level_operations_total

router = APIRouter(prefix="/api/price-levels", tags=["价位标注"])


@router.get("", response_model=list[PriceLevelResponse])
def list_price_levels(
    variety_id: int | None = Query(None),
    type: str | None = Query(None, pattern=r"^(support|resistance)$"),
    scope: str | None = Query(None, pattern=r"^(continuous|main|contract)$"),
    contract_id: int | None = Query(None, ge=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    items = PriceLevelService(db).list_price_levels(
        current_user.id, variety_id, type, scope, contract_id, skip=skip, limit=limit
    )
    price_level_operations_total.labels(action="list", result="success").inc()
    return [PriceLevelResponse.model_validate(i) for i in items]


@router.post("", response_model=PriceLevelResponse, status_code=201)
def create_price_level(
    item: PriceLevelCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    try:
        pl = PriceLevelService(db).create_price_level(current_user.id, item)
        price_level_operations_total.labels(action="create", result="success").inc()
    except (NotFoundError, ConflictError) as exc:
        price_level_operations_total.labels(action="create", result="failure").inc()
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
        pl = PriceLevelService(db).update_price_level(current_user.id, price_level_id, item)
        price_level_operations_total.labels(action="update", result="success").inc()
    except (NotFoundError, ForbiddenError, ConflictError) as exc:
        price_level_operations_total.labels(action="update", result="failure").inc()
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return PriceLevelResponse.model_validate(pl)


@router.delete("/{price_level_id}", response_model=MessageResponse)
def delete_price_level(
    price_level_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    try:
        PriceLevelService(db).delete_price_level(current_user.id, price_level_id)
        price_level_operations_total.labels(action="delete", result="success").inc()
    except (NotFoundError, ForbiddenError) as exc:
        price_level_operations_total.labels(action="delete", result="failure").inc()
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return {"detail": "已删除"}


@router.post("/batch", response_model=PriceLevelBatchResponse)
def create_price_levels_batch(
    body: PriceLevelBatchCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    success_orm, failed = PriceLevelService(db).create_price_levels_batch(
        current_user.id, body
    )
    price_level_operations_total.labels(action="batch_create", result="success").inc()
    success = [PriceLevelResponse.model_validate(pl) for pl in success_orm]
    return PriceLevelBatchResponse(
        success=success,
        failed=failed,
        created_count=len(success),
        failed_count=len(failed),
    )
