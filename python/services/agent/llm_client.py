"""Agent LLM 客户端。

封装 OpenAI 兼容 Chat Completions 调用，供各类 Agent 复用。
"""

from __future__ import annotations

from typing import Any

import httpx

import config
from errors import ErrorCode
from services.domain.exceptions import ServiceError


class AgentLLMClient:
    """OpenAI 兼容 Chat Completions 客户端。"""

    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(config.OPENAI_API_KEY)

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
        if not self.is_configured:
            raise ServiceError(
                code=ErrorCode.AGENT_LLM_ERROR,
                message="AI 助手尚未配置。请管理员设置 OPENAI_API_KEY 环境变量。",
                status_code=503,
            )

        payload: dict[str, Any] = {
            "model": config.OPENAI_MODEL,
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
                    f"{config.OPENAI_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config.OPENAI_API_KEY}",
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
