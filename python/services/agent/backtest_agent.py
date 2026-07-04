"""Strategy backtesting Agent."""

from __future__ import annotations

from dataclasses import asdict

from services.agent.core import Agent, AgentResult, AgentStatus
from services.backtest.parser import parse_strategy_intent
from services.backtest.service import run_strategy_backtest


class BacktestAgent(Agent):
    """Convert user strategy intent into a deterministic backtest report."""

    name = "backtest"
    description = "策略回测专家，可将口头策略转换为可复现的历史回测与评分"

    async def run(self, query: str) -> AgentResult:
        self._add_step("thought", f"解析回测需求：{query}")
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

        metrics = result["metrics"]
        window = result["data_window"]
        self._add_step("observation", f"回测区间：{window['start']} 至 {window['end']}，共 {window['bars']} 根 K 线")
        self._add_step("system", f"策略评分：{metrics['score']}/100")

        answer = _format_backtest_report(result)
        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=answer,
            data=result,
            steps=self.get_steps(),
        )


def _format_backtest_report(result: dict) -> str:
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

    return "\n".join([
        f"## {variety['name']} ({config['symbol']}) 策略回测",
        "",
        f"策略：{config['short_window']} 周期均线上穿/下穿 {config['long_window']} 周期均线，方向 {config['direction']}",
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
