"""Agent LLM 客户端。

封装 OpenAI 兼容 Chat Completions 调用，供各类 Agent 复用。
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session

from errors import ErrorCode
from services.domain.exceptions import ServiceError
from services.llm_config import ResolvedLLMConfig, resolve_llm_config


class AgentLLMClient:
    """OpenAI 兼容 Chat Completions 客户端。"""

    def __init__(self, db: Session | None = None, user_id: int | None = None, timeout: float = 60.0) -> None:
        self.db = db
        self.user_id = user_id
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return self._resolve_config() is not None

    def _resolve_config(self) -> ResolvedLLMConfig | None:
        return resolve_llm_config(self.db, self.user_id)

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """调用 OpenAI 兼容 chat/completions，并返回 assistant message。"""
        llm_config = self._resolve_config()
        if llm_config is None:
            raise ServiceError(
                code=ErrorCode.AGENT_LLM_ERROR,
                message="AI 助手尚未配置。请在个人设置中配置 API Key，或请管理员设置系统默认 OPENAI_API_KEY。",
                status_code=503,
            )

        payload: dict[str, Any] = {
            "model": llm_config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{llm_config.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {llm_config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise ServiceError(
                code=ErrorCode.AGENT_LLM_ERROR,
                message="AI 服务暂时不可用，请稍后重试。",
                status_code=503,
            ) from exc
        except Exception as exc:
            raise ServiceError(
                code=ErrorCode.AGENT_LLM_ERROR,
                message=f"请求 AI 服务时发生错误：{exc}",
                status_code=503,
            ) from exc

        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ServiceError(
                code=ErrorCode.AGENT_LLM_ERROR,
                message="AI 服务返回格式异常。",
                status_code=503,
            ) from exc
