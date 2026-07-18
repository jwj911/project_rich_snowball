
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from dependencies import get_current_user_dependency, get_db
from models import (
    ContractRolloverDB,
    FutContractDB,
    FutMainDailyDataDB,
    FutTradeFeeDB,
    UserDB,
    VarietyDB,
)
from schemas import (
    CommentResponse,
    ContractResponse,
    ContractRolloverResponse,
    VarietyDetailResponse,
    VarietyFeeResponse,
    VarietyResponse,
    VarietyWithQuoteResponse,
)
from services.domain.market_data_service import MarketDataService

router = APIRouter(prefix="/api/varieties", tags=["品种"])


@router.get("", response_model=list[VarietyWithQuoteResponse])
def get_varieties(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=1000),
    search: str | None = Query(None, max_length=100),
    category: str | None = Query(None, max_length=50),
    direction: str = Query("all", pattern="^(all|up|down)$"),
    sort_by: str = Query("change_percent", pattern="^(change_percent|volume|current_price)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """品种列表：主力日线优先，实时行情作为 fallback。"""
    from urllib.parse import quote

    items, summary = MarketDataService(db).get_varieties_with_realtime(
        skip=skip,
        limit=limit,
        search=search,
        category=category,
        direction=direction,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    response.headers["X-Total-Count"] = str(summary["total"])
    response.headers["X-Total-Volume"] = str(summary["total_volume"])
    response.headers["X-Up-Count"] = str(summary["up_count"])
    response.headers["X-Down-Count"] = str(summary["down_count"])
    response.headers["X-Categories"] = ",".join(quote(c) for c in summary["categories"])
    return items


@router.get("/{symbol}", response_model=VarietyResponse)
def get_variety(symbol: str, db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user_dependency)):
    v = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not v:
        raise HTTPException(status_code=404, detail="品种不存在")
    return v


@router.get("/{symbol}/detail", response_model=VarietyDetailResponse)
def get_variety_detail(
    symbol: str,
    comment_skip: int = Query(0, ge=0),
    comment_limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """品种详情（含日线行情 + 评论列表），数据来自 fut_daily_data。"""
    from models import CommentDB

    v = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not v:
        raise HTTPException(status_code=404, detail="品种不存在")

    comments = (
        db.query(CommentDB)
        .filter(CommentDB.variety_id == v.id)
        .options(joinedload(CommentDB.user))
        .order_by(CommentDB.created_at.desc())
        .offset(comment_skip)
        .limit(comment_limit)
        .all()
    )

    def _to_float(val):
        return float(val) if val is not None else None

    def _price_precision(tick_size):
        if not tick_size:
            return 2
        ts = float(tick_size)
        s = f"{ts:.10f}".rstrip("0")
        if "." in s:
            return len(s.split(".")[1])
        return 0

    # 取最新日线数据（period='D'）
    d = (
        db.query(FutMainDailyDataDB)
        .filter(FutMainDailyDataDB.variety_id == v.id, FutMainDailyDataDB.period == "D")
        .order_by(desc(FutMainDailyDataDB.trade_date))
        .first()
    )

    change_percent = None
    if d and d.pre_settle is not None and float(d.pre_settle) != 0 and d.settle is not None:
        change_percent = (float(d.settle) - float(d.pre_settle)) / float(d.pre_settle) * 100

    return VarietyDetailResponse(
        id=v.id,
        symbol=v.symbol,
        contract_code=v.contract_code,
        name=v.name,
        exchange=v.exchange,
        category=v.category,
        margin_rate=_to_float(v.margin_rate),
        commission=_to_float(v.commission),
        tick_size=_to_float(v.tick_size),
        current_price=_to_float(d.close_price) if d else None,
        change_percent=change_percent,
        open_price=_to_float(d.open_price) if d else None,
        high=_to_float(d.high_price) if d else None,
        low=_to_float(d.low_price) if d else None,
        close_price=_to_float(d.close_price) if d else None,
        settle=_to_float(d.settle) if d else None,
        volume=d.volume if d else None,
        pre_settlement=_to_float(d.pre_settle) if d else None,
        open_interest=d.open_interest if d else None,
        oi_chg=d.oi_chg if d else None,
        bid1=None,
        ask1=None,
        limit_up=None,
        limit_down=None,
        price_precision=_price_precision(v.tick_size),
        updated_at=d.trade_date if d else None,
        trade_date=d.trade_date if d else None,
        comments=[
            CommentResponse(
                id=c.id,
                variety_id=c.variety_id,
                product_symbol=v.symbol,
                product_name=v.name,
                variety_symbol=v.symbol,
                variety_name=v.name,
                user_id=c.user_id,
                username=c.user.username if c.user else "未知用户",
                content=c.content,
                sentiment=c.sentiment,
                price_level_id=c.price_level_id,
                created_at=c.created_at,
            )
            for c in comments
        ],
    )


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
