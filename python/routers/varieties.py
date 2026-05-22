
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import ContractRolloverDB, FutContractDB, FutTradeFeeDB, UserDB, VarietyDB
from schemas import ContractResponse, ContractRolloverResponse, VarietyFeeResponse, VarietyResponse

router = APIRouter(prefix="/api/varieties", tags=["品种"])


@router.get("", response_model=list[VarietyResponse])
def get_varieties(
    category: str | None = None,
    search: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
    response: Response = None,
):
    q = db.query(VarietyDB)
    if category:
        q = q.filter(VarietyDB.category == category)
    if search:
        q = q.filter(VarietyDB.name.contains(search))
    total = q.count()
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
    return q.offset(skip).limit(limit).all()


@router.get("/{symbol}", response_model=VarietyResponse)
def get_variety(symbol: str, db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user_dependency)):
    v = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not v:
        raise HTTPException(status_code=404, detail="品种不存在")
    return v


@router.get("/{variety_id}/contracts", response_model=list[ContractResponse], deprecated=True)
def get_variety_contracts(
    variety_id: int,
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取某品种下的所有合约（已废弃，请使用 GET /api/contracts?variety_id=X）。"""
    variety = db.query(VarietyDB).filter(VarietyDB.id == variety_id).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    q = db.query(FutContractDB).filter(FutContractDB.fut_code == variety.symbol)
    if active_only:
        q = q.filter(FutContractDB.is_active.is_(True))
    return q.order_by(FutContractDB.delist_date.desc()).all()


@router.get("/{variety_id}/rollovers", response_model=list[ContractRolloverResponse], deprecated=True)
def get_variety_rollovers(
    variety_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取某品种的合约切换历史（已废弃，请使用 GET /api/contracts/rollovers?variety_id=X）。"""
    variety = db.query(VarietyDB).filter(VarietyDB.id == variety_id).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    return (
        db.query(ContractRolloverDB)
        .filter(ContractRolloverDB.variety_id == variety_id)
        .order_by(ContractRolloverDB.effective_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{symbol}/fees", response_model=VarietyFeeResponse)
def get_variety_fees(
    symbol: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取品种最新的手续费与保证金数据。"""
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    # 优先精确匹配 contract_code
    fee = (
        db.query(FutTradeFeeDB)
        .filter(FutTradeFeeDB.contract_code == variety.contract_code)
        .order_by(FutTradeFeeDB.fee_updated_at.desc())
        .first()
    )
    if not fee:
        # fallback：按品种前缀匹配最新记录
        fee = (
            db.query(FutTradeFeeDB)
            .filter(FutTradeFeeDB.contract_code.like(f"{symbol}%"))
            .order_by(FutTradeFeeDB.fee_updated_at.desc())
            .first()
        )

    def _to_float(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    def _pick_fee(rate, fixed):
        rate_f = _to_float(rate)
        if rate_f is not None:
            return rate_f
        return _to_float(fixed)

    # 有 FutTradeFeeDB 记录时优先使用；无记录时用 VarietyDB 基础数据兜底
    if fee:
        return VarietyFeeResponse(
            symbol=variety.symbol,
            name=variety.name,
            exchange=variety.exchange,
            margin_rate=_to_float(variety.margin_rate),
            margin_amount=_to_float(fee.margin_per_hand),
            commission_open=_pick_fee(fee.fee_open_rate, fee.fee_open_fixed),
            commission_close=_pick_fee(fee.fee_close_yesterday_rate, fee.fee_close_yesterday_fixed),
            commission_close_today=_pick_fee(fee.fee_close_today_rate, fee.fee_close_today_fixed),
            unit=fee.remark,
            updated_at=fee.fee_updated_at,
        )

    # fallback：使用 variety 基础保证金/手续费构造简化响应
    return VarietyFeeResponse(
        symbol=variety.symbol,
        name=variety.name,
        exchange=variety.exchange,
        margin_rate=_to_float(variety.margin_rate),
        margin_amount=None,
        commission_open=_to_float(variety.commission),
        commission_close=None,
        commission_close_today=None,
        unit=None,
        updated_at=None,
    )
