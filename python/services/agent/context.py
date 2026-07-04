"""Agent 上下文。

封装 Agent 执行时需要的共享状态：数据库会话、用户信息、任务 ID 等。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class AgentContext:
    """Agent 执行上下文。

    贯穿 Agent 执行全生命周期，提供对数据库、缓存、配置等的统一访问。
    """

    def __init__(
        self,
        db: Session,
        user_id: int,
        task_id: int | None = None,
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.task_id = task_id

    def __repr__(self) -> str:
        return f"AgentContext(user_id={self.user_id}, task_id={self.task_id})"
