import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM
from config import SECRET_KEY as _SECRET_KEY

# mypy 确认：config.py 在导入期已验证 SECRET_KEY 非空
SECRET_KEY: str = _SECRET_KEY


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except (ValueError, TypeError):
        # 防御：若 hash 格式异常（如 dummy hash），视为验证失败
        return False


def create_access_token(data: dict) -> str:
    """生成 JWT access token。仅允许白名单字段进入 payload，避免敏感信息泄露。"""
    allowed_fields = {"sub", "username", "user_id", "role"}
    to_encode = {k: v for k, v in data.items() if k in allowed_fields}
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def generate_refresh_token() -> str:
    """生成高熵 refresh token 原始值（仅返回一次，调用方需保存 hash）。"""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """对 refresh token 做 SHA-256 hash，用于数据库存储和查询。"""
    return hashlib.sha256(token.encode()).hexdigest()


def ensure_utc(dt: datetime | None) -> datetime | None:
    """将客户端传入的 datetime 统一转换为 UTC aware datetime。

    数据库列已全面使用 DateTime(timezone=True)，应保留 aware datetime。
    本函数将带时区的时间正确转为 UTC，避免 naive/aware 比较错误和时区歧义。
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(UTC)
    # naive datetime 视为 UTC（向后兼容）
    return dt.replace(tzinfo=UTC)
