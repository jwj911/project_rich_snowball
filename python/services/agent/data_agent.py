"""数据获取 Agent。

能够独立完成品种数据查询任务，通过 LLM function calling 选择合适工具。
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from services.agent.context import AgentContext
from services.agent.core import Agent, AgentEvent, AgentEventType, AgentResult, AgentStatus
import services.agent.data_tools  # noqa: F401  # 注册 DataAgent 可用工具
from services.agent.llm_client import AgentLLMClient
from services.agent.tools import get_tool_registry
from services.domain.exceptions import ServiceError

logger = logging.getLogger(__name__)

_MAX_STEPS = 5

_SYSTEM_PROMPT = (
    "你是「期货交流社区」的数据查询专家 Agent。\n"
    "你的任务是通过调用工具获取数据，然后为用户提供清晰、准确的回答。\n"
    "规则：\n"
    "1. 每次只调用一个工具\n"
    "2. 如果用户询问具体品种，优先查询该品种的实时行情\n"
    "3. 如果用户要求历史走势，调用 K 线数据工具\n"
    "4. 数据获取完成后，用简洁专业的中文总结\n"
    "5. 所有分析仅供参考，不构成投资建议\n"
)


class DataAgent(Agent):
    """数据查询 Agent。

    基于 OpenAI function calling 实现工具选择和调用。
    """

    name = "data"
    description = "期货数据查询专家，可获取品种信息、实时行情、K线数据、市场状态等"

    def __init__(self, context: AgentContext) -> None:
        super().__init__(context)
        self._registry = get_tool_registry()
        self._llm = AgentLLMClient()

    async def run(self, query: str) -> AgentResult:
        """执行数据查询任务。

        流程：
        1. 构建 function calling 请求
        2. 解析模型返回的工具调用
        3. 执行工具并获取结果
        4. 将结果返回给模型生成最终回答
        5. 重复直到模型不再调用工具或达到最大步数
        """
        if not self._llm.is_configured:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message="AI 助手尚未配置。请管理员设置 OPENAI_API_KEY 环境变量。",
            )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        for step in range(_MAX_STEPS):
            try:
                message = await self._llm.chat_completion(
                    messages,
                    tools=self._registry.get_openai_schemas(),
                    tool_choice="auto",
                    temperature=0.3,
                    max_tokens=2048,
                )

                # 检查是否有工具调用
                tool_calls = message.get("tool_calls")
                if tool_calls:
                    # 记录模型回复（包含 tool_calls）
                    self._add_step("thought", f"第 {step + 1} 步：决定调用工具")
                    messages.append(message)

                    for tc in tool_calls:
                        tool_name = tc["function"]["name"]
                        tool_args = json.loads(tc["function"].get("arguments") or "{}")

                        self._add_step(
                            "action",
                            f"调用工具：{tool_name}",
                            tool_name=tool_name,
                            tool_input=tool_args,
                        )

                        # 执行工具
                        tool_result = await self._registry.execute(tool_name, self.context, tool_args)

                        self._add_step(
                            "observation",
                            f"工具返回结果：{tool_result}",
                            tool_name=tool_name,
                            tool_input=tool_args,
                            tool_output=tool_result,
                        )

                        # 将工具结果添加到消息历史
                        messages.append({
                            "tool_call_id": tc["id"],
                            "role": "tool",
                            "name": tool_name,
                            "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                        })
                else:
                    # 模型直接回答，不再调用工具
                    answer = message.get("content", "").strip()
                    self._add_step("system", f"最终回答：{answer}")
                    return AgentResult(
                        status=AgentStatus.COMPLETED,
                        answer=answer,
                        data={"query": query},
                        steps=self.get_steps(),
                    )

            except ServiceError as e:
                logger.warning("DataAgent service error: %s", e.message)
                return AgentResult(
                    status=AgentStatus.FAILED,
                    error_message=e.message,
                    steps=self.get_steps(),
                )
            except Exception as e:
                logger.exception("DataAgent error: %s", e)
                return AgentResult(
                    status=AgentStatus.FAILED,
                    error_message=f"执行出错：{e}",
                    steps=self.get_steps(),
                )

        # 达到最大步数
        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer="分析步骤过多，请尝试简化您的问题。",
            data={"query": query},
            steps=self.get_steps(),
        )

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行数据查询任务。

        每轮 thought / action / observation 都会 yield 事件，
        前端可实时展示工具调用过程。
        """
        if not self._llm.is_configured:
            error_message = "AI 助手尚未配置。请管理员设置 OPENAI_API_KEY 环境变量。"
            self._add_step("error", error_message)
            yield AgentEvent(
                event_type=AgentEventType.ERROR,
                content=error_message,
            ).to_dict()
            return

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        for step in range(_MAX_STEPS):
            try:
                message = await self._llm.chat_completion(
                    messages,
                    tools=self._registry.get_openai_schemas(),
                    tool_choice="auto",
                    temperature=0.3,
                    max_tokens=2048,
                )

                tool_calls = message.get("tool_calls")
                if tool_calls:
                    thought_step = self._add_step("thought", f"第 {step + 1} 步：决定调用工具")
                    yield AgentEvent(
                        event_type=AgentEventType.THOUGHT,
                        step_number=thought_step.step_number,
                        role=thought_step.role,
                        content=thought_step.content,
                    ).to_dict()
                    messages.append(message)

                    for tc in tool_calls:
                        tool_name = tc["function"]["name"]
                        tool_args = json.loads(tc["function"].get("arguments") or "{}")

                        action_step = self._add_step(
                            "action",
                            f"调用工具：{tool_name}",
                            tool_name=tool_name,
                            tool_input=tool_args,
                        )
                        yield AgentEvent(
                            event_type=AgentEventType.ACTION,
                            step_number=action_step.step_number,
                            role=action_step.role,
                            content=action_step.content,
                            tool_name=tool_name,
                            tool_input=tool_args,
                        ).to_dict()

                        tool_result = await self._registry.execute(tool_name, self.context, tool_args)

                        observation_step = self._add_step(
                            "observation",
                            f"工具返回结果：{tool_result}",
                            tool_name=tool_name,
                            tool_input=tool_args,
                            tool_output=tool_result,
                        )
                        yield AgentEvent(
                            event_type=AgentEventType.OBSERVATION,
                            step_number=observation_step.step_number,
                            role=observation_step.role,
                            content=observation_step.content,
                            tool_name=tool_name,
                            tool_input=tool_args,
                            tool_output=tool_result,
                        ).to_dict()

                        messages.append({
                            "tool_call_id": tc["id"],
                            "role": "tool",
                            "name": tool_name,
                            "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                        })
                else:
                    answer = message.get("content", "").strip()
                    self._add_step("system", f"最终回答：{answer}")
                    result = AgentResult(
                        status=AgentStatus.COMPLETED,
                        answer=answer,
                        data={"query": query},
                        steps=self.get_steps(),
                    )
                    yield AgentEvent(
                        event_type=AgentEventType.RESULT,
                        content=answer,
                        result=result.to_dict(),
                    ).to_dict()
                    return

            except ServiceError as e:
                logger.warning("DataAgent service error: %s", e.message)
                error_message = e.message
                self._add_step("error", error_message)
                yield AgentEvent(
                    event_type=AgentEventType.ERROR,
                    content=error_message,
                    error_message=error_message,
                ).to_dict()
                return
            except Exception as e:
                logger.exception("DataAgent error: %s", e)
                error_message = f"执行出错：{e}"
                self._add_step("error", error_message)
                yield AgentEvent(
                    event_type=AgentEventType.ERROR,
                    content=error_message,
                    error_message=error_message,
                ).to_dict()
                return

        # 达到最大步数
        answer = "分析步骤过多，请尝试简化您的问题。"
        self._add_step("system", answer)
        result = AgentResult(
            status=AgentStatus.COMPLETED,
            answer=answer,
            data={"query": query},
            steps=self.get_steps(),
        )
        yield AgentEvent(
            event_type=AgentEventType.RESULT,
            content=answer,
            result=result.to_dict(),
        ).to_dict()
