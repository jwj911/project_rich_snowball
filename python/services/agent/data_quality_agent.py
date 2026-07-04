"""数据质量 Agent。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from services.agent.core import Agent, AgentEvent, AgentEventType, AgentResult, AgentStatus
from services.data_quality import DataQualityService


class DataQualityAgent(Agent):
    """确定性数据质检 Agent，不依赖 LLM。"""

    name = "data_quality"
    description = "数据质检 Agent，检查 K 线和实时行情覆盖、异常与可用性"

    async def run(self, query: str) -> AgentResult:
        self._add_step("thought", f"开始数据质量检查：{query}")
        service = DataQualityService(self.context.db)
        report = service.inspect(query).to_dict()
        self._add_step(
            "action", "执行确定性数据质量规则", tool_name="data_quality.inspect", tool_input={"query": query}
        )
        self._add_step("observation", f"质量状态：{report['status']}，评分：{report['score']}", tool_output=report)

        answer = _format_answer(report)
        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=answer,
            data=report,
            steps=self.get_steps(),
        )

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        result = await self.run(query)
        for step in result.steps:
            yield AgentEvent(
                event_type=_map_role_to_event_type(step.role),
                step_number=step.step_number,
                role=step.role,
                content=step.content,
                tool_name=step.tool_name,
                tool_input=step.tool_input,
                tool_output=step.tool_output,
            ).to_dict()
        yield AgentEvent(
            event_type=AgentEventType.RESULT,
            content=result.answer,
            result=result.to_dict(),
        ).to_dict()


def _map_role_to_event_type(role: str) -> AgentEventType:
    mapping = {
        "thought": AgentEventType.THOUGHT,
        "action": AgentEventType.ACTION,
        "observation": AgentEventType.OBSERVATION,
        "system": AgentEventType.THOUGHT,
        "error": AgentEventType.ERROR,
    }
    return mapping.get(role, AgentEventType.THOUGHT)


def _format_answer(report: dict[str, Any]) -> str:
    scope = report.get("scope", {})
    dataset = scope.get("dataset", "all")
    symbol = scope.get("symbol")
    period = scope.get("period")
    title_parts = ["数据质量检查"]
    if symbol:
        title_parts.append(str(symbol))
    if period:
        title_parts.append(str(period))
    if dataset != "all":
        title_parts.append(str(dataset))

    lines = [
        f"## {' / '.join(title_parts)}",
        "",
        f"**状态**：{report['status']}  **评分**：{report['score']}/100",
        f"**覆盖**：{report.get('coverage', {})}",
    ]

    issues = report.get("issues") or []
    if issues:
        lines.extend(["", "### 问题"])
        for issue in issues:
            lines.append(f"- [{issue['severity']}] {issue['code']}：{issue['message']}")
    else:
        lines.extend(["", "未发现 P0 级数据质量问题。"])

    recommendations = report.get("recommendations") or []
    if recommendations:
        lines.extend(["", "### 建议"])
        for item in recommendations:
            lines.append(f"- {item}")

    datasets = report.get("datasets") or []
    if datasets:
        lines.extend(["", "### 数据集"])
        for item in datasets:
            lines.append(f"- {item.get('dataset_name')}：{item.get('quality_status')}，rows={item.get('row_count', 0)}")

    return "\n".join(lines)
