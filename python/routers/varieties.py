
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import asc, case, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from dependencies import get_current_user_dependency, get_db
from models import ContractRolloverDB, FutContractDB, FutTradeFeeDB, RealtimeQuoteDB, UserDB, VarietyDB
from schemas import (
    CommentResponse,
    ContractResponse,
    ContractRolloverResponse,
    VarietyDetailResponse,
    VarietyFeeResponse,
    VarietyResponse,
    VarietyWithQuoteResponse,
)

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
    """品种列表（含实时行情），用于替代 /api/products。

    联合查询 VarietyDB + RealtimeQuoteDB，支持搜索/分类/涨跌筛选/排序/分页。
    """
    from urllib.parse import quote

    # 基础查询：只查活跃品种
    q = db.query(VarietyDB).filter(VarietyDB.is_active.is_(True))

    keyword = search.strip() if search else ""
    if keyword:
        pattern = f"%{keyword}%"
        q = q.filter(
            or_(
                VarietyDB.name.ilike(pattern),
                VarietyDB.symbol.ilike(pattern),
                VarietyDB.category.ilike(pattern),
            )
        )

    if category and category != "all":
        q = q.filter(VarietyDB.category == category)

    # 涨跌筛选需要在 RealtimeQuoteDB 上过滤
    if direction == "up":
        q = q.join(RealtimeQuoteDB).filter(
            func.coalesce(RealtimeQuoteDB.change_percent, 0) >= 0
        )
    elif direction == "down":
        q = q.join(RealtimeQuoteDB).filter(
            func.coalesce(RealtimeQuoteDB.change_percent, 0) < 0
        )
    else:
        q = q.outerjoin(RealtimeQuoteDB)

    # 统计（基于当前过滤条件）
    stats_query = q.with_entities(
        func.count(VarietyDB.id),
        func.sum(func.coalesce(RealtimeQuoteDB.volume, 0)),
        func.sum(case((func.coalesce(RealtimeQuoteDB.change_percent, 0) >= 0, 1), else_=0)),
        func.sum(case((func.coalesce(RealtimeQuoteDB.change_percent, 0) < 0, 1), else_=0)),
    )
    total_count, total_volume, up_count, down_count = stats_query.one()

    categories = [
        row[0]
        for row in db.query(VarietyDB.category)
        .filter(VarietyDB.is_active.is_(True), VarietyDB.category.isnot(None), VarietyDB.category != "")
        .distinct()
        .order_by(VarietyDB.category.asc())
        .all()
    ]

    # 排序
    sort_column_map = {
        "change_percent": RealtimeQuoteDB.change_percent,
        "volume": RealtimeQuoteDB.volume,
        "current_price": RealtimeQuoteDB.current_price,
    }
    sort_col = sort_column_map[sort_by]
    sort_expr = (
        desc(func.coalesce(sort_col, 0))
        if sort_order == "desc"
        else asc(func.coalesce(sort_col, 0))
    )

    # 分页取结果，并预加载 realtime
    results = (
        q.options(joinedload(VarietyDB.realtime))
        .order_by(sort_expr, VarietyDB.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    response.headers["X-Total-Count"] = str(total_count or 0)
    response.headers["X-Total-Volume"] = str(total_volume or 0)
    response.headers["X-Up-Count"] = str(up_count or 0)
    response.headers["X-Down-Count"] = str(down_count or 0)
    response.headers["X-Categories"] = ",".join(quote(c) for c in categories)

    # 构造响应（手动映射，因为 VarietyDB 字段名与 VarietyWithQuoteResponse 不完全一致）
    def _to_float(v):
        return float(v) if v is not None else None

    def _price_precision(tick_size):
        if not tick_size:
            return 2
        ts = float(tick_size)
        s = f"{ts:.10f}".rstrip("0")
        if "." in s:
            return len(s.split(".")[1])
        return 0

    return [
        VarietyWithQuoteResponse(
            id=v.id,
            symbol=v.symbol,
            name=v.name,
            category=v.category,
            current_price=_to_float(v.realtime.current_price) if v.realtime else None,
            change_percent=_to_float(v.realtime.change_percent) if v.realtime else None,
            open_price=_to_float(v.realtime.open_price) if v.realtime else None,
            high=_to_float(v.realtime.high) if v.realtime else None,
            low=_to_float(v.realtime.low) if v.realtime else None,
            volume=v.realtime.volume if v.realtime else None,
            limit_up=_to_float(v.realtime.limit_up) if v.realtime else None,
            limit_down=_to_float(v.realtime.limit_down) if v.realtime else None,
            price_precision=_price_precision(v.tick_size),
            margin_rate=_to_float(v.margin_rate),
            commission=_to_float(v.commission),
            updated_at=str(v.realtime.updated_at) if v.realtime and v.realtime.updated_at else None,
        )
        for v in results
    ]


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
    """品种详情（含实时行情 + 评论列表），用于替代 /api/products/{id}。"""
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

    r = v.realtime
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
        current_price=_to_float(r.current_price) if r else None,
        change_percent=_to_float(r.change_percent) if r else None,
        open_price=_to_float(r.open_price) if r else None,
        high=_to_float(r.high) if r else None,
        low=_to_float(r.low) if r else None,
        volume=r.volume if r else None,
        pre_settlement=_to_float(r.pre_settlement) if r else None,
        open_interest=r.open_interest if r else None,
        bid1=_to_float(r.bid1) if r else None,
        ask1=_to_float(r.ask1) if r else None,
        limit_up=_to_float(r.limit_up) if r else None,
        limit_down=_to_float(r.limit_down) if r else None,
        price_precision=_price_precision(v.tick_size),
        updated_at=r.updated_at if r else None,
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
