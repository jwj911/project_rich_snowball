"""Strategy backtesting Agent.

支持两种回测路径：
1. 传统均线交叉（兼容 Phase 2）
2. DSL 编译策略（Phase 3 -> Phase 4 链路）
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, AsyncIterator

from services.agent.core import Agent, AgentEvent, AgentEventType, AgentResult, AgentStatus
from services.agent.strategy_compiler_agent import StrategyParser
from services.backtest.parser import parse_strategy_intent
from services.backtest.service import run_dsl_backtest, run_strategy_backtest


class BacktestAgent(Agent):
    """Convert user strategy intent into a deterministic backtest report."""

    name = "backtest"
    description = "策略回测专家，可将口头策略转换为可复现的历史回测与评分"

    async def run(self, query: str) -> AgentResult:
        self._add_step("thought", f"解析回测需求：{query}")

        # 优先尝试 DSL 编译（支持 MACD/RSI/布林带等多种策略）
        parser = StrategyParser(self.context.db)
        dsl = parser.parse(query)
        if dsl and dsl.entry.get("conditions"):
            self._add_step(
                "action",
                "策略编译为 DSL",
                tool_name="StrategyParser",
                tool_input={"query": query},
                tool_output=dsl.to_dict(),
            )
            try:
                result = run_dsl_backtest(
                    self.context.db,
                    symbol=dsl.universe[0],
                    period=dsl.timeframe,
                    direction=dsl.direction,
                    entry_conditions=dsl.entry["conditions"],
                    exit_conditions=dsl.exit["conditions"],
                )
            except ValueError as exc:
                return AgentResult(
                    status=AgentStatus.FAILED,
                    error_message=str(exc),
                    steps=self.get_steps(),
                )
            return self._format_result(result, dsl=dsl.to_dict())

        # 回退到传统均线交叉解析
        intent = parse_strategy_intent(self.context.db, query)
        if intent is None:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message="无法识别回测品种，请提供品种代码或名称，例如：螺纹钢 5 日上穿 20 日均线回测",
                steps=self.get_steps(),
            )

        self._add_step(
            "action",
            "生成结构化策略参数",
            tool_name="parse_strategy_intent",
            tool_input={"query": query},
            tool_output=asdict(intent),
        )

        try:
            result = run_strategy_backtest(self.context.db, intent)
        except ValueError as exc:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=str(exc),
                steps=self.get_steps(),
            )

        return self._format_result(result)

    def _format_result(self, result: dict, dsl: dict | None = None) -> AgentResult:
        metrics = result["metrics"]
        window = result["data_window"]
        self._add_step("observation", f"回测区间：{window['start']} 至 {window['end']}，共 {window['bars']} 根 K 线")
        self._add_step("system", f"策略评分：{metrics['score']}/100")

        answer = _format_backtest_report(result, dsl=dsl)
        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=answer,
            data=result,
            steps=self.get_steps(),
        )

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行策略回测任务。

        按「解析策略 → 获取数据 → 运行回测 → 计算指标 → 返回结果」各阶段
        yield 事件，前端可实时展示执行过程。
        """
        result = await self.run(query)

        for step in result.steps:
            yield AgentEvent(
                event_type=self._map_role_to_event_type(step.role),
                step_number=step.step_number,
                role=step.role,
                content=step.content,
                tool_name=step.tool_name,
                tool_input=step.tool_input,
                tool_output=step.tool_output,
            ).to_dict()

        if result.success:
            yield AgentEvent(
                event_type=AgentEventType.RESULT,
                content=result.answer,
                result=result.to_dict(),
            ).to_dict()
        else:
            yield AgentEvent(
                event_type=AgentEventType.ERROR,
                content=result.error_message or "策略回测失败",
                error_message=result.error_message,
                result=result.to_dict(),
            ).to_dict()

    @staticmethod
    def _map_role_to_event_type(role: str) -> AgentEventType:
        """将步骤 role 映射到 SSE 事件类型。"""
        mapping = {
            "thought": AgentEventType.THOUGHT,
            "action": AgentEventType.ACTION,
            "observation": AgentEventType.OBSERVATION,
            "system": AgentEventType.THOUGHT,
            "error": AgentEventType.ERROR,
        }
        return mapping.get(role, AgentEventType.THOUGHT)


def _format_backtest_report(result: dict, dsl: dict | None = None) -> str:
    config = result["config"]
    metrics = result["metrics"]
    variety = result["variety"]
    window = result["data_window"]
    trades = result["trades"][:5]

    trade_lines = [
        f"- {t['entry_time']} -> {t['exit_time']}：{t['direction']} {t['entry_price']} -> {t['exit_price']}，PnL {t['pnl']}"
        for t in trades
    ]
    if not trade_lines:
        trade_lines = ["- 回测区间内没有形成完整开平仓交易"]

    if dsl:
        strategy_desc = dsl.get("description", f"方向 {dsl.get('direction', 'long')}")
    else:
        strategy_desc = f"{config['short_window']} 周期均线上穿/下穿 {config['long_window']} 周期均线，方向 {config['direction']}"

    return "\n".join([
        f"## {variety['name']} ({config['symbol']}) 策略回测",
        "",
        f"策略：{strategy_desc}",
        f"周期：{config['period']}，区间：{window['start']} 至 {window['end']}，样本：{window['bars']} 根",
        "",
        "### 核心指标",
        f"- 策略评分：{metrics['score']}/100",
        f"- 总收益率：{metrics['total_return_pct']}%",
        f"- 年化收益率：{metrics['annualized_return_pct']}%",
        f"- 最大回撤：{metrics['max_drawdown_pct']}%",
        f"- 胜率：{metrics['win_rate_pct']}%",
        f"- 盈亏比：{metrics['profit_factor']}",
        f"- 夏普：{metrics['sharpe']}",
        f"- 交易次数：{metrics['trade_count']}",
        "",
        "### 最近交易",
        *trade_lines,
        "",
        "> 回测基于历史数据和固定规则，不构成投资建议；后续应加入滑点、合约换月和样本外验证。",
    ])
