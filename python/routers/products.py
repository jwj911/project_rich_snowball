from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from models import ProductDB, CommentDB
from schemas import ProductResponse, ProductDetailResponse, CommentResponse
from dependencies import get_db

router = APIRouter(prefix="/api/products", tags=["品种(兼容)"])


@router.get("", response_model=List[ProductResponse])
def get_products(db: Session = Depends(get_db)):
    products = db.query(ProductDB).all()
    return products


@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="品种不存在")

    comments = db.query(CommentDB).filter(CommentDB.product_id == product_id)\
        .order_by(CommentDB.created_at.desc()).all()

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
