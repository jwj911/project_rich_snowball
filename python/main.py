from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os
import traceback

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from models import init_db
from config import ENV, ENABLE_SCHEDULER
from routers import auth, products, comments, varieties, kline, realtime, health

logger = logging.getLogger(__name__)


def _error_response(code: str, message: str, errors: list = None, status_code: int = 500, detail: dict = None) -> JSONResponse:
    """统一错误响应格式。"""
    content = {
        "code": code,
        "message": message,
        "errors": errors or [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if detail:
        content.update(detail)
    return JSONResponse(
        status_code=status_code,
        content=content,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from data_collector.init_varieties import init_varieties
    init_varieties()
    if ENV != "production":
        from data_collector.init_mock_data import init_mock_data
        init_mock_data()
    if ENABLE_SCHEDULER:
        from data_collector.scheduler import start_scheduler, refresh_realtime_quotes, sync_daily_kline
        start_scheduler()
        # 立即执行一次数据采集，确保首次启动和测试环境有初始数据
        refresh_realtime_quotes()
        sync_daily_kline()
    yield
    if ENABLE_SCHEDULER:
        from data_collector.scheduler import shutdown_scheduler
        shutdown_scheduler()


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(comments.router)
app.include_router(varieties.router)
app.include_router(kline.router)
app.include_router(realtime.router)
app.include_router(health.router)


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
async def generic_exception_handler(request, exc: Exception):
    """兜底异常处理器，防止未捕获异常暴露内部信息。"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    detail = {}
    if ENV == "development":
        detail["exception"] = str(exc)
        detail["traceback"] = traceback.format_exc()
    return _error_response(
        code="INTERNAL_ERROR",
        message="服务器内部错误",
        status_code=500,
        detail=detail if ENV == "development" else None,
    )


@app.get("/")
def root():
    return {"message": "期货交流社区 API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8200"))
    uvicorn.run(app, host=host, port=port)
