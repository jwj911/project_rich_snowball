"""数据获取 Agent。

能够独立完成品种数据查询任务，通过 LLM function calling 选择合适工具。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import services.agent.data_tools as data_tools  # noqa: F401  # 注册 DataAgent 可用工具
import services.agent.database_tools as database_tools  # noqa: F401  # 注册数据库查询工具
from services.agent.context import AgentContext
from services.agent.core import Agent, AgentEvent, AgentEventType, AgentResult, AgentStatus
from services.agent.llm_client import AgentLLMClient
from services.agent.tools import get_tool_registry
from services.agent.utils import resolve_symbol
from services.domain.exceptions import ServiceError

logger = logging.getLogger(__name__)

_MAX_STEPS = 5

_SYSTEM_PROMPT = (
    "你是「期货交流社区」的数据查询专家 Agent。\n"
    "你的任务是通过调用工具获取数据，然后为用户提供清晰、准确的回答。\n"
    "你可以使用的工具包括：\n"
    "- get_variety_info: 查询品种基础信息\n"
    "- get_realtime_quote: 获取实时行情\n"
    "- get_kline_data: 获取 K 线历史数据\n"
    "- get_continuous_klines: 获取连续 K 线（主力切换拼接）\n"
    "- get_main_klines: 获取当前主力合约 K 线\n"
    "- list_active_varieties: 列出活跃品种\n"
    "- get_market_status: 获取市场状态\n"
    "- get_warehouse_receipts: 查询仓单日报（库存压力分析）\n"
    "- get_holding_rankings: 查询持仓排名（资金流向分析）\n"
    "- get_settlement_params: 查询结算参数（保证金/手续费）\n"
    "- get_price_limits: 查询涨跌停价格\n"
    "- query_database: 通用 SQL 查询（灵活查询任何已入库数据表）\n"
    "- list_tables: 列出可查询的数据库表\n"
    "- get_table_schema: 获取表结构\n"
    "\n"
    "规则：\n"
    "1. 每次只调用一个工具\n"
    "2. 如果用户询问具体品种，优先查询该品种的实时行情\n"
    "3. 如果用户要求历史走势，调用 K 线数据工具\n"
    "4. 如果用户询问仓单/库存，调用 get_warehouse_receipts\n"
    "5. 如果用户询问持仓/主力动向，调用 get_holding_rankings\n"
    "6. 如果用户询问保证金/手续费/结算价，调用 get_settlement_params\n"
    "7. 当用户询问『涨幅前 N』、『排名前 N』时，必须将 sort_order 设为 desc；询问『跌幅前 N』时设为 asc\n"
    "8. 当用户的问题超出上述专用工具范围时，你可以使用 query_database 工具直接写 SQL 查询数据库\n"
    "9. 使用 query_database 前，如果不确定表结构，先调用 list_tables 或 get_table_schema\n"
    "10. 数据获取完成后，用简洁专业的中文总结\n"
    "11. 所有分析仅供参考，不构成投资建议\n"
)


class DataAgent(Agent):
    """数据查询 Agent。

    基于 OpenAI function calling 实现工具选择和调用。
    """

    name = "data"
    description = (
        "期货数据查询专家，可获取品种信息、实时行情、K线数据（含连续/主力合约）、"
        "仓单日报、持仓排名、结算参数、涨跌停价格、市场状态等。"
        "支持通用 SQL 查询，可灵活访问数据库中任何已入库的数据。"
    )

    def __init__(self, context: AgentContext) -> None:
        super().__init__(context)
        self._registry = get_tool_registry()
        self._llm = AgentLLMClient()

    def _build_system_prompt(self, query: str) -> str:
        """构建包含已解析品种提示的系统提示。"""
        symbol = resolve_symbol(self.context.db, query)
        prompt = _SYSTEM_PROMPT
        if symbol:
            prompt += f"\n\n（系统提示：用户查询中识别到的品种代码为 {symbol}，工具调用时优先使用此代码。）\n"
        return prompt

    async def run(self, query: str) -> AgentResult:
        """执行数据查询任务。"""
        if not self._llm.is_configured:
            self._add_step("thought", "LLM 未配置，使用规则化兜底路径")
            return await self._run_fallback(query)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._build_system_prompt(query)},
            {"role": "user", "content": query},
        ]

        for step in range(_MAX_STEPS):
            try:
                message = await self._llm.chat_completion(
                    messages,
                    tools=self._registry.get_openai_schemas(),
                    tool_choice="auto",
                    temperature=0.3,
                    max_tokens=2048,
                )

                # 检查是否有工具调用
                tool_calls = message.get("tool_calls")
                if tool_calls:
                    # 记录模型回复（包含 tool_calls）
                    self._add_step("thought", f"第 {step + 1} 步：决定调用工具")
                    messages.append(message)

                    for tc in tool_calls:
                        tool_name = tc["function"]["name"]
                        tool_args = json.loads(tc["function"].get("arguments") or "{}")

                        self._add_step(
                            "action",
                            f"调用工具：{tool_name}",
                            tool_name=tool_name,
                            tool_input=tool_args,
                        )

                        # 执行工具
                        tool_result = await self._registry.execute(tool_name, self.context, tool_args)

                        self._add_step(
                            "observation",
                            f"工具返回结果：{tool_result}",
                            tool_name=tool_name,
                            tool_input=tool_args,
                            tool_output=tool_result,
                        )

                        # 将工具结果添加到消息历史
                        messages.append({
                            "tool_call_id": tc["id"],
                            "role": "tool",
                            "name": tool_name,
                            "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                        })
                else:
                    # 模型直接回答，不再调用工具
                    answer = message.get("content", "").strip()
                    self._add_step("system", f"最终回答：{answer}")
                    return AgentResult(
                        status=AgentStatus.COMPLETED,
                        answer=answer,
                        data={"query": query},
                        steps=self.get_steps(),
                    )

            except ServiceError as e:
                logger.warning("DataAgent service error: %s", e.message)
                return AgentResult(
                    status=AgentStatus.FAILED,
                    error_message=e.message,
                    steps=self.get_steps(),
                )
            except Exception as e:
                logger.exception("DataAgent error: %s", e)
                return AgentResult(
                    status=AgentStatus.FAILED,
                    error_message=f"执行出错：{e}",
                    steps=self.get_steps(),
                )

        # 达到最大步数
        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer="分析步骤过多，请尝试简化您的问题。",
            data={"query": query},
            steps=self.get_steps(),
        )

    async def _run_fallback(self, query: str) -> AgentResult:
        """LLM 不可用时按规则直接调用数据工具。

        覆盖常见查询：实时行情、K 线、品种排名、市场状态、品种信息。
        """
        db = self.context.db
        symbol = resolve_symbol(db, query)

        # 1. 排名 / 列表类查询（中文 + 英文）
        # 中文关键词
        cn_ranking = any(k in query for k in ["涨幅", "跌幅", "前", "排名", "排序", "活跃品种"])
        # 英文关键词
        en_ranking = any(k in query.lower() for k in ["top", "ranking", "gainer", "loser", "active", "sort"])
        if cn_ranking or en_ranking:
            sort_by = "change_percent"
            # 中文排序方向
            if "涨幅" in query or "前" in query:
                sort_order = "desc"
            elif "跌幅" in query:
                sort_order = "asc"
            # 英文排序方向
            elif any(k in query.lower() for k in ["top gainer", "top", "gainer", "bull"]):
                sort_order = "desc"
            elif any(k in query.lower() for k in ["top loser", "loser", "bear"]):
                sort_order = "asc"
            else:
                sort_order = "desc"  # 默认降序

            # 成交量排序
            if "成交量" in query or "成交" in query or "volume" in query.lower():
                sort_by = "volume"
            # 提取类别
            category = None
            for cat in ["有色金属", "黑色系", "贵金属", "能源化工", "农产品"]:
                if cat in query:
                    category = cat
                    break
            # 提取数量
            import re
            limit_match = re.search(r"(\d+)", query)
            limit = int(limit_match.group(1)) if limit_match else 5

            result = data_tools._list_active_varieties(
                db,
                category=category,
                sort_by=sort_by,
                sort_order=sort_order,
                limit=limit,
            )
            self._add_step("action", "调用工具：list_active_varieties", tool_name="list_active_varieties", tool_input={"category": category, "sort_by": sort_by, "sort_order": sort_order, "limit": limit})
            self._add_step("observation", f"工具返回结果：{result}", tool_name="list_active_varieties", tool_input={"category": category, "sort_by": sort_by, "sort_order": sort_order, "limit": limit}, tool_output=result)

            lines = [f"{'类别：' + category + ' ' if category else ''}品种排名（按 {sort_by} {'降序' if sort_order == 'desc' else '升序'}）："]
            label = "Ranking" if any(k in query.lower() for k in ["top", "ranking", "gainer", "loser"]) else "品种排名"
            lines = [f"{'Category: ' + category + ' | ' if category else ''}{label} (sort by {sort_by} {'DESC' if sort_order == 'desc' else 'ASC'}):"]
            for i, item in enumerate(result, 1):
                lines.append(
                    f"{i}. {item.get('name', item.get('symbol'))} ({item.get('symbol')}): "
                    f"最新价 {item.get('current_price', '—')}，涨跌幅 {item.get('change_percent', '—')}%，成交量 {item.get('volume', '—')}"
                )
            answer = "\n".join(lines)
            return AgentResult(
                status=AgentStatus.COMPLETED,
                answer=answer,
                data={"query": query, "result": result},
                steps=self.get_steps(),
            )

        # 2. 市场状态
        if any(k in query for k in ["市场状态", "交易时间", "是否开盘", "开盘"]):
            result = data_tools._get_market_status(db)
            self._add_step("action", "调用工具：get_market_status", tool_name="get_market_status", tool_input={})
            self._add_step("observation", f"工具返回结果：{result}", tool_name="get_market_status", tool_input={}, tool_output=result)
            answer = f"当前日期：{result.get('date')}，是否交易日：{result.get('is_trading_day')}，当前时段：{result.get('current_session')}，下一交易日：{result.get('next_trade_date') or '—'}。"
            return AgentResult(
                status=AgentStatus.COMPLETED,
                answer=answer,
                data={"query": query, "result": result},
                steps=self.get_steps(),
            )

        # 3. 无品种识别时返回提示
        if not symbol:
            error_message = "无法识别查询中的品种代码或类别，请提供品种代码（如 RB、AU）或品种名称。"
            self._add_step("error", error_message)
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_message,
                steps=self.get_steps(),
            )

        # 4. K 线 / 历史走势
        if any(k in query for k in ["K线", "k线", "历史", "走势", "日线", "周线", "小时线", "分钟线"]):
            import re
            period_map = {"日线": "1d", "周线": "1w", "小时线": "1h", "1小时": "1h", "30分钟": "30m", "15分钟": "15m", "5分钟": "5m", "1分钟": "1m"}
            period = "1d"
            for k, v in period_map.items():
                if k in query:
                    period = v
                    break
            limit_match = re.search(r"(\d+)", query)
            limit = int(limit_match.group(1)) if limit_match else 60
            result = data_tools._get_kline_data(db, symbol, period=period, limit=limit)
            self._add_step("action", f"调用工具：get_kline_data ({symbol})", tool_name="get_kline_data", tool_input={"symbol": symbol, "period": period, "limit": limit})
            self._add_step("observation", f"获取 K 线 {len(result)} 根", tool_name="get_kline_data", tool_input={"symbol": symbol, "period": period, "limit": limit}, tool_output=result)

            if not result:
                answer = f"未找到 {symbol} 的 K 线数据。"
            else:
                latest = result[-1]
                answer = (
                    f"{symbol} 最近 {len(result)} 根 {period} K 线：\n"
                    f"最新：开 {latest['open']} / 高 {latest['high']} / 低 {latest['low']} / 收 {latest['close']}，成交量 {latest['volume']}\n"
                    f"区间：{result[0]['time'][:10]} ~ {latest['time'][:10]}"
                )
            return AgentResult(
                status=AgentStatus.COMPLETED,
                answer=answer,
                data={"query": query, "symbol": symbol, "result": result},
                steps=self.get_steps(),
            )

        # 5. 默认：品种信息 + 实时行情
        variety_info = data_tools._get_variety_info(db, symbol)
        quote = data_tools._get_realtime_quote(db, symbol)
        self._add_step("action", f"调用工具：get_variety_info / get_realtime_quote ({symbol})", tool_name="get_realtime_quote", tool_input={"symbol": symbol})
        self._add_step("observation", f"品种信息：{variety_info}；行情：{quote}", tool_name="get_realtime_quote", tool_input={"symbol": symbol}, tool_output={"variety_info": variety_info, "quote": quote})

        if not variety_info:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"未找到品种 {symbol}",
                steps=self.get_steps(),
            )

        name = variety_info.get("name", symbol)
        exchange = variety_info.get("exchange", "—")
        current = quote.get("current_price", "—") if quote else "—"
        change = quote.get("change_percent", "—") if quote else "—"
        volume = quote.get("volume", "—") if quote else "—"
        answer = (
            f"{name} ({symbol}) · 交易所：{exchange}\n"
            f"最新价：{current}，涨跌幅：{change}%，成交量：{volume}"
        )
        data: dict[str, Any] = {"query": query, "symbol": symbol}
        if quote:
            data.update(quote)
        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=answer,
            data=data,
            steps=self.get_steps(),
        )

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行数据查询任务。

        每轮 thought / action / observation 都会 yield 事件，
        前端可实时展示工具调用过程。
        """
        if not self._llm.is_configured:
            thought_step = self._add_step("thought", "LLM 未配置，使用规则化兜底路径")
            yield AgentEvent(
                event_type=AgentEventType.THOUGHT,
                step_number=thought_step.step_number,
                role=thought_step.role,
                content=thought_step.content,
            ).to_dict()

            result = await self._run_fallback(query)
            for step in result.steps[1:]:
                yield AgentEvent(
                    event_type=AgentEventType.ACTION if step.role == "action" else AgentEventType.OBSERVATION if step.role == "observation" else AgentEventType.THOUGHT,
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
                    content=result.error_message or "数据查询失败",
                    error_message=result.error_message,
                    result=result.to_dict(),
                ).to_dict()
            return

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._build_system_prompt(query)},
            {"role": "user", "content": query},
        ]

        for step in range(_MAX_STEPS):
            try:
                message = await self._llm.chat_completion(
                    messages,
                    tools=self._registry.get_openai_schemas(),
                    tool_choice="auto",
                    temperature=0.3,
                    max_tokens=2048,
                )

                tool_calls = message.get("tool_calls")
                if tool_calls:
                    thought_step = self._add_step("thought", f"第 {step + 1} 步：决定调用工具")
                    yield AgentEvent(
                        event_type=AgentEventType.THOUGHT,
                        step_number=thought_step.step_number,
                        role=thought_step.role,
                        content=thought_step.content,
                    ).to_dict()
                    messages.append(message)

                    for tc in tool_calls:
                        tool_name = tc["function"]["name"]
                        tool_args = json.loads(tc["function"].get("arguments") or "{}")

                        action_step = self._add_step(
                            "action",
                            f"调用工具：{tool_name}",
                            tool_name=tool_name,
                            tool_input=tool_args,
                        )
                        yield AgentEvent(
                            event_type=AgentEventType.ACTION,
                            step_number=action_step.step_number,
                            role=action_step.role,
                            content=action_step.content,
                            tool_name=tool_name,
                            tool_input=tool_args,
                        ).to_dict()

                        tool_result = await self._registry.execute(tool_name, self.context, tool_args)

                        observation_step = self._add_step(
                            "observation",
                            f"工具返回结果：{tool_result}",
                            tool_name=tool_name,
                            tool_input=tool_args,
                            tool_output=tool_result,
                        )
                        yield AgentEvent(
                            event_type=AgentEventType.OBSERVATION,
                            step_number=observation_step.step_number,
                            role=observation_step.role,
                            content=observation_step.content,
                            tool_name=tool_name,
                            tool_input=tool_args,
                            tool_output=tool_result,
                        ).to_dict()

                        messages.append({
                            "tool_call_id": tc["id"],
                            "role": "tool",
                            "name": tool_name,
                            "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                        })
                else:
                    answer = message.get("content", "").strip()
                    self._add_step("system", f"最终回答：{answer}")
                    result = AgentResult(
                        status=AgentStatus.COMPLETED,
                        answer=answer,
                        data={"query": query},
                        steps=self.get_steps(),
                    )
                    yield AgentEvent(
                        event_type=AgentEventType.RESULT,
                        content=answer,
                        result=result.to_dict(),
                    ).to_dict()
                    return

            except ServiceError as e:
                logger.warning("DataAgent service error: %s", e.message)
                error_message = e.message
                self._add_step("error", error_message)
                yield AgentEvent(
                    event_type=AgentEventType.ERROR,
                    content=error_message,
                    error_message=error_message,
                ).to_dict()
                return
            except Exception as e:
                logger.exception("DataAgent error: %s", e)
                error_message = f"执行出错：{e}"
                self._add_step("error", error_message)
                yield AgentEvent(
                    event_type=AgentEventType.ERROR,
                    content=error_message,
                    error_message=error_message,
                ).to_dict()
                return

        # 达到最大步数
        answer = "分析步骤过多，请尝试简化您的问题。"
        self._add_step("system", answer)
        result = AgentResult(
            status=AgentStatus.COMPLETED,
            answer=answer,
            data={"query": query},
            steps=self.get_steps(),
        )
        yield AgentEvent(
            event_type=AgentEventType.RESULT,
            content=answer,
            result=result.to_dict(),
        ).to_dict()
