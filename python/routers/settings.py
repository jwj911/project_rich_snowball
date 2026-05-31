"""用户偏好设置路由
==================
提供当前登录用户的偏好设置查询与更新。
所有接口均为用户级隔离，只能操作自己的偏好。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import UserDB, UserPreferenceDB
from schemas import UserPreferenceResponse, UserPreferenceUpdate

router = APIRouter(prefix="/api/settings", tags=["设置"])


def _get_or_create_preference(db: Session, user_id: int) -> UserPreferenceDB:
    """获取用户偏好；不存在时自动创建默认值。"""
    pref = db.query(UserPreferenceDB).filter(UserPreferenceDB.user_id == user_id).first()
    if pref is None:
        pref = UserPreferenceDB(user_id=user_id)
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref


@router.get("", response_model=UserPreferenceResponse)
def get_user_settings(
    current_user: UserDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db),  # noqa: B008
):
    """获取当前用户的偏好设置。"""
    pref = _get_or_create_preference(db, current_user.id)
    return pref


@router.put("", response_model=UserPreferenceResponse)
def update_user_settings(
    update: UserPreferenceUpdate,
    current_user: UserDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db),  # noqa: B008
):
    """更新当前用户的偏好设置（Patch 语义：仅更新提供的字段）。"""
    pref = _get_or_create_preference(db, current_user.id)

    changed = False
    for field in ("theme", "polling_interval_seconds", "notifications_enabled", "language"):
        value = getattr(update, field)
        if value is not None:
            setattr(pref, field, value)
            changed = True

    if changed:
        db.commit()
        db.refresh(pref)

    return pref
