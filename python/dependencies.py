
import logging

import jwt
from fastapi import Depends, Header, HTTPException
from jwt.exceptions import PyJWTError
from sqlalchemy.orm import Session

from config import ALGORITHM
from config import SECRET_KEY as _SECRET_KEY
from models import SessionLocal, UserDB

SECRET_KEY: str = _SECRET_KEY

logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(token: str, db: Session) -> UserDB | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return db.query(UserDB).filter(UserDB.id == int(user_id)).first()
    except PyJWTError as e:
        logger.warning(f"JWT decode failed: {e}")
        return None
    except ValueError as e:
        logger.error(f"Unexpected error in get_current_user: {e}")
        return None


def get_current_user_dependency(
    authorization: str = Header(None),
    db: Session = Depends(get_db),  # noqa: B008
) -> UserDB:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization.replace("Bearer ", "")
    user = get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="无效的 token")
    return user


def get_current_user_from_token(token: str, db: Session) -> UserDB:
    """供 SSE 等无法使用标准 Header 的场景使用。"""
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    user = get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="无效的 token")
    return user
