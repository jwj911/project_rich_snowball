"""分析流水线 Agent。

第一个多 Agent 编排场景：
用户提出「帮我完整分析某品种」类请求时，系统自动并行执行
DataAgent + TechAnalysisAgent（两者无依赖），然后串行执行
RiskManagementAgent（依赖前两者的结果），最后汇总为三合一报告。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from services.agent.context import AgentContext
from services.agent.core import Agent, AgentEventType, AgentResult, AgentStatus
from services.agent.data_agent import DataAgent
from services.agent.executor import AgentExecutor
from services.agent.risk_management_agent import RiskManagementAgent
from services.agent.tech_analysis_agent import TechAnalysisAgent
from services.agent.utils import extract_direction, resolve_symbol
from services.data_catalog import DataCatalogService

logger = logging.getLogger(__name__)


class AnalysisPipelineAgent(Agent):
    """分析流水线 Agent。

    将复杂分析请求拆解为数据获取 → 技术分析 → 风控方案三个子任务，
    并汇总为完整报告。
    """

    name = "analysis_pipeline"
    description = "期货完整分析流水线：数据 + 技术分析 + 风控方案"

    async def run(self, query: str) -> AgentResult:
        """执行分析流水线。"""
        self._add_step("thought", f"开始分析流水线：{query}")

        db = self.context.db
        user_id = self.context.user_id
        parent_task_id = self.context.task_id

        # 1. 解析品种与方向
        symbol = resolve_symbol(db, query)
        if not symbol:
            error_message = "无法从查询中识别品种代码，请提供品种代码（如 RB、AU）或品种名称"
            self._add_step("error", error_message)
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_message,
                steps=self.get_steps(),
            )

        direction = extract_direction(query) or "long"
        self._add_step("action", f"识别品种：{symbol}，方向：{direction}")

        # 2. 数据可用性前置检查。bad 时降级执行，warning 时继续并保留风险提示。
        data_preflight = self._check_pipeline_data(symbol, "1d")
        preflight_bad = data_preflight["status"] == "bad"
        if preflight_bad:
            self._add_step(
                "thought",
                f"{symbol} 日线数据质量为 bad，将尝试降级为「数据现状报告 + 可用的技术分析」。"
                f"{_preflight_issue_summary(data_preflight)}",
            )

        # 3. 创建子任务执行器
        executor = AgentExecutor(db, user_id)
        sub_results: list[tuple[str, AgentResult]] = []

        # Step 1 & 2: DataAgent + TechAnalysisAgent 并行执行（无依赖关系）
        data_query = f"获取 {symbol} 的品种信息和最新行情"
        ta_query = f"分析 {symbol} 日线技术面"

        self._add_step("thought", "并行执行：DataAgent + TechAnalysisAgent")
        data_task_id = executor.create_task("data", data_query, parent_task_id=parent_task_id)
        ta_task_id = executor.create_task("tech_analysis", ta_query, parent_task_id=parent_task_id)

        data_agent = DataAgent(AgentContext(db=db, user_id=user_id, task_id=data_task_id))
        ta_agent = TechAnalysisAgent(AgentContext(db=db, user_id=user_id, task_id=ta_task_id))

        data_task = executor.execute(data_agent, data_query, task_id=data_task_id)
        ta_task = executor.execute(ta_agent, ta_query, task_id=ta_task_id)

        data_result, ta_result = await asyncio.gather(data_task, ta_task)
        sub_results.append(("data", data_result))
        sub_results.append(("tech_analysis", ta_result))
        self._add_step(
            "observation",
            f"DataAgent 完成：{data_result.status.value}  |  TechAnalysisAgent 完成：{ta_result.status.value}",
            tool_name="DataAgent + TechAnalysisAgent",
            tool_input={"data_query": data_query, "ta_query": ta_query},
            tool_output={"data": data_result.to_dict(), "tech_analysis": ta_result.to_dict()},
        )

        if not data_result.success:
            error_message = f"数据获取失败：{data_result.error_message}"
            self._add_step("error", error_message)
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_message,
                steps=self.get_steps(),
            )

        if preflight_bad and not ta_result.success:
            # 数据质量 bad 且技术分析无法完成：返回数据现状报告
            self._add_step("system", "数据质量不足，生成数据现状报告")
            report = self._build_report(
                symbol,
                direction,
                data_result,
                ta_result,
                AgentResult(
                    status=AgentStatus.FAILED,
                    error_message="因 K 线数据不足，未生成风控方案",
                ),
                data_preflight,
            )
            summary = self._build_degraded_summary(report, reason="data_bad")
            return AgentResult(
                status=AgentStatus.COMPLETED,
                answer=summary,
                data=report,
                steps=self.get_steps(),
            )

        if not ta_result.success:
            error_message = f"技术分析失败：{ta_result.error_message}"
            self._add_step("error", error_message)
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_message,
                steps=self.get_steps(),
            )

        # 提取当前价格用于风控
        current_price = None
        if data_result.data and isinstance(data_result.data, dict):
            current_price = data_result.data.get("current_price")

        # Step 3: RiskManagementAgent - 风控方案（依赖 Data + Tech 结果）
        risk_query = f"{symbol} {'做多' if direction == 'long' else '做空'} 风控方案"
        if current_price:
            risk_query += f"，入场价 {current_price}"
        self._add_step("thought", f"步骤 3：调用 RiskManagementAgent - {risk_query}")
        risk_task_id = executor.create_task("risk_management", risk_query, parent_task_id=parent_task_id)
        risk_agent = RiskManagementAgent(AgentContext(db=db, user_id=user_id, task_id=risk_task_id))
        risk_result = await executor.execute(risk_agent, risk_query, task_id=risk_task_id)
        sub_results.append(("risk_management", risk_result))
        self._add_step(
            "observation",
            f"RiskManagementAgent 执行完成：{risk_result.status.value}",
            tool_name="RiskManagementAgent",
            tool_input={"query": risk_query},
            tool_output=risk_result.to_dict(),
        )

        if not risk_result.success:
            error_message = f"风控方案生成失败：{risk_result.error_message}"
            self._add_step("error", error_message)
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_message,
                steps=self.get_steps(),
            )

        # 4. 汇总报告
        self._add_step("system", "汇总各子 Agent 结果，生成完整分析报告")
        report = self._build_report(symbol, direction, data_result, ta_result, risk_result, data_preflight)
        summary = self._build_summary(report)

        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=summary,
            data=report,
            steps=self.get_steps(),
        )

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行分析流水线。

        通过后台任务执行 run()，将 _add_step 记录的步骤实时推送到进度队列并 yield，
        包括子 Agent 的完成情况。
        """
        async for event in self._stream_run(query):
            yield event

    def _check_pipeline_data(self, symbol: str, period: str) -> dict[str, Any]:
        """检查完整分析流水线所需的基础 K 线数据。"""
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
            f"流水线数据前置检查：{symbol} {period} K 线质量 {preflight['status']}",
            tool_name="DataCatalogService",
            tool_input={"symbol": symbol, "period": period, "dataset_name": "kline_data"},
            tool_output=preflight,
        )
        return preflight

    @staticmethod
    def _map_role_to_event_type(role: str) -> AgentEventType:
        mapping = {
            "thought": AgentEventType.THOUGHT,
            "action": AgentEventType.ACTION,
            "observation": AgentEventType.OBSERVATION,
            "system": AgentEventType.THOUGHT,
            "error": AgentEventType.ERROR,
        }
        return mapping.get(role, AgentEventType.THOUGHT)

    def _build_report(
        self,
        symbol: str,
        direction: str,
        data_result: AgentResult,
        ta_result: AgentResult,
        risk_result: AgentResult,
        data_preflight: dict[str, Any],
    ) -> dict[str, Any]:
        """构建结构化汇总报告。"""
        data = data_result.data or {}
        ta = ta_result.data or {}
        risk = risk_result.data or {}

        return {
            "symbol": symbol,
            "direction": direction,
            "data": {
                "name": data.get("name") or ta.get("name"),
                "exchange": data.get("exchange") or ta.get("exchange"),
                "current_price": data.get("current_price") or ta.get("current_price"),
                "change_percent": data.get("change_percent") or ta.get("change_percent"),
            },
            "technical": {
                "score": ta.get("score"),
                "rating": ta.get("rating"),
                "direction": ta.get("direction"),
                "bias": ta.get("bias"),
                "money_flow": ta.get("money_flow"),
                "kline_trend": ta.get("kline_trend"),
                "key_levels": ta.get("key_levels"),
                "risk_note": ta.get("risk_note"),
                "trend": ta.get("trend"),
                "pattern": ta.get("pattern"),
                "divergence": ta.get("divergence"),
                "indicators": ta.get("indicators"),
            },
            "risk": {
                "entry_price": risk.get("entry_price"),
                "risk_level": risk.get("risk_level"),
                "position": risk.get("position"),
                "stop_loss": risk.get("stop_loss"),
                "take_profit": risk.get("take_profit"),
                "drawdown_control": risk.get("drawdown_control"),
            },
            "data_quality": data_preflight,
            "sub_task_results": {
                "data": data_result.to_dict(),
                "tech_analysis": ta_result.to_dict(),
                "risk_management": risk_result.to_dict(),
            },
        }

    def _build_summary(self, report: dict[str, Any]) -> str:
        """生成 Markdown 汇总报告。"""
        data = report["data"]
        tech = report["technical"]
        risk = report["risk"]
        direction_label = "做多" if report["direction"] == "long" else "做空"

        lines = [
            f"## {data.get('name') or report['symbol']} ({report['symbol']}) 完整分析报告",
            "",
            f"**方向**：{direction_label}  **最新价**：{data.get('current_price')}  **涨跌**：{data.get('change_percent')}%",
            "",
            "### 1. 品种概况",
            f"- 交易所：{data.get('exchange') or '—'}",
            f"- 最新价：{data.get('current_price')}",
            f"- 涨跌幅：{data.get('change_percent')}%",
            "",
            "### 数据检查",
            f"- K 线质量：{(report.get('data_quality') or {}).get('status')}",
        ]
        data_quality = report.get("data_quality") or {}
        coverage = data_quality.get("coverage") or {}
        if coverage:
            lines.append(
                f"- 覆盖：{coverage.get('first_date') or '—'} 至 {coverage.get('last_date') or '—'}，样本 {coverage.get('row_count', 0)} 根"
            )
        if data_quality.get("status") in ("warning", "bad"):
            lines.append(f"- 风险提示：{_preflight_issue_summary(data_quality)}")

        lines.extend(
            [
                "",
                "### 2. 技术分析",
            ]
        )

        if tech.get("score") is not None:
            lines.append(f"- 综合评分：{tech['score']}/100（{tech.get('rating', '—')}）")
        if tech.get("direction"):
            lines.append(f"- 趋势方向：{tech['direction']}")
        if tech.get("bias"):
            lines.append(f"- 多空倾向：{tech['bias']}")
        if tech.get("money_flow"):
            lines.append(f"- 资金流向：{tech['money_flow']}")
        if tech.get("kline_trend"):
            lines.append(f"- K线走势：{tech['kline_trend']}")
        if tech.get("pattern") and isinstance(tech["pattern"], dict):
            lines.append(f"- 形态：{tech['pattern'].get('pattern', '—')}")
        if tech.get("divergence") and isinstance(tech["divergence"], dict):
            lines.append(f"- 背离：{tech['divergence'].get('divergence', '—')}")
        if tech.get("risk_note"):
            lines.append(f"- 风险提示：{tech['risk_note']}")

        lines.extend(
            [
                "",
                "### 3. 风控方案",
            ]
        )

        position = risk.get("position") or {}
        stop_loss = risk.get("stop_loss") or {}
        take_profit = risk.get("take_profit") or {}

        lines.extend(
            [
                f"- 建议仓位：{position.get('suggested_lots', '—')} 手（占用 {position.get('position_size_pct', '—')}%）",
                f"- 止损价：{stop_loss.get('stop_loss_price', '—')}（{stop_loss.get('risk_distance_pct', '—')}%）",
                f"- 止盈价：{take_profit.get('take_profit_price', '—')}（风险收益比 1:{take_profit.get('risk_reward_ratio', '—')}）",
            ]
        )

        lines.extend(
            [
                "",
                "> ⚠️ 以上分析由数据、技术分析、风控三个 Agent 自动汇总生成，仅供参考，不构成投资建议。",
            ]
        )

        return "\n".join(str(line) for line in lines)

    def _build_degraded_summary(self, report: dict[str, Any], reason: str) -> str:
        """生成数据质量不足时的降级报告。"""
        data = report["data"]
        data_quality = report.get("data_quality") or {}
        coverage = data_quality.get("coverage") or {}

        lines = [
            f"## {data.get('name') or report['symbol']} ({report['symbol']}) 数据现状报告",
            "",
            f"**状态**：K 线数据质量为 **{data_quality.get('status', 'unknown')}**，完整分析已降级。",
            "",
            "### 数据检查",
            f"- K 线质量：{data_quality.get('status')}",
        ]
        if coverage:
            lines.append(
                f"- 覆盖：{coverage.get('first_date') or '—'} 至 {coverage.get('last_date') or '—'}，"
                f"样本 {coverage.get('row_count', 0)} 根"
            )
        lines.append(f"- 问题说明：{_preflight_issue_summary(data_quality) or '—'}")

        lines.extend(
            [
                "",
                "### 品种概况",
                f"- 交易所：{data.get('exchange') or '—'}",
                f"- 最新价：{data.get('current_price') or '—'}",
                f"- 涨跌幅：{data.get('change_percent') or '—'}%",
                "",
                "### 建议",
                "- 数据不足可能导致技术指标失真，建议等待数据回填后再进行完整分析",
                "- 可检查该品种是否已加入采集列表，或联系管理员补充历史数据",
                "",
                "> ⚠️ 以上报告由数据 Agent 自动生成，仅供参考，不构成投资建议。",
            ]
        )
        return "\n".join(str(line) for line in lines)


def _preflight_issue_summary(preflight: dict[str, Any]) -> str:
    issues = (preflight.get("quality") or {}).get("issues") or []
    if not issues:
        return ""
    return "；".join(str(issue.get("message") or issue.get("code")) for issue in issues[:3])
