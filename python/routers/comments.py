
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import UserDB
from schemas import CommentCreate, CommentResponse
from services.domain.comment_service import CommentService
from services.domain.exceptions import ServiceError

router = APIRouter(prefix="/api/comments", tags=["评论"])


@router.post("", response_model=CommentResponse)
def create_comment(
    comment: CommentCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    try:
        return CommentService(db).create_comment(current_user.id, current_user, comment)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/me", response_model=list[CommentResponse])
def get_my_comments(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取当前登录用户的评论历史。"""
    return CommentService(db).get_user_comments(current_user.username, skip, limit)


@router.get("/user/{username}", response_model=list[CommentResponse], deprecated=True)
def get_user_comments(
    username: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取指定用户的评论历史（仅允许查看自己的评论）。"""
    if username != current_user.username:
        raise HTTPException(status_code=403, detail="无权查看其他用户的评论")
    return CommentService(db).get_user_comments(username, skip, limit)
