"""智能意图路由器测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from services.agent.intent_router import IntentRouter


@pytest.fixture
def router(db_session):
    return IntentRouter(db_session, user_id=1)


class TestIntentRouterRules:
    """测试规则匹配层。"""

    def test_route_parameter_optimizer(self, router):
        assert asyncio.run(router.route("帮我参数优化均线策略")) == "parameter_optimizer"
        assert asyncio.run(router.route("网格搜索最优参数")) == "parameter_optimizer"
        assert asyncio.run(router.route("参数调优")) == "parameter_optimizer"

    def test_route_backtest(self, router):
        assert asyncio.run(router.route("回测这个策略")) == "backtest"
        assert asyncio.run(router.route("策略回测")) == "backtest"

    def test_route_strategy_compiler(self, router):
        assert asyncio.run(router.route("编译策略DSL")) == "strategy_compiler"
        assert asyncio.run(router.route("策略规则")) == "strategy_compiler"

    def test_route_factor_mining(self, router):
        assert asyncio.run(router.route("因子评估")) == "factor_mining"
        assert asyncio.run(router.route("rank IC分析")) == "factor_mining"

    def test_route_analysis_pipeline(self, router):
        assert asyncio.run(router.route("完整分析螺纹钢")) == "analysis_pipeline"
        assert asyncio.run(router.route("全面分析")) == "analysis_pipeline"

    def test_route_risk_management(self, router):
        assert asyncio.run(router.route("风控方案")) == "risk_management"
        assert asyncio.run(router.route("止损止盈")) == "risk_management"

    def test_route_tech_analysis(self, router):
        assert asyncio.run(router.route("技术分析")) == "tech_analysis"
        assert asyncio.run(router.route("MACD金叉")) == "tech_analysis"
        assert asyncio.run(router.route("KDJ指标")) == "tech_analysis"

    def test_route_data_quality(self, router):
        assert asyncio.run(router.route("数据质量检查")) == "data_quality"
        assert asyncio.run(router.route("数据完整性")) == "data_quality"

    def test_route_data(self, router):
        assert asyncio.run(router.route("K线数据")) == "data"
        assert asyncio.run(router.route("实时行情")) == "data"
        assert asyncio.run(router.route("价格查询")) == "data"

    def test_route_fallback_to_data(self, router):
        """无匹配时应兜底返回 data。"""
        assert asyncio.run(router.route("hello world")) == "data"
        assert asyncio.run(router.route("")) == "data"

    def test_route_priority_order(self, router):
        """测试规则优先级：parameter_optimizer 应在 data 之前匹配。"""
        assert asyncio.run(router.route("参数优化K线数据")) == "parameter_optimizer"
        assert asyncio.run(router.route("回测技术分析")) == "backtest"


class TestIntentRouterLLM:
    """测试 LLM fallback 层。"""

    def test_llm_fallback_valid(self, router):
        """LLM 返回合法 agent_type 时应采用。"""
        mock_llm = AsyncMock()
        mock_llm.is_configured = True
        mock_llm.chat_completion = AsyncMock(
            return_value={"content": '{"agent_type": "tech_analysis"}'}
        )
        router._llm = mock_llm

        # 清除规则匹配的干扰（用一个不匹配的查询）
        result = asyncio.run(router.route("unmatched_xyz_123"))
        assert result == "tech_analysis"

    def test_llm_fallback_invalid(self, router):
        """LLM 返回非法 agent_type 时应兜底到 data。"""
        mock_llm = AsyncMock()
        mock_llm.is_configured = True
        mock_llm.chat_completion = AsyncMock(
            return_value={"content": '{"agent_type": "invalid_type"}'}
        )
        router._llm = mock_llm

        result = asyncio.run(router.route("unmatched_xyz_456"))
        assert result == "data"

    def test_llm_fallback_malformed_json(self, router):
        """LLM 返回非 JSON 时应尝试提取 agent_type。"""
        mock_llm = AsyncMock()
        mock_llm.is_configured = True
        mock_llm.chat_completion = AsyncMock(
            return_value={"content": '经分析，"agent_type": "risk_management"'}
        )
        router._llm = mock_llm

        result = asyncio.run(router.route("unmatched_xyz_789"))
        assert result == "risk_management"

    def test_llm_fallback_unconfigured(self, router):
        """LLM 未配置时直接兜底到 data。"""
        mock_llm = AsyncMock()
        mock_llm.is_configured = False
        router._llm = mock_llm

        result = asyncio.run(router.route("unmatched_xyz_000"))
        assert result == "data"

    def test_llm_fallback_exception(self, router):
        """LLM 调用异常时应兜底到 data。"""
        mock_llm = AsyncMock()
        mock_llm.is_configured = True
        mock_llm.chat_completion = AsyncMock(side_effect=Exception("LLM error"))
        router._llm = mock_llm

        result = asyncio.run(router.route("unmatched_xyz_111"))
        assert result == "data"
