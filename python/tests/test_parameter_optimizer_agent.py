"""参数优化 Agent 测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from models import UserDB
from services.agent.context import AgentContext
from services.agent.core import AgentStatus
from services.agent.parameter_optimizer_agent import ParameterOptimizerAgent


def _create_user(db_session) -> UserDB:
    user = UserDB(
        username="opt_user",
        email="opt@example.com",
        password_hash="x",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_parameter_optimizer_agent_run_success(db_session):
    """测试参数优化 Agent 正常执行流程。"""
    user = _create_user(db_session)
    context = AgentContext(db_session, user.id)
    agent = ParameterOptimizerAgent(context)

    # Mock StrategyDSL
    mock_dsl = MagicMock()
    mock_dsl.to_dict.return_value = {"name": "test", "universe": ["RB"]}
    mock_dsl.to_json.return_value = "{}"
    mock_dsl.name = "test strategy"
    mock_dsl.universe = ["RB"]
    mock_dsl.timeframe = "1d"
    mock_dsl.direction = "long"

    # Mock OptimizationReport
    mock_report = MagicMock()
    mock_report.to_dict.return_value = {
        "symbol": "RB",
        "strategy_name": "test",
        "total_combinations": 25,
        "valid_results": 20,
        "best_params": {"short_window": 5, "long_window": 20},
        "best_metrics": {"score": 75},
        "results": [],
    }
    mock_report.best_metrics = {"score": 75}
    mock_report.symbol = "RB"
    mock_report.strategy_name = "test"

    with patch("services.agent.parameter_optimizer_agent.StrategyParser") as MockParser:
        parser_instance = MockParser.return_value
        parser_instance.parse.return_value = mock_dsl

        with patch(
            "services.agent.parameter_optimizer_agent.optimize_strategy",
            return_value=mock_report,
        ):
            with patch(
                "services.agent.parameter_optimizer_agent.format_optimization_report",
                return_value="## 优化报告\n\n最佳参数：short=5, long=20",
            ):
                import asyncio

                result = asyncio.run(agent.run("螺纹钢5日上穿20日均线参数优化"))

    assert result.status == AgentStatus.COMPLETED
    assert result.answer == "## 优化报告\n\n最佳参数：short=5, long=20"
    assert result.data is not None
    steps = agent.get_steps()
    assert any(s.role == "thought" for s in steps)
    assert any(s.role == "action" for s in steps)
    assert any(s.role == "system" for s in steps)


def test_parameter_optimizer_agent_run_parse_failure(db_session):
    """测试策略解析失败时返回 FAILED。"""
    user = _create_user(db_session)
    context = AgentContext(db_session, user.id)
    agent = ParameterOptimizerAgent(context)

    with patch("services.agent.parameter_optimizer_agent.StrategyParser") as MockParser:
        parser_instance = MockParser.return_value
        parser_instance.parse.return_value = None

        import asyncio

        result = asyncio.run(agent.run("随便说点什么"))

    assert result.status == AgentStatus.FAILED
    assert "无法识别策略品种" in result.error_message
    steps = agent.get_steps()
    assert any(s.role == "thought" for s in steps)
