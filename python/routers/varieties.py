from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from models import VarietyDB
from schemas import VarietyResponse
from dependencies import get_db

router = APIRouter(prefix="/api/varieties", tags=["品种"])


@router.get("", response_model=List[VarietyResponse])
def get_varieties(
    category: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    q = db.query(VarietyDB)
    if category:
        q = q.filter(VarietyDB.category == category)
    if search:
        q = q.filter(VarietyDB.name.contains(search))
    return q.offset(skip).limit(limit).all()


@router.get("/{symbol}", response_model=VarietyResponse)
def get_variety(symbol: str, db: Session = Depends(get_db)):
    v = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not v:
        raise HTTPException(status_code=404, detail="品种不存在")
    return v
