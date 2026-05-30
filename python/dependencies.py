
import logging

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request
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
    request: Request,
    authorization: str = Header(None),
    access_token: str = Cookie(None),
    db: Session = Depends(get_db),  # noqa: B008
) -> UserDB:
    """通用鉴权依赖：优先 Authorization header，GET/HEAD 可回退到 cookie。

    CSRF 防护：POST/PUT/PATCH/DELETE 必须显式携带 Authorization header，
    不接受 cookie 中的 access_token，防止跨站请求伪造。
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    elif access_token and request.method in ("GET", "HEAD"):
        token = access_token

    if not token:
        raise HTTPException(status_code=401, detail="未登录")
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


def require_admin_user(
    request: Request,
    authorization: str = Header(None),
    access_token: str = Cookie(None),
    db: Session = Depends(get_db),  # noqa: B008
) -> UserDB:
    """管理员鉴权依赖：仅允许 role=admin 的用户访问。

    复用 get_current_user_dependency 的 token 提取逻辑，
    额外校验 user.role == 'admin'。
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    elif access_token and request.method in ("GET", "HEAD"):
        token = access_token

    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    user = get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="无效的 token")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="无权访问")
    return user
