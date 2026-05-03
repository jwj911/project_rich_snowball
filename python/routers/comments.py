from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List
from models import CommentDB, ProductDB, UserDB
from schemas import CommentCreate, CommentResponse
from dependencies import get_db, get_current_user

router = APIRouter(prefix="/api/comments", tags=["评论"])


@router.post("", response_model=CommentResponse)
def create_comment(comment: CommentCreate, authorization: str = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请登录后评论")
    token = authorization.replace("Bearer ", "")
    user = get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="无效的 token")

    product = db.query(ProductDB).filter(ProductDB.id == comment.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="品种不存在")

    db_comment = CommentDB(
        product_id=comment.product_id,
        user_id=user.id,
        content=comment.content
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)

    return CommentResponse(
        id=db_comment.id,
        product_id=db_comment.product_id,
        user_id=db_comment.user_id,
        username=user.username,
        content=db_comment.content,
        created_at=db_comment.created_at
    )


@router.get("/user/{username}", response_model=List[CommentResponse])
def get_user_comments(username: str, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    comments = db.query(CommentDB).filter(CommentDB.user_id == user.id)\
        .order_by(CommentDB.created_at.desc()).all()

    return [
        CommentResponse(
            id=c.id,
            product_id=c.product_id,
            user_id=c.user_id,
            username=user.username,
            content=c.content,
            created_at=c.created_at
        ) for c in comments
    ]
