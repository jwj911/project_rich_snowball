from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from config import ACCESS_TOKEN_EXPIRE_MINUTES, ENV, REFRESH_TOKEN_EXPIRE_DAYS
from dependencies import get_current_user_dependency, get_db
from errors import ErrorCode
from middleware.rate_limit import _get_client_ip, check_rate_limit
from middleware.rate_limit import clear_rate_limit_store as _middleware_clear_rate_limit
from models import RefreshTokenDB, UserDB
from schemas import (
    MessageResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from services.domain.exceptions import ConflictError, UnauthorizedError
from services.metrics import auth_operations_total
from utils import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["认证"])
ACCESS_TOKEN_COOKIE_NAME = "access_token"
REFRESH_TOKEN_COOKIE_NAME = "refresh_token"

# Auth 专用限流配置（比全局限流更严格）
_AUTH_RATE_LIMIT_WINDOW = 60
_AUTH_RATE_LIMIT_MAX = 10


def clear_rate_limit_store():
    """清空限流计数器，供测试使用。"""
    _middleware_clear_rate_limit()


# 恒定时间比较用的 dummy hash（有效 bcrypt hash，确保计算耗时与真实 hash 接近）
_DUMMY_HASH = "$2b$12$cPBBd9OrTIWiStqUdReQ9OJxJiPTUD.ux8DZ7UN8b4sEbmKn5jXL."


def _set_access_cookie(response: Response, access_token: str) -> None:
    """Set the cookie used by SSE and compatible read-only requests."""
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=ENV == "production",
        samesite="lax",
        path="/",
    )


def _clear_access_cookie(response: Response) -> None:
    """Clear the SSE/read-only access token cookie."""
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        httponly=True,
        secure=ENV == "production",
        samesite="lax",
        path="/",
    )


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Set the JavaScript-inaccessible refresh token cookie."""
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
    raise UnauthorizedError("Refresh token 无效或已过期", code=ErrorCode.TOKEN_INVALID)


@router.post("/register", response_model=UserResponse, status_code=201)
def register(request: Request, user: UserCreate, db: Session = Depends(get_db)):  # noqa: B008
    client_ip = _get_client_ip(request)
    if not check_rate_limit(
        client_ip,
        "auth:register",
        window_seconds=_AUTH_RATE_LIMIT_WINDOW,
        max_requests=_AUTH_RATE_LIMIT_MAX,
    ):
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后再试",
            headers={"Retry-After": str(_AUTH_RATE_LIMIT_WINDOW)},
        )

    existing = db.query(UserDB).filter((UserDB.username == user.username) | (UserDB.email == user.email)).first()
    if existing:
        auth_operations_total.labels(operation="register", result="failure").inc()
        raise ConflictError("用户名或邮箱已存在", code=ErrorCode.USERNAME_TAKEN)

    db_user = UserDB(username=user.username, email=user.email, password_hash=hash_password(user.password))
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # 自动创建默认用户偏好
    from models import UserPreferenceDB

    db.add(UserPreferenceDB(user_id=db_user.id))
    db.commit()

    auth_operations_total.labels(operation="register", result="success").inc()
    return db_user


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    client_ip = _get_client_ip(request)
    if not check_rate_limit(
        client_ip,
        "auth:login",
        window_seconds=_AUTH_RATE_LIMIT_WINDOW,
        max_requests=_AUTH_RATE_LIMIT_MAX,
    ):
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后再试",
            headers={"Retry-After": str(_AUTH_RATE_LIMIT_WINDOW)},
        )

    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()

    # 恒定时间比较：无论用户是否存在，都执行一次 verify_password
    password_hash: str = str(user.password_hash) if user else _DUMMY_HASH
    password_ok = verify_password(form_data.password, password_hash)

    if not user or not password_ok:
        auth_operations_total.labels(operation="login", result="failure").inc()
        raise UnauthorizedError("用户名或密码错误", code=ErrorCode.INVALID_CREDENTIALS)

    access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
    auth_operations_total.labels(operation="login", result="success").inc()

    # Access token cookie supports SSE, which cannot send a bearer header.
    _set_access_cookie(response, access_token)

    # 生成 refresh token 并持久化
    raw_refresh = generate_refresh_token()
    refresh_hash = hash_refresh_token(raw_refresh)
    expires_at = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
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
    db: Session = Depends(get_db),  # noqa: B008
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
    rt = (
        db.query(RefreshTokenDB)
        .filter(
            RefreshTokenDB.token_hash == token_hash,
            RefreshTokenDB.revoked_at.is_(None),
            RefreshTokenDB.expires_at > datetime.now(UTC),
        )
        .first()
    )

    if not rt:
        auth_operations_total.labels(operation="refresh", result="failure").inc()
        raise UnauthorizedError("Refresh token 无效或已过期", code=ErrorCode.TOKEN_INVALID)

    # Refresh token 轮转：生成新 token，吊销旧 token
    new_raw_refresh = generate_refresh_token()
    new_refresh_hash = hash_refresh_token(new_raw_refresh)
    new_expires_at = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    new_rt = RefreshTokenDB(
        user_id=rt.user_id,
        token_hash=new_refresh_hash,
        expires_at=new_expires_at,
        device_info=rt.device_info,
    )
    db.add(new_rt)
    rt.revoked_at = datetime.now(UTC)
    db.commit()

    access_token = create_access_token(data={"sub": str(rt.user_id)})
    _set_access_cookie(response, access_token)
    _set_refresh_cookie(response, new_raw_refresh)
    auth_operations_total.labels(operation="refresh", result="success").inc()
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
    db: Session = Depends(get_db),  # noqa: B008
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
):
    """吊销当前 refresh token（logout）。"""
    raw_refresh = _extract_refresh_token(request, body)
    token_hash = hash_refresh_token(raw_refresh)
    rt = (
        db.query(RefreshTokenDB)
        .filter(
            RefreshTokenDB.token_hash == token_hash,
            RefreshTokenDB.user_id == current_user.id,
        )
        .first()
    )

    if rt:
        rt.revoked_at = datetime.now(UTC)
        db.commit()

    _clear_refresh_cookie(response)
    _clear_access_cookie(response)
    return {"detail": "已退出登录"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: UserDB = Depends(get_current_user_dependency)):  # noqa: B008
    return current_user
