# 期货社区后端重构 - 高鲁棒性迭代计划 v5.1

> 版本：v5.1（执行收敛版）  
> 日期：2026-05-04  
> 基线：`BACKEND_ITERATION_AND_REVIEW_PLAN.md` v4.1  
> 吸收：v5.0 的鲁棒性原则、缓存统计、健康检查、job listener、熔断/重试作为后续增强  
> 执行原则：第一阶段先消除上线阻塞风险；鲁棒性增强分批落地，避免把生产级体系全部塞进 P0。

---

## 一、执行判断

v5.0 的鲁棒性方向正确，但原版 P0 过重。v5.1 调整为：

- **P0：5 天内完成**。只做启动安全、缓存对象生命周期、认证限流、测试隔离和最小健康检查。
- **P1：第 2-3 周完成**。做 Alembic 迁移、数据管道正确性、scheduler 防重入、N+1、输入校验、OHLC、docs/CORS。
- **P2：第 4-6 周完成**。做结构化日志、统一错误响应、RobustCache 完整版、性能基线、CI 门禁。
- **P3+：中长期**。熔断、DB retry、混沌测试、PostgreSQL/Redis、SSE/WebSocket、交易日历、合约换月。

---

## 二、全局鲁棒性原则

所有阶段遵循：

1. **Fail Fast**：启动配置错误必须立即失败。
2. **Fail Safe**：依赖失败不能写入错误数据。
3. **Defensive Input**：HTTP、DB、第三方 API 都视为不可信。
4. **Idempotency**：采集写入、同步任务必须可重复执行。
5. **Observability**：关键路径至少有结构化日志入口，P2 接指标。
6. **Compatibility First**：旧 `/api/products` 和前端页面不能被第一阶段破坏。

---

## 三、P0 修复清单（Week 1）

### 3.1 DB engine 条件化 + SQLite timeout/WAL

**文件**：`python/models.py`  
**修复重点**：

- PostgreSQL 不接收 SQLite-only 参数。
- SQLite 增加 `timeout=30`。
- SQLite 启用 WAL。
- P0 不引入 `mmap_size/cache_size/pool_size=1` 等性能调参。

```python
from sqlalchemy import create_engine, event
from config import DATABASE_URL

engine_kwargs = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_engine(DATABASE_URL, **engine_kwargs)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()
```

**验收**：

- SQLite 测试通过。
- PostgreSQL URL 启动不因 `check_same_thread` 失败。
- `PRAGMA journal_mode` 返回 `wal`。

---

### 3.2 启动环境隔离：mock data 与 scheduler 显式开关

**文件**：`python/config.py`，`python/main.py`  
**修复重点**：

- 不使用 `assert` 做生产校验。
- 默认不初始化 mock data。
- 默认不启动 scheduler。
- scheduler 后续可独立 worker 化。

```python
# config.py
import os

ENV = os.getenv("ENV", "development")
INIT_MOCK_DATA = os.getenv("INIT_MOCK_DATA", "false").lower() == "true"
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "false").lower() == "true"

if ENV == "production":
    if INIT_MOCK_DATA:
        raise RuntimeError("INIT_MOCK_DATA must be false in production")
    if len(os.getenv("SECRET_KEY", "")) < 32:
        raise RuntimeError("SECRET_KEY must be >= 32 chars in production")
```

```python
# main.py lifespan
init_db()

if ENV != "production" and INIT_MOCK_DATA:
    from data_collector.init_mock_data import init_mock_data
    init_mock_data()

if ENABLE_SCHEDULER:
    from data_collector.scheduler import start_scheduler
    start_scheduler()

yield

if ENABLE_SCHEDULER:
    from data_collector.scheduler import shutdown_scheduler
    shutdown_scheduler()
```

**验收**：

- 默认启动无 demo 用户。
- 默认启动无 scheduler。
- `ENV=production INIT_MOCK_DATA=true` 启动失败。
- `ENV=production SECRET_KEY=short` 启动失败。

---

### 3.3 缓存修复：加锁 + 不缓存 ORM

**文件**：`python/services/cache.py`，`python/routers/realtime.py`  
**P0 目标**：不做完整 `RobustCache` 重写，只做安全修复。

```python
from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Callable

_cache: dict[str, Any] = {}
_cache_time: dict[str, datetime] = {}
_lock = RLock()
DEFAULT_TTL_SECONDS = 5

def get_cached(key: str, fetch_func: Callable[[], Any], ttl: int = DEFAULT_TTL_SECONDS) -> Any:
    now = datetime.now()
    with _lock:
        if key in _cache and now - _cache_time[key] < timedelta(seconds=ttl):
            return _cache[key]

    value = fetch_func()
    if hasattr(value, "_sa_instance_state"):
        raise ValueError("Cache refused to store SQLAlchemy ORM object")

    with _lock:
        _cache[key] = value
        _cache_time[key] = now
    return value

def invalidate_cache(key: str | None = None) -> None:
    with _lock:
        if key is None:
            _cache.clear()
            _cache_time.clear()
        else:
            _cache.pop(key, None)
            _cache_time.pop(key, None)
```

`realtime.py` 的 `_fetch()` 必须返回 dict：

```python
def _fetch() -> dict | None:
    quote = db.query(RealtimeQuoteDB).filter(
        RealtimeQuoteDB.variety_id == variety.id
    ).first()
    if not quote:
        return None
    return {
        "symbol": variety.symbol,
        "current_price": quote.current_price,
        "change_percent": quote.change_percent or 0,
        "open_price": quote.open_price,
        "high": quote.high,
        "low": quote.low,
        "volume": quote.volume,
        "updated_at": quote.updated_at,
    }
```

**P2 增强**：再引入 max size、LRU、stats、hit rate。

---

### 3.4 注册/登录限流

**文件**：`python/rate_limit.py`，`python/main.py`，`python/routers/auth.py`  
**重点**：避免 router 反向 import `main.py`。

```python
# rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
```

```python
# main.py
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from rate_limit import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
```

```python
# routers/auth.py
from fastapi import Request
from rate_limit import limiter

@router.post("/register", response_model=UserResponse)
@limiter.limit("5/minute")
def register(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    ...

@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    ...
```

**依赖**：

```txt
slowapi>=0.1.9
```

---

### 3.5 测试隔离基础设施

**文件**：`python/tests/conftest.py`  
**关键要求**：环境变量必须在导入 `main/app/config/models` 前设置。

```python
import os

os.environ.setdefault("ENV", "testing")
os.environ.setdefault("INIT_MOCK_DATA", "false")
os.environ.setdefault("ENABLE_SCHEDULER", "false")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-long!!")

import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from dependencies import get_db
from main import app
from models import Base

@pytest.fixture(scope="function")
def db_engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    os.unlink(path)

@pytest.fixture(scope="function")
def client(db_engine):
    Session = sessionmaker(bind=db_engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

---

### 3.6 最小健康检查

**文件**：新增 `python/routers/health.py`  
**原因**：上线前至少需要基础存活/就绪探针。

```python
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from models import SessionLocal

router = APIRouter(prefix="/health", tags=["health"])

@router.get("")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

@router.get("/ready")
def ready():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    finally:
        db.close()
```

---

## 四、P1 修复清单（Week 2-3）

### 4.1 数据 Pipeline 与 Schema 迁移

执行前先更新并遵循 `DATA_PIPELINE_DESIGN.md` v2.0。

P1 必须包括：

- Alembic migration 流程。
- `pre_settlement` 字段。
- OHLC 完整校验。
- Akshare 合约硬编码修复。
- `sync_prices_to_products` 批量化。
- `insert_kline_bulk` 批量 variety lookup。
- `KlineDataDB.contract_code` 方案确定。

```bash
cd python
alembic revision --autogenerate -m "add settlement and pipeline fields"
alembic upgrade head
```

验收：

- 空库迁移成功。
- 旧库迁移成功。
- SQLite 文件先备份再迁移。

### 4.2 Scheduler 防重入与 job listener

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

scheduler = BackgroundScheduler(job_defaults={
    "max_instances": 1,
    "coalesce": True,
    "misfire_grace_time": 30,
})

def _job_listener(event):
    if event.exception:
        logger.error("Scheduler job failed", exc_info=True)
    else:
        logger.info("Scheduler job completed", extra={"job_id": event.job_id})

scheduler.add_listener(_job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
```

### 4.3 输入校验与鉴权一致性

- `UserCreate`：`EmailStr`、username pattern、password length。
- `CommentCreate`：`mode="before"` strip，空白评论 422。
- `comments.py`：统一 `Depends(get_current_user_dependency)`。
- `dependencies.py`：只 catch `PyJWTError` 和 `ValueError`；DB 错误不伪装成 401。

### 4.4 生产配置

- `docs_url=None if ENV == "production" else "/docs"`。
- `CORS_ORIGINS` 按环境配置，生产禁止 `*`。
- `/api/products` 增加 `skip/limit`，但保持数组响应兼容。

---

## 五、P2 修复清单（Week 4-6）

### 5.1 RobustCache 完整增强

在 P0 简单修复稳定后，再升级：

- max size。
- LRU/TTL 清理。
- `get_stats()`。
- hit/miss/eviction/error 统计。
- `/health` 暴露 cache 基础状态。

### 5.2 可观测性

- 结构化 JSON 日志。
- 采集状态日志或 `data_ingestion_runs` 表。
- OpenAPI/JSON schema 契约快照。
- pytest coverage + ruff。
- 性能基线仅观察，不作为早期 PR 阻断。

### 5.3 错误响应标准化

统一为：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "请求参数校验失败",
  "errors": [],
  "timestamp": "2026-05-04T00:00:00Z"
}
```

注意：该项影响前端，应在前端 adapter 同步后执行。

---

## 六、P3+ 生产级增强

- CircuitBreaker：外部源连续失败后降级。
- DB retry：仅对 SQLite `database is locked` 做有限重试。
- 混沌测试：采集器失败、DB lock、scheduler 异常。
- PostgreSQL 迁移。
- Redis 缓存和分布式限流。
- SSE/WebSocket 实时行情推送。
- 交易日历、夜盘、合约换月、主连 K 线。

---

## 七、Review 与验收

### P0 验收

- `pytest -m "not slow"` 通过。
- 默认无 mock 用户。
- 默认 scheduler 不启动。
- cache 不存 ORM。
- 20 线程 cache 测试无异常。
- 注册/登录限流生效。
- `/health` 与 `/health/ready` 可用。
- SQLite WAL 模式确认。

### 上线标准

- P0 全部完成。
- P1 中 scheduler 防重入、OHLC、输入校验、docs/CORS 完成。
- 旧 `/api/products` 兼容。
- 前端冒烟联调通过。
- 安全测试无注入、无认证绕过。

### 生产级标准

- PostgreSQL 验证。
- 数据采集状态可观测。
- 50 并发错误率 0%。
- 100 万 K 线查询基线达标。
- 备份/恢复演练通过。

---

## 八、执行路线

```text
Week 1
├─ Day 1: DB engine 条件化 + SQLite timeout/WAL
├─ Day 2: mock/scheduler 开关 + 生产配置显式 raise
├─ Day 3: cache lock + realtime dict 缓存
├─ Day 4: auth rate limit + health endpoints
└─ Day 5: conftest 测试隔离 + P0 review

Week 2-3
├─ DATA_PIPELINE_DESIGN v2.0 对齐实现
├─ Alembic: pre_settlement / pipeline fields
├─ scheduler 防重入 + N+1 修复
├─ cleaner OHLC + Akshare 合约修复
└─ 输入校验 + docs/CORS

Week 4-6
├─ RobustCache 完整版
├─ 结构化日志 + 采集状态
├─ 统一错误响应 + 契约快照
└─ CI/lint/coverage/perf baseline
```

---

## 九、最终结论

v5.1 可以进入执行阶段。执行方式不是照 v5.0 全量推进，而是：

1. **先做 v4.1 P0 + v5 必要鲁棒性补丁**。
2. **再按 `DATA_PIPELINE_DESIGN.md` v2.0 推进数据获取链路**。
3. **最后把 v5.0 中的熔断、重试、混沌、完整可观测性逐步补齐**。

这样既保留高鲁棒性目标，又避免第一阶段过载。
