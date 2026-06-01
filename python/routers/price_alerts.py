"""价格预警端点。

用户可为品种设置价格触发型预警（above/below）。
实时行情更新时由 scheduler 自动检查触发条件。
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query  # noqa: F401
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from dependencies import get_current_user_dependency, get_db
from models import PriceAlertDB, RealtimeQuoteDB, UserDB, VarietyDB
from schemas import PriceAlertCreate, PriceAlertResponse, PriceAlertUpdate

router = APIRouter(prefix="/api/price-alerts", tags=["价格预警"])


def _to_response(alert: PriceAlertDB) -> PriceAlertResponse:
    """将 ORM 对象转换为响应模型。"""
    variety = alert.variety
    return PriceAlertResponse(
        id=alert.id,
        user_id=alert.user_id,
        variety_id=alert.variety_id,
        variety_symbol=variety.symbol if variety else "",
        variety_name=variety.name if variety else "",
        alert_type=alert.alert_type,
        target_price=alert.target_price,
        is_triggered=alert.is_triggered,
        triggered_at=alert.triggered_at,
        created_at=alert.created_at,
    )


@router.get("", response_model=list[PriceAlertResponse])
def list_price_alerts(
    variety_id: int | None = Query(None, description="按品种筛选"),
    triggered: bool | None = Query(None, description="按触发状态筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """查询当前用户的价格预警列表。"""
    q = db.query(PriceAlertDB).options(joinedload(PriceAlertDB.variety)).filter(
        PriceAlertDB.user_id == current_user.id
    )
    if variety_id:
        q = q.filter(PriceAlertDB.variety_id == variety_id)
    if triggered is not None:
        q = q.filter(PriceAlertDB.is_triggered.is_(triggered))
    alerts = (
        q.order_by(desc(PriceAlertDB.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_to_response(a) for a in alerts]


@router.get("/triggered", response_model=list[PriceAlertResponse])
def list_triggered_alerts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """查询当前用户已触发的价格预警（前端轮询用）。"""
    alerts = (
        db.query(PriceAlertDB)
        .options(joinedload(PriceAlertDB.variety))
        .filter(
            PriceAlertDB.user_id == current_user.id,
            PriceAlertDB.is_triggered.is_(True),
        )
        .order_by(desc(PriceAlertDB.triggered_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_to_response(a) for a in alerts]


@router.post("", response_model=PriceAlertResponse, status_code=201)
def create_price_alert(
    data: PriceAlertCreate,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """创建价格预警。"""
    variety = db.get(VarietyDB, data.variety_id)
    if not variety:
        raise HTTPException(status_code=404, detail="variety_not_found")

    alert = PriceAlertDB(
        user_id=current_user.id,
        variety_id=data.variety_id,
        alert_type=data.alert_type,
        target_price=data.target_price,
        is_triggered=False,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    alert.variety = variety
    return _to_response(alert)


@router.put("/{alert_id}", response_model=PriceAlertResponse)
def update_price_alert(
    alert_id: int,
    data: PriceAlertUpdate,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """更新价格预警（仅 owner）。支持手动重置触发状态。"""
    alert = db.get(PriceAlertDB, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="alert_not_found")
    if alert.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="not_owner")

    if data.target_price is not None:
        alert.target_price = data.target_price
        # 修改目标价后重置触发状态
        alert.is_triggered = False
        alert.triggered_at = None
    if data.is_triggered is not None:
        alert.is_triggered = data.is_triggered
        if data.is_triggered:
            alert.triggered_at = datetime.now(UTC)
        else:
            alert.triggered_at = None

    db.commit()
    db.refresh(alert)
    if alert.variety is None:
        alert.variety = db.get(VarietyDB, alert.variety_id)
    return _to_response(alert)


@router.delete("/{alert_id}", status_code=204)
def delete_price_alert(
    alert_id: int,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """删除价格预警（仅 owner）。"""
    alert = db.get(PriceAlertDB, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="alert_not_found")
    if alert.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="not_owner")
    db.delete(alert)
    db.commit()
    return None
