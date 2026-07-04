"""Agent 运行时核心。

提供 Agent 基类、执行结果、状态枚举等核心抽象。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, AsyncIterator


class AgentStatus(StrEnum):
    """Agent 执行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentEventType(StrEnum):
    """Agent 流式事件类型。"""

    START = "start"
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    RESULT = "result"
    ERROR = "error"
    DONE = "done"


@dataclass
class AgentStep:
    """Agent 执行的单个步骤（ReAct 链路中的一步）。"""

    step_number: int
    role: str  # thought | action | observation | system | error
    content: str
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "role": self.role,
            "content": self.content,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
        }


@dataclass
class AgentEvent:
    """Agent 流式事件。

    后端 SSE 和前端事件展示统一使用这个结构，避免不同 Agent 自己拼字段。
    """

    event_type: AgentEventType | str
    task_id: int | None = None
    step_number: int | None = None
    role: str | None = None
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: Any = None
    result: dict[str, Any] | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        event_type = self.event_type.value if isinstance(self.event_type, AgentEventType) else self.event_type
        payload: dict[str, Any] = {"event_type": event_type}
        for key in (
            "task_id",
            "step_number",
            "role",
            "content",
            "tool_name",
            "tool_input",
            "tool_output",
            "result",
            "error_message",
        ):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload


@dataclass
class AgentResult:
    """Agent 执行结果。"""

    status: AgentStatus
    answer: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    steps: list[AgentStep] = field(default_factory=list)
    error_message: str | None = None
    task_id: int | None = None

    @property
    def success(self) -> bool:
        return self.status == AgentStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "answer": self.answer,
            "data": self.data,
            "steps": [s.to_dict() for s in self.steps],
            "error_message": self.error_message,
            "task_id": self.task_id,
        }


class Agent:
    """Agent 基类。

    所有具体 Agent 必须继承此类，并实现 run 方法。
    """

    name: str = "base"
    description: str = "基础 Agent"

    def __init__(self, context: "AgentContext") -> None:  # type: ignore[name-defined]
        from services.agent.context import AgentContext

        self.context: AgentContext = context
        self._steps: list[AgentStep] = []
        self._step_counter: int = 0

    def _add_step(
        self,
        role: str,
        content: str,
        tool_name: str | None = None,
        tool_input: dict[str, Any] | None = None,
        tool_output: Any = None,
    ) -> AgentStep:
        """记录执行步骤。"""
        self._step_counter += 1
        step = AgentStep(
            step_number=self._step_counter,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
        )
        self._steps.append(step)
        return step

    async def run(self, query: str) -> AgentResult:
        """执行 Agent 任务。

        子类必须重写此方法。
        """
        raise NotImplementedError

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行 Agent 任务。

        默认实现回退到 run()，一次性 yield 结果事件。
        子类可覆盖此方法以在关键步骤 yield 中间事件。
        """
        result = await self.run(query)
        yield AgentEvent(
            event_type=AgentEventType.RESULT,
            task_id=result.task_id,
            content=result.answer,
            result=result.to_dict(),
        ).to_dict()

    def get_steps(self) -> list[AgentStep]:
        """获取已记录的所有步骤。"""
        return list(self._steps)
