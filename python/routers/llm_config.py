"""用户级 LLM 配置 API。"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from errors import ErrorCode
from models import UserDB
from schemas import LLMConfigResponse, LLMConfigTestResponse, LLMConfigUpdate
from services.domain.exceptions import ServiceError
from services.llm_config import (
    config_to_response,
    decrypt_api_key,
    delete_user_api_key,
    get_user_llm_config,
    normalize_base_url,
    resolve_llm_config,
    upsert_user_llm_config,
)

router = APIRouter(prefix="/api/llm-config", tags=["LLM 配置"])


@router.get("", response_model=LLMConfigResponse)
def get_llm_config(
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """获取当前用户的 LLM 配置摘要。"""
    return config_to_response(db, current_user.id)


@router.put("", response_model=LLMConfigResponse)
def update_llm_config(
    data: LLMConfigUpdate,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """创建或更新当前用户的 LLM 配置。"""
    try:
        upsert_user_llm_config(
            db,
            current_user.id,
            provider=data.provider,
            base_url=data.base_url,
            model=data.model,
            api_key=data.api_key,
        )
    except ValueError as exc:
        raise ServiceError(code=ErrorCode.VALIDATION_ERROR, message=str(exc), status_code=422) from exc
    return config_to_response(db, current_user.id)


@router.post("/test", response_model=LLMConfigTestResponse)
async def test_llm_config(
    data: LLMConfigUpdate | None = None,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """测试当前或提交中的 OpenAI 兼容配置。"""
    if data is not None:
        base_url = normalize_base_url(data.base_url)
        model = data.model.strip()
        api_key = data.api_key
        if not api_key:
            existing = get_user_llm_config(db, current_user.id)
            api_key = decrypt_api_key(existing.api_key_encrypted) if existing else None
    else:
        resolved = resolve_llm_config(db, current_user.id)
        current = config_to_response(db, current_user.id)
        base_url = resolved.base_url if resolved else current["base_url"]
        model = resolved.model if resolved else current["model"]
        api_key = resolved.api_key if resolved else None

    if not api_key:
        return LLMConfigTestResponse(ok=False, model=model, message="未配置用户 API Key，无法测试连接。")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "temperature": 0,
                    "max_tokens": 8,
                },
            )
            resp.raise_for_status()
    except Exception as exc:
        return LLMConfigTestResponse(ok=False, model=model, message=f"连接失败：{exc}")

    return LLMConfigTestResponse(ok=True, model=model, message="连接成功")


@router.delete("/api-key", status_code=204)
def delete_llm_api_key(
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """清除当前用户保存的 API key。"""
    delete_user_api_key(db, current_user.id)
    return None
