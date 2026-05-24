import asyncio
import json
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from jwt.exceptions import PyJWTError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from config import ALGORITHM
from config import SECRET_KEY as _SECRET_KEY

SECRET_KEY: str = _SECRET_KEY
from dependencies import get_current_user_dependency, get_db
from models import RealtimeQuoteDB, SessionLocal, UserDB, VarietyDB
from schemas import RealtimeBatchResponse, RealtimeResponse
from services.cache import get_cached
from services.realtime_state import get_last_update_time

router = APIRouter(prefix="/api/realtime", tags=["实时行情"])

SSE_STREAM_TOKEN_EXPIRE_SECONDS = 60
SSE_STREAM_TOKEN_TYPE = "realtime_stream"

# SSE 并发连接限制：按 user_id 限制同时只能维持 1 个活跃 SSE 连接
_sse_connections: dict[int, asyncio.Task] = {}
_sse_connections_lock = asyncio.Lock()


def _create_stream_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "typ": SSE_STREAM_TOKEN_TYPE,
        "exp": datetime.now(UTC) + timedelta(seconds=SSE_STREAM_TOKEN_EXPIRE_SECONDS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _get_user_from_stream_token(token: str, db: Session) -> UserDB:
    if not token:
        raise HTTPException(status_code=401, detail="未登录或 token 无效")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("typ") != SSE_STREAM_TOKEN_TYPE:
            raise HTTPException(status_code=401, detail="无效的实时行情 token")
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="无效的实时行情 token")
        user = db.query(UserDB).filter(UserDB.id == int(user_id)).first()
        if not user:
            raise HTTPException(status_code=401, detail="无效的实时行情 token")
        return user
    except (PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="无效的实时行情 token")

SSE_PUSH_INTERVAL_SECONDS = 5
SSE_MAX_SYMBOLS = 50
SSE_MAX_PUSHES = 720  # 最大推送次数（约 1 小时 @5s 间隔）
SSE_HEARTBEAT_INTERVAL = 6  # 每 6 次推送（30 秒）发送一次心跳 comment
SSE_MAX_GLOBAL_CONNECTIONS = 100  # 全局 SSE 并发连接上限


def _sse_test_mode() -> bool:
    """运行时读取环境变量，避免导入期求值与测试模块加载顺序冲突。"""
    return os.getenv("SSE_TEST_MODE") == "1"


def _fetch_realtime(symbol: str, db: Session, variety: VarietyDB | None = None):
    """获取单个品种实时行情，返回 dict 或 None（不抛异常）。

    支持传入预查的 variety 对象，避免 batch 场景下的 N+1 查询。
    """
    if variety is None:
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
            "delayed": q.data_source == "akshare",
            "data_source": q.data_source,
            "limit_up": q.limit_up,
            "limit_down": q.limit_down,
        }

    return get_cached(f"futures:realtime:{symbol}", _fetch)


def _fetch_realtime_batch(symbols: list[str], db: Session) -> tuple[list[dict], list[str]]:
    """批量获取实时行情，将 RealtimeQuoteDB 查询从 N 次降为 1 次。

    返回 (quotes, not_found)。不经过缓存层，适合 batch / SSE 高频场景。
    """
    varieties = {
        v.symbol: v
        for v in db.query(VarietyDB).filter(VarietyDB.symbol.in_(symbols)).all()
    }

    variety_ids = [v.id for v in varieties.values()]
    quotes_rows = (
        db.query(RealtimeQuoteDB)
        .filter(RealtimeQuoteDB.variety_id.in_(variety_ids))
        .all()
    )
    quotes_map = {q.variety_id: q for q in quotes_rows}

    quotes: list[dict] = []
    not_found: list[str] = []

    for symbol in symbols:
        variety = varieties.get(symbol)
        if not variety:
            not_found.append(symbol)
            continue

        q = quotes_map.get(variety.id)
        if not q:
            not_found.append(symbol)
            continue

        quotes.append({
            "symbol": variety.symbol,
            "current_price": q.current_price,
            "change_percent": q.change_percent or 0,
            "open_price": q.open_price,
            "high": q.high,
            "low": q.low,
            "volume": q.volume,
            "updated_at": q.updated_at,
            "delayed": q.data_source == "akshare",
            "data_source": q.data_source,
        })

    return quotes, not_found


@router.get("/batch", response_model=RealtimeBatchResponse)
def get_realtime_batch(
    symbols: list[str] = Query(default=[], description="品种代码列表，如 ?symbols=AU&symbols=CU"),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency),
):
    quotes, not_found = _fetch_realtime_batch(symbols, db)
    return {"quotes": quotes, "not_found": not_found}


@router.post("/stream-token")
def create_realtime_stream_token(current_user: UserDB = Depends(get_current_user_dependency)):
    """Issue a short-lived token for EventSource connections."""
    return {
        "stream_token": _create_stream_token(current_user.id),
        "expires_in": SSE_STREAM_TOKEN_EXPIRE_SECONDS,
    }


def _sse_fetch_once(symbols: list[str], token: str):
    """在线程池中执行的同步函数：验证 token 并查询批量行情。
    内部独立创建和关闭 session，避免跨线程共享 session。"""
    db = SessionLocal()
    try:
        user = _get_user_from_stream_token(token, db)
        quotes, not_found = _fetch_realtime_batch(symbols, db)
        return user, quotes, not_found
    finally:
        db.close()


async def _sse_realtime_generator(symbols: list[str], token: str, user_id: int):
    """SSE 推送生成器：基于数据变更感知的智能推送。

    - 首次连接无条件推送初始数据
    - 后续只在 scheduler 更新 realtime_quotes 后才查询并推送
    - 心跳每 30 秒发送一次，保持连接活跃
    - 所有同步 DB 调用均通过 run_in_threadpool 放入线程池

    效果：将数据库查询频率从"每 5 秒"降到"每 60 秒 + 新连接时"。
    """
    push_count = 0
    last_sent_time = datetime.min.replace(tzinfo=UTC)
    last_heartbeat_time = datetime.now(UTC)
    try:
        while push_count < SSE_MAX_PUSHES:
            now = datetime.now(UTC)

            # 心跳：每 30 秒发送一次 comment
            if (now - last_heartbeat_time).total_seconds() >= SSE_HEARTBEAT_INTERVAL * SSE_PUSH_INTERVAL_SECONDS:
                yield ":heartbeat\n\n"
                last_heartbeat_time = now

            last_update = get_last_update_time()
            # 首次连接 或 数据已更新 时才查询推送
            if last_update > last_sent_time or last_sent_time == datetime.min.replace(tzinfo=UTC):
                try:
                    user, quotes, not_found = await run_in_threadpool(_sse_fetch_once, symbols, token)
                except HTTPException:
                    yield f"event: error\ndata: {json.dumps({'code': 'unauthorized'})}\n\n"
                    break

                payload = json.dumps({"quotes": quotes, "not_found": not_found}, default=str)
                yield f"data: {payload}\n\n"
                last_sent_time = now
                push_count += 1

                # 测试模式下只推送一次，避免 TestClient 无限等待
                if _sse_test_mode():
                    break

            await asyncio.sleep(SSE_PUSH_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        # 客户端断开，正常结束
        pass
    finally:
        async with _sse_connections_lock:
            _sse_connections.pop(user_id, None)


@router.get("/stream")
async def get_realtime_stream(
    symbols: list[str] = Query(default=[], description="品种代码列表，如 ?symbols=AU&symbols=CU"),
    token: str = Query(default="", description="JWT token（EventSource 不支持自定义 Header，通过 query param 传递）"),
    access_token: str = Cookie(None),
):
    """SSE 实时行情推送端点。每 5 秒推送一次订阅品种的行情数据。

    并发限制：同一用户同时只能维持 1 个活跃 SSE 连接，新连接建立时旧连接会被取消。
    """
    effective_token = token or access_token
    if not effective_token or len(effective_token) < 10:
        raise HTTPException(status_code=401, detail="未登录或 token 无效")
    if len(symbols) > SSE_MAX_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"订阅品种数超过上限 {SSE_MAX_SYMBOLS}"
        )
    # symbols 为空时自动订阅全部活跃品种
    if len(symbols) == 0:
        db = SessionLocal()
        try:
            all_symbols = [v.symbol for v in db.query(VarietyDB).all()]
            symbols = all_symbols[:SSE_MAX_SYMBOLS]
        finally:
            db.close()
        if len(symbols) == 0:
            raise HTTPException(status_code=400, detail="系统中暂无活跃品种")

    # 验证 token 并获取 user_id
    try:
        payload = jwt.decode(effective_token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": True})
        user_id = int(payload.get("sub", 0))
        if not user_id:
            raise HTTPException(status_code=401, detail="未登录或 token 无效")
    except PyJWTError:
        raise HTTPException(status_code=401, detail="未登录或 token 无效")

    # 全局并发连接上限
    async with _sse_connections_lock:
        if len(_sse_connections) >= SSE_MAX_GLOBAL_CONNECTIONS and user_id not in _sse_connections:
            raise HTTPException(
                status_code=503,
                detail=f"SSE 连接数已达上限 {SSE_MAX_GLOBAL_CONNECTIONS}，请稍后重试"
            )
        # 取消同一用户的旧连接（每用户限 1 个）
        old_task = _sse_connections.get(user_id)
        if old_task and not old_task.done():
            old_task.cancel()
        # 预占位（生成器内部会在 finally 中清理）
        _sse_connections[user_id] = asyncio.current_task()

    return StreamingResponse(
        _sse_realtime_generator(symbols, token, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 等代理的缓冲
        },
    )


@router.get("/{symbol}", response_model=RealtimeResponse)
def get_realtime(symbol: str, db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user_dependency)):
    quote = _fetch_realtime(symbol, db)
    if not quote:
        raise HTTPException(status_code=404, detail="暂无实时行情数据")
    return quote
