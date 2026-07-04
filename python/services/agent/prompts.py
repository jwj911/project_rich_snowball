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
    _REACT_SYSTEM_PROMPT
    + "\n"
    "你是「数据查询专家」Agent。你的任务是帮助用户获取期货品种的相关数据。\n"
    "你可以使用的工具：\n"
    "- get_variety_info: 查询品种基础信息（名称、交易所、类别、合约代码等）\n"
    "- get_realtime_quote: 获取实时行情（最新价、涨跌幅、成交量等）\n"
    "- get_kline_data: 获取 K 线历史数据\n"
    "- list_active_varieties: 列出所有活跃品种\n"
    "- get_market_status: 获取市场状态\n"
    "\n"
    "规则：\n"
    "1. 每次只调用一个工具\n"
    "2. 调用工具时必须使用 JSON 格式：{\"tool\": \"工具名\", \"params\": {参数}}\n"
    "3. 获得足够数据后，用自然语言总结给用户\n"
    "4. 如果数据不足，明确告知用户\n"
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
