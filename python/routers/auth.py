from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from threading import Lock

from models import UserDB
from schemas import UserCreate, UserResponse, TokenResponse
from dependencies import get_db, get_current_user_dependency
from utils import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/api/auth", tags=["认证"])

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


def _check_rate_limit(client_ip: str) -> bool:
    now = datetime.now()
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
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    existing = db.query(UserDB).filter(
        (UserDB.username == user.username) | (UserDB.email == user.email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名或邮箱已存在")

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
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()

    # 恒定时间比较：无论用户是否存在，都执行一次 verify_password
    password_hash = user.password_hash if user else _DUMMY_HASH
    password_ok = verify_password(form_data.password, password_hash)

    if not user or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: UserDB = Depends(get_current_user_dependency)):
    return current_user
