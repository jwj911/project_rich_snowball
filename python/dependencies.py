from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Optional

from models import SessionLocal, UserDB
from config import SECRET_KEY, ALGORITHM
import jwt
from jwt.exceptions import PyJWTError
import logging

logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(token: str, db: Session) -> Optional[UserDB]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return db.query(UserDB).filter(UserDB.id == int(user_id)).first()
    except PyJWTError as e:
        logger.warning(f"JWT decode failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_current_user: {e}")
        return None


def get_current_user_dependency(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
) -> UserDB:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization.replace("Bearer ", "")
    user = get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="无效的 token")
    return user
