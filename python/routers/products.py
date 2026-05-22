
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import UserDB
from schemas import ProductDetailResponse, ProductResponse
from services.domain.product_service import ProductService

router = APIRouter(prefix="/api/products", tags=["品种(兼容)"])


@router.get("", response_model=list[ProductResponse])
def get_products(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=1000),
    search: str | None = Query(None, max_length=100),
    category: str | None = Query(None, max_length=50),
    direction: str = Query("all", pattern="^(all|up|down)$"),
    sort_by: str = Query("change_percent", pattern="^(change_percent|volume|current_price)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    products, headers = ProductService(db).list_products(
        skip, limit, search, category, direction, sort_by, sort_order
    )
    for k, v in headers.items():
        response.headers[k] = v
    return products


@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product(
    product_id: int,
    comment_skip: int = Query(0, ge=0),
    comment_limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    return ProductService(db).get_product_detail(product_id, comment_skip, comment_limit)
