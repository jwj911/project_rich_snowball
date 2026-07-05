"""Agent 端点。

提供 Agent 任务提交、状态查询、流式对话等接口。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from errors import ErrorCode
from models import AgentTaskDB, UserDB
from schemas import AgentChatRequest, AgentPermissionHeartbeat, AgentStatusSummary, AgentTaskCreate, AgentTaskResponse
from services.agent.analysis_pipeline_agent import AnalysisPipelineAgent
from services.agent.backtest_agent import BacktestAgent
from services.agent.context import AgentContext
from services.agent.core import Agent
from services.agent.data_agent import DataAgent
from services.agent.data_quality_agent import DataQualityAgent
from services.agent.executor import AgentExecutor
from services.agent.factor_mining_agent import FactorMiningAgent
from services.agent.risk_management_agent import RiskManagementAgent
from services.agent.strategy_compiler_agent import StrategyCompilerAgent
from services.agent.strategy_evolution_agent import StrategyEvolutionAgent
from services.agent.intent_router import IntentRouter
from services.agent.parameter_optimizer_agent import ParameterOptimizerAgent
from services.agent.tech_analysis_agent import TechAnalysisAgent
from services.agent.trader_agent import TraderAgent
from services.domain.exceptions import NotFoundError, ServiceError
from services.llm_config import resolve_llm_config

router = APIRouter(prefix="/api/agents", tags=["AI Agent"])

_AGENT_CAPABILITIES: dict[str, dict[str, Any]] = {
    "data": {"label": "数据助手", "requires_llm": True},
    "data_quality": {"label": "数据质检", "requires_llm": False},
    "tech_analysis": {"label": "技术分析", "requires_llm": False},
    "risk_management": {"label": "风控管理", "requires_llm": False},
    "analysis_pipeline": {"label": "完整分析", "requires_llm": False},
    "backtest": {"label": "策略回测", "requires_llm": False},
    "factor_mining": {"label": "因子评估", "requires_llm": False},
    "strategy_compiler": {"label": "策略编译", "requires_llm": False},
    "parameter_optimizer": {"label": "参数优化", "requires_llm": False},
    "strategy_evolution": {"label": "策略进化", "requires_llm": False},
    "trader": {"label": "交易员", "requires_llm": False},
}


def _capability_status(db: Session | None = None, user_id: int | None = None) -> list[dict[str, Any]]:
    """返回各 Agent 模式的可用性。"""
    llm_configured = resolve_llm_config(db, user_id) is not None
    capabilities = []
    for agent_type, meta in _AGENT_CAPABILITIES.items():
        requires_llm = bool(meta.get("requires_llm"))
        enabled = not requires_llm or llm_configured
        capabilities.append({
            "agent_type": agent_type,
            "label": meta["label"],
            "enabled": enabled,
            "requires_llm": requires_llm,
            "reason": None if enabled else "OPENAI_API_KEY 未配置",
        })
    return capabilities


def _task_to_response(task: AgentTaskDB) -> dict[str, Any]:
    """将 ORM 对象转换为字典。"""
    result = None
    if task.result_json:
        try:
            result = json.loads(task.result_json)
        except json.JSONDecodeError:
            result = None

    steps = []
    for s in task.steps:
        step_data: dict[str, Any] = {
            "id": s.id,
            "task_id": s.task_id,
            "step_number": s.step_number,
            "role": s.role,
            "content": s.content,
            "tool_name": s.tool_name,
            "tool_input": None,
            "tool_output": None,
            "created_at": s.created_at,
        }
        if s.tool_input_json:
            try:
                step_data["tool_input"] = json.loads(s.tool_input_json)
            except json.JSONDecodeError:
                pass
        if s.tool_output_json:
            try:
                step_data["tool_output"] = json.loads(s.tool_output_json)
            except json.JSONDecodeError:
                pass
        steps.append(step_data)

    return {
        "id": task.id,
        "user_id": task.user_id,
        "parent_task_id": task.parent_task_id,
        "agent_type": task.agent_type,
        "query": task.query,
        "status": task.status,
        "result": result,
        "error_message": task.error_message,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "created_at": task.created_at,
        "steps": steps,
        "sub_tasks": [_task_to_response(t) for t in (task.sub_tasks or [])],
    }


def _build_agent(agent_type: str, context: AgentContext) -> Agent:
    """根据类型创建 Agent 实例。"""
    if agent_type == "data":
        return DataAgent(context)
    if agent_type == "data_quality":
        return DataQualityAgent(context)
    if agent_type == "tech_analysis":
        return TechAnalysisAgent(context)
    if agent_type == "risk_management":
        return RiskManagementAgent(context)
    if agent_type == "analysis_pipeline":
        return AnalysisPipelineAgent(context)
    if agent_type == "strategy_compiler":
        return StrategyCompilerAgent(context)
    if agent_type == "factor_mining":
        return FactorMiningAgent(context)
    if agent_type == "backtest":
        return BacktestAgent(context)
    if agent_type == "parameter_optimizer":
        return ParameterOptimizerAgent(context)
    if agent_type == "strategy_evolution":
        return StrategyEvolutionAgent(context)
    if agent_type == "trader":
        return TraderAgent(context)
    raise ServiceError(
        code=ErrorCode.AGENT_INVALID_MODE,
        message=f"暂不支持 Agent 类型：{agent_type}",
        status_code=400,
    )


@router.get("/tasks", response_model=list[AgentTaskResponse])
def list_agent_tasks(
    status: str | None = Query(None, pattern=r"^(pending|running|completed|failed)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """查询当前用户的 Agent 任务列表。"""
    q = db.query(AgentTaskDB).filter(AgentTaskDB.user_id == current_user.id)
    if status:
        q = q.filter(AgentTaskDB.status == status)
    tasks = (
        q.order_by(AgentTaskDB.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_task_to_response(t) for t in tasks]


@router.get("/status", response_model=AgentStatusSummary)
def get_agent_status(
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """获取当前用户 Agent 任务状态与系统能力状态。"""
    rows = (
        db.query(AgentTaskDB.status, func.count(AgentTaskDB.id))
        .filter(AgentTaskDB.user_id == current_user.id)
        .group_by(AgentTaskDB.status)
        .all()
    )
    counts = {status: count for status, count in rows}
    recent_failed = (
        db.query(AgentTaskDB)
        .filter(AgentTaskDB.user_id == current_user.id, AgentTaskDB.status == "failed")
        .order_by(AgentTaskDB.created_at.desc())
        .limit(5)
        .all()
    )
    return {
        "server_time": datetime.now(UTC),
        "llm_configured": resolve_llm_config(db, current_user.id) is not None,
        "total_tasks": sum(counts.values()),
        "running_tasks": counts.get("running", 0),
        "completed_tasks": counts.get("completed", 0),
        "failed_tasks": counts.get("failed", 0),
        "recent_failed_tasks": [_task_to_response(t) for t in recent_failed],
        "capabilities": _capability_status(db, current_user.id),
    }


@router.get("/permission-heartbeat", response_model=AgentPermissionHeartbeat)
def get_agent_permission_heartbeat(
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """返回当前用户对 Agent 系统的权限心跳。"""
    allowed_agent_types = [item["agent_type"] for item in _capability_status(db, current_user.id) if item["enabled"]]
    return {
        "server_time": datetime.now(UTC),
        "authenticated": True,
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "can_create_tasks": True,
        "can_stream_chat": True,
        "can_view_own_tasks": True,
        "can_delete_own_tasks": True,
        "allowed_agent_types": allowed_agent_types,
        "csrf_policy": "POST/PUT/PATCH/DELETE 必须使用 Authorization: Bearer；GET/HEAD 可回退 cookie。",
        "token_transport": "Authorization Bearer 优先；GET/HEAD 支持 access_token cookie。",
    }


@router.get("/tasks/{task_id}", response_model=AgentTaskResponse)
def get_agent_task(
    task_id: int,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """获取单个 Agent 任务详情。"""
    task = db.query(AgentTaskDB).filter(AgentTaskDB.id == task_id).first()
    if not task:
        raise NotFoundError("任务不存在", code=ErrorCode.AGENT_TASK_NOT_FOUND)
    if task.user_id != current_user.id:
        raise ServiceError(
            code=ErrorCode.FORBIDDEN,
            message="无权查看他人任务",
            status_code=403,
        )
    return _task_to_response(task)


@router.post("/tasks")
async def create_agent_task(
    data: AgentTaskCreate,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """创建 Agent 任务并同步执行（简单查询 <3s 场景）。

    返回完整执行结果。对于需要长时间运行的场景，建议使用 SSE /api/agents/chat。
    """
    executor = AgentExecutor(db, current_user.id)
    task_id = executor.create_task(data.agent_type, data.query)

    context = AgentContext(db=db, user_id=current_user.id, task_id=task_id)

    try:
        agent = _build_agent(data.agent_type, context)
    except ServiceError as exc:
        executor.update_task_status(
            task_id,
            "failed",
            error_message=exc.message,
        )
        raise

    result = await executor.execute(agent, data.query, task_id=task_id)

    return _task_to_response(db.get(AgentTaskDB, task_id))


@router.post("/chat")
async def agent_chat(
    data: AgentChatRequest,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """Agent 流式对话接口（SSE）。

    前端通过 EventSource 接收 Agent 的每一步执行过程。
    """
    async def event_stream():
        executor = AgentExecutor(db, current_user.id)

        # 处理 auto 模式：先路由到目标 Agent
        actual_agent_type = data.agent_type
        if data.agent_type == "auto":
            router = IntentRouter(db, current_user.id)
            actual_agent_type = await router.route(data.content)

        task_id = executor.create_task(actual_agent_type, data.content)
        context = AgentContext(db=db, user_id=current_user.id, task_id=task_id)

        try:
            agent = _build_agent(actual_agent_type, context)
        except ServiceError as exc:
            executor.update_task_status(
                task_id,
                "failed",
                error_message=exc.message,
            )
            yield f"event: error\ndata: {json.dumps({'event_type': 'error', 'task_id': task_id, 'error_message': exc.message}, ensure_ascii=False)}\n\n"
            return

        async for event in executor.execute_streaming(agent, data.content, task_id=task_id):
            yield f"event: message\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/tasks/{task_id}", status_code=204)
def delete_agent_task(
    task_id: int,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """删除 Agent 任务（仅 owner）。"""
    task = db.query(AgentTaskDB).filter(AgentTaskDB.id == task_id).first()
    if not task:
        raise NotFoundError("任务不存在", code=ErrorCode.AGENT_TASK_NOT_FOUND)
    if task.user_id != current_user.id:
        raise ServiceError(
            code=ErrorCode.FORBIDDEN,
            message="无权删除他人任务",
            status_code=403,
        )
    db.delete(task)
    db.commit()
    return None
