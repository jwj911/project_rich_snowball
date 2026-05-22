from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from config import ACCESS_TOKEN_EXPIRE_MINUTES, ENV, REFRESH_TOKEN_EXPIRE_DAYS
from dependencies import get_current_user_dependency, get_db
from middleware.rate_limit import _get_client_ip
from models import RefreshTokenDB, UserDB
from schemas import (
    MessageResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from utils import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["认证"])
REFRESH_TOKEN_COOKIE_NAME = "refresh_token"

# 简单内存限流：IP -> [(timestamp, count)]
_rate_limit_store: dict[str, list[datetime]] = {}
_rate_limit_lock = Lock()


def clear_rate_limit_store():
    """清空限流计数器，供测试使用。"""
    with _rate_limit_lock:
        _rate_limit_store.clear()

_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_REQUESTS = 10

# 恒定时间比较用的 dummy hash（有效 bcrypt hash，确保计算耗时与真实 hash 接近）
_DUMMY_HASH = "$2b$12$cPBBd9OrTIWiStqUdReQ9OJxJiPTUD.ux8DZ7UN8b4sEbmKn5jXL."


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Set the JS-inaccessible refresh token cookie."""
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=ENV == "production",
        samesite="lax",
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        httponly=True,
        secure=ENV == "production",
        samesite="lax",
        path="/api/auth",
    )


def _extract_refresh_token(request: Request, body: RefreshTokenRequest | None) -> str:
    """Read refresh token from HttpOnly cookie, with legacy body fallback."""
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
    if refresh_token:
        return refresh_token
    if body and body.refresh_token:
        return body.refresh_token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token 无效或已过期",
    )


def _check_rate_limit(client_ip: str) -> bool:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=_RATE_LIMIT_WINDOW_SECONDS)

    with _rate_limit_lock:
        timestamps = _rate_limit_store.get(client_ip, [])
        # 清理过期记录
        timestamps = [ts for ts in timestamps if ts > window_start]
        if len(timestamps) >= _RATE_LIMIT_MAX_REQUESTS:
            _rate_limit_store[client_ip] = timestamps
            return False
        timestamps.append(now)
        _rate_limit_store[client_ip] = timestamps
        return True


@router.post("/register", response_model=UserResponse)
def register(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    client_ip = _get_client_ip(request)
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    existing = db.query(UserDB).filter(
        (UserDB.username == user.username) | (UserDB.email == user.email)
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名或邮箱已存在")

    db_user = UserDB(
        username=user.username,
        email=user.email,
        password_hash=hash_password(user.password)
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    client_ip = _get_client_ip(request)
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()

    # 恒定时间比较：无论用户是否存在，都执行一次 verify_password
    password_hash: str = str(user.password_hash) if user else _DUMMY_HASH
    password_ok = verify_password(form_data.password, password_hash)

    if not user or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    access_token = create_access_token(data={"sub": str(user.id)})

    # 生成 refresh token 并持久化
    raw_refresh = generate_refresh_token()
    refresh_hash = hash_refresh_token(raw_refresh)
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    rt = RefreshTokenDB(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=expires_at,
        device_info=request.headers.get("user-agent", "")[:200],
    )
    db.add(rt)
    db.commit()
    _set_refresh_cookie(response, raw_refresh)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": None,
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh_token(
    request: Request,
    response: Response,
    body: RefreshTokenRequest | None = None,
    db: Session = Depends(get_db),
):
    """用 HttpOnly refresh cookie 换取新的 access token（refresh token 轮转）。

    安全行为：
    1. 验证当前 refresh token
    2. 生成新的 refresh token 并持久化
    3. 吊销旧的 refresh token（防止重放攻击）
    4. 通过 HttpOnly cookie 返回新的 refresh token
    """
    raw_refresh = _extract_refresh_token(request, body)
    token_hash = hash_refresh_token(raw_refresh)
    rt = db.query(RefreshTokenDB).filter(
        RefreshTokenDB.token_hash == token_hash,
        RefreshTokenDB.revoked_at.is_(None),
        RefreshTokenDB.expires_at > datetime.now(timezone.utc),
    ).first()

    if not rt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token 无效或已过期"
        )

    # Refresh token 轮转：生成新 token，吊销旧 token
    new_raw_refresh = generate_refresh_token()
    new_refresh_hash = hash_refresh_token(new_raw_refresh)
    new_expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    new_rt = RefreshTokenDB(
        user_id=rt.user_id,
        token_hash=new_refresh_hash,
        expires_at=new_expires_at,
        device_info=rt.device_info,
    )
    db.add(new_rt)
    rt.revoked_at = datetime.now(timezone.utc)
    db.commit()

    access_token = create_access_token(data={"sub": str(rt.user_id)})
    _set_refresh_cookie(response, new_raw_refresh)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    body: RefreshTokenRequest | None = None,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """吊销当前 refresh token（logout）。"""
    raw_refresh = _extract_refresh_token(request, body)
    token_hash = hash_refresh_token(raw_refresh)
    rt = db.query(RefreshTokenDB).filter(
        RefreshTokenDB.token_hash == token_hash,
        RefreshTokenDB.user_id == current_user.id,
    ).first()

    if rt:
        rt.revoked_at = datetime.now(timezone.utc)
        db.commit()

    _clear_refresh_cookie(response)
    return {"detail": "已退出登录"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: UserDB = Depends(get_current_user_dependency)):
    return current_user
