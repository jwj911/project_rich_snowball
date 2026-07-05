"""策略进化 API 路由。

提供进化运行历史、策略生命周期追踪和衰减评估端点。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import (
    StrategyDB,
    StrategyEvolutionRunDB,
    StrategyGenerationDB,
    StrategyLifecycleDB,
    UserDB,
)
from schemas import (
    DecayEvaluationRequest,
    DecayEvaluationResponse,
    EvolutionRunDetailResponse,
    EvolutionRunListResponse,
    EvolutionRunResponse,
    GenerationSnapshotResponse,
    LifecycleComparisonItem,
    LifecycleComparisonRequest,
    LifecycleComparisonResponse,
    StrategyLifecycleResponse,
)
from services.agent.evolution.strategy_lifecycle import StrategyLifecycleManager

logger = logging.getLogger("routers.evolution")
router = APIRouter(prefix="/api/evolution", tags=["evolution"])


# ---------------------------------------------------------------------------
# 进化运行历史
# ---------------------------------------------------------------------------


@router.get("/runs", response_model=EvolutionRunListResponse)
def list_evolution_runs(
    symbol: str | None = Query(None, description="品种代码过滤"),
    status: str | None = Query(None, description="状态过滤 (pending/running/completed/failed)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取当前用户的进化运行记录列表。"""
    q = db.query(StrategyEvolutionRunDB).filter(
        StrategyEvolutionRunDB.user_id == current_user.id
    )

    if symbol:
        q = q.filter(StrategyEvolutionRunDB.symbol == symbol.upper())
    if status:
        q = q.filter(StrategyEvolutionRunDB.status == status)

    total = q.count()
    runs = q.order_by(StrategyEvolutionRunDB.created_at.desc()).offset(skip).limit(limit).all()

    return EvolutionRunListResponse(
        items=[_run_to_response(r) for r in runs],
        total=total,
    )


@router.get("/runs/{run_id}", response_model=EvolutionRunDetailResponse)
def get_evolution_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取单次进化运行详情（含代际快照）。"""
    run = db.query(StrategyEvolutionRunDB).filter(
        StrategyEvolutionRunDB.id == run_id,
        StrategyEvolutionRunDB.user_id == current_user.id,
    ).first()

    if run is None:
        raise HTTPException(status_code=404, detail="进化运行记录不存在")

    result = _run_to_response(run)
    result_dict = result.model_dump()

    # 加载代际快照
    gens = (
        db.query(StrategyGenerationDB)
        .filter(StrategyGenerationDB.evolution_run_id == run_id)
        .order_by(StrategyGenerationDB.generation_number.asc())
        .all()
    )

    result_dict["generations_snapshots"] = [
        GenerationSnapshotResponse(
            id=g.id,
            generation_number=g.generation_number,
            best_fitness=float(g.best_fitness) if g.best_fitness is not None else None,
            avg_fitness=float(g.avg_fitness) if g.avg_fitness is not None else None,
            diversity_score=float(g.diversity_score) if g.diversity_score is not None else None,
            created_at=g.created_at.isoformat() if g.created_at else None,
        )
        for g in gens
    ]

    return EvolutionRunDetailResponse(**result_dict)


# ---------------------------------------------------------------------------
# 策略生命周期
# ---------------------------------------------------------------------------


@router.get("/lifecycles", response_model=list[StrategyLifecycleResponse])
def list_lifecycles(
    status: str | None = Query(None, description="状态过滤"),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取当前用户所有策略的生命周期记录。"""
    lifecycles = (
        db.query(StrategyLifecycleDB)
        .join(StrategyDB, StrategyLifecycleDB.strategy_id == StrategyDB.id)
        .filter(StrategyDB.user_id == current_user.id)
        .order_by(StrategyLifecycleDB.updated_at.desc())
        .all()
    )

    if status:
        lifecycles = [lc for lc in lifecycles if lc.status == status]

    return [_lifecycle_to_response(lc) for lc in lifecycles]


@router.get("/lifecycle/{strategy_id}", response_model=StrategyLifecycleResponse)
def get_lifecycle(
    strategy_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取单个策略的生命周期详情。"""
    strategy = db.query(StrategyDB).filter(
        StrategyDB.id == strategy_id,
        StrategyDB.user_id == current_user.id,
    ).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="策略不存在")

    lifecycle = db.query(StrategyLifecycleDB).filter(
        StrategyLifecycleDB.strategy_id == strategy_id,
    ).first()

    if lifecycle is None:
        return StrategyLifecycleResponse(
            id=0,
            strategy_id=strategy_id,
            source="manual",
            status="active",
        )

    return _lifecycle_to_response(lifecycle)


# ---------------------------------------------------------------------------
# 退化评估
# ---------------------------------------------------------------------------


@router.post("/evaluate-decay", response_model=DecayEvaluationResponse)
def evaluate_decay(
    body: DecayEvaluationRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """评估策略退化程度。"""
    strategy = db.query(StrategyDB).filter(
        StrategyDB.id == body.strategy_id,
        StrategyDB.user_id == current_user.id,
    ).first()
    if strategy is None:
        raise HTTPException(status_code=404, detail="策略不存在")

    result = StrategyLifecycleManager.evaluate_decay(
        db, body.strategy_id, recent_metrics=body.recent_metrics,
    )
    return DecayEvaluationResponse(
        strategy_id=body.strategy_id,
        decay_score=result["decay_score"],
        status=result["status"],
        recommended_action=result["recommended_action"],
        details=result["details"],
    )


@router.post("/compare", response_model=LifecycleComparisonResponse)
def compare_lifecycles(
    body: LifecycleComparisonRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """对比多个策略的生命周期状态。"""
    if len(body.strategy_ids) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 个策略进行对比")
    if len(body.strategy_ids) > 20:
        raise HTTPException(status_code=400, detail="最多支持 20 个策略同时对比")

    items = StrategyLifecycleManager.compare_strategies(db, body.strategy_ids)
    return LifecycleComparisonResponse(
        items=[LifecycleComparisonItem(**item) for item in items],
    )


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _run_to_response(run: StrategyEvolutionRunDB) -> EvolutionRunResponse:
    """将 ORM 对象转换为响应模型。"""
    return EvolutionRunResponse(
        id=run.id,
        user_id=run.user_id,
        symbol=run.symbol,
        config_json=run.config_json,
        status=run.status,
        generations=run.generations,
        population_size=run.population_size,
        best_strategy_id=run.best_strategy_id,
        summary_json=run.summary_json,
        error_message=run.error_message,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        created_at=run.created_at.isoformat() if run.created_at else None,
    )


def _lifecycle_to_response(lc: StrategyLifecycleDB) -> StrategyLifecycleResponse:
    """将生命周期 ORM 对象转换为响应模型。"""

    def _parse_json(raw: str | None) -> dict[str, Any] | None:
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    return StrategyLifecycleResponse(
        id=lc.id,
        strategy_id=lc.strategy_id,
        source=lc.source,
        status=lc.status,
        evolution_run_id=lc.evolution_run_id,
        in_sample_metrics=_parse_json(lc.in_sample_metrics),
        out_of_sample_metrics=_parse_json(lc.out_of_sample_metrics),
        walk_forward_metrics=_parse_json(lc.walk_forward_metrics),
        decay_score=float(lc.decay_score) if lc.decay_score is not None else None,
        performance_trend=float(lc.performance_trend) if lc.performance_trend is not None else None,
        last_evaluated_at=lc.last_evaluated_at.isoformat() if lc.last_evaluated_at else None,
        created_at=lc.created_at.isoformat() if lc.created_at else None,
        updated_at=lc.updated_at.isoformat() if lc.updated_at else None,
    )
