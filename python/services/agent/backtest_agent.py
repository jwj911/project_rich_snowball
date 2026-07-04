"""Strategy backtesting Agent.

支持三种回测路径：
1. 传统均线交叉（兼容 Phase 2）
2. DSL 编译策略（Phase 3 -> Phase 4 链路）
3. 多策略对比：同一品种针对不同策略模板的横向对比
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Any

from services.agent.core import Agent, AgentEventType, AgentResult, AgentStatus
from services.agent.strategy_compiler_agent import StrategyParser
from services.agent.utils import resolve_symbol
from services.backtest.parser import parse_strategy_intent
from services.data_catalog import DataCatalogService


class BacktestAgent(Agent):
    """Convert user strategy intent into a deterministic backtest report."""

    name = "backtest"
    description = "策略回测专家，可将口头策略转换为可复现的历史回测与评分"

    async def run(self, query: str) -> AgentResult:
        self._add_step("thought", f"解析回测需求：{query}")

        # 延迟导入，避免 services.agent 与 services.backtest 的循环引用
        from services.backtest.service import run_dsl_backtest, run_strategy_backtest

        # 检测多策略对比模式："比较/对比/哪个"
        if _is_comparison_query(query):
            return await self._run_strategy_comparison(query)

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

            # Multi-symbol backtest
            symbols = dsl.universe
            if len(symbols) > 1:
                return await self._run_multi_symbol(dsl, symbols)

            preflight = self._check_backtest_data(symbols[0], dsl.timeframe)
            if preflight["status"] == "bad":
                return self._blocked_by_data_quality(preflight)

            try:
                result = run_dsl_backtest(
                    self.context.db,
                    symbol=symbols[0],
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
            result["data_preflight"] = preflight
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

        preflight = self._check_backtest_data(intent.symbol, intent.period)
        if preflight["status"] == "bad":
            return self._blocked_by_data_quality(preflight)

        try:
            result = run_strategy_backtest(self.context.db, intent)
        except ValueError as exc:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=str(exc),
                steps=self.get_steps(),
            )

        result["data_preflight"] = preflight
        return self._format_result(result)

    async def _run_strategy_comparison(self, query: str) -> AgentResult:
        """Run multiple strategies on one symbol and produce a comparison report.

        Detects phrases like "比较均线交叉和MACD", "哪个夏普更高", "回测对比".
        """
        from services.backtest.service import run_dsl_backtest

        symbol = resolve_symbol(self.context.db, query)
        if not symbol:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message="多策略对比需要明确指定品种，例如：螺纹钢 均线交叉 vs MACD 回测对比",
                steps=self.get_steps(),
            )

        # 提取要对比的策略关键词
        strategy_keywords = _extract_strategy_keywords(query)
        if len(strategy_keywords) < 2:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message="请指定至少两个要对比的策略，例如：回测比较螺纹钢的均线交叉和MACD策略",
                steps=self.get_steps(),
            )

        preflight = self._check_backtest_data(symbol, "1d")
        if preflight["status"] == "bad":
            return self._blocked_by_data_quality(preflight)

        results: list[dict[str, Any]] = []
        errors: list[str] = []
        parser = StrategyParser(self.context.db)

        for kw in strategy_keywords:
            sim_query = f"{query.strip()} {kw}"
            try:
                dsl = parser.parse(sim_query)
                if dsl and dsl.entry.get("conditions"):
                    result = run_dsl_backtest(
                        self.context.db,
                        symbol=symbol,
                        period=dsl.timeframe,
                        direction=dsl.direction,
                        entry_conditions=dsl.entry["conditions"],
                        exit_conditions=dsl.exit["conditions"],
                    )
                    result["_strategy_label"] = kw
                    result["data_preflight"] = preflight
                    results.append(result)
                else:
                    errors.append(f"{kw}: 无法编译为 DSL")
            except ValueError as exc:
                errors.append(f"{kw}: {exc}")

        if not results:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"所有策略均编译/回测失败：{'; '.join(errors)}" if errors else "无法生成有效回测",
                steps=self.get_steps(),
            )

        self._add_step(
            "observation",
            f"多策略对比完成：{symbol} 上 {len(results)} 个策略（{len(errors)} 个失败）",
        )
        answer = _format_strategy_comparison_report(symbol, results, errors)
        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=answer,
            data={
                "comparison_mode": "strategies",
                "symbol": symbol,
                "strategy_count": len(results),
                "results": results,
                "errors": errors,
                "data_preflight": preflight,
            },
            steps=self.get_steps(),
        )

    async def _run_multi_symbol(self, dsl, symbols: list[str]) -> AgentResult:
        """Run backtest across multiple symbols and produce a comparison report."""
        from services.backtest.service import run_dsl_backtest

        results: list[dict[str, Any]] = []
        errors: list[str] = []

        for sym in symbols:
            preflight = self._check_backtest_data(sym, dsl.timeframe)
            if preflight["status"] == "bad":
                errors.append(f"{sym}: 数据质量为 bad，已跳过；{_preflight_issue_summary(preflight)}")
                continue
            try:
                result = run_dsl_backtest(
                    self.context.db,
                    symbol=sym,
                    period=dsl.timeframe,
                    direction=dsl.direction,
                    entry_conditions=dsl.entry["conditions"],
                    exit_conditions=dsl.exit["conditions"],
                )
                result["data_preflight"] = preflight
                results.append(result)
            except ValueError as exc:
                errors.append(f"{sym}: {exc}")

        if not results and errors:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message="; ".join(errors),
                steps=self.get_steps(),
            )

        answer = _format_comparison_report(results, dsl=dsl.to_dict(), errors=errors)
        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=answer,
            data={
                "comparison": True,
                "symbols": symbols,
                "results": results,
                "errors": errors,
                "data_preflight": [item.get("data_preflight") for item in results],
            },
            steps=self.get_steps(),
        )

    def _check_backtest_data(self, symbol: str, period: str) -> dict[str, Any]:
        """Run deterministic data availability checks before entering the backtest engine."""
        catalog = DataCatalogService(self.context.db)
        coverage = catalog.get_symbol_data_coverage(symbol, period=period)
        quality = catalog.get_data_quality_summary(symbol=symbol, dataset_name="kline_data", period=period)
        preflight = {
            "dataset_name": "kline_data",
            "symbol": coverage["symbol"],
            "period": coverage["period"],
            "coverage": coverage["datasets"]["kline_data"],
            "quality": quality,
            "status": quality["status"],
        }
        self._add_step(
            "action",
            f"回测前数据检查：{preflight['symbol']} {period} K 线质量 {preflight['status']}",
            tool_name="DataCatalogService",
            tool_input={"symbol": symbol, "period": period, "dataset_name": "kline_data"},
            tool_output=preflight,
        )
        return preflight

    def _blocked_by_data_quality(self, preflight: dict[str, Any]) -> AgentResult:
        message = (
            f"{preflight['symbol']} {preflight['period']} K 线数据质量为 bad，已停止回测。"
            f"{_preflight_issue_summary(preflight)}"
        )
        self._add_step("error", message)
        return AgentResult(
            status=AgentStatus.FAILED,
            error_message=message,
            data={"data_preflight": preflight},
            steps=self.get_steps(),
        )

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

        通过后台任务执行 run()，将 _add_step 记录的步骤实时推送到进度队列并 yield，
        前端可实时展示「解析策略 → 获取数据 → 运行回测 → 计算指标 → 返回结果」各阶段。
        """
        async for event in self._stream_run(query):
            yield event

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


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------


def _is_comparison_query(query: str) -> bool:
    """检测是否为多策略对比查询。"""
    patterns = [
        r"(比较|对比|哪个|哪个更|vs\.?|PK|之间).*(?:策略|均线|MACD|RSI|布林带|突破)",
        r"(均线|MACD|RSI|布林带).*(?:和|与|或).*(?:均线|MACD|RSI|布林带)",
        r"回测.*(?:比较|对比|看看|试试).*",
    ]
    return any(re.search(p, query) for p in patterns)


def _extract_strategy_keywords(query: str) -> list[str]:
    """从对比查询中提取策略关键词列表。"""
    strategy_phrases = [
        "均线交叉",
        "MACD金叉",
        "MACD死叉",
        "RSI超卖",
        "RSI超买",
        "布林带",
        "突破策略",
        "均线多头排列",
    ]
    found = []
    for phrase in strategy_phrases:
        if phrase in query:
            found.append(phrase)
    if not found:
        for kw in ["均线交叉", "均线", "MACD", "RSI", "布林带", "突破"]:
            if kw in query and kw not in found:
                found.append(kw)
    return found


def _preflight_issue_summary(preflight: dict[str, Any]) -> str:
    """Return a compact readable summary for data preflight issues."""
    issues = (preflight.get("quality") or {}).get("issues") or []
    if not issues:
        return ""
    return "；".join(str(issue.get("message") or issue.get("code")) for issue in issues[:3])


def _format_backtest_report(result: dict, dsl: dict | None = None) -> str:
    config = result["config"]
    metrics = result["metrics"]
    variety = result["variety"]
    window = result["data_window"]
    trades = result["trades"][:5]
    preflight = result.get("data_preflight") or {}

    trade_lines = [
        f"- {t['entry_time']} -> {t['exit_time']}：{t['direction']} {t['entry_price']} -> {t['exit_price']}，PnL {t['pnl']}"
        for t in trades
    ]
    if not trade_lines:
        trade_lines = ["- 回测区间内没有形成完整开平仓交易"]

    if dsl:
        strategy_desc = dsl.get("description", f"方向 {dsl.get('direction', 'long')}")
    else:
        strategy_desc = (
            f"{config['short_window']} 周期均线上穿/下穿 {config['long_window']} 周期均线，方向 {config['direction']}"
        )

    lines = [
        f"## {variety['name']} ({config['symbol']}) 策略回测",
        "",
        f"策略：{strategy_desc}",
        f"周期：{config['period']}，区间：{window['start']} 至 {window['end']}，样本：{window['bars']} 根",
        "",
    ]
    if preflight:
        coverage = preflight.get("coverage") or {}
        quality = preflight.get("quality") or {}
        lines.extend(
            [
                "### 数据检查",
                f"- 数据集：{preflight.get('dataset_name', 'kline_data')}，质量：{preflight.get('status')}",
                f"- 覆盖：{coverage.get('first_date') or '—'} 至 {coverage.get('last_date') or '—'}，行数 {coverage.get('row_count', 0)}",
            ]
        )
        if preflight.get("status") == "warning":
            lines.append(f"- 提示：{_preflight_issue_summary(preflight) or '存在 warning 级别数据问题'}")
        if quality.get("score") is not None:
            lines.append(f"- 质量评分：{quality['score']}/100")
        lines.append("")

    lines.extend(
        [
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
        ]
    )
    return "\n".join(lines)


def _format_comparison_report(results: list[dict], dsl: dict, errors: list[str] | None = None) -> str:
    """Generate a multi-symbol comparison backtest report."""
    errors = errors or []
    direction = dsl.get("direction", "long")
    direction_label = "做多" if direction == "long" else "做空"

    lines = [
        "## 多品种策略对比回测",
        "",
        f"**策略**：{dsl.get('description', '—')}",
        f"**方向**：{direction_label}",
        f"**对比品种数**：{len(results)}{f'（{len(errors)} 个失败）' if errors else ''}",
        "",
        "| 品种 | 评分 | 总收益 | 年化收益 | 最大回撤 | 胜率 | 盈亏比 | 夏普 | 交易次数 |",
        "|------|------|--------|----------|----------|------|--------|------|----------|",
    ]
    preflights = [r.get("data_preflight") for r in results if r.get("data_preflight")]
    warnings = [p for p in preflights if p.get("status") == "warning"]
    if warnings:
        lines.extend(["", "### 数据检查", ""])
        for item in warnings:
            lines.append(f"- {item['symbol']} {item['period']} 数据质量 warning：{_preflight_issue_summary(item)}")

    best_idx = 0
    best_score = -1
    for i, r in enumerate(results):
        m = r["metrics"]
        v = r["variety"]
        lines.append(
            f"| {v['name']}({v.get('symbol', r['config']['symbol'])}) "
            f"| {m['score']} "
            f"| {m['total_return_pct']}% "
            f"| {m['annualized_return_pct']}% "
            f"| {m['max_drawdown_pct']}% "
            f"| {m['win_rate_pct']}% "
            f"| {m['profit_factor']} "
            f"| {m['sharpe']} "
            f"| {m['trade_count']} |"
        )
        if m["score"] > best_score:
            best_score = m["score"]
            best_idx = i

    if errors:
        lines.extend(["", "### 失败的品种", ""])
        for e in errors:
            lines.append(f"- {e}")

    if results:
        best = results[best_idx]
        best_v = best["variety"]
        lines.extend(
            [
                "",
                "### 最佳表现",
                f"- **{best_v['name']}** 评分 {best_score}/100，在 {len(results)} 个品种中表现最优",
                f"- 总收益 {best['metrics']['total_return_pct']}%，最大回撤 {best['metrics']['max_drawdown_pct']}%",
            ]
        )

    lines.extend(
        [
            "",
            "> 回测基于历史数据和固定规则，不构成投资建议；跨品种对比需注意合约乘数和保证金差异。",
        ]
    )
    return "\n".join(lines)


def _format_strategy_comparison_report(symbol: str, results: list[dict], errors: list[str]) -> str:
    """Generate a multi-strategy comparison report for one symbol."""
    from services.agent.data_tools import _get_variety_info

    variety_info = _get_variety_info(None, symbol) or {"name": symbol}
    variety_name = variety_info.get("name", symbol) if isinstance(variety_info, dict) else symbol

    lines = [
        f"## {variety_name} ({symbol}) 多策略对比回测",
        "",
        f"**对比策略数**：{len(results)}{f'（{len(errors)} 个失败）' if errors else ''}",
        "",
        "| 策略 | 评分 | 总收益 | 年化收益 | 最大回撤 | 胜率 | 盈亏比 | 夏普 | 交易次数 |",
        "|------|------|--------|----------|----------|------|--------|------|----------|",
    ]
    preflight = next((r.get("data_preflight") for r in results if r.get("data_preflight")), None)
    if preflight:
        coverage = preflight.get("coverage") or {}
        lines.extend(
            [
                "",
                "### 数据检查",
                f"- 数据集：kline_data，质量：{preflight.get('status')}，覆盖 {coverage.get('first_date') or '—'} 至 {coverage.get('last_date') or '—'}",
            ]
        )
        if preflight.get("status") == "warning":
            lines.append(f"- 提示：{_preflight_issue_summary(preflight)}")

    best_idx = 0
    best_score = -1
    for i, r in enumerate(results):
        m = r["metrics"]
        label = r.get("_strategy_label", f"策略{i + 1}")
        lines.append(
            f"| {label} "
            f"| {m['score']} "
            f"| {m['total_return_pct']}% "
            f"| {m['annualized_return_pct']}% "
            f"| {m['max_drawdown_pct']}% "
            f"| {m['win_rate_pct']}% "
            f"| {m['profit_factor']} "
            f"| {m['sharpe']} "
            f"| {m['trade_count']} |"
        )
        if m["score"] > best_score:
            best_score = m["score"]
            best_idx = i

    if errors:
        lines.extend(["", "### 失败的策略", ""])
        for e in errors:
            lines.append(f"- {e}")

    if len(results) >= 2:
        best = results[best_idx]
        best_label = best.get("_strategy_label", f"策略{best_idx + 1}")
        lines.extend(
            [
                "",
                "### 对比结论",
                f"- **最优策略**：{best_label}（评分 {best_score}/100）",
                f"- 总收益 {best['metrics']['total_return_pct']}%，夏普 {best['metrics']['sharpe']}",
                f"- 最大回撤 {best['metrics']['max_drawdown_pct']}%，胜率 {best['metrics']['win_rate_pct']}%",
            ]
        )
        scores = [(r.get("_strategy_label", ""), r["metrics"]["sharpe"]) for r in results]
        sorted_by_sharpe = sorted(scores, key=lambda x: x[1], reverse=True)
        if sorted_by_sharpe:
            lines.append(f"- 夏普排名：{' > '.join(f'{label}({s:.2f})' for label, s in sorted_by_sharpe)}")

    lines.extend(
        [
            "",
            "> 回测基于历史数据和固定规则，不构成投资建议。策略选择应综合考虑收益、风险和自身风险偏好。",
        ]
    )
    return "\n".join(lines)
