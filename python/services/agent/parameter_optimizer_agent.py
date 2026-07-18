"""参数优化 Agent。

对策略 DSL 执行参数网格搜索，返回最优参数组合。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from services.agent.core import Agent, AgentResult, AgentStatus
from services.agent.parameter_optimizer import format_optimization_report, optimize_strategy
from services.agent.strategy_compiler_agent import StrategyParser


class ParameterOptimizerAgent(Agent):
    """策略参数优化 Agent。

    对策略进行参数网格搜索并返回最优参数组合。
    """

    name = "parameter_optimizer"
    description = "策略参数优化专家，对策略进行参数网格搜索并返回最优参数组合"

    async def run(self, query: str) -> AgentResult:
        """执行参数优化。"""
        self._add_step("thought", f"开始参数优化：{query}")

        db = self.context.db

        # 1. 解析策略
        parser = StrategyParser(db)
        dsl = parser.parse(query)

        if dsl is None:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message="无法识别策略品种，请提供品种代码（如 RB、AU）或品种名称",
                steps=self.get_steps(),
            )

        self._add_step(
            "action",
            "策略解析完成",
            tool_name="StrategyParser",
            tool_input={"query": query},
            tool_output=dsl.to_dict(),
        )

        # 2. 执行优化
        report = optimize_strategy(db, dsl, query, top_n=10)

        # 3. 生成报告
        markdown = format_optimization_report(report)
        self._add_step(
            "system",
            f"参数优化完成，最优评分：{report.best_metrics.get('score', '—')}",
        )

        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=markdown,
            data=report.to_dict(),
            steps=self.get_steps(),
        )

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行参数优化任务。"""
        async for event in self._stream_run(query):
            yield event
