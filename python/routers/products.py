from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List
from models import ProductDB, CommentDB
from schemas import ProductResponse, ProductDetailResponse, CommentResponse
from dependencies import get_db

router = APIRouter(prefix="/api/products", tags=["品种(兼容)"])


@router.get("", response_model=List[ProductResponse])
def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    products = db.query(ProductDB).offset(skip).limit(limit).all()
    return products


@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="品种不存在")

    comments = (
        db.query(CommentDB)
        .options(joinedload(CommentDB.user))
        .filter(CommentDB.product_id == product_id)
        .order_by(CommentDB.created_at.desc())
        .limit(100)
        .all()
    )

    return {
        "product": product,
        "comments": [
            CommentResponse(
                id=c.id,
                product_id=c.product_id,
                user_id=c.user_id,
                username=c.user.username if c.user else "未知用户",
                content=c.content,
                created_at=c.created_at
            ) for c in comments
        ]
    }
