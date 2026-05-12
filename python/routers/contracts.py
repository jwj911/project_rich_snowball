from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from models import FutContractDB, KlineDataDB, ContractRolloverDB, VarietyDB
from schemas import ContractResponse, ContractRolloverResponse, KlineResponse
from dependencies import get_db

router = APIRouter(prefix="/api", tags=["合约"])


@router.get("/contracts", response_model=List[ContractResponse])
def list_contracts(
    variety_id: Optional[int] = Query(None, ge=1),
    exchange: Optional[str] = Query(None),
    active_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
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


@router.get("/contracts/{contract_id}", response_model=ContractResponse)
def get_contract(contract_id: int, db: Session = Depends(get_db)):
    """获取单个合约详情。"""
    c = db.query(FutContractDB).filter(FutContractDB.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="合约不存在")
    return c


@router.get("/contracts/{contract_id}/kline", response_model=List[KlineResponse])
def get_contract_kline(
    contract_id: int,
    period: str = Query("D", pattern=r"^(D|W|M|5|15|30|60)$"),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db)
):
    """获取单个合约的 K 线数据。"""
    c = db.query(FutContractDB).filter(FutContractDB.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="合约不存在")

    q = (
        db.query(KlineDataDB)
        .filter(KlineDataDB.contract_id == contract_id)
        .filter(KlineDataDB.period == period)
    )
    if start:
        q = q.filter(KlineDataDB.trading_time >= start)
    if end:
        q = q.filter(KlineDataDB.trading_time <= end)

    rows = q.order_by(KlineDataDB.trading_time.asc()).limit(limit).all()
    return [
        KlineResponse(
            time=r.trading_time.isoformat(),
            open=float(r.open_price),
            high=float(r.high_price),
            low=float(r.low_price),
            close=float(r.close_price),
            volume=r.volume,
        )
        for r in rows
    ]


@router.get("/varieties/{variety_id}/contracts", response_model=List[ContractResponse])
def get_variety_contracts(
    variety_id: int,
    active_only: bool = Query(False),
    db: Session = Depends(get_db)
):
    """获取某品种下的所有合约。"""
    variety = db.query(VarietyDB).filter(VarietyDB.id == variety_id).first()
    if not variety:
        raise HTTPException(status_code=404, detail="品种不存在")

    q = db.query(FutContractDB).filter(FutContractDB.fut_code == variety.symbol)
    if active_only:
        q = q.filter(FutContractDB.is_active.is_(True))
    return q.order_by(FutContractDB.delist_date.desc()).all()


@router.get("/varieties/{variety_id}/rollovers", response_model=List[ContractRolloverResponse])
def get_variety_rollovers(
    variety_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
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
