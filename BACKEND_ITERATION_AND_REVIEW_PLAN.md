# 期货社区后端重构 - 综合迭代计划与 Review 方案

> 版本：v4.1（执行校准版）  
> 日期：2026-05-04  
> 综合来源：`BACKEND_REVIEW_REPORT.md` / `BACKEND_TEST_PLAN.md` / `BACKEND_COMPREHENSIVE_v3.md` / `DEEP_CODE_REVIEW_FINDINGS.md`  
> 修订原则：P0 只保留真实阻塞上线或会造成安全/启动/数据一致性事故的问题；涉及数据库 schema、前端响应兼容、资金语义的数据改造进入 P1，并配套迁移与回滚方案。

---

## 一、执行摘要

当前后端已经完成了从单体脚本向 FastAPI 分层后端的关键重构，但距离可稳定上线仍有几类硬风险：

1. **启动与环境隔离风险**：生产环境可能自动写入 mock 用户；scheduler 默认随 Web 进程启动；数据库 engine 对 SQLite/PostgreSQL 参数未区分。
2. **并发与缓存风险**：实时行情缓存保存 ORM 对象，且全局 dict 无锁；scheduler job 缺少防重入；SQLite 缺少 timeout/WAL 验证。
3. **安全边界风险**：注册/登录缺少限流；评论鉴权实现不统一；输入校验不足。
4. **测试可信度风险**：现有测试依赖真实数据库、固定种子数据和固定用户，无法作为 CI 质量门禁。
5. **业务正确性演进风险**：价格精度、昨结算价、合约维度、OHLC 校验需要修复，但其中 schema 级变更必须配合 Alembic、兼容策略和回滚计划，不能粗暴塞进 P0。

本计划将修复分为：

- **P0：本周完成，阻塞上线**。不涉及大规模 schema 迁移，优先消除安全、启动、缓存、测试隔离风险。
- **P1：第 2-3 周完成，强烈建议上线前完成或至少进入灰度**。包含 Alembic 迁移、业务字段增强、scheduler 防重入、N+1、输入校验、健康检查等。
- **P2：第 4-6 周完成，工程质量与可观测性优化**。包含统一错误响应、结构化日志、类型标注、CI/lint 扩展、契约测试等。
- **P3+：中长期生产化**。PostgreSQL、Redis、SSE/WebSocket、交易日历、主连 K 线、混沌测试。

---

## 二、P0 修复清单（本周内必须完成）

### 2.1 数据库引擎条件化

**文件**：`python/models.py:10-17`  
**问题**：`check_same_thread=False` 是 SQLite 专用参数，目前无条件传入，PostgreSQL 启动会失败。  
**修复代码**：

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
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
```

**验收**：

- SQLite 下 `pytest -m "not slow"` 通过。
- 设置 PostgreSQL URL 时应用启动阶段不因 `check_same_thread` 报错。
- SQLite 连接检查 `PRAGMA journal_mode` 为 `wal`。

**回滚方案**：

- 如 WAL 在当前环境导致异常，可先保留 `timeout=30`，临时移除 PRAGMA 监听，并记录 SQLite 并发测试为待修。

---

### 2.2 Mock 数据初始化必须显式开启

**文件**：`python/main.py:12-16`，`python/data_collector/init_mock_data.py:25-29`  
**问题**：应用启动时会自动写入 `password123` 的 demo 用户。  
**修复代码**：

```python
# config.py
ENV = os.getenv("ENV", "development")
INIT_MOCK_DATA = os.getenv("INIT_MOCK_DATA", "false").lower() == "true"
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "false").lower() == "true"
```

```python
# main.py lifespan
if ENV != "production" and INIT_MOCK_DATA:
    from data_collector.init_mock_data import init_mock_data
    init_mock_data()
```

**验收**：

- 默认启动不会创建 `trader001`、`investor_wang`、`futures_master`。
- `ENV=development INIT_MOCK_DATA=true` 时仍可初始化演示数据。

**回滚方案**：

- 如本地开发受影响，通过 `.env` 设置 `INIT_MOCK_DATA=true`。

---

### 2.3 Scheduler 启动必须显式开启

**文件**：`python/main.py:15-19`，`python/data_collector/scheduler.py:78-85`  
**问题**：Web 进程启动即启动 scheduler，多 worker 部署会重复采集。  
**修复代码**：

```python
# main.py lifespan
if ENABLE_SCHEDULER:
    from data_collector.scheduler import start_scheduler
    start_scheduler()

yield

if ENABLE_SCHEDULER:
    from data_collector.scheduler import shutdown_scheduler
    shutdown_scheduler()
```

**验收**：

- 默认启动无定时任务。
- `ENABLE_SCHEDULER=true` 时 scheduler 正常启动。

**回滚方案**：

- 如采集任务临时异常，直接取消环境变量 `ENABLE_SCHEDULER` 并重启服务。

---

### 2.4 缓存层修复：加锁 + 禁止缓存 ORM 对象

**文件**：`python/services/cache.py`，`python/routers/realtime.py:17-20`  
**问题**：缓存 ORM 对象会跨 request/session 复用；全局 dict 无锁。  
**修复代码**：

```python
# services/cache.py
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

    data = fetch_func()

    with _lock:
        _cache[key] = data
        _cache_time[key] = now
    return data

def invalidate_cache(key: str | None = None) -> None:
    with _lock:
        if key is None:
            _cache.clear()
            _cache_time.clear()
        else:
            _cache.pop(key, None)
            _cache_time.pop(key, None)
```

```python
# routers/realtime.py
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

**验收**：

- `/api/realtime/{symbol}` 返回正常。
- 缓存值为 `dict`，不含 `_sa_instance_state`。
- 20 线程并发调用 `get_cached()` 无异常。

**注意**：

- `get_cached()` 是通用缓存函数，不应靠它自动转换任意 ORM 对象。转换责任放在调用方，例如 `realtime.py` 的 `_fetch()`。

---

### 2.5 注册/登录限流

**文件**：`python/routers/auth.py:12-39`，新增 `python/rate_limit.py`，`python/main.py`  
**问题**：注册/登录无 rate limit，可被爆破和批量注册。  
**修复代码**：

```python
# rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
```

```python
# main.py
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
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

**依赖变更**：

```txt
slowapi>=0.1.9
```

**验收**：

- 连续 6 次注册，第 6 次返回 429。
- 连续 11 次登录，第 11 次返回 429。
- 正常低频注册/登录不受影响。

**回滚方案**：

- 通过环境变量配置更宽松的限流值；必要时临时移除 middleware，但必须保留测试标记为待修。

---

### 2.6 测试隔离基础设施

**文件**：`python/tests/conftest.py`（新建）  
**问题**：当前测试依赖真实数据库、固定用户和固定产品 id。  
**修复代码**：

```python
import os
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
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

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

**验收**：

- 连续执行 3 次 `pytest` 结果一致。
- 单独执行任意测试文件通过。
- 测试不再依赖 `trader001`、`AU`、`product_id=1` 这类隐式开发数据。

**注意**：

- 当前 `main.app` lifespan 里可能初始化数据和 scheduler，P0 的环境开关必须先完成，否则 isolated client 仍可能有副作用。

---

## 三、P1 修复清单（第 2-3 周）

### 3.1 数据迁移与业务字段增强

#### 3.1.1 Alembic 迁移流程（新增必备项）

**适用问题**：新增 `pre_settlement`、字段类型调整、未来合约维度字段。  
**原因**：任何 schema 变更都必须有迁移脚本，不能只改 `models.py`。

**执行步骤**：

```bash
cd python
alembic revision --autogenerate -m "add settlement and price precision fields"
alembic upgrade head
```

**验收**：

- 空库 `alembic upgrade head` 成功。
- 旧库迁移成功，原有数据可读。
- 如支持回滚，`alembic downgrade -1` 成功；如不可逆，迁移脚本中明确说明。

#### 3.1.2 价格精度策略校准

**原计划问题**：全量 `Float → Decimal` 放在 P0 过重。  
**修订策略**：

- 展示型行情字段短期可保留 `Float`，但 API 输出必须格式稳定。
- 资金语义字段优先迁移 Decimal：`margin`、`commission`、`target_price`、`stop_loss`。
- 若 `RealtimeQuoteDB.current_price` 等行情字段迁移 Decimal，必须同步处理 Pydantic 序列化和前端展示。

**建议字段**：

```python
from sqlalchemy import Numeric

margin = Column(Numeric(10, 4), default=0)
commission = Column(Numeric(10, 4), default=0)
target_price = Column(Numeric(15, 4))
stop_loss = Column(Numeric(15, 4))
```

**兼容策略**：

- 短期 API 可将 Decimal 转为 `float` 保持前端兼容。
- 若改为 string，必须版本化接口或前端同步适配。

#### 3.1.3 昨结算价与涨跌幅修正

**文件**：`models.py`，`mock_collector.py`，`cleaner.py`  
**修复**：

- `RealtimeQuoteDB` 新增 `pre_settlement`。
- collector 输出内部标准字段 `pre_settlement`。
- 涨跌幅统一按 `(current_price - pre_settlement) / pre_settlement * 100`。

**验收**：

- `pre_settlement` 缺失或为 0 时不崩溃。
- mock 数据涨跌幅与手动计算一致。
- Alembic 迁移覆盖该字段。

---

### 3.2 架构、性能与安全修复表

| # | 问题 | 文件 | 修复方案 | 工作量 | 验收 |
|---|------|------|----------|--------|------|
| 1 | Scheduler 重入保护 | `scheduler.py:81-85` | `max_instances=1, coalesce=True, misfire_grace_time=10` | 5 分钟 | 长任务不会重入 |
| 2 | `sync_prices_to_products` N+1 | `scheduler.py:60-70` | `selectinload` + `symbol→product` 批量映射 | 30 分钟 | 查询数不随 quote 线性增长 |
| 3 | K-line bulk 循环查 variety | `upsert.py:38-65` | 单次查询全部 symbol 建 dict | 30 分钟 | 1000 rows 仅一次 variety 查询 |
| 4 | Product detail comments N+1 | `products.py:23-36` | `.options(selectinload(CommentDB.user))` | 15 分钟 | 评论 100 条无 N+1 |
| 5 | 注册输入验证增强 | `schemas.py:7-10` | `EmailStr` + username pattern + password length | 15 分钟 | 非法邮箱/短密码 422 |
| 6 | 空白评论通过校验 | `schemas.py:41-48` | `mode="before"` validator，strip 后空字符串 raise | 15 分钟 | `"   "` 返回 422 |
| 7 | JWT 异常吞掉所有错误 | `dependencies.py:22-34` | 只 catch `PyJWTError` 和 `ValueError`，DB 错误 re-raise | 15 分钟 | DB 错误不伪装成 401 |
| 8 | OHLC 校验不完整 | `cleaner.py:16,55` | 增加 `_valid_ohlc()` | 30 分钟 | high/open/close/low 矛盾数据被丢弃 |
| 9 | Akshare 硬编码合约月 | `akshare_collector.py:52-55` | 从 DB/配置查 active contract，`"1h"→"60"` | 1 小时 | 不再固定 `2506` |
| 10 | Production docs 暴露 | `main.py:22` | `docs_url=None if ENV=="production" else "/docs"` | 5 分钟 | 生产 `/docs` 404 |
| 11 | CORS 环境配置 | `main.py:24-31` | 从 `CORS_ORIGINS` 读取，生产禁止 `*` | 10 分钟 | staging/prod origin 明确 |
| 12 | `/api/products` 分页 | `products.py:11-14` | 增加 `skip/limit`，默认仍返回数组 | 15 分钟 | 旧前端不破坏 |
| 13 | 评论接口统一鉴权 | `comments.py:13-20` | 使用 `Depends(get_current_user_dependency)` | 15 分钟 | comments/auth/me 鉴权一致 |
| 14 | `/health` 与 `/ready` | 新建 `routers/health.py` | `/health` 存活；`/ready` 检查 DB | 30 分钟 | 部署探针可用 |
| 15 | SECRET_KEY 强度 | `config.py` | 生产环境要求长度 >= 32 | 10 分钟 | 弱密钥生产启动失败 |

---

## 四、P2 优化清单（第 4-6 周）

| # | 问题 | 文件 | 修复方案 |
|---|------|------|----------|
| 1 | Import 顺序不规范 | `main.py:1-4` 等 | PEP8 顺序：标准库 → 第三方 → 本地 |
| 2 | 返回类型缺失 | `auth.py:13`, `products.py:12` 等 | 补全 `-> UserDB`, `-> list[ProductDB]`, `-> None` |
| 3 | Mock collector 改全局 random | `mock_collector.py:16-18` | `self._random = random.Random(seed)` |
| 4 | print → logging | `init_mock_data.py:46`, `init_varieties.py:40` | 使用 `logger.info()` |
| 5 | init_varieties 重复 engine | `init_varieties.py:8-16` | 复用 `models.SessionLocal` |
| 6 | datetime 别名 | `schemas.py:3` | 直接 `from datetime import datetime` |
| 7 | 抽象方法体 | `base.py:6-19` | `pass` → `...` |
| 8 | 错误响应标准化 | 全局 | 统一为 `{code, message, errors[], timestamp}`，需前端同步 |
| 9 | 结构化日志 | 全局 | JSON 格式，接入 ELK/Loki |
| 10 | CI/CD 基础门禁 | `.github/workflows/test.yml` | `pytest -m "not slow"` + coverage + ruff |
| 11 | 契约快照测试 | API schema | OpenAPI/JSON schema diff |
| 12 | 性能基线 | `tests/perf/` | benchmark 只做基线，不阻断早期 PR |

---

## 五、兼容策略

### 5.1 `/api/products` 分页

- 短期保持返回类型为数组。
- 添加可选 `skip` / `limit`，默认行为与旧前端接近。
- 若未来改为 `{items, total, skip, limit}`，必须新开 `/api/v2/products` 或前端同步切换。

### 5.2 Decimal 序列化

- 短期保持前端接收 number，不改变响应类型。
- 若资金字段改为 string，必须明确字段级契约并补前端适配。
- 所有精度迁移必须配套 API 契约测试。

### 5.3 错误响应标准化

- P2 阶段推进，避免在 P0/P1 中打断前端错误处理。
- 新格式落地前保留 FastAPI 默认 `detail`，或在前端统一 adapter 层兼容两种格式。

### 5.4 Mock/Scheduler 开关

- 开发环境通过 `.env` 显式设置：

```env
ENV=development
INIT_MOCK_DATA=true
ENABLE_SCHEDULER=true
```

- 生产环境必须显式关闭 mock data，并将 scheduler 独立进程化。

---

## 六、回滚与应急方案

| 变更 | 回滚/应急 |
|------|-----------|
| DB engine 条件化 | 移除 WAL PRAGMA，保留 SQLite timeout；PostgreSQL 参数仍需保留 |
| mock data 开关 | 开发环境设置 `INIT_MOCK_DATA=true` |
| scheduler 开关 | 移除 `ENABLE_SCHEDULER` 并重启；采集独立 worker 后再恢复 |
| cache dict 化 | 如实时行情异常，临时 `invalidate_cache()` 并降级为无缓存查询 |
| rate limit | 调高限流阈值或临时关闭 middleware，但保留安全测试为待修 |
| Alembic schema 迁移 | 先备份 SQLite 文件；执行 downgrade 或恢复备份 |
| Decimal 序列化 | API 层临时转 float，恢复前端兼容 |
| `/api/products` 分页 | 默认 `limit=1000` 临时兼容旧页面 |

---

## 七、Review 计划（多视角验证）

### 7.1 Review 维度与检查表

| 视角 | 检查项 | 当前评分 | 目标 | 检查方法 |
|------|--------|----------|------|----------|
| 后端架构 | 启动隔离、scheduler、防腐层、数据层边界 | 7/10 | 8/10 | 代码走读 |
| 安全 | 限流、JWT、CORS、密码策略、XSS | 7/10 | 8.5/10 | 安全测试 + 代码审计 |
| 运维 | `/health`、日志、配置、部署开关 | 5/10 | 8/10 | 部署演练 |
| 前端契约 | 字段一致性、分页、错误格式、时间格式 | 6/10 | 8/10 | 联调 + 契约快照 |
| 性能并发 | SQLite 并发、缓存锁、N+1、深分页 | 5/10 | 8/10 | 并发测试 + query count |
| 业务正确 | OHLC、昨结算价、合约、交易日历 | 5/10 | 8/10 | 业务数据校验 |

### 7.2 Review 执行流程

**Round 1：P0 代码走读**

- `models.py` engine 条件化。
- `main.py` mock/scheduler 开关。
- `cache.py` lock。
- `realtime.py` 缓存 dict。
- `auth.py` 限流装饰器与 app 集成。
- `tests/conftest.py` 是否使用独立 test DB。

**Round 2：安全审计**

- SQL 注入：`/api/varieties?search=' OR 1=1 --`
- XSS：评论 `<script>` 输入。
- 认证绕过：无 token / fake token / expired token。
- 限流：连续注册/登录触发 429。

**Round 3：并发压测**

- 20 线程访问 `/api/realtime/AU`，验证缓存无异常。
- scheduler 写入 + 用户注册/评论写入混合测试。
- SQLite WAL 文件库混合读写，无 `database is locked`。

**Round 4：业务数据校验**

- OHLC 不合法数据被丢弃。
- `pre_settlement` 缺失或为 0 不崩溃。
- Decimal 字段迁移后精度无尾差。

**Round 5：回归验证**

- 旧接口 `/api/products` 兼容。
- 前端首页/列表页/详情页/K 线图正常展示。
- 评论区正常显示、可发表评论。

### 7.3 Review 通过标准

- P0 全部完成。
- `pytest -m "not slow"` 全部通过。
- 测试不依赖真实开发库。
- 安全测试无注入、限流生效。
- 并发测试无缓存异常和 SQLite 锁错误。
- 前端联调通过。

---

## 八、测试计划（分层执行）

### 8.1 测试基础设施

```bash
pip install pytest pytest-asyncio httpx pytest-cov slowapi
```

```ini
# python/pytest.ini
[pytest]
markers =
    unit: fast unit tests
    integration: API and database integration tests
    concurrency: thread/process contention tests
    security: security boundary tests
    business: futures-domain correctness tests
    slow: slow tests excluded from default CI
    perf: performance baseline tests
```

### 8.2 P0 测试用例

#### 测试隔离

```python
def test_no_hardcoded_user(client):
    r = client.post("/api/auth/login", data={
        "username": "trader001",
        "password": "password123",
    })
    assert r.status_code == 401

def test_uuid_user_register_login(client):
    import uuid
    username = f"u_{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register", json={
        "username": username,
        "email": f"{username}@test.com",
        "password": "password123",
    })
    r = client.post("/api/auth/login", data={
        "username": username,
        "password": "password123",
    })
    assert r.status_code == 200
```

#### 缓存正确性

```python
def test_cache_concurrent_safety():
    import threading
    from services.cache import get_cached

    errors = []

    def worker():
        try:
            value = get_cached("test:concurrent", lambda: {"price": 450.0}, ttl=5)
            assert isinstance(value, dict)
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
```

#### 实时行情不缓存 ORM

```python
def test_realtime_response_is_plain_json(client, seeded_realtime_quote):
    r = client.get("/api/realtime/AU")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    assert "current_price" in data
```

#### 鉴权边界

```python
def test_no_token_401(client):
    r = client.post("/api/comments", json={"product_id": 1, "content": "x"})
    assert r.status_code == 401

def test_fake_token_401(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 401

def test_expired_token_401(client):
    import jwt
    from datetime import datetime, timedelta, timezone
    from config import SECRET_KEY, ALGORITHM

    token = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
```

#### SQLite 文件库并发

```python
def test_sqlite_wal_enabled(db_engine):
    from sqlalchemy import text
    with db_engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
    assert mode.lower() == "wal"
```

### 8.3 P1 测试用例

```python
def test_blank_comment_rejected():
    import pytest
    from pydantic import ValidationError
    from schemas import CommentCreate

    with pytest.raises(ValidationError):
        CommentCreate(product_id=1, content="   ")

def test_clean_ohlc_integrity():
    from datetime import datetime
    from data_collector.cleaner import clean_kline

    raw = [{
        "symbol": "AU",
        "trading_time": datetime.now(),
        "open_price": 100,
        "high_price": 95,
        "low_price": 98,
        "close_price": 102,
        "volume": 1000,
    }]
    assert clean_kline(raw, "AU") == []
```

### 8.4 性能基线测试

性能测试先用于观察，不作为早期 PR 阻断项。

```python
def test_realtime_cached_latency(benchmark, client, seeded_realtime_quote):
    client.get("/api/realtime/AU")
    result = benchmark(client.get, "/api/realtime/AU")
    assert result.status_code == 200
```

---

## 九、修复路线图时间线

```text
Week 1 (P0)
├─ Day 1: DB engine 条件化 + mock/scheduler 环境开关
├─ Day 2: cache lock + realtime dict 缓存
├─ Day 3: auth 限流 + 测试隔离 conftest.py
├─ Day 4: P0 自动化测试补齐
└─ Day 5: P0 review + 前端冒烟回归

Week 2-3 (P1)
├─ Alembic 迁移方案 + pre_settlement
├─ OHLC 校验 + 输入验证 + 评论统一鉴权
├─ scheduler 防重入 + N+1 修复
├─ /health /ready + docs/CORS 生产配置
└─ P1 review + 业务数据校验

Week 4-6 (P2)
├─ 代码规范：import/type hints/logging
├─ 错误响应标准化 + 契约快照测试
├─ CI/CD 基础门禁
└─ 性能基线与慢测试分组

Week 7-8 (P3)
├─ PostgreSQL 迁移验证
├─ Redis 缓存/限流后端
├─ 交易日历 + 夜盘处理
└─ 50 并发压测

Week 9-12 (P4)
├─ SSE/WebSocket 实时推送
├─ 合约换月 + 主连 K 线拼接
├─ 审计日志 + 监控告警
└─ 混沌测试
```

---

## 十、验收标准汇总

| 阶段 | 标准 |
|------|------|
| P0 完成 | `pytest -m "not slow"` 通过；测试不依赖真实库；无 mock 弱口令默认用户；scheduler 默认不启动；缓存不存 ORM；限流生效 |
| 上线标准 | P0 全部完成；P1 中 `/health`、docs/CORS、输入校验、OHLC、scheduler 防重入完成；旧接口兼容；前端联调通过 |
| 生产级标准 | PostgreSQL 迁移验证；监控和结构化日志接入；100 万条 K 线查询基线达标；50 并发错误率 0%；业务字段与交易所语义一致 |

---

## 十一、一句话总结

v4.1 的核心变化是把 P0 从“所有正确的事”收敛为“真正阻塞上线的事”：数据库启动安全、mock/scheduler 环境隔离、缓存对象生命周期、认证限流和测试隔离。Decimal、昨结算价、合约维度等业务正确性问题仍然重要，但必须通过 Alembic、兼容策略和回滚方案进入 P1，避免一次性大改造成新的不稳定来源。
