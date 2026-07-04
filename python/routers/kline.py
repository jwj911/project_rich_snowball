from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import UserDB
from schemas import ContinuousKlineResponse, IndicatorResponse, KlineResponse, KlineSummaryResponse
from services.domain.exceptions import NotFoundError
from services.domain.kline_service import KlineService
from utils import ensure_utc

router = APIRouter(prefix="/api/klines", tags=["K线"])


def _get_kline_service(db: Session = Depends(get_db)) -> KlineService:
    return KlineService(db)


@router.get("/{symbol}", response_model=list[KlineResponse])
def get_kline(
    symbol: str,
    period: str = Query("1h", pattern="^(1m|5m|15m|30m|1h|1d|1w)$"),
    limit: int = Query(100, ge=1, le=1000),
    contract_id: int | None = Query(None, ge=1, description="合约 ID，不传则返回当前主力合约 K 线"),
    service: KlineService = Depends(_get_kline_service),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    rows = service.get_klines(symbol, period=period, limit=limit, contract_id=contract_id)
    return rows


@router.get("/{symbol}/continuous", response_model=list[ContinuousKlineResponse])
def get_continuous_kline_api(
    symbol: str,
    period: str = Query("D", pattern=r"^(D|W|M|5|15|30|60|1m|5m|15m|30m|1h|1d|1w)$"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    service: KlineService = Depends(_get_kline_service),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取连续 K 线（按主力切换拼接多合约）。"""
    rows = service.get_continuous_klines(
        symbol, period=period, start=ensure_utc(start), end=ensure_utc(end), limit=limit
    )
    return rows


@router.get("/{symbol}/main", response_model=list[ContinuousKlineResponse])
def get_main_contract_kline_api(
    symbol: str,
    period: str = Query("D", pattern=r"^(D|W|M|5|15|30|60|1m|5m|15m|30m|1h|1d|1w)$"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    service: KlineService = Depends(_get_kline_service),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取当前主力合约的 K 线（不拼接）。"""
    rows = service.get_main_klines(
        symbol, period=period, start=ensure_utc(start), end=ensure_utc(end), limit=limit
    )
    return rows


@router.get("/{symbol}/indicators", response_model=list[IndicatorResponse])
def get_kline_indicators(
    symbol: str,
    period: str = Query("1d", pattern=r"^(1m|5m|15m|30m|1h|1d|1w)$"),
    indicators: list[str] | None = Query(None, description="指标名列表，如 MA,MACD,RSI；为空则返回全部"),
    limit: int = Query(500, ge=10, le=1000),
    service: KlineService = Depends(_get_kline_service),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取 K 线技术指标。"""
    return service.calculate_indicators(symbol, period=period, indicators=indicators, limit=limit)


@router.get("/{symbol}/summary", response_model=KlineSummaryResponse)
def get_kline_summary(
    symbol: str,
    periods: list[str] = Query(..., description="周期列表，如 ?periods=1d&periods=1h"),
    limit: int = Query(100, ge=1, le=500),
    service: KlineService = Depends(_get_kline_service),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    """获取多周期 K 线汇总。"""
    result = service.get_kline_summary(symbol, periods=periods, limit=limit)
    return {"data": result}
