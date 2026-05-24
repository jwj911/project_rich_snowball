import asyncio
import logging
import os
import sys
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response

from config import ENABLE_SCHEDULER, ENV

# ------------------------------------------------------------------
# 抑制 Windows asyncio ProactorEventLoop 已知噪音 (ConnectionResetError 10054)
# Python 3.8+ on Windows 的 race condition：远程关闭连接后 _call_connection_lost
# 调用 shutdown() 时 socket 已失效。此错误无害但会污染日志。
# 直接 patch _call_connection_lost 方法本身，比事件循环异常处理器更可靠
# （uvicorn 在 Windows 上的 loop 创建路径可能绕过后者）。
# ------------------------------------------------------------------
if sys.platform == "win32":
    import asyncio.proactor_events

    _original_call_connection_lost = asyncio.proactor_events._ProactorBasePipeTransport._call_connection_lost

    def _silenced_call_connection_lost(self, exc):
        try:
            _original_call_connection_lost(self, exc)
        except ConnectionResetError as e:
            if getattr(e, "winerror", None) == 10054:
                # 远程已强制关闭连接，补做 socket 清理避免 fd 泄漏
                try:
                    if getattr(self, "_sock", None) is not None:
                        self._sock.close()
                        self._sock = None
                except (OSError, AttributeError):
                    pass
                return
            raise

    asyncio.proactor_events._ProactorBasePipeTransport._call_connection_lost = _silenced_call_connection_lost
from models import init_db
from services.logging_config import setup_logging

# 最早初始化结构化日志（必须在其他模块导入前完成，确保全链路日志一致）
setup_logging()

from middleware.rate_limit import rate_limit_middleware, _is_trusted_proxy  # noqa: E402
from routers import (  # noqa: E402
    auth,
    comments,
    contracts,
    health,
    kline,
    market,
    price_levels,
    products,
    realtime,
    varieties,
    watchlists,
    workspace,
)
from services.metrics import (  # noqa: E402
    get_content_type,
    http_exceptions_total,
    http_request_duration_seconds,
    http_requests_total,
    metrics_response,
)

logger = logging.getLogger(__name__)


def _error_response(
    code: str,
    message: str,
    errors: list = None,
    status_code: int = 500,
    detail: dict = None,
) -> JSONResponse:
    """统一错误响应格式。"""
    content = {
        "code": code,
        "message": message,
        "errors": errors or [],
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if detail:
        content.update(detail)
    return JSONResponse(
        status_code=status_code,
        content=content,
    )


_delayed_sync_task = None


async def _delayed_first_sync():
    """延迟执行首次数据采集，避免阻塞应用启动。"""
    await asyncio.sleep(5)
    try:
        from data_collector.scheduler import refresh_realtime_quotes, sync_daily_kline
        refresh_realtime_quotes()
        sync_daily_kline()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Delayed first sync failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from data_collector.init_varieties import init_varieties
    init_varieties()
    if ENV != "production":
        from data_collector.init_mock_data import init_mock_data
        init_mock_data()
    if ENABLE_SCHEDULER:
        from data_collector.scheduler import start_scheduler
        start_scheduler()
        # 首次数据采集放入后台任务，避免阻塞启动
        global _delayed_sync_task
        _delayed_sync_task = asyncio.create_task(_delayed_first_sync())
    yield
    if ENABLE_SCHEDULER:
        from data_collector.scheduler import shutdown_scheduler
        shutdown_scheduler()
    # 取消可能仍在 sleep/执行的后台同步任务
    if _delayed_sync_task and not _delayed_sync_task.done():
        _delayed_sync_task.cancel()
        try:
            await _delayed_sync_task
        except asyncio.CancelledError:
            pass
    # 显式关闭 SQLAlchemy 连接池，避免 uvicorn 等待连接超时
    from models import engine
    engine.dispose()


_docs_url = None if ENV == "production" else "/docs"
_redoc_url = None if ENV == "production" else "/redoc"

app = FastAPI(
    title="期货交流社区 API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
)

# CORS 配置：优先读取 CORS_ORIGINS，兼容 ALLOW_ORIGINS
origins_raw = os.getenv("CORS_ORIGINS") or os.getenv("ALLOW_ORIGINS")
if ENV == "production" and not origins_raw:
    raise ValueError("CORS_ORIGINS (or ALLOW_ORIGINS) is required in production")
default_origins = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3200,http://127.0.0.1:3200"
origins = [origin.strip() for origin in (origins_raw or default_origins).split(",") if origin.strip()]

if ENV == "production":
    for origin in origins:
        if origin == "*":
            raise ValueError("CORS_ORIGINS cannot contain '*' in production when allow_credentials=True")
        if origin.startswith("http://"):
            raise ValueError(f"CORS origin must use HTTPS in production: {origin}")
        if "localhost" in origin or "127.0.0.1" in origin:
            raise ValueError(f"Localhost origins are not allowed in production: {origin}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# 全局限流中间件：覆盖所有写入端点（POST/PUT/PATCH/DELETE）
app.middleware("http")(rate_limit_middleware)

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(comments.router)
app.include_router(varieties.router)
app.include_router(kline.router)
app.include_router(realtime.router)
app.include_router(watchlists.router)
app.include_router(price_levels.router)
app.include_router(workspace.router)
app.include_router(contracts.router)
app.include_router(health.router)
app.include_router(market.router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """为每个请求生成或复用 X-Request-ID，便于日志串联。"""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    # 将 request_id 注入 structlog 上下文，确保全链路日志可追踪
    import structlog
    structlog.contextvars.bind_contextvars(request_id=request_id)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    """记录请求延迟和状态码到 Prometheus 指标。跳过内部端点避免噪声。"""
    path = request.url.path
    if path in ("/metrics", "/docs", "/redoc", "/openapi.json", "/"):
        return await call_next(request)

    method = request.method
    start = time.time()
    status_code = "500"
    try:
        response = await call_next(request)
    except Exception as exc:
        status_code = "500"
        route = request.scope.get("route")
        endpoint = getattr(route, "path", None) or path
        http_exceptions_total.labels(exception_type=type(exc).__name__, endpoint=endpoint).inc()
        raise
    else:
        status_code = str(response.status_code)
    finally:
        duration = time.time() - start
        # 使用路由模板路径而非完整解析路径，避免 cardinality 爆炸
        # 例如 /api/products/{id} 而不是 /api/products/123
        route = request.scope.get("route")
        endpoint = getattr(route, "path", None) or path
        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)
        http_requests_total.labels(method=method, endpoint=endpoint, status_code=status_code).inc()

    return response


@app.get("/metrics")
def metrics(request: Request):
    """Prometheus 指标抓取端点。仅限本地/内网访问。"""
    client_host = request.client.host if request.client else ""
    if not _is_trusted_proxy(client_host):
        raise HTTPException(status_code=403, detail="Forbidden")
    return Response(content=metrics_response(), media_type=get_content_type())


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """统一 HTTPException 响应格式。"""
    return _error_response(
        code=str(exc.status_code),
        message=exc.detail,
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """统一参数校验错误格式。"""
    errors = [
        {"field": err["loc"][-1], "message": err["msg"]}
        for err in exc.errors()
    ]
    return _error_response(
        code="VALIDATION_ERROR",
        message="请求参数校验失败",
        errors=errors,
        status_code=422,
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """兜底异常处理器，防止未捕获异常暴露内部信息。"""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"[{request_id}] Unhandled exception: {exc}", exc_info=True)
    detail = {"request_id": request_id}
    if ENV == "development":
        detail["exception"] = str(exc)
        detail["traceback"] = traceback.format_exc()
    return _error_response(
        code="INTERNAL_ERROR",
        message="服务器内部错误",
        status_code=500,
        detail=detail,
    )


@app.get("/")
def root():
    return RedirectResponse(url="/docs")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8200"))
    uvicorn.run(app, host=host, port=port, timeout_graceful_shutdown=5)
