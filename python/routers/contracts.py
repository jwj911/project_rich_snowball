from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import ContractRolloverDB, FutContractDB, UserDB, VarietyDB
from schemas import ContractResponse, ContractRolloverResponse, KlineResponse
from services.domain.kline_service import KlineService
from utils import ensure_utc

router = APIRouter(prefix="/api/contracts", tags=["合约"])


def _get_kline_service(db: Session = Depends(get_db)) -> KlineService:
    return KlineService(db)


@router.get("", response_model=list[ContractResponse])
def list_contracts(
    variety_id: int | None = Query(None, ge=1),
    exchange: str | None = Query(None, max_length=20),
    active_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """列出期货合约，支持按品种、交易所筛选。"""
    q = db.query(FutContractDB)
    if variety_id:
        # variety_id 不在 FutContractDB 中，通过 fut_code 关联
        variety = db.query(VarietyDB).filter(VarietyDB.id == variety_id).first()
        if variety:
            q = q.filter(FutContractDB.fut_code == variety.symbol)
    if exchange:
        q = q.filter(FutContractDB.exchange == exchange)
    if active_only:
        q = q.filter(FutContractDB.is_active.is_(True))
    return q.order_by(FutContractDB.delist_date.desc()).offset(skip).limit(limit).all()


@router.get("/rollovers", response_model=list[ContractRolloverResponse])
def list_contract_rollovers(
    variety_id: int = Query(..., ge=1, description="品种 ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取某品种的合约切换历史。"""
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


@router.get("/{contract_id}", response_model=ContractResponse)
def get_contract(contract_id: int, db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user_dependency)):
    """获取单个合约详情。"""
    c = db.query(FutContractDB).filter(FutContractDB.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="合约不存在")
    return c


@router.get("/{contract_id}/kline", response_model=list[KlineResponse])
def get_contract_kline(
    contract_id: int,
    period: str = Query("D", pattern=r"^(D|W|M|5|15|30|60|1m|5m|15m|30m|1h|1d|1w)$"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    service: KlineService = Depends(_get_kline_service),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取单个合约的 K 线数据。"""
    return service.get_contract_klines(
        contract_id, period=period, start=ensure_utc(start), end=ensure_utc(end), limit=limit
    )
