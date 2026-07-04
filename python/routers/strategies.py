"""策略管理路由。

提供策略 CRUD 和回测触发入口，打通 StrategyCompilerAgent -> StrategyDB -> BacktestAgent 链路。
"""

from __future__ import annotations

import json
import logging
import math
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from errors import ErrorCode
from models import BacktestRunDB, RealtimeQuoteDB, StrategyDB, UserDB, VarietyDB
from schemas import (
    BacktestRunResponse,
    BacktestSignalsResponse,
    OptimizationRunItem,
    StrategyBacktestRequest,
    StrategyCreate,
    StrategyOptimizationRequest,
    StrategyOptimizationResponse,
    StrategyPortfolioPlanRequest,
    StrategyPortfolioPlanResponse,
    StrategyResponse,
)
from services.agent.risk_management.drawdown_control import generate_risk_management_plan
from services.backtest.service import run_dsl_backtest
from services.domain.exceptions import ForbiddenError, NotFoundError, ServiceError

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
    """获取当前用户的策略列表，同时包含系统内置示例策略。"""
    rows = (
        db.query(StrategyDB)
        .filter(
            StrategyDB.is_active.is_(True),
            or_(StrategyDB.user_id == current_user.id, StrategyDB.is_builtin.is_(True)),
        )
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
        raise ServiceError(f"DSL JSON 格式无效：{exc}", code=ErrorCode.VALIDATION_ERROR) from exc

    # 基础校验
    if not dsl_dict.get("entry") or not dsl_dict.get("exit"):
        raise ServiceError("DSL 缺少 entry 或 exit 条件", code=ErrorCode.VALIDATION_ERROR)

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
    """获取策略详情。系统内置策略对所有用户可见。"""
    row = db.query(StrategyDB).filter(StrategyDB.id == strategy_id).first()
    if not row:
        raise NotFoundError("策略不存在", code=ErrorCode.NOT_FOUND)
    if row.user_id != current_user.id and not row.is_builtin:
        raise ForbiddenError("无权访问该策略")
    return row


@router.delete("/{strategy_id}")
def delete_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """软删除策略。系统内置策略不可删除。"""
    row = db.query(StrategyDB).filter(StrategyDB.id == strategy_id).first()
    if not row:
        raise NotFoundError("策略不存在", code=ErrorCode.NOT_FOUND)
    if row.is_builtin:
        raise ForbiddenError("系统内置策略不可删除")
    if row.user_id != current_user.id:
        raise ForbiddenError("无权删除该策略")
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
        raise ForbiddenError("无权访问该策略")

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
        # 创建告警事件
        try:
            from services.alert_events import create_strategy_alert_for_backtest
            create_strategy_alert_for_backtest(
                db,
                strategy_id=strategy.id,
                user_id=current_user.id,
                symbol=strategy.symbol,
                error_message=str(exc),
            )
            db.commit()
        except Exception as alert_exc:
            logger.warning("Failed to create backtest alert: %s", alert_exc)
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
        raise ForbiddenError("无权访问该策略")

    rows = (
        db.query(BacktestRunDB)
        .filter(BacktestRunDB.strategy_id == strategy_id)
        .order_by(BacktestRunDB.created_at.desc())
        .all()
    )
    return rows


# ------------------------------------------------------------------
# 回测信号
# ------------------------------------------------------------------

@router.get("/{strategy_id}/backtests/{backtest_id}/signals", response_model=BacktestSignalsResponse)
def get_backtest_signals(
    strategy_id: int,
    backtest_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取回测的买卖信号列表。"""
    strategy = db.query(StrategyDB).filter(StrategyDB.id == strategy_id).first()
    if not strategy:
        raise NotFoundError("策略不存在", code=ErrorCode.NOT_FOUND)
    if strategy.user_id != current_user.id:
        raise ForbiddenError("无权访问该策略")

    run = db.query(BacktestRunDB).filter(
        BacktestRunDB.id == backtest_id,
        BacktestRunDB.strategy_id == strategy_id,
    ).first()
    if not run:
        raise NotFoundError("回测记录不存在", code=ErrorCode.NOT_FOUND)

    result_json = run.result_json or "{}"
    result = json.loads(result_json)
    signals_raw = result.get("signals", [])
    trades_raw = result.get("trades", [])

    signals = [
        BacktestSignal(
            time=str(s.get("time", "")),
            type=str(s.get("type", "")),
            price=float(s.get("price", 0)),
        )
        for s in signals_raw
        if s.get("type") in ("entry", "exit")
    ]

    return BacktestSignalsResponse(
        strategy_id=strategy_id,
        backtest_id=backtest_id,
        signals=signals,
        trades=trades_raw,
    )

@router.post("/{strategy_id}/portfolio-plan", response_model=StrategyPortfolioPlanResponse)
def generate_strategy_portfolio_plan(
    strategy_id: int,
    params: StrategyPortfolioPlanRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """Generate a rule-based simulated position plan for a saved strategy."""
    strategy = db.query(StrategyDB).filter(StrategyDB.id == strategy_id).first()
    if not strategy:
        raise NotFoundError("策略不存在", code=ErrorCode.NOT_FOUND)
    if strategy.user_id != current_user.id:
        raise ForbiddenError("无权访问该策略")

    variety = db.query(VarietyDB).filter(VarietyDB.symbol == strategy.symbol).first()
    if not variety:
        raise NotFoundError("策略品种不存在", code=ErrorCode.NOT_FOUND)

    quote = db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
    entry_price = params.entry_price or (quote.current_price if quote else None)
    if entry_price is None:
        raise ServiceError("无法获取实时价格，请手动输入入场价", code=ErrorCode.VALIDATION_ERROR)

    entry_float = float(entry_price)
    margin_rate = float(variety.margin_rate) if variety.margin_rate is not None else None
    multiplier = float(variety.multiplier) if variety.multiplier is not None else 10.0
    tick_size = float(variety.tick_size) if variety.tick_size is not None else 1.0

    plan = generate_risk_management_plan(
        account_balance=float(params.account_balance),
        entry_price=entry_float,
        direction=strategy.direction,  # type: ignore[arg-type]
        risk_level=params.risk_level,  # type: ignore[arg-type]
        margin_rate=margin_rate,
        contract_multiplier=multiplier,
        tick_size=tick_size,
    )

    position = plan.position_sizing
    stop_loss = plan.stop_loss
    take_profit = plan.take_profit
    suggested_lots = float(position.get("suggested_lots", 0) or 0)
    suggested_quantity = math.floor(suggested_lots)

    notes = list(plan.notes)
    if suggested_quantity < 1:
        notes.append("建议手数小于 1 手，当前资金或止损距离不适合直接创建模拟持仓。")

    return StrategyPortfolioPlanResponse(
        strategy_id=strategy.id,
        variety_id=variety.id,
        symbol=variety.symbol,
        variety_name=variety.name,
        direction=strategy.direction,
        account_balance=params.account_balance,
        risk_level=params.risk_level,
        entry_price=Decimal(str(entry_float)),
        suggested_lots=suggested_lots,
        suggested_quantity=suggested_quantity,
        can_create=suggested_quantity >= 1,
        stop_loss_price=Decimal(str(stop_loss["stop_loss_price"])),
        take_profit_price=Decimal(str(take_profit["take_profit_price"])),
        margin_required=Decimal(str(position.get("margin_required", 0) or 0)),
        risk_amount=Decimal(str(position.get("risk_amount", 0) or 0)),
        risk_reward_ratio=Decimal(str(take_profit.get("risk_reward_ratio", 0) or 0)),
        notes=notes,
    )



# ------------------------------------------------------------------
# 参数优化引擎
# ------------------------------------------------------------------

@router.post("/{strategy_id}/optimize", response_model=StrategyOptimizationResponse)
def optimize_strategy_params_api(
    strategy_id: int,
    params: StrategyOptimizationRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """对已有策略执行参数网格搜索优化。"""
    strategy = db.query(StrategyDB).filter(StrategyDB.id == strategy_id).first()
    if not strategy:
        raise NotFoundError("策略不存在", code=ErrorCode.NOT_FOUND)
    if strategy.user_id != current_user.id:
        raise ForbiddenError("无权访问该策略")

    dsl = json.loads(strategy.dsl_json)
    entry_conditions = dsl.get("entry", {}).get("conditions", [])
    exit_conditions = dsl.get("exit", {}).get("conditions", [])

    from services.backtest.optimization_engine import optimize_strategy_params

    try:
        result = optimize_strategy_params(
            db,
            symbol=strategy.symbol,
            period=strategy.timeframe,
            direction=strategy.direction,
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            param_space=params.param_space,
            initial_cash=params.initial_cash,
            quantity=params.quantity,
            limit=params.limit,
            top_n=params.top_n,
            metric_weights=params.metric_weights,
        )
    except Exception as exc:
        logger.exception("Optimization failed for strategy %s", strategy_id)
        try:
            from services.alert_events import create_strategy_alert_for_optimization
            create_strategy_alert_for_optimization(
                db,
                strategy_id=strategy.id,
                user_id=current_user.id,
                symbol=strategy.symbol,
                error_message=str(exc),
            )
            db.commit()
        except Exception as alert_exc:
            logger.warning("Failed to create optimization alert: %s", alert_exc)
        raise ServiceError("参数优化失败: " + str(exc), code=ErrorCode.INVALID_INPUT)

    top_results = [
        OptimizationRunItem(
            params=r["params"],
            metrics=r.get("metrics"),
            score=r["score"],
            trades_count=r.get("trades_count", 0),
        )
        for r in result["top_results"]
    ]

    return StrategyOptimizationResponse(
        strategy_id=strategy.id,
        best_params=result["best_params"],
        best_score=result["best_score"],
        best_metrics=result.get("best_metrics"),
        top_results=top_results,
        param_space=result["param_space"],
        total_combinations=result["total_combinations"],
        tested_combinations=result["tested_combinations"],
        runtime_seconds=result["runtime_seconds"],
        sensitivity_matrix=result["sensitivity_matrix"],
    )


def _utc_now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc)
