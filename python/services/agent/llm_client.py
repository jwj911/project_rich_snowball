"""Agent LLM 客户端。

封装 OpenAI 兼容 Chat Completions 调用，供各类 Agent 复用。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from errors import ErrorCode
from services.domain.exceptions import ServiceError
from services.llm_config import ResolvedLLMConfig, resolve_llm_config

logger = logging.getLogger(__name__)

# 共享 AsyncClient，减少连接建立开销
_AGENT_HTTP_CLIENT: httpx.AsyncClient | None = None


def _get_http_client(timeout: float) -> httpx.AsyncClient:
    """获取或创建共享的 httpx.AsyncClient。"""
    global _AGENT_HTTP_CLIENT
    if _AGENT_HTTP_CLIENT is None or _AGENT_HTTP_CLIENT.timeout.read != timeout:
        _AGENT_HTTP_CLIENT = httpx.AsyncClient(timeout=timeout)
    return _AGENT_HTTP_CLIENT


class AgentLLMClient:
    """OpenAI 兼容 Chat Completions 客户端。"""

    def __init__(self, db: Session | None = None, user_id: int | None = None, timeout: float = 60.0) -> None:
        self.db = db
        self.user_id = user_id
        self.timeout = timeout
        self._max_retries = 2

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

        client = _get_http_client(self.timeout)
        last_exception: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
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
                return self._extract_message(data)
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                logger.warning(
                    "Agent LLM HTTP error (attempt %d/%d): status=%s, response=%s",
                    attempt + 1,
                    self._max_retries + 1,
                    status_code,
                    exc.response.text[:500],
                )
                # 4xx 客户端错误不重试
                if 400 <= status_code < 500:
                    raise self._http_status_error(exc) from exc
                last_exception = exc
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                logger.warning(
                    "Agent LLM network error (attempt %d/%d): %s",
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                )
                last_exception = exc
            except Exception as exc:
                logger.exception("Agent LLM unexpected error: %s", exc)
                raise ServiceError(
                    code=ErrorCode.AGENT_LLM_ERROR,
                    message=f"请求 AI 服务时发生错误：{exc}",
                    status_code=503,
                ) from exc

        # 重试耗尽
        if isinstance(last_exception, httpx.HTTPStatusError):
            raise self._http_status_error(last_exception) from last_exception

        raise ServiceError(
            code=ErrorCode.AGENT_LLM_ERROR,
            message="AI 服务暂时不可用，请稍后重试。",
            status_code=503,
        ) from last_exception

    def _http_status_error(self, exc: httpx.HTTPStatusError) -> ServiceError:
        """根据上游 HTTP 状态码生成用户友好的错误。"""
        status_code = exc.response.status_code
        if status_code == 401:
            message = "AI 服务认证失败，请检查 API Key 是否有效。"
        elif status_code == 429:
            message = "AI 服务请求过于频繁，请稍后再试。"
        elif status_code >= 500:
            message = "AI 服务暂时不可用，请稍后重试。"
        else:
            message = "AI 服务暂时不可用，请稍后重试。"
        return ServiceError(
            code=ErrorCode.AGENT_LLM_ERROR,
            message=message,
            status_code=503,
        )

    def _extract_message(self, data: dict[str, Any]) -> dict[str, Any]:
        """从响应中提取 assistant message，失败时给出明确错误。"""
        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            response_summary = str(data)[:500]
            logger.error("Agent LLM response format invalid: %s", response_summary)
            raise ServiceError(
                code=ErrorCode.AGENT_LLM_ERROR,
                message="AI 服务返回格式异常。",
                status_code=503,
            ) from exc
