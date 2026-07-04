"""Agent 系统 Prompt 模板。

所有 Agent 共享的 prompt 构造逻辑，确保风格统一。
"""

from __future__ import annotations

from typing import Any

_REACT_SYSTEM_PROMPT = (
    "你是「期货交流社区」的 AI 助手，专注于期货数据分析与交易辅助。\n"
    "你遵循 ReAct（Reasoning + Acting）模式解决问题：\n"
    "1. 首先理解用户问题，进行推理（Thought）\n"
    "2. 然后选择合适工具获取数据（Action）\n"
    "3. 观察工具返回结果（Observation）\n"
    "4. 重复以上步骤直到能给出最终答案\n"
    "\n"
    "所有分析仅供参考，不构成投资建议。\n"
    "使用中文回答，术语准确，表达简洁专业。\n"
)

_DATA_AGENT_PROMPT = (
    _REACT_SYSTEM_PROMPT + "\n"
    "你是「数据查询专家」Agent。你的任务是帮助用户获取期货品种的相关数据。\n"
    "你可以使用的工具：\n"
    "- get_variety_info: 查询品种基础信息（名称、交易所、类别、合约代码等）\n"
    "- get_realtime_quote: 获取实时行情（最新价、涨跌幅、成交量等）\n"
    "- get_kline_data: 获取 K 线历史数据\n"
    "- get_continuous_klines: 获取连续 K 线（主力切换拼接，适合长期趋势分析）\n"
    "- get_main_klines: 获取当前主力合约 K 线\n"
    "- list_active_varieties: 列出所有活跃品种\n"
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
    '2. 调用工具时必须使用 JSON 格式：{"tool": "工具名", "params": {参数}}\n'
    "3. 获得足够数据后，用自然语言总结给用户\n"
    "4. 如果数据不足，明确告知用户\n"
    "5. 当用户询问仓单/库存时，优先使用 get_warehouse_receipts\n"
    "6. 当用户询问持仓/主力动向时，优先使用 get_holding_rankings\n"
    "7. 当用户询问保证金/手续费时，优先使用 get_settlement_params\n"
    "8. 当问题超出专用工具范围时，使用 query_database 写 SQL 查询\n"
    "9. 使用 query_database 前如不确定表结构，先调用 list_tables 或 get_table_schema\n"
)


def build_react_prompt(
    query: str,
    tools_description: str,
    history: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """构造 ReAct 风格的 messages 列表。

    Args:
        query: 用户原始查询
        tools_description: 可用工具描述
        history: 历史步骤（thought/action/observation）

    Returns:
        OpenAI 兼容的 messages 列表
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _REACT_SYSTEM_PROMPT + "\n" + tools_description},
    ]

    if history:
        for h in history:
            role = h.get("role", "user")
            content = h.get("content", "")
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": query})
    return messages


def build_data_agent_prompt(query: str, history: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    """构造 DataAgent 专用 prompt。"""
    return build_react_prompt(query, _DATA_AGENT_PROMPT, history)
