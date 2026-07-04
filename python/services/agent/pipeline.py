"""Agent 流水线计划结构。

为复杂多 Agent 任务提供简单的步骤计划抽象。
当前仅支持串行执行，后续可扩展为 DAG。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from schemas import AgentType


@dataclass
class PipelineStep:
    """流水线中的单个子任务。"""

    agent_type: AgentType
    query: str
    reason: str = ""
    depends_on: list[int] = field(default_factory=list)
    output_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_type": self.agent_type.value if isinstance(self.agent_type, AgentType) else self.agent_type,
            "query": self.query,
            "reason": self.reason,
            "depends_on": self.depends_on,
            "output_key": self.output_key,
        }


@dataclass
class PipelinePlan:
    """流水线执行计划。"""

    steps: list[PipelineStep] = field(default_factory=list)

    def add_step(
        self,
        agent_type: AgentType,
        query: str,
        reason: str = "",
        output_key: str | None = None,
    ) -> PipelineStep:
        """添加一个串行步骤（默认依赖前一步）。"""
        depends_on = [len(self.steps) - 1] if self.steps else []
        step = PipelineStep(
            agent_type=agent_type,
            query=query,
            reason=reason,
            depends_on=depends_on,
            output_key=output_key,
        )
        self.steps.append(step)
        return step

    def to_dict(self) -> dict[str, Any]:
        return {"steps": [s.to_dict() for s in self.steps]}
