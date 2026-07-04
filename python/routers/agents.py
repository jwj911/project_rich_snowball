"""Agent 端点。

提供 Agent 任务提交、状态查询、流式对话等接口。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from errors import ErrorCode
from models import AgentTaskDB, UserDB
from schemas import AgentChatRequest, AgentTaskCreate, AgentTaskResponse
from services.agent.context import AgentContext
from services.agent.core import Agent
from services.agent.data_agent import DataAgent
from services.agent.executor import AgentExecutor
from services.agent.risk_management_agent import RiskManagementAgent
from services.agent.tech_analysis_agent import TechAnalysisAgent
from services.domain.exceptions import NotFoundError, ServiceError

router = APIRouter(prefix="/api/agents", tags=["AI Agent"])


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
        "agent_type": task.agent_type,
        "query": task.query,
        "status": task.status,
        "result": result,
        "error_message": task.error_message,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "created_at": task.created_at,
        "steps": steps,
    }


def _build_agent(agent_type: str, context: AgentContext) -> Agent:
    """根据类型创建 Agent 实例。"""
    if agent_type == "data":
        return DataAgent(context)
    if agent_type == "tech_analysis":
        return TechAnalysisAgent(context)
    if agent_type == "risk_management":
        return RiskManagementAgent(context)
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

    返回完整执行结果。
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
        task_id = executor.create_task(data.agent_type, data.content)
        context = AgentContext(db=db, user_id=current_user.id, task_id=task_id)

        try:
            agent = _build_agent(data.agent_type, context)
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
