# 后端迭代方案 v7 —— 综合整改计划

> 版本：v7 Comprehensive
> 生成日期：2026-05-05
> 依据：`BACKEND_TECH_REVIEW_AND_ITERATION_PLAN_20260505.md` + `BACKEND_COMPREHENSIVE_REVIEW_20260505.md` 综合评审结果
> 目标：把生产运行的硬风险压下去，补齐期货业务核心数据模型，建立可扩展的运维体系

---

## 计划评价

V7 的总体方向正确，已经覆盖了前次后端架构审查中最关键的风险：PostgreSQL upsert、生产禁用 SQLite、CORS 配置、缓存 DTO、合约模型、K 线按合约隔离、换月历史、交易日历、夜盘归属和实时推送。相较早期计划，它不再停留在功能堆叠，而是先处理生产阻断点，再补期货业务模型，这个顺序是合理的。

仍需修正的地方主要有五类：

1. **实施细节需更稳**：`dialect_insert` 不应放到 `models.py`，应留在 `upsert.py`，避免模型层反向承载写入策略。
2. **迁移策略需更谨慎**：`kline_data.contract_id` 不能长期 nullable 后直接依赖唯一键，否则 PostgreSQL/SQLite 对 NULL 唯一约束语义会让脏数据继续进入。
3. **生产降级需更克制**：Tushare/AkShare 初始化失败时，开发环境可以 fallback Mock；生产 worker 不应悄悄切 Mock 伪造行情，应失败并告警。
4. **Decimal 改造需兼容前端**：数据库和内部计算应使用 Decimal/Numeric，但现有 API 若直接把 JSON number 改成 string 会影响前端；需分阶段兼容。
5. **SSE 触发机制需重设**：第四阶段拆分 API 与 worker 后，worker 不能直接触发 API 进程内 broadcast；SSE 应通过 Redis Pub/Sub 或 API 侧轻量读取数据源实现。

基于以上评价，下面计划保留 V7 的阶段结构，但对关键任务做了落地修订。

---

## 一、迭代总览

本轮迭代不是一次性重构全部架构，而是分五个阶段，从"可运行"到"可追溯"到"可扩展"，逐步推进。

| 阶段 | 主题 | 优先级 | 建议周期 | 核心产出 |
|------|------|--------|----------|----------|
| 第一阶段 | P0/P1 稳定性修复 | P0/P1 | 2-3 天 | PostgreSQL 兼容、配置安全、缓存安全、评论分页 |
| 第二阶段 | 合约与 K 线模型重建 | P1 | 5-7 天 | contracts 表、K 线绑定 contract、换月历史 |
| 第三阶段 | 期货交易日与业务建模 | P1/P2 | 5-7 天 | 交易日历、夜盘归属、涨跌停识别、时区统一 |
| 第四阶段 | 生产化与可观测性 | P2 | 7-10 天 | Worker 拆分、Redis 限流、Prometheus 监控、数据源熔断 |
| 第五阶段 | 实时推送与前端升级 | P2 | 5-7 天 | SSE 行情推送、前端降级轮询、合约选择 K 线 |

---

## 二、第一阶段：P0/P1 稳定性修复

**目标**：消除生产阻断风险，使系统在 PostgreSQL 下可稳定运行，配置不再误判，缓存和查询安全。

**建议周期**：2-3 天

### 任务 1：修复 PostgreSQL upsert dialect（P0）

**改动范围**：
- `python/data_collector/upsert.py`
- `python/tests/`（新增 PostgreSQL 集成测试）

**实施要点**：
```python
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from models import engine

def dialect_insert(model):
    if engine.dialect.name == "postgresql":
        return pg_insert(model)
    if engine.dialect.name == "sqlite":
        return sqlite_insert(model)
    return sqlite_insert(model)
```
- 所有 `insert(Model)` 改为 `dialect_insert(Model)`。
- `dialect_insert` 放在 `data_collector/upsert.py` 内，不放入 `models.py`，避免模型层依赖写入策略。
- PostgreSQL 的 `on_conflict_do_update` 需使用 `set_={"column": stmt.excluded.column}` 语法，和 SQLite 相同。
- `upsert_fut_weekly_detail_bulk`、`upsert_fut_wsr_bulk`、`upsert_fut_holding_bulk` 从逐条查询改为批量 upsert 前，必须先补齐对应唯一约束；没有唯一约束时不要使用 `on_conflict_do_nothing`，否则冲突目标不明确。
- PostgreSQL 集成测试使用临时 schema 或独立测试库，测试结束清理数据，避免污染开发库。

**验收标准**：
- [ ] PostgreSQL 下 `upsert_realtime`、`insert_kline_bulk`、`upsert_fut_daily_bulk`、`upsert_fut_settle_bulk`、`upsert_fut_price_limit_bulk` 均可执行。
- [ ] SQLite 测试不回退，CI 全部通过。
- [ ] 新增 `test_postgres_upsert_integration.py`，在 CI 的 PostgreSQL service 容器上运行。

---

### 任务 2：生产禁止 SQLite（P1）

**改动范围**：
- `python/config.py`
- `.env.example`
- `python/tests/test_p0_fixes.py`

**实施要点**：
```python
if ENV == "production" and DATABASE_URL.startswith("sqlite"):
    raise ValueError("SQLite is not allowed in production. Use PostgreSQL.")
```
- `.env.example` 中 ENV=production 时默认注释 SQLite，启用 PostgreSQL 配置。

**验收标准**：
- [ ] `ENV=production DATABASE_URL=sqlite:///x.db` 导入配置时抛出 `ValueError`。
- [ ] `ENV=production DATABASE_URL=postgresql://...` 正常启动。
- [ ] 测试覆盖上述两种场景。

---

### 任务 3：修复 CORS 配置不一致（P1）

**改动范围**：
- `python/main.py`
- `.env.example`
- `python/tests/test_p0_fixes.py`

**实施要点**：
```python
origins_raw = os.getenv("CORS_ORIGINS") or os.getenv("ALLOW_ORIGINS")
if ENV == "production" and not origins_raw:
    raise ValueError("CORS_ORIGINS (or ALLOW_ORIGINS) is required in production")
origins = [origin.strip() for origin in origins_raw.split(",") if origin.strip()]
```
- `.env.example` 统一使用 `CORS_ORIGINS`，保留注释说明旧名称仍兼容。

**验收标准**：
- [ ] 测试覆盖 `CORS_ORIGINS` 和 `ALLOW_ORIGINS` 两种变量名。
- [ ] 生产环境缺失 CORS 配置时启动失败。

---

### 任务 4：缓存 DTO 化（P1）

**改动范围**：
- `python/routers/realtime.py`
- `python/services/cache.py`
- `python/tests/test_p0_fixes.py`

**实施要点**：
```python
def _fetch():
    q = db.query(RealtimeQuoteDB).filter(...).first()
    if not q:
        return None
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
```
- 缓存中只存 `dict`，不存 ORM 实例。
- 保留 TTL、LRU 和线程锁行为不变。

**验收标准**：
- [ ] 并发请求 `/api/realtime/AU` 100 次，无 `DetachedInstanceError` 或 session 异常。
- [ ] API 响应结构不变，前端兼容。

---

### 任务 5：修复 Alembic 版本硬编码（P1）

**改动范围**：
- `python/models.py`
- `python/tests/test_phase1_3_integration.py`

**实施要点**：
- 删除 `init_db()` 中手动插入 `alembic_version` 的逻辑。
- `init_db()` 仅执行 `Base.metadata.create_all(bind=engine)` 和 SQLite WAL 设置。
- 新环境部署时，使用 `alembic upgrade head` 管理 schema 迁移。
- 非生产环境（`ENV != production`）保留 `create_all` 以支持开发零配置启动。
- 生产环境不执行 `Base.metadata.create_all()`；启动前必须完成 `alembic upgrade head`。如需启动时校验，可只检查当前 revision 是否等于 head，不自动建表。

**验收标准**：
- [ ] 空库启动后，`alembic_version` 表不存在或由 Alembic 自行管理。
- [ ] `alembic upgrade head` 可从空库创建完整 schema。
- [ ] CI 执行 `alembic upgrade head` 后启动应用，无报错。

---

### 任务 6：调度器延迟初始化（P1）

**改动范围**：
- `python/data_collector/scheduler.py`
- `python/main.py`

**实施要点**：
- `_build_collectors()` 不再在模块导入时执行，改为 `start_scheduler()` 首次调用时延迟初始化。
- 非生产环境若所有 collector 初始化失败，可降级为 `MockCollector` 并记录 `CRITICAL` 日志，保证开发应用可启动。
- 生产环境的 worker 不应静默降级到 Mock 行情；应启动失败或进入 unhealthy 状态并触发告警，避免向用户展示伪造行情。
- 模块级全局变量改为 `None`，通过 `@lru_cache` 或单例模式延迟实例化。

**验收标准**：
- [ ] 非生产环境 Tushare Token 无效时，应用仍可启动，scheduler 以 Mock 模式运行。
- [ ] 非生产环境日志中记录 `CRITICAL: All collectors failed, fallback to MockCollector`。
- [ ] `ENV=production DATA_SOURCE=tushare` 且 Tushare 初始化失败时，worker 健康检查失败，不向外提供 Mock 行情。

---

### 任务 7：修复健康探针 scheduler 语义（P1）

**改动范围**：
- `python/routers/health.py`

**实施要点**：
```python
scheduler_ok = True  # API 进程本身不判断 scheduler 是否启用
# 或：若需监控 scheduler 健康，检查最近心跳时间
```
- `/health/ready` 的 readiness 逻辑改为：DB 可连接即 `ready=True`。
- scheduler 健康状态单独在 `/health/scheduler` 暴露（返回最近运行时间、任务数、下次运行时间）。

**验收标准**：
- [ ] `ENABLE_SCHEDULER=0` 时，`/health/ready` 仍返回 `ready=True`。
- [ ] 新增 `/health/scheduler` 端点，返回 scheduler 状态。

---

### 任务 8：评论空白内容校验 + 分页（P2）

**改动范围**：
- `python/schemas.py`
- `python/routers/comments.py`
- `python/tests/test_p0_fixes.py`

**实施要点**：
```python
@field_validator("content", mode="before")
@classmethod
def sanitize_content(cls, v: str) -> str:
    if isinstance(v, str):
        v = html.escape(v.strip())
    if not v:
        raise ValueError("评论内容不能为空")
    return v
```
- `get_user_comments` 增加 `skip: int = Query(0, ge=0)`、`limit: int = Query(100, ge=1, le=1000)`。
- `get_product`（`routers/products.py`）中的评论查询也增加分页参数。

**验收标准**：
- [ ] `content="   "` 返回 422，`"评论内容不能为空"`。
- [ ] 评论列表接口支持 `?skip=0&limit=10`。
- [ ] 超过 1000 条时截断。

---

### 任务 9：通用异常处理器环境感知（P2）

**改动范围**：
- `python/main.py`

**实施要点**：
```python
@app.exception_handler(Exception)
async def generic_exception_handler(request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    content = {"code": "INTERNAL_ERROR", "message": "服务器内部错误"}
    if ENV == "development":
        content["detail"] = str(exc)
        content["traceback"] = traceback.format_exc()
    return JSONResponse(status_code=500, content=content)
```

**验收标准**：
- [ ] 开发环境返回异常详情；生产环境不暴露。
- [ ] 前端 500 错误弹窗可显示 `message` 字段。

---

### 第一阶段验收清单

- [ ] 全部测试通过：`SECRET_KEY=test-secret-key pytest tests/ -v`
- [ ] PostgreSQL 集成测试通过（CI 中 docker-compose up -d postgres）
- [ ] 手动验证：`ENV=production DATABASE_URL=sqlite:///x.db python -c "import config"` 抛出 ValueError
- [ ] 手动验证：`ENABLE_SCHEDULER=0` 时 `/health/ready` 返回 `ready=True`
- [ ] 手动验证：非生产环境 Tushare Token 无效时应用仍可启动并降级 Mock；生产 worker 不降级 Mock，而是 unhealthy 并告警

---

### 第一阶段复核补充（2026-05-05）

> 本节记录第一阶段现有实现与 V7 验收标准之间的差距。后续继续推进第一阶段时，应优先补齐本节，而不是直接进入第二阶段。

#### 当前复核结论

- PostgreSQL 服务启动后，现有测试可运行到 `44 passed, 2 skipped, 1 failed`；唯一失败为 `test_kline_has_data`，原因是本地 PostgreSQL 中存在 `AU` 品种但没有 `AU/1h` K 线测试数据（查询结果为 `variety_id=1, count=0`）。
- `requirements.txt` 已发现并补充两个环境依赖问题：`email-validator==2.2.0`（Pydantic `EmailStr` 必需）和 `bcrypt<5`（避免 `passlib==1.7.4` 与 bcrypt 5.x 不兼容）。
- 现有测试“接近全绿”不等于第一阶段完全验收通过；当前测试尚未覆盖若干 V7 第一阶段关键风险。

#### 仍未闭环的代码项

| 项目 | 当前状态 | 需要补齐 |
|------|----------|----------|
| 生产环境禁止自动建表 | `models.init_db()` 仍无条件执行 `Base.metadata.create_all(bind=engine)`，`main.lifespan` 仍无条件调用 `init_db()` | 生产环境不执行 `create_all`；生产启动只做 Alembic revision 校验或完全依赖部署前 `alembic upgrade head` |
| 生产环境禁止 Mock fallback | `scheduler._ensure_collectors()` 在 `DATA_SOURCE=tushare/auto` 且真实 collector 全失败时仍可能加入 `MockCollector` | `ENV=production` 时真实数据源失败必须 unhealthy / fail fast；仅开发环境允许降级 Mock |
| CORS 模板变量名统一 | `.env.example` 仍写 `ALLOW_ORIGINS` | 改为 `CORS_ORIGINS`，并注释说明 `ALLOW_ORIGINS` 仅作为旧兼容变量 |
| Alembic 测试语义 | `test_phase1_3_integration.py` 仍期待 `alembic_version` 一定存在 | 调整为：`create_all` 开发启动不要求 `alembic_version`；`alembic upgrade head` 后由 Alembic 自行创建并维护 |
| K 线接口测试数据 | `test_kline_has_data` 依赖本地库已有 `AU/1h` 数据 | 测试内显式插入一条 `KlineDataDB(variety_id=AU.id, period="1h", ...)`，避免依赖调度器或历史采集结果 |

#### 仍需新增或增强的测试

| 测试文件 | 覆盖目标 | 关键断言 |
|----------|----------|----------|
| `tests/test_production_config.py` | 生产配置安全 | `ENV=production + sqlite` 导入配置失败；`ENV=production + postgresql` 可通过配置校验；生产缺失 CORS 配置失败 |
| `tests/test_cors_variable.py` | CORS 变量兼容 | `CORS_ORIGINS` 优先；仅设置 `ALLOW_ORIGINS` 时仍兼容；两个都缺失且生产环境时报错 |
| `tests/test_postgres_upsert_integration.py` | PostgreSQL upsert 真执行 | `upsert_realtime`、`insert_kline_bulk`、`upsert_fut_daily_bulk`、`upsert_fut_settle_bulk`、`upsert_fut_price_limit_bulk` 在 PostgreSQL 下可插入、冲突更新或跳过 |
| `tests/test_alembic_upgrade.py` | 迁移链完整性 | 空 PostgreSQL 测试库执行 `alembic upgrade head` 后 schema 完整；应用启动不写死旧 revision |
| `tests/test_scheduler_fallback.py` | 数据源降级边界 | 开发环境真实 collector 失败可 fallback Mock 并记录告警；生产环境不 fallback Mock |
| `tests/test_cache_orm_detached.py` | 缓存 DTO 化 | 多次/并发请求 `/api/realtime/AU` 不返回 ORM 实例，不出现 `DetachedInstanceError` |
| `tests/test_comment_validation_and_pagination.py` | 评论输入和分页 | `content="   "` 返回 422；用户评论、品种详情评论支持 `skip/limit`，`limit>1000` 返回 422 |
| `tests/test_kline_seeded_api.py` | K 线 API 稳定测试 | 测试自建 `AU/1h` K 线数据，接口返回非空且按时间升序/降序符合当前 API 约定 |

#### 本地 Tushare 灌库前置建议

- 本地研究 Tushare 数据可以使用 PostgreSQL：`DATABASE_URL=postgresql://futures:futures123@localhost:15432/futures_community`。
- 建议先执行 `alembic upgrade head`，再启动应用或手动运行采集脚本，避免 `create_all` 与 Alembic 管理的 schema 混用。
- 灌库研究不应替代自动化测试。Tushare 数据依赖 token、积分、交易日、外部接口状态，适合人工分析；自动化测试仍应使用可控 fixture 或 mock collector。
- 第一阶段继续完善时，建议先让测试库和开发研究库分离：开发库用于 Tushare 真实数据探索，测试库用于可重复验收，避免测试结果受已有行情数据影响。

#### 第一阶段重新验收命令建议

```powershell
# PostgreSQL 基础设施
cd D:\Code\project_rich_snowball
docker-compose up -d postgres

# 后端依赖
cd D:\Code\project_rich_snowball\python
python -m pip install -r requirements.txt

# 迁移
$env:SECRET_KEY="test-secret-key-for-local-development-123456"
$env:ENV="development"
$env:ENABLE_SCHEDULER="0"
$env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
alembic upgrade head

# 全量测试
pytest tests/ -v
```

第一阶段完成的最低标准应为：
- [ ] SQLite 本地测试全绿。
- [ ] PostgreSQL 本地测试全绿。
- [ ] PostgreSQL upsert 专项测试全绿。
- [ ] 生产配置安全测试全绿。
- [ ] 生产环境不会自动建表，也不会降级 Mock 行情。

---

## 三、第二阶段：合约与 K 线模型重建

**目标**：建立合约生命周期管理，K 线数据绑定具体合约，主力换月可追溯。

**建议周期**：5-7 天

### 任务 10：新增 contracts 表

**改动范围**：
- `python/models.py`
- `python/alembic/versions/`（新增迁移脚本）
- `python/data_collector/init_varieties.py`
- `python/schemas.py`

**模型设计**：
```python
class ContractDB(Base):
    __tablename__ = "contracts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id"), nullable=False, index=True)
    contract_code = Column(String(30), unique=True, nullable=False, index=True)
    exchange = Column(String(20), nullable=False)
    listing_date = Column(DateTime)
    last_trading_date = Column(DateTime)
    is_main = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.datetime.now(timezone.utc), onupdate=datetime.datetime.now(timezone.utc))
```

**实施要点**：
- `varieties.contract_code` 暂时保留作为兼容字段，文档注明为"当前主力合约缓存"；不要把现有 Column 改成 `@property`，否则会破坏迁移和兼容接口。
- 初始化时为每个品种创建当前合约记录（从 `variety.contract_code` 迁移）。
- `RealtimeQuoteDB` 可增加 `contract_id` 和 `contract_code_snapshot`，但第一步保持 `variety_id` 唯一约束不变，避免旧实时行情接口破裂；当数据源能稳定返回具体合约后，再改为按合约存多条实时报价。

**验收标准**：
- [ ] `contracts.contract_code` 唯一。
- [ ] 每个初始化品种至少有一个 `is_main=True` 的合约。
- [ ] 同一 `variety_id` 只能有一个 `is_main=True` 合约，可通过应用逻辑或数据库部分唯一索引保障。
- [ ] Alembic 迁移可从空库 `upgrade head`。

---

### 任务 11：K 线绑定 contract_id

**改动范围**：
- `python/models.py`
- `python/data_collector/upsert.py`
- `python/routers/kline.py`
- `python/alembic/versions/`

**实施要点**：
- `kline_data` 增加 `contract_id`（迁移第一步允许 `nullable=True`，完成回填后改为新写入必填）。
- 新唯一键：`contract_id, period, trading_time`。不要长期依赖 `contract_id=NULL` 的唯一约束，因为 PostgreSQL/SQLite 都允许多条 NULL 通过唯一约束。
- 旧数据迁移：为现有 K 线查找对应 `contract_id`（通过 `variety.contract_code` 匹配）。无法匹配的旧数据标记为 `migration_status="unmatched"` 或写入迁移报告，不允许新的 K 线继续以 `NULL contract_id` 入库。
- `insert_kline_bulk` 根据 `contract_code` 查询 `contract_id`，再写入。
- `clean_kline` 必须保留并传递 `contract_code`；如果数据源返回的 `contract_code` 与当前采集目标不一致，记录告警并跳过。
- `routers/kline.py` 旧接口 `/api/kline/{symbol}` 默认查询当前主力合约（`is_main=True`）。
- 新增 `/api/kline/{symbol}?contract_code=AU2512` 按具体合约查询。

**验收标准**：
- [ ] 同一品种两个合约、同一周期、同一时间 K 线可同时入库，不冲突。
- [ ] 新写入 K 线 `contract_id` 非空；无法解析合约时返回 skipped 并记录采集批次错误。
- [ ] 旧接口前端不破（返回当前主力合约 K 线）。
- [ ] 新接口可按 `contract_code` 查询历史合约 K 线。

---

### 任务 12：记录主力合约换月历史

**改动范围**：
- `python/models.py`
- `python/data_collector/pipeline.py` `run_fut_mapping()`
- `python/data_collector/scheduler.py`

**模型设计**：
```python
class ContractRolloverDB(Base):
    __tablename__ = "contract_rollovers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id"), nullable=False, index=True)
    old_contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False)
    new_contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False)
    old_contract_code = Column(String(30), nullable=False)
    new_contract_code = Column(String(30), nullable=False)
    effective_date = Column(DateTime, nullable=False)
    source = Column(String(50), default="tushare_fut_mapping")
    created_at = Column(DateTime, default=datetime.datetime.now(timezone.utc))
```

**实施要点**：
- `run_fut_mapping()` 发现主力变化时：
  1. 插入新合约到 `contracts`（若不存在）。
  2. 更新旧合约 `is_main=False`。
  3. 更新新合约 `is_main=True`。
  4. 更新 `varieties.contract_code`（兼容）。
  5. 插入 `contract_rollovers` 记录。
- 上述 5 步必须在同一个数据库事务中完成；失败时整体回滚，避免出现两个主力合约或无主力合约。
- `effective_date` 使用数据源返回的 `trade_date`，不要用任务运行时间代替。
- 不再只覆盖 `varieties.contract_code`。

**验收标准**：
- [ ] 任何主力切换都有审计记录。
- [ ] 历史 K 线不被新合约覆盖（旧合约 K 线仍可按 `contract_code` 查询）。
- [ ] 同一品种任意时刻最多一个 `is_main=True` 合约。
- [ ] 测试：模拟 AU2506 → AU2512 切换，断言 rollover 记录存在，旧 K 线可查询。

---

### 任务 13：金融字段精度统一（P1）

**改动范围**：
- `python/models.py`
- `python/data_collector/cleaner.py`
- `python/data_collector/adapters.py`
- `python/schemas.py`

**实施要点**：
- 资金/结算类字段统一 `Numeric(18, 6)`：
  - `fut_settle.settle`、`trading_fee_rate`、`trading_fee`、`delivery_fee`...
  - `fut_price_limits.up_limit`、`down_limit`
  - `fut_daily_data.amount`
  - `products.pre_settlement`、`margin`、`commission`
  - `watchlists.resistance_level`、`support_level`
- 行情展示类字段改为 `Numeric(18, 4)`：
  - `realtime_quotes.current_price`、`open_price`、`high`、`low`、`bid1`、`ask1`
  - `kline_data.open_price`、`high_price`、`low_price`、`close_price`
  - `products.current_price`、`open_price`、`high`、`low`
- Cleaner 层返回 `Decimal`（`from decimal import Decimal`），不再转 `float`。
- Schema 层内部可以使用 `Decimal` 类型，但现有前端已按 JSON number 消费价格字段；本阶段保持现有公开响应字段兼容，可在 response mapper 中显式 `float(quantized_decimal)` 用于展示。
- 对资金、结算、保证金等后续可能参与计算的字段，新增 v2 响应字段或文档注明可返回 string，以避免 JSON number 精度损失。

**验收标准**：
- [ ] 新增 Decimal 精度测试：`Decimal("0.1") + Decimal("0.2") == Decimal("0.3")`。
- [ ] 现有 API 响应中行情展示字段仍为 JSON number，前端不需要同步改动。
- [ ] 内部资金/结算计算不使用 float。
- [ ] SQLite 和 PostgreSQL 均支持 Numeric。

---

### 第二阶段验收清单

- [ ] `alembic upgrade head` 从空库创建完整 schema（含 contracts、contract_rollovers、K 线 contract_id）。
- [ ] 同一品种多合约 K 线并存测试通过。
- [ ] 主力换月历史记录测试通过。
- [ ] 所有金融字段 Decimal 精度测试通过。

---

## 四、第三阶段：期货交易日与业务建模

**目标**：建立交易日历，正确处理夜盘归属、涨跌停、时区策略。

**建议周期**：5-7 天

### 任务 14：交易日历服务

**改动范围**：
- 新增 `python/services/trading_calendar.py`
- 新增 `python/models.py` `TradingCalendarDB`
- `python/data_collector/scheduler.py`（任务跳过逻辑）

**实施要点**：
```python
class TradingCalendarDB(Base):
    __tablename__ = "trading_calendar"
    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange = Column(String(20), nullable=False, index=True)
    trading_date = Column(Date, nullable=False, index=True)
    is_trading_day = Column(Boolean, nullable=False)
    session_day = Column(Boolean, default=True)   # 日盘是否交易
    session_night = Column(Boolean, default=True) # 夜盘是否交易
    is_holiday = Column(Boolean, default=False)
    holiday_name = Column(String(50))
```
- 初始化时导入国内期货交易所（上期所、大商所、郑商所、中金所、能源中心、广期所）近 2 年交易日历。
- 提供函数 `get_trading_day(exchange, dt: datetime) -> date`：
  - 21:00-23:59 和 00:00-02:30 归属下一交易日。
  - 如果下一自然日不是交易日，继续向后查找下一个交易日，不能简单取自然日 + 1。
  - 非交易时间或休市日返回 `None`，由调用方决定跳过或降级；不要默认返回上一交易日，以免把休市数据误归档。
- Scheduler 的日终任务（16:05 后）在运行前检查当日是否为交易日，非交易日跳过。

**验收标准**：
- [ ] 2026-01-01（元旦）`is_trading_day=False`。
- [ ] 2026-01-02 21:00 的夜盘归属下一个交易日，而不是周六 2026-01-03；测试应按导入日历断言具体日期。
- [ ] 非交易日不触发日线同步，或明确跳过并记录日志。

---

### 任务 15：K 线增加 trading_day / session

**改动范围**：
- `python/models.py` `KlineDataDB`
- `python/data_collector/adapters.py`
- `python/data_collector/cleaner.py`

**实施要点**：
- `kline_data` 增加 `trading_day`（`Date`）和 `session`（`String(10)`，取值 `day`/`night`/`full`）。
- Adapter 层根据 `trading_time` 和 `TradingCalendarDB` 计算 `trading_day`。
- Cleaner 层校验 `trading_day` 非空。
- 所有 `datetime` 统一使用 timezone-aware（`datetime.now(timezone.utc)` 或东八区业务时间 + UTC 存储）。
- 建议策略：数据库统一存储 UTC，`trading_day` 按东八区业务日计算，API 层按前端时区格式化。

**验收标准**：
- [ ] 夜盘 K 线（21:00-23:59, 00:00-02:30）的 `session="night"`。
- [ ] 日盘 K 线（09:00-15:00）的 `session="day"`。
- [ ] 日线聚合不会把夜盘错误归到自然日。

---

### 任务 16：涨跌停识别

**改动范围**：
- `python/models.py`
- `python/data_collector/cleaner.py`
- `python/routers/realtime.py`

**实施要点**：
- `RealtimeQuoteDB` 增加 `limit_status`（`String(10)`，取值 `normal`/`up_limit`/`down_limit`）。
- Cleaner 层结合 `fut_price_limits` 表识别：
  - 若 `current_price >= up_limit * 0.999` → `up_limit`
  - 若 `current_price <= down_limit * 1.001` → `down_limit`
  - 容差 0.1% 避免浮点精度问题（改为 Decimal 后可用精确比较）。
- `RealtimeResponse` Schema 增加 `limit_status` 字段。
- `routers/realtime.py` 返回时填充该字段。

**验收标准**：
- [ ] 当前价等于涨停价时 API 返回 `limit_status="up_limit"`。
- [ ] 当前价等于跌停价时 API 返回 `limit_status="down_limit"`。
- [ ] 正常价格返回 `limit_status="normal"`。

---

### 第三阶段验收清单

- [ ] 交易日历导入测试：覆盖元旦、春节、国庆。
- [ ] 夜盘 trading_day 归属测试：21:00 归属下一交易日。
- [ ] 涨跌停识别测试：涨停/跌停/正常三种状态。
- [ ] 时区统一测试：数据库 UTC，API 东八区格式化。

---

## 五、第四阶段：生产化与可观测性

**目标**：API 与采集分离，限流熔断外部化，监控告警完整。

**建议周期**：7-10 天

### 任务 17：采集任务独立化

**改动范围**：
- `Dockerfile` / `docker-compose.yml`
- `python/main.py`
- `python/data_collector/scheduler.py`
- 新增 `python/worker.py`

**实施要点**：
- 拆分 `worker` 入口：
  ```python
  # worker.py
  import threading

  from data_collector.scheduler import start_scheduler

  start_scheduler()
  threading.Event().wait()
  ```
- 不使用 `signal.pause()` 作为唯一阻塞方式；该写法在 Windows 和部分容器环境不可用。
- `docker-compose.yml` 新增 `worker` 服务，单副本，`ENABLE_SCHEDULER=1`。
- `backend`（API）服务设置 `ENABLE_SCHEDULER=0`。
- `main.py` lifespan 中：`if ENABLE_SCHEDULER: start_scheduler()` 保留，支持开发单体模式。

**验收标准**：
- [ ] API 容器横向扩容（3 副本）不重复采集。
- [ ] Worker 单实例运行 scheduler，健康状态可通过 `/health` 探针可见。
- [ ] 开发环境 `python main.py` 仍可单体运行。

---

### 任务 18：限流和熔断外部化

**改动范围**：
- `python/routers/auth.py`
- 新增 `python/services/rate_limit.py`
- 新增 `python/services/circuit_breaker.py`
- `python/data_collector/base.py` / `scheduler.py`

**实施要点**：
- Redis 限流（滑动窗口）：
  ```python
  # services/rate_limit.py
  def is_allowed(key: str, limit: int, window: int) -> bool:
      # 使用 Redis sorted set，score 为时间戳
      ...
  ```
- 数据源熔断器：
  ```python
  # services/circuit_breaker.py
  class CircuitBreaker:
      states = ["CLOSED", "OPEN", "HALF_OPEN"]
      # 失败率 > 50% 进入 OPEN，60s 后 HALF_OPEN，成功则 CLOSED
  ```
- Auth 路由使用 Redis 限流替代进程内 dict。
- Collector 使用熔断器包装，Open 状态时直接跳过该数据源。

**验收标准**：
- [ ] 多进程下登录限流一致（并发 20 次请求，仅 10 次通过）。
- [ ] 数据源连续失败 5 次后进入冷却，不再请求外部 API。
- [ ] 冷却结束后自动探测恢复。

---

### 任务 19：监控与告警

**改动范围**：
- `python/main.py`
- `python/data_collector/pipeline.py`
- `python/routers/health.py`
- `requirements.txt`

**实施要点**：
- 接入 `prometheus-fastapi-instrumentator`：
  ```python
  from prometheus_fastapi_instrumentator import Instrumentator
  Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
  ```
- 自定义指标：
  - `futures_api_requests_total`（按 method、path、status 计数）
  - `futures_api_request_duration_seconds`（histogram）
  - `futures_cache_hits_total` / `futures_cache_misses_total`
  - `futures_scheduler_last_run_timestamp`（gauge，按 job_name）
  - `futures_collector_success_total` / `futures_collector_failed_total`（按 source、job_name）
  - `futures_db_connections_active`（gauge，通过 SQLAlchemy 连接池统计）
- Pipeline 中 `_record_run()` 同时更新 Prometheus counter/gauge。
- `/health/ready` 增加指标摘要（可选）。

**验收标准**：
- [ ] `curl http://localhost:8000/metrics` 可抓取 Prometheus 格式指标。
- [ ] Grafana 可配置告警规则：采集超过 5 分钟未更新触发告警。
- [ ] API P99 延迟 > 500ms 触发告警。

---

### 任务 20：Token 安全升级（可选，长期）

**改动范围**：
- `python/routers/auth.py`
- `python/dependencies.py`
- 前端 `lib/api.ts`

**实施要点**：
- 缩短 access token 至 15 分钟。
- 新增 `/api/auth/refresh` 接口，使用 refresh token（存 HttpOnly Cookie）换取新 access token。
- 或：直接改用 HttpOnly Cookie 传输 access token，前端不再手动管理 token。

**验收标准**：
- [ ] XSS 脚本无法读取 token。
- [ ] Token 过期后自动刷新，用户无感知。

---

### 第四阶段验收清单

- [ ] docker-compose up 启动 api（3 副本）+ worker（1 副本）+ postgres + redis。
- [ ] API 副本不重复采集。
- [ ] Prometheus 可抓取 `/metrics`。
- [ ] Redis 限流跨进程生效。
- [ ] 数据源熔断测试通过。

---

## 六、第五阶段：实时推送与前端升级

**目标**：降低行情延迟，从轮询升级到推送，支持合约选择。

**建议周期**：5-7 天

### 任务 21：SSE 实时行情推送

**改动范围**：
- 新增 `python/routers/sse.py`
- `python/main.py`
- 前端行情页面

**实施要点**：
- SSE 端点：`/api/sse/quotes`
- 服务端维护一个内存中的最近报价 dict（key: symbol）。
- 若第四阶段已拆分 API 与 worker，worker 不能直接触发 API 进程内 broadcast。推荐使用 Redis Pub/Sub：worker 采集完成后发布 quote event，API 订阅后更新内存 dict 并推送 SSE。
- 若暂不接入 Redis Pub/Sub，则 API 侧用轻量后台任务每 1-3 秒读取 `realtime_quotes.updated_at` 增量变化，再推送 SSE；不要依赖跨进程内存共享。
- 前端建立 SSE 连接，接收 `data: {"symbol": "AU", "price": 555.2, ...}`。
- 断线后前端自动重连（`EventSource.onerror` → `setTimeout` 重连）。
- 保留轮询作为降级（SSE 连接失败时，fallback 到 30 秒轮询）。

**验收标准**：
- [ ] 浏览器建立 SSE 连接后，行情更新延迟 < 5 秒（采集间隔 + 推送延迟）。
- [ ] 断线后 3 秒内自动重连。
- [ ] 同时支持 100+ 并发 SSE 连接（内存维持 dict，非数据库查询）。
- [ ] API 与 worker 分离部署时，SSE 仍能收到 worker 采集事件。

---

### 任务 22：前端 K 线合约选择

**改动范围**：
- 前端 `app/products/[id]/page.tsx`
- `components/KlineChart.tsx`
- `lib/api.ts`

**实施要点**：
- 品种详情页增加"合约选择"下拉框，列出该品种所有历史合约。
- 默认选中当前主力合约。
- 切换合约后，K 线图重新请求 `/api/kline/{symbol}?contract_code=AU2512`。
- 连续 K 线视图（可选）：`/api/varieties/{symbol}/continuous-kline`。

**验收标准**：
- [ ] 换月后 K 线图不再"跳跃"（数据按合约隔离）。
- [ ] 可查看历史合约 K 线（如 AU2506 已到期）。
- [ ] 连续 K 线视图正确拼接主力合约换月前后数据。

---

### 第五阶段验收清单

- [ ] SSE 行情推送延迟 < 5 秒。
- [ ] 前端合约选择功能正常。
- [ ] 连续 K 线数据正确（换月日价格不突变）。

---

## 七、测试与 CI 强化

### 7.1 必须新增的测试

| 测试 | 所属阶段 | 说明 |
|------|----------|------|
| `test_postgres_upsert.py` | 第一阶段 | PostgreSQL service 容器上跑全部 upsert |
| `test_production_sqlite_ban.py` | 第一阶段 | `ENV=production` + SQLite 启动失败 |
| `test_cors_variable.py` | 第一阶段 | `CORS_ORIGINS` / `ALLOW_ORIGINS` 兼容 |
| `test_cache_orm_detached.py` | 第一阶段 | 并发请求 `/api/realtime` 无异常 |
| `test_comment_blank.py` | 第一阶段 | `"   "` 返回 422 |
| `test_comment_pagination.py` | 第一阶段 | skip/limit 边界测试 |
| `test_alembic_upgrade.py` | 第一阶段 | 空库 `upgrade head` 后启动 |
| `test_multi_contract_kline.py` | 第二阶段 | 同一品种多合约 K 线并存 |
| `test_contract_rollover.py` | 第二阶段 | 换月历史记录测试 |
| `test_decimal_precision.py` | 第二阶段 | Decimal 0.1+0.2==0.3 |
| `test_trading_calendar.py` | 第三阶段 | 节假日、夜盘归属 |
| `test_limit_up_down.py` | 第三阶段 | 涨跌停识别 |
| `test_circuit_breaker.py` | 第四阶段 | 熔断状态转换 |
| `test_redis_rate_limit.py` | 第四阶段 | 跨进程限流一致性 |
| `test_sse_quotes.py` | 第五阶段 | SSE 推送 + 重连 |

### 7.2 CI 配置建议

```yaml
# .github/workflows/backend.yml（示例）
name: Backend CI
on: [push, pull_request]
jobs:
  test-sqlite:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: cd python && pip install -r requirements.txt && pip install pytest httpx
      - run: cd python && SECRET_KEY=test-secret-key pytest tests/ -v

  test-postgres:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: futures
          POSTGRES_PASSWORD: futures123
          POSTGRES_DB: futures_community
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: cd python && pip install -r requirements.txt && pip install pytest httpx psycopg2-binary
      - run: cd python && DATABASE_URL=postgresql://futures:futures123@localhost:5432/futures_community SECRET_KEY=test-secret-key pytest tests/test_postgres_upsert.py -v
```

---

## 八、上线门禁（Checklist）

生产发布前必须满足：

- [ ] `ENV=production` 时无法使用 SQLite。
- [ ] `SECRET_KEY` 长度不少于 32。
- [ ] `CORS_ORIGINS` 明确配置为真实前端域名。
- [ ] PostgreSQL upsert 测试通过（CI `test-postgres` job 绿色）。
- [ ] Alembic 可从空库 `upgrade head`。
- [ ] API 实例不运行 scheduler（`ENABLE_SCHEDULER=0`），采集 worker 单独部署。
- [ ] K 线数据可以按具体合约查询。
- [ ] `/metrics` 可抓取，告警规则已配置。
- [ ] 备份策略明确：PostgreSQL 每日全量 + WAL 归档，RPO ≤ 15 分钟。
- [ ] 至少完成一次恢复演练，有演练记录文档。

---

## 九、迭代节奏建议

| 周次 | 阶段 | 里程碑 |
|------|------|--------|
| 第 1 周 | 第一阶段 | P0/P1 修复全部完成，CI 通过，可稳定运行 |
| 第 2-3 周 | 第二阶段 | contracts 表上线，K 线绑定合约，换月可追溯 |
| 第 3-4 周 | 第三阶段 | 交易日历、夜盘、涨跌停、时区统一 |
| 第 4-5 周 | 第四阶段 | Worker 拆分、Redis 限流、Prometheus 监控 |
| 第 5-6 周 | 第五阶段 | SSE 推送、前端合约选择、连续 K 线 |

---

## 十、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| Alembic 迁移失败（已有数据） | 第二阶段 K 线加 contract_id 时，旧数据迁移复杂 | 编写数据迁移脚本，先根据 `variety.contract_code` 反查 contract_id，无法匹配则设为 NULL |
| 前端兼容性破裂 | K 线接口增加 contract_code 参数，旧前端不传 | 旧接口默认查询主力合约，参数 optional，前端不破 |
| Tushare 配额不足 | 扩展数据采集（日线、结算、持仓等）消耗积分 | 开发环境可 Mock fallback；生产环境应切换备用真实数据源、降低采集频率或标记数据延迟，不允许静默降级为 Mock |
| SSE 连接数过高 | 1000+ 并发 SSE 连接消耗内存 | 使用 asyncio + 共享内存 dict，避免每连接一个线程；或改用 WebSocket |
| 时区改造影响现有数据 | 所有 datetime 改为 UTC-aware，旧数据可能无 tzinfo | 迁移时假设旧数据为 UTC（或东八区），统一转换后存储 |

---

*方案制定：2026-05-05*
*依据：后端全面技术评审报告 + 历史迭代计划综合*
