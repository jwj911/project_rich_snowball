"""交易观点/日记端点。

用户可针对品种发表多空观点，记录目标价、止损价和理由，
支持事后复盘标记状态（open/closed_profit/closed_loss/expired）。
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query  # noqa: F401
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from dependencies import get_current_user_dependency, get_db
from models import OpinionDB, UserDB, VarietyDB
from schemas import OpinionCreate, OpinionResponse, OpinionUpdate

router = APIRouter(prefix="/api/opinions", tags=["交易观点"])


def _to_response(opinion: OpinionDB) -> OpinionResponse:
    """将 ORM 对象转换为响应模型。"""
    variety = opinion.variety
    return OpinionResponse(
        id=opinion.id,
        user_id=opinion.user_id,
        variety_id=opinion.variety_id,
        variety_symbol=variety.symbol if variety else "",
        variety_name=variety.name if variety else "",
        type=opinion.type,
        reason=opinion.reason,
        target_price=opinion.target_price,
        stop_loss=opinion.stop_loss,
        status=opinion.status,
        actual_outcome=opinion.actual_outcome,
        created_at=opinion.created_at,
        closed_at=opinion.closed_at,
    )


@router.get("", response_model=list[OpinionResponse])
def list_opinions(
    variety_id: int | None = Query(None, description="按品种筛选"),
    status: str | None = Query(None, max_length=20, description="按状态筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """查询交易观点列表（登录用户可见全部用户的公开观点）。"""
    q = db.query(OpinionDB).options(joinedload(OpinionDB.variety))
    if variety_id:
        q = q.filter(OpinionDB.variety_id == variety_id)
    if status:
        q = q.filter(OpinionDB.status == status)
    opinions = (
        q.order_by(desc(OpinionDB.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_to_response(o) for o in opinions]


@router.get("/me", response_model=list[OpinionResponse])
def list_my_opinions(
    status: str | None = Query(None, max_length=20, description="按状态筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """查询当前用户的交易观点时间线。"""
    q = db.query(OpinionDB).options(joinedload(OpinionDB.variety)).filter(
        OpinionDB.user_id == current_user.id
    )
    if status:
        q = q.filter(OpinionDB.status == status)
    opinions = (
        q.order_by(desc(OpinionDB.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_to_response(o) for o in opinions]


@router.get("/{opinion_id}", response_model=OpinionResponse)
def get_opinion(
    opinion_id: int,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """获取单条观点详情。"""
    opinion = (
        db.query(OpinionDB)
        .options(joinedload(OpinionDB.variety))
        .filter(OpinionDB.id == opinion_id)
        .first()
    )
    if not opinion:
        raise HTTPException(status_code=404, detail="opinion_not_found")
    return _to_response(opinion)


@router.post("", response_model=OpinionResponse, status_code=201)
def create_opinion(
    data: OpinionCreate,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """创建交易观点。"""
    variety = db.get(VarietyDB, data.variety_id)
    if not variety:
        raise HTTPException(status_code=404, detail="variety_not_found")

    opinion = OpinionDB(
        user_id=current_user.id,
        variety_id=data.variety_id,
        type=data.type,
        reason=data.reason,
        target_price=data.target_price,
        stop_loss=data.stop_loss,
        status="open",
    )
    db.add(opinion)
    db.commit()
    db.refresh(opinion)
    # 手动加载 variety 关系，避免 lazy load 在响应序列化后失效
    opinion.variety = variety
    return _to_response(opinion)


@router.put("/{opinion_id}", response_model=OpinionResponse)
def update_opinion(
    opinion_id: int,
    data: OpinionUpdate,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """更新交易观点（仅 owner）。支持关闭观点和标记复盘结果。"""
    opinion = db.get(OpinionDB, opinion_id)
    if not opinion:
        raise HTTPException(status_code=404, detail="opinion_not_found")
    if opinion.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="not_owner")

    if data.reason is not None:
        opinion.reason = data.reason
    if data.target_price is not None:
        opinion.target_price = data.target_price
    if data.stop_loss is not None:
        opinion.stop_loss = data.stop_loss
    if data.status is not None:
        opinion.status = data.status
        # 如果状态从 open 变为关闭态，自动记录 closed_at
        if data.status != "open" and opinion.closed_at is None:
            opinion.closed_at = datetime.now(UTC)
    if data.actual_outcome is not None:
        opinion.actual_outcome = data.actual_outcome

    db.commit()
    db.refresh(opinion)
    # 确保 variety 关系已加载
    if opinion.variety is None:
        opinion.variety = db.get(VarietyDB, opinion.variety_id)
    return _to_response(opinion)


@router.delete("/{opinion_id}", status_code=204)
def delete_opinion(
    opinion_id: int,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """删除交易观点（仅 owner）。"""
    opinion = db.get(OpinionDB, opinion_id)
    if not opinion:
        raise HTTPException(status_code=404, detail="opinion_not_found")
    if opinion.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="not_owner")
    db.delete(opinion)
    db.commit()
    return None
