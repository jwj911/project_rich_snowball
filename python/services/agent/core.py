"""Agent 运行时核心。

提供 Agent 基类、执行结果、状态枚举等核心抽象。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AgentStatus(StrEnum):
    """Agent 执行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentEventType(StrEnum):
    """Agent 流式事件类型。"""

    START = "start"
    PROGRESS = "progress"
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

    def __init__(self, context: AgentContext) -> None:  # noqa: F821  # forward reference, resolved at runtime
        from services.agent.context import AgentContext

        self.context: AgentContext = context
        self._steps: list[AgentStep] = []
        self._step_counter: int = 0
        self._progress_queue: asyncio.Queue[dict[str, Any]] | None = None

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
        self._emit_step_event(step)
        return step

    def _emit_step_event(self, step: AgentStep) -> None:
        """将步骤转换为流式事件并推入进度队列（如正在流式执行）。"""
        if self._progress_queue is None:
            return
        mapping = {
            "thought": AgentEventType.THOUGHT,
            "action": AgentEventType.ACTION,
            "observation": AgentEventType.OBSERVATION,
            "system": AgentEventType.THOUGHT,
            "error": AgentEventType.ERROR,
        }
        event = AgentEvent(
            event_type=mapping.get(step.role, AgentEventType.THOUGHT),
            step_number=step.step_number,
            role=step.role,
            content=step.content,
            tool_name=step.tool_name,
            tool_input=step.tool_input,
            tool_output=step.tool_output,
        )
        self._progress_queue.put_nowait(event.to_dict())

    def _emit_progress(self, content: str) -> None:
        """推送一个无 step_number 的进度提示事件（如正在流式执行）。"""
        if self._progress_queue is None:
            return
        self._progress_queue.put_nowait(
            AgentEvent(
                event_type=AgentEventType.PROGRESS,
                content=content,
            ).to_dict()
        )

    async def _consume_progress_stream(
        self,
        task: asyncio.Task[AgentResult],
    ) -> AsyncIterator[dict[str, Any]]:
        """消费进度队列中的事件，直到后台任务结束且队列为空。"""
        while not task.done() or (self._progress_queue is not None and not self._progress_queue.empty()):
            if self._progress_queue is not None:
                try:
                    event = await asyncio.wait_for(self._progress_queue.get(), timeout=0.1)
                    yield event
                except TimeoutError:
                    if task.done():
                        break
            else:
                await asyncio.sleep(0.05)

    async def _stream_run(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """通用流式执行辅助：后台运行 self.run(query) 并实时 yield 步骤/进度事件。

        适用于本地确定性计算的 Agent。子类可在 run() 中调用 _emit_progress() 增加进度提示。
        """
        self._progress_queue = asyncio.Queue()
        task = asyncio.create_task(self.run(query))

        async for event in self._consume_progress_stream(task):
            yield event

        result = task.result()
        if result.success:
            yield AgentEvent(
                event_type=AgentEventType.RESULT,
                task_id=result.task_id,
                content=result.answer,
                result=result.to_dict(),
            ).to_dict()
        else:
            yield AgentEvent(
                event_type=AgentEventType.ERROR,
                task_id=result.task_id,
                content=result.error_message or "执行失败",
                error_message=result.error_message,
                result=result.to_dict(),
            ).to_dict()

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
