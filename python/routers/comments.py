from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from models import CommentDB, ProductDB, UserDB, PriceLevelDB
from schemas import CommentCreate, CommentResponse
from dependencies import get_db, get_current_user, get_current_user_dependency

router = APIRouter(prefix="/api/comments", tags=["评论"])


@router.post("", response_model=CommentResponse)
def create_comment(
    comment: CommentCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    product = db.query(ProductDB).filter(ProductDB.id == comment.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="品种不存在")

    if comment.price_level_id:
        pl = db.query(PriceLevelDB).filter(
            PriceLevelDB.id == comment.price_level_id,
            PriceLevelDB.user_id == current_user.id
        ).first()
        if not pl:
            raise HTTPException(status_code=404, detail="关联的价位标注不存在")

    db_comment = CommentDB(
        product_id=comment.product_id,
        user_id=current_user.id,
        price_level_id=comment.price_level_id,
        content=comment.content
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)

    return CommentResponse(
        id=db_comment.id,
        product_id=db_comment.product_id,
        user_id=db_comment.user_id,
        username=current_user.username,
        content=db_comment.content,
        price_level_id=db_comment.price_level_id,
        created_at=db_comment.created_at
    )


@router.get("/user/{username}", response_model=List[CommentResponse])
def get_user_comments(
    username: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    user = db.query(UserDB).filter(UserDB.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    comments = (
        db.query(CommentDB)
        .filter(CommentDB.user_id == user.id)
        .order_by(CommentDB.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [
        CommentResponse(
            id=c.id,
            product_id=c.product_id,
            user_id=c.user_id,
            username=user.username,
            content=c.content,
            price_level_id=c.price_level_id,
            created_at=c.created_at
        ) for c in comments
    ]
