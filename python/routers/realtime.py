import asyncio
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from models import RealtimeQuoteDB, VarietyDB, SessionLocal
from schemas import RealtimeResponse, RealtimeBatchResponse
from dependencies import get_db, get_current_user_from_token
from services.cache import get_cached

router = APIRouter(prefix="/api/realtime", tags=["实时行情"])

SSE_PUSH_INTERVAL_SECONDS = 5
SSE_TEST_MODE = os.getenv("SSE_TEST_MODE") == "1"


def _fetch_realtime(symbol: str, db: Session):
    """获取单个品种实时行情，返回 dict 或 None（不抛异常）。"""
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        return None

    def _fetch():
        q = db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
        if not q:
            return None
        # 缓存纯 dict，不存 ORM 实例，避免 detached session 风险
        return {
            "symbol": variety.symbol,
            "current_price": q.current_price,
            "change_percent": q.change_percent or 0,
            "open_price": q.open_price,
            "high": q.high,
            "low": q.low,
            "volume": q.volume,
            "updated_at": q.updated_at,
        }

    return get_cached(f"realtime:{symbol}", _fetch)


@router.get("/batch", response_model=RealtimeBatchResponse)
def get_realtime_batch(
    symbols: list[str] = Query(default=[], description="品种代码列表，如 ?symbols=AU&symbols=CU"),
    db: Session = Depends(get_db),
):
    quotes: list[dict] = []
    not_found: list[str] = []

    for symbol in symbols:
        quote = _fetch_realtime(symbol, db)
        if quote:
            quotes.append(quote)
        else:
            not_found.append(symbol)

    return {"quotes": quotes, "not_found": not_found}


async def _sse_realtime_generator(symbols: list[str], token: str):
    """SSE 推送生成器：每 5 秒查询一次批量行情并推送。"""
    push_count = 0
    try:
        while True:
            db = SessionLocal()
            try:
                # 验证 token（每次循环都验证，避免长连接期间 token 被吊销后仍继续推送）
                try:
                    user = get_current_user_from_token(token, db)
                    if not user:
                        yield f"event: error\ndata: {json.dumps({'code': 'unauthorized'})}\n\n"
                        break
                except HTTPException:
                    yield f"event: error\ndata: {json.dumps({'code': 'unauthorized'})}\n\n"
                    break

                quotes: list[dict] = []
                not_found: list[str] = []
                for symbol in symbols:
                    quote = _fetch_realtime(symbol, db)
                    if quote:
                        quotes.append(quote)
                    else:
                        not_found.append(symbol)

                payload = json.dumps({"quotes": quotes, "not_found": not_found}, default=str)
                yield f"data: {payload}\n\n"
                push_count += 1

                # 测试模式下只推送一次，避免 TestClient 无限等待
                if SSE_TEST_MODE:
                    break
            finally:
                db.close()

            await asyncio.sleep(SSE_PUSH_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        # 客户端断开，正常结束
        pass


@router.get("/stream")
def get_realtime_stream(
    symbols: list[str] = Query(default=[], description="品种代码列表，如 ?symbols=AU&symbols=CU"),
    token: str = Query(default="", description="JWT token（EventSource 不支持自定义 Header，通过 query param 传递）"),
):
    """SSE 实时行情推送端点。每 5 秒推送一次订阅品种的行情数据。"""
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    return StreamingResponse(
        _sse_realtime_generator(symbols, token),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 等代理的缓冲
        },
    )


@router.get("/{symbol}", response_model=RealtimeResponse)
def get_realtime(symbol: str, db: Session = Depends(get_db)):
    quote = _fetch_realtime(symbol, db)
    if not quote:
        raise HTTPException(status_code=404, detail="暂无实时行情数据")
    return quote
