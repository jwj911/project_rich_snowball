"""策略管理路由。

提供策略 CRUD 和回测触发入口，打通 StrategyCompilerAgent -> StrategyDB -> BacktestAgent 链路。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from errors import ErrorCode
from models import BacktestRunDB, StrategyDB, UserDB
from schemas import BacktestRunResponse, StrategyBacktestRequest, StrategyCreate, StrategyResponse
from services.agent.strategy_compiler_agent import StrategyParser, StrategyValidator
from services.backtest.service import run_dsl_backtest
from services.domain.exceptions import NotFoundError, ServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategies", tags=["策略"])


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

@router.get("", response_model=list[StrategyResponse])
def list_strategies(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取当前用户的策略列表。"""
    rows = (
        db.query(StrategyDB)
        .filter(StrategyDB.user_id == current_user.id, StrategyDB.is_active.is_(True))
        .order_by(StrategyDB.created_at.desc())
        .all()
    )
    return rows


@router.post("", response_model=StrategyResponse)
def create_strategy(
    data: StrategyCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """创建策略（支持从自然语言编译或直接提交 DSL）。"""
    # 校验 DSL JSON 有效性
    try:
        dsl_dict = json.loads(data.dsl_json)
    except json.JSONDecodeError as exc:
        raise ServiceError(f"DSL JSON 格式无效：{exc}", code=ErrorCode.INVALID_INPUT) from exc

    # 基础校验
    if not dsl_dict.get("entry") or not dsl_dict.get("exit"):
        raise ServiceError("DSL 缺少 entry 或 exit 条件", code=ErrorCode.INVALID_INPUT)

    strategy = StrategyDB(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        symbol=data.symbol,
        dsl_json=data.dsl_json,
        timeframe=data.timeframe,
        direction=data.direction,
        is_active=True,
    )
    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return strategy


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取策略详情。"""
    row = db.query(StrategyDB).filter(StrategyDB.id == strategy_id).first()
    if not row:
        raise NotFoundError("策略不存在", code=ErrorCode.NOT_FOUND)
    if row.user_id != current_user.id:
        raise ServiceError("无权访问该策略", code=ErrorCode.FORBIDDEN)
    return row


@router.delete("/{strategy_id}")
def delete_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """软删除策略。"""
    row = db.query(StrategyDB).filter(StrategyDB.id == strategy_id).first()
    if not row:
        raise NotFoundError("策略不存在", code=ErrorCode.NOT_FOUND)
    if row.user_id != current_user.id:
        raise ServiceError("无权删除该策略", code=ErrorCode.FORBIDDEN)
    row.is_active = False
    db.commit()
    return {"message": "策略已删除"}


# ------------------------------------------------------------------
# 回测
# ------------------------------------------------------------------

@router.post("/{strategy_id}/backtest", response_model=BacktestRunResponse)
def run_strategy_backtest_api(
    strategy_id: int,
    params: StrategyBacktestRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """对已有策略执行回测。"""
    strategy = db.query(StrategyDB).filter(StrategyDB.id == strategy_id).first()
    if not strategy:
        raise NotFoundError("策略不存在", code=ErrorCode.NOT_FOUND)
    if strategy.user_id != current_user.id:
        raise ServiceError("无权访问该策略", code=ErrorCode.FORBIDDEN)

    run_record = BacktestRunDB(
        strategy_id=strategy.id,
        user_id=current_user.id,
        query=strategy.name,
        status="running",
    )
    db.add(run_record)
    db.commit()
    db.refresh(run_record)

    try:
        dsl = json.loads(strategy.dsl_json)
        result = run_dsl_backtest(
            db,
            symbol=strategy.symbol,
            period=strategy.timeframe,
            direction=strategy.direction,
            entry_conditions=dsl.get("entry", {}).get("conditions", []),
            exit_conditions=dsl.get("exit", {}).get("conditions", []),
            initial_cash=params.initial_cash,
            quantity=params.quantity,
            limit=params.limit,
        )
        metrics = result["metrics"]
        run_record.result_json = json.dumps(result, ensure_ascii=False)
        run_record.metrics_score = metrics.get("score")
        run_record.trade_count = metrics.get("trade_count")
        run_record.total_return_pct = metrics.get("total_return_pct")
        run_record.max_drawdown_pct = metrics.get("max_drawdown_pct")
        run_record.status = "completed"
    except Exception as exc:
        logger.exception("Backtest failed for strategy %s", strategy_id)
        run_record.status = "failed"
        run_record.error_message = str(exc)
    finally:
        run_record.finished_at = _utc_now()
        db.commit()
        db.refresh(run_record)

    return run_record


@router.get("/{strategy_id}/backtests", response_model=list[BacktestRunResponse])
def list_strategy_backtests(
    strategy_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取策略的回测历史。"""
    strategy = db.query(StrategyDB).filter(StrategyDB.id == strategy_id).first()
    if not strategy:
        raise NotFoundError("策略不存在", code=ErrorCode.NOT_FOUND)
    if strategy.user_id != current_user.id:
        raise ServiceError("无权访问该策略", code=ErrorCode.FORBIDDEN)

    rows = (
        db.query(BacktestRunDB)
        .filter(BacktestRunDB.strategy_id == strategy_id)
        .order_by(BacktestRunDB.created_at.desc())
        .all()
    )
    return rows


# ------------------------------------------------------------------
# 辅助
# ------------------------------------------------------------------

def _utc_now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc)
