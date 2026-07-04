"""智能意图路由器。

根据用户查询自动匹配最佳 Agent 类型。
"""

from __future__ import annotations

import json
import logging
import re

from services.agent.llm_client import AgentLLMClient

logger = logging.getLogger(__name__)


class IntentRouter:
    """智能意图路由器。"""

    # 规则映射：正则模式 → agent_type（优先级从高到低）
    _RULE_MAP = [
        (r"参数优化|优化参数|网格搜索|最优参数|参数调优|调参", "parameter_optimizer"),
        (r"回测|策略回测|历史回测|排除|过滤", "backtest"),
        (r"策略编译|策略DSL|策略规则|编译策略", "strategy_compiler"),
        (r"因子评估|因子挖掘|多因子|复合因子|组合因子|ICIR加权|因子组合|IC|rank IC|分层回测", "factor_mining"),
        (r"完整分析|综合分析|全面分析|分析流水线|完整研判", "analysis_pipeline"),
        (r"风控|仓位管理|止损|止盈|回撤|风险控制", "risk_management"),
        (r"技术分析|技术指标|MACD|RSI|KDJ|布林带|均线|技术研判", "tech_analysis"),
        (r"数据质量|数据检查|数据质检|数据完整性|数据缺口", "data_quality"),
        (r"K线|行情|价格|品种|实时|数据查询|数据获取", "data"),
    ]

    _VALID_AGENTS = frozenset(
        {
            "data",
            "data_quality",
            "tech_analysis",
            "risk_management",
            "analysis_pipeline",
            "backtest",
            "factor_mining",
            "strategy_compiler",
            "parameter_optimizer",
        }
    )

    def __init__(self, db, user_id: int) -> None:
        self.db = db
        self.user_id = user_id
        self._llm = AgentLLMClient(db, user_id)

    async def route(self, query: str) -> str:
        """根据用户查询路由到最佳 Agent 类型。"""
        # 1. 规则匹配
        for pattern, agent_type in self._RULE_MAP:
            if re.search(pattern, query):
                return agent_type

        # 2. LLM 兜底
        if self._llm.is_configured:
            try:
                agent_type = await self._llm_route(query)
                if agent_type in self._VALID_AGENTS:
                    return agent_type
            except Exception:
                logger.exception("LLM 路由失败")

        # 3. 默认兜底
        return "data"

    async def _llm_route(self, query: str) -> str:
        """使用 LLM 进行意图路由。"""
        system_prompt = (
            "你是期货助手意图路由器，根据用户查询选择最佳 Agent 类型。"
            "可选类型及描述：\n"
            "- data: 数据查询（行情、K线、品种信息）\n"
            "- data_quality: 数据质量检查（数据完整性、缺口检查）\n"
            "- tech_analysis: 技术分析（MACD、RSI、KDJ、布林带、均线等）\n"
            "- risk_management: 风控管理（仓位、止损、止盈、回撤）\n"
            "- analysis_pipeline: 完整分析（综合数据+技术+风控）\n"
            "- backtest: 策略回测（历史回测、策略验证）\n"
            "- factor_mining: 因子评估（IC、rank IC、分层回测）\n"
            "- strategy_compiler: 策略编译（将自然语言转为策略DSL）\n"
            "- parameter_optimizer: 参数优化（网格搜索、参数调优）\n"
            '请直接返回 JSON，格式：{"agent_type": "xxx"}'
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户查询：{query}\n请返回最佳 agent_type："},
        ]

        result = await self._llm.chat_completion(messages, temperature=0.0, max_tokens=128)
        content = result.get("content", "")

        # 解析 JSON
        try:
            data = json.loads(content)
            return data.get("agent_type", "data")
        except json.JSONDecodeError:
            # 尝试从文本中提取 agent_type
            match = re.search(r'"agent_type"\s*:\s*"([^"]+)"', content)
            if match:
                return match.group(1)
            return "data"
