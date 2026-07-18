"""Agent 执行器。

管理 Agent 生命周期、持久化步骤到数据库、提供流式输出支持。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from models import AgentTaskDB, AgentTaskStepDB
from services.agent.core import Agent, AgentEvent, AgentEventType, AgentResult, AgentStatus, AgentStep

logger = logging.getLogger(__name__)


class AgentExecutor:
    """Agent 执行器。

    负责：
    1. 创建和更新数据库中的任务记录
    2. 持久化执行步骤
    3. 捕获异常并记录错误
    """

    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def create_task(self, agent_type: str, query: str, parent_task_id: int | None = None) -> int:
        """创建任务记录，返回 task_id。"""
        task = AgentTaskDB(
            user_id=self.user_id,
            parent_task_id=parent_task_id,
            agent_type=agent_type,
            query=query,
            status="pending",
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task.id

    def update_task_status(
        self,
        task_id: int,
        status: str,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """更新任务状态。"""
        from datetime import UTC, datetime

        task = self.db.get(AgentTaskDB, task_id)
        if not task:
            return
        task.status = status
        if result is not None:
            task.result_json = json.dumps(result, ensure_ascii=False, default=str)
        if error_message is not None:
            task.error_message = error_message
        if status == "running" and task.started_at is None:
            task.started_at = datetime.now(UTC)
        if status in ("completed", "failed"):
            task.finished_at = datetime.now(UTC)
        self.db.commit()

    def persist_step(self, task_id: int, step: AgentStep) -> None:
        """将单个步骤加入当前事务，由任务状态更新统一提交。"""
        db_step = AgentTaskStepDB(
            task_id=task_id,
            step_number=step.step_number,
            role=step.role,
            content=step.content,
            tool_name=step.tool_name,
            tool_input_json=json.dumps(step.tool_input, ensure_ascii=False, default=str) if step.tool_input else None,
            tool_output_json=json.dumps(step.tool_output, ensure_ascii=False, default=str)
            if step.tool_output is not None
            else None,
        )
        self.db.add(db_step)

    async def execute(self, agent: Agent, query: str, task_id: int | None = None) -> AgentResult:
        """执行 Agent 并持久化全链路。

        Args:
            agent: 已初始化的 Agent 实例
            query: 用户查询
            task_id: 可选的任务 ID（如为 None 则不持久化）

        Returns:
            AgentResult
        """
        if task_id is not None:
            self.update_task_status(task_id, "running")

        try:
            result = await agent.run(query)
            result.task_id = task_id

            # 持久化步骤
            if task_id is not None:
                for step in agent.get_steps():
                    self.persist_step(task_id, step)
                final_status = result.status.value
                self.update_task_status(
                    task_id,
                    final_status,
                    result=result.to_dict(),
                    error_message=result.error_message,
                )

            return result

        except Exception as exc:
            logger.exception("Agent execution failed: %s", exc)
            error_msg = str(exc)
            result = AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_msg,
                task_id=task_id,
            )
            if task_id is not None:
                agent._add_step("error", error_msg)
                for step in agent.get_steps():
                    self.persist_step(task_id, step)
                self.update_task_status(task_id, "failed", error_message=error_msg)
            return result

    async def execute_streaming(
        self,
        agent: Agent,
        query: str,
        task_id: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式执行 Agent，每完成一步就 yield 一个事件。

        用于 SSE 推送到前端。
        """
        if task_id is not None:
            self.update_task_status(task_id, "running")

        yield AgentEvent(
            event_type=AgentEventType.START,
            task_id=task_id,
            content="开始分析...",
        ).to_dict()

        final_result: dict[str, Any] | None = None
        final_error: str | None = None
        final_status: AgentStatus | None = None

        try:
            # 所有 Agent 都应实现 run_stream；基类提供默认回退实现
            async for event in agent.run_stream(query):
                event["task_id"] = task_id
                # 持久化步骤
                if task_id is not None and event.get("step_number"):
                    step = AgentStep(
                        step_number=event["step_number"],
                        role=event.get("role", "system"),
                        content=event.get("content", ""),
                        tool_name=event.get("tool_name"),
                        tool_input=event.get("tool_input"),
                        tool_output=event.get("tool_output"),
                    )
                    self.persist_step(task_id, step)

                # 收集最终结果用于任务状态更新
                if event.get("event_type") == "result":
                    final_result = event.get("result")
                    final_status = AgentStatus.COMPLETED
                elif event.get("event_type") == "error":
                    final_result = event.get("result")
                    final_error = event.get("error_message") or event.get("content")
                    final_status = AgentStatus.FAILED

                yield event

            # 流式执行结束后统一更新任务状态
            if task_id is not None:
                if final_status is not None:
                    self.update_task_status(
                        task_id,
                        final_status.value,
                        result=final_result,
                        error_message=final_error,
                    )
                else:
                    # 未收到 result/error 事件，按 completed 兜底
                    self.update_task_status(task_id, "completed")

        except Exception as exc:
            logger.exception("Agent streaming failed: %s", exc)
            error_msg = str(exc)
            if task_id is not None:
                self.update_task_status(task_id, "failed", error_message=error_msg)
            yield AgentEvent(
                event_type=AgentEventType.ERROR,
                task_id=task_id,
                error_message=error_msg,
            ).to_dict()

        yield AgentEvent(event_type=AgentEventType.DONE, task_id=task_id).to_dict()
