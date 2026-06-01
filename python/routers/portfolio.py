"""模拟持仓（Portfolio）端点。

用户可基于观点创建虚拟交易记录，支持盈亏计算与复盘。
"""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query  # noqa: F401
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from dependencies import get_current_user_dependency, get_db
from models import RealtimeQuoteDB, TradeRecordDB, UserDB, VarietyDB
from schemas import TradeRecordClose, TradeRecordCreate, TradeRecordResponse

router = APIRouter(prefix="/api/portfolio", tags=["模拟持仓"])


def _calculate_pnl(direction: str, entry: Decimal, exit_: Decimal, qty: int, multiplier: Decimal | None) -> tuple[Decimal, Decimal]:
    """计算盈亏金额和盈亏百分比。

    Returns:
        (pnl, pnl_percent)
    """
    mult = multiplier or Decimal("1")
    notional = entry * Decimal(qty) * mult
    if direction == "long":
        pnl = (exit_ - entry) * Decimal(qty) * mult
    else:
        pnl = (entry - exit_) * Decimal(qty) * mult
    pnl_percent = (pnl / notional * Decimal("100")) if notional != 0 else Decimal("0")
    return pnl, pnl_percent


def _to_response(record: TradeRecordDB, current_price: Decimal | None = None) -> TradeRecordResponse:
    """将 ORM 对象转换为响应模型，支持浮动盈亏计算。"""
    variety = record.variety
    multiplier = variety.multiplier if variety else None

    pnl = record.pnl
    pnl_percent = record.pnl_percent
    unrealized_pnl = None
    unrealized_pnl_percent = None

    if record.status == "open" and current_price is not None:
        unrealized_pnl, unrealized_pnl_percent = _calculate_pnl(
            record.direction, record.entry_price, current_price, record.quantity, multiplier
        )

    return TradeRecordResponse(
        id=record.id,
        user_id=record.user_id,
        variety_id=record.variety_id,
        variety_symbol=variety.symbol if variety else "",
        variety_name=variety.name if variety else "",
        opinion_id=record.opinion_id,
        direction=record.direction,
        entry_price=record.entry_price,
        exit_price=record.exit_price,
        quantity=record.quantity,
        status=record.status,
        pnl=pnl,
        pnl_percent=pnl_percent,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_percent=unrealized_pnl_percent,
        closed_at=record.closed_at,
        created_at=record.created_at,
    )


@router.get("", response_model=list[TradeRecordResponse])
def list_portfolio(
    status: str | None = Query(None, max_length=10, description="按状态筛选: open/closed"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """查询当前用户的模拟持仓列表（含实时浮动盈亏）。"""
    q = db.query(TradeRecordDB).options(joinedload(TradeRecordDB.variety)).filter(
        TradeRecordDB.user_id == current_user.id
    )
    if status:
        q = q.filter(TradeRecordDB.status == status)
    records = (
        q.order_by(desc(TradeRecordDB.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )

    # 批量查询实时价格用于浮动盈亏计算
    variety_ids = [r.variety_id for r in records if r.status == "open"]
    quotes = {}
    if variety_ids:
        for quote in db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id.in_(variety_ids)).all():
            quotes[quote.variety_id] = quote.current_price

    return [_to_response(r, quotes.get(r.variety_id)) for r in records]


@router.post("", response_model=TradeRecordResponse, status_code=201)
def create_trade(
    data: TradeRecordCreate,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """创建模拟持仓。"""
    variety = db.get(VarietyDB, data.variety_id)
    if not variety:
        raise HTTPException(status_code=404, detail="variety_not_found")

    record = TradeRecordDB(
        user_id=current_user.id,
        variety_id=data.variety_id,
        opinion_id=data.opinion_id,
        direction=data.direction,
        entry_price=data.entry_price,
        quantity=data.quantity,
        status="open",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    record.variety = variety
    return _to_response(record)


@router.post("/{record_id}/close", response_model=TradeRecordResponse)
def close_trade(
    record_id: int,
    data: TradeRecordClose,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """平仓并计算盈亏（仅 owner）。"""
    record = db.get(TradeRecordDB, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="record_not_found")
    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="not_owner")
    if record.status != "open":
        raise HTTPException(status_code=400, detail="already_closed")

    variety = db.get(VarietyDB, record.variety_id)
    multiplier = variety.multiplier if variety else None

    pnl, pnl_percent = _calculate_pnl(
        record.direction, record.entry_price, data.exit_price, record.quantity, multiplier
    )

    record.exit_price = data.exit_price
    record.status = "closed"
    record.pnl = pnl
    record.pnl_percent = pnl_percent
    record.closed_at = datetime.now(UTC)

    db.commit()
    db.refresh(record)
    if record.variety is None:
        record.variety = variety
    return _to_response(record)


@router.delete("/{record_id}", status_code=204)
def delete_trade(
    record_id: int,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """删除持仓记录（仅 owner）。"""
    record = db.get(TradeRecordDB, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="record_not_found")
    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="not_owner")
    db.delete(record)
    db.commit()
    return None
