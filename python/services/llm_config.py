"""用户级 LLM 配置服务。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

import config
from models import UserLLMConfigDB

_PROVIDER = "openai-compatible"
_VERSION = "v1"


@dataclass(frozen=True)
class ResolvedLLMConfig:
    """调用 LLM 时使用的最终配置。"""

    provider: str
    base_url: str
    model: str
    api_key: str
    uses_system_default: bool
    updated_at: datetime | None = None


def normalize_base_url(base_url: str) -> str:
    """规范化 OpenAI 兼容 API 根路径。"""
    value = base_url.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        raise ValueError("base_url 必须以 http:// 或 https:// 开头")
    return value


def mask_api_key(api_key: str | None) -> str | None:
    """返回 API key 的脱敏展示。"""
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:3]}...{api_key[-4:]}"


def encrypt_api_key(api_key: str) -> str:
    """用应用密钥派生出的流密钥加密 API key。"""
    nonce = os.urandom(16)
    plaintext = api_key.encode("utf-8")
    cipher = _xor_bytes(plaintext, _keystream(nonce, len(plaintext)))
    mac = hmac.new(_secret_bytes(), nonce + cipher, hashlib.sha256).digest()
    payload = base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")
    return f"{_VERSION}:{payload}"


def decrypt_api_key(value: str | None) -> str | None:
    """解密已存储的 API key。"""
    if not value:
        return None
    try:
        version, encoded = value.split(":", 1)
        if version != _VERSION:
            return None
        raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
        nonce, mac, cipher = raw[:16], raw[16:48], raw[48:]
        expected = hmac.new(_secret_bytes(), nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            return None
        return _xor_bytes(cipher, _keystream(nonce, len(cipher))).decode("utf-8")
    except Exception:
        return None


def get_user_llm_config(db: Session, user_id: int) -> UserLLMConfigDB | None:
    """读取当前用户启用的 LLM 配置。"""
    return (
        db.query(UserLLMConfigDB)
        .filter(UserLLMConfigDB.user_id == user_id, UserLLMConfigDB.is_active == True)  # noqa: E712
        .first()
    )


def resolve_llm_config(db: Session | None = None, user_id: int | None = None) -> ResolvedLLMConfig | None:
    """按用户配置优先、系统环境兜底的顺序解析 LLM 配置。"""
    if db is not None and user_id is not None:
        user_config = get_user_llm_config(db, user_id)
        if user_config:
            api_key = decrypt_api_key(user_config.api_key_encrypted)
            if api_key:
                return ResolvedLLMConfig(
                    provider=user_config.provider,
                    base_url=user_config.base_url,
                    model=user_config.model,
                    api_key=api_key,
                    uses_system_default=False,
                    updated_at=user_config.updated_at,
                )

    if config.OPENAI_API_KEY:
        return ResolvedLLMConfig(
            provider=_PROVIDER,
            base_url=config.OPENAI_BASE_URL.rstrip("/"),
            model=config.OPENAI_MODEL,
            api_key=config.OPENAI_API_KEY,
            uses_system_default=True,
            updated_at=None,
        )
    return None


def config_to_response(db: Session, user_id: int) -> dict:
    """生成安全的配置响应，不回显明文 API key。"""
    user_config = get_user_llm_config(db, user_id)
    if user_config:
        api_key = decrypt_api_key(user_config.api_key_encrypted)
        if api_key:
            return {
                "provider": user_config.provider,
                "base_url": user_config.base_url,
                "model": user_config.model,
                "has_api_key": True,
                "api_key_masked": mask_api_key(api_key),
                "uses_system_default": False,
                "updated_at": user_config.updated_at,
            }
        if not config.OPENAI_API_KEY:
            return {
                "provider": user_config.provider,
                "base_url": user_config.base_url,
                "model": user_config.model,
                "has_api_key": False,
                "api_key_masked": None,
                "uses_system_default": False,
                "updated_at": user_config.updated_at,
            }

    return {
        "provider": _PROVIDER,
        "base_url": config.OPENAI_BASE_URL.rstrip("/"),
        "model": config.OPENAI_MODEL,
        "has_api_key": bool(config.OPENAI_API_KEY),
        "api_key_masked": mask_api_key(config.OPENAI_API_KEY),
        "uses_system_default": True,
        "updated_at": None,
    }


def upsert_user_llm_config(
    db: Session,
    user_id: int,
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str | None,
) -> UserLLMConfigDB:
    """创建或更新当前用户的 LLM 配置。"""
    cfg = db.query(UserLLMConfigDB).filter(UserLLMConfigDB.user_id == user_id).first()
    if cfg is None:
        cfg = UserLLMConfigDB(user_id=user_id)
        db.add(cfg)

    cfg.provider = provider.strip() or _PROVIDER
    cfg.base_url = normalize_base_url(base_url)
    cfg.model = model.strip()
    cfg.is_active = True
    if api_key:
        cfg.api_key_encrypted = encrypt_api_key(api_key.strip())
    cfg.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(cfg)
    return cfg


def delete_user_api_key(db: Session, user_id: int) -> None:
    """清除当前用户配置中的 API key。"""
    cfg = db.query(UserLLMConfigDB).filter(UserLLMConfigDB.user_id == user_id).first()
    if cfg:
        cfg.api_key_encrypted = None
        cfg.updated_at = datetime.now(UTC)
        db.commit()


def _secret_bytes() -> bytes:
    return hashlib.sha256(config.SECRET_KEY.encode("utf-8")).digest()


def _keystream(nonce: bytes, length: int) -> bytes:
    blocks = []
    counter = 0
    secret = _secret_bytes()
    while sum(len(block) for block in blocks) < length:
        blocks.append(hmac.new(secret, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right, strict=True))
