# 后端技术审查报告与迭代方案

## 概览

- 审查日期：2026-05-05
- 审查范围：`python/` 后端、数据采集 Pipeline、部署配置、前端实时访问方式
- 代码总行数：约 5,569 行
- 测试代码：约 646 行，测试代码行占比约 11.6%
- 测试覆盖率：未知。审查时尝试运行 `pytest tests -q`，当前环境缺少 `fastapi`，未能执行
- P0 问题数：1
- P1 问题数：9
- P2 问题数：9

## 一、核心结论

当前后端已经完成了一批基础安全修复：`SECRET_KEY` 不再硬编码，密码哈希已改为 bcrypt，JWT 异常处理较明确，缓存层加了锁，SQLite 开启 WAL，采集 Pipeline 也从早期脚本式逻辑演进为 Collector、Adapter、Cleaner、Upsert 的链路。

但从生产化和期货业务正确性看，系统仍有几个必须优先处理的风险：

1. `python/data_collector/upsert.py` 固定使用 SQLite dialect 的 `insert`，当前 `.env` 已切 PostgreSQL 时，采集 upsert 可能失败。这是 P0。
2. 默认数据库仍会回退 SQLite，生产环境没有禁止 SQLite。
3. K 线表未绑定具体合约，只有 `variety_id + period + trading_time`，换月后历史 K 线容易混表。
4. 主力合约切换只覆盖 `varieties.contract_code`，没有换月历史、合约表或连续合约语义。
5. CORS 示例变量名是 `ALLOW_ORIGINS`，代码读取的是 `CORS_ORIGINS`，存在生产配置误判风险。
6. 实时行情仍依赖轮询，没有 SSE/WebSocket；短期可接受，但需要先把采集频率、缓存和 DB 写入链路稳住。
7. 夜盘、节假日、涨跌停、交易日归属没有被建模，期货业务边界仍偏弱。

## 二、架构审查

### 2.1 整体分层

- **现状**：FastAPI Router 直接访问 SQLAlchemy Model；数据采集有 `Collector -> Adapter -> Cleaner -> Upsert` Pipeline；业务 API 无 Service/Repository 层。
- **评级**：P2
- **问题**：当前评论、认证、行情查询逻辑较薄，短期可接受；但合约、交易日历、换月、连续 K 线会迅速变复杂。
- **建议**：新增 `services/market_data.py`、`repositories/kline_repo.py`，Router 只做参数解析和响应转换。
- **优先级**：长期

### 2.2 依赖注入 / 控制反转

- **现状**：API 使用 `Depends(get_db)`；Pipeline 和 Scheduler 直接创建 `SessionLocal()`。
- **评级**：P2
- **问题**：采集链路测试替换数据库和 Collector 成本较高。
- **建议**：Pipeline 构造函数注入 `session_factory`，测试可注入内存 DB 或 PostgreSQL 测试库。
- **优先级**：本迭代

### 2.3 单体架构选择

- **现状**：单体 FastAPI + APScheduler 内嵌采集任务。
- **评级**：P2
- **问题**：当前规模适合单体；但生产多实例部署时 APScheduler 会重复跑任务。
- **建议**：短期保持单体；生产部署时 API 实例设置 `ENABLE_SCHEDULER=0`，采集任务改为独立 worker 或定时任务容器。
- **优先级**：本迭代

### 2.4 API 设计

- **现状**：RESTful 风格，`/api/products` 是旧兼容层，`/api/varieties`、`/api/realtime`、`/api/kline` 是新接口。
- **评级**：P2
- **问题**：K 线接口只按 `symbol` 查询，不能指定具体合约，换月后历史查询语义不清。
- **建议**：新增 `/api/contracts/{contract_code}/kline` 和 `/api/varieties/{symbol}/continuous-kline`。
- **优先级**：本迭代

### 2.5 认证授权体系

- **现状**：JWT + OAuth2 密码流；bcrypt；评论接口要求登录。
- **评级**：P2
- **问题**：基础安全已修；但前端 token 存在 `localStorage`，XSS 后可被窃取。
- **建议**：生产改 HttpOnly SameSite Cookie，或至少缩短 access token 有效期并引入 refresh token。
- **优先级**：长期

### 2.6 限流、熔断、降级

- **现状**：`auth.py` 有进程内 IP 限流；采集器有重试和 fallback。
- **评级**：P1
- **问题**：进程内限流在多实例下失效；Tushare/AkShare 没有统一熔断状态和配额保护。
- **建议**：引入 Redis 或网关限流；数据源失败率超过阈值后短时间熔断。
- **优先级**：本迭代

### 2.7 日志、监控、链路追踪

- **现状**：使用 Python logging，采集批次写入 `data_ingestion_runs`。
- **评级**：P2
- **问题**：无 Prometheus 指标、无请求 ID、无慢查询日志。
- **建议**：接入 `prometheus-fastapi-instrumentator`，为采集任务暴露成功数、失败数、延迟和最近采集时间。
- **优先级**：长期

### 2.8 部署架构

- **现状**：有 Dockerfile 和 docker-compose，PostgreSQL/Redis 可启动，但 backend 服务注释；当前 `.env` 使用 PostgreSQL。
- **评级**：P1
- **问题**：默认配置仍回退 SQLite；生产没有阻止 SQLite；compose 中 DB 密码为弱默认值。
- **建议**：`ENV=production` 时强制 `DATABASE_URL` 为 PostgreSQL，并通过云服务密钥管理注入密码。
- **优先级**：立即

## 三、代码审查

### 3.1 PostgreSQL 下 upsert 可能失效

- **位置**：`python/data_collector/upsert.py:2`
- **评级**：P0
- **问题**：代码固定 `from sqlalchemy.dialects.sqlite import insert`。当前 `.env` 已使用 PostgreSQL，采集 Pipeline 执行 `on_conflict_*` 时应使用 PostgreSQL dialect。
- **修复建议**：

```diff
- from sqlalchemy.dialects.sqlite import insert
+ from sqlalchemy.dialects.postgresql import insert as pg_insert
+ from sqlalchemy.dialects.sqlite import insert as sqlite_insert
+ from models import engine
+
+ def dialect_insert(model):
+     if engine.dialect.name == "postgresql":
+         return pg_insert(model)
+     return sqlite_insert(model)
```

然后把 `insert(Model)` 改为 `dialect_insert(Model)`。

- **自动化建议**：CI 增加 PostgreSQL 服务，跑 realtime/kline upsert 集成测试。

### 3.2 SQLite 仍是默认数据库

- **位置**：`python/config.py:10`、`python/models.py:12`
- **评级**：P1
- **问题**：未配置 `DATABASE_URL` 时默认 SQLite；生产只校验 `SECRET_KEY`，不校验 DB 类型。
- **修复建议**：

```python
if ENV == "production" and DATABASE_URL.startswith("sqlite"):
    raise ValueError("SQLite is not allowed in production")
```

- **自动化建议**：增加 `ENV=production DATABASE_URL=sqlite:///x.db` 启动失败测试。

### 3.3 K 线按品种混存

- **位置**：`python/models.py:100`、`python/models.py:144`、`python/data_collector/upsert.py:76`
- **评级**：P1
- **问题**：`VarietyDB` 只有当前 `contract_code`，`KlineDataDB` 只存 `variety_id`，没有 `contract_id` 或 `contract_code`。换月后 AU2506 和 AU2512 的同周期同时间数据会落到同一个品种下。
- **修复建议**：

```python
class ContractDB(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id"), nullable=False, index=True)
    contract_code = Column(String(30), unique=True, nullable=False)
    exchange = Column(String(20), nullable=False)
    listing_date = Column(DateTime)
    last_trading_date = Column(DateTime)
    is_main = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
```

`kline_data` 增加 `contract_id`，唯一键改为 `contract_id, period, trading_time`。

- **自动化建议**：构造同一品种两个合约同一时间 K 线，断言可同时存在。

### 3.4 主力合约切换只覆盖当前值

- **位置**：`python/data_collector/pipeline.py:382`
- **评级**：P1
- **问题**：`run_fut_mapping()` 只更新 `VarietyDB.contract_code`，不记录切换历史、不生成连续合约衔接关系、不通知用户。
- **修复建议**：新增 `contract_rollovers` 表，保存 `old_contract_code/new_contract_code/effective_date/source`。
- **自动化建议**：测试 mapping 从 AU2506 切到 AU2512 后，历史 K 线仍按旧合约可查。

### 3.5 Alembic 状态可能漂移

- **位置**：`python/models.py:41`
- **评级**：P1
- **问题**：`init_db()` 手动插入固定版本 `7a8e00d86747`，但仓库已有后续迁移。新库的 `alembic_version` 与实际 head 可能不一致。
- **修复建议**：应用启动不要写 `alembic_version`；用 `alembic upgrade head` 管理 schema。
- **自动化建议**：CI 执行 `alembic upgrade head` 后启动应用。

### 3.6 CORS 环境变量名不一致

- **位置**：`python/main.py:62`、`.env.example:25`
- **评级**：P1
- **问题**：代码读取 `CORS_ORIGINS`，示例写的是 `ALLOW_ORIGINS`。生产以为收紧了 CORS，实际可能回退默认值。
- **修复建议**：

```python
origins_raw = os.getenv("CORS_ORIGINS") or os.getenv("ALLOW_ORIGINS")
if ENV == "production" and not origins_raw:
    raise ValueError("CORS_ORIGINS is required in production")
origins = [origin.strip() for origin in origins_raw.split(",") if origin.strip()]
```

- **自动化建议**：配置校验测试覆盖变量名。

### 3.7 缓存存储 SQLAlchemy ORM 对象

- **位置**：`python/routers/realtime.py:17`、`python/services/cache.py:37`
- **评级**：P1
- **问题**：缓存中保存 `RealtimeQuoteDB` ORM 实例，跨请求或线程复用时可能出现 detached object、线程安全和脏数据问题。
- **修复建议**：缓存纯 dict 或 Pydantic DTO。

```python
def _fetch():
    q = db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
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

- **自动化建议**：并发请求 `/api/realtime/AU`，断言无 detached session 异常。

### 3.8 金额和价格大量使用 Float

- **位置**：`python/models.py:130`、`python/models.py:150`、`python/data_collector/cleaner.py:41`
- **评级**：P1
- **问题**：行情价、结算价、手续费部分仍用 `Float` 和 Python `float`。展示行情可接受，但盈亏、保证金、结算类计算不能使用二进制浮点。
- **修复建议**：资金和结算字段统一 `Numeric(18, 6)` + `Decimal`；响应层再格式化。
- **自动化建议**：增加 Decimal 精度测试。

### 3.9 评论空白内容可绕过

- **位置**：`python/schemas.py:42`
- **评级**：P2
- **问题**：Pydantic 先按原始字符串做 `min_length=1`，validator 再 `strip()`；`"   "` 可能变成空评论。
- **修复建议**：

```python
v = html.escape(v.strip())
if not v:
    raise ValueError("评论内容不能为空")
return v
```

- **自动化建议**：新增空白评论 422 测试。

### 3.10 评论历史无分页

- **位置**：`python/routers/comments.py:46`
- **评级**：P2
- **问题**：用户评论历史 `.all()`，数据量大时会拖慢接口。
- **修复建议**：加 `skip/limit`，默认 100，上限 1000。
- **自动化建议**：API 参数边界测试。

## 四、数据 Pipeline 审查

### 4.1 Pipeline 架构图

```text
APScheduler
  -> Collector(Tushare/AkShare/Mock)
  -> Adapter(字段映射)
  -> Cleaner(OHLC/缺失/去重)
  -> Upsert(SQLAlchemy)
  -> PostgreSQL/SQLite
  -> API 查询
  -> 前端 30 秒轮询
```

### 4.2 行情数据采集

- **现状**：`DATA_SOURCE=tushare`；Tushare/AkShare/Mock fallback；实时任务 60 秒，分钟线 15 分钟。
- **评级**：P1
- **问题**：实时性不足；Tushare/AkShare 权限、限额、失败熔断不完整。
- **建议**：实时行情独立 worker；失败率熔断 1-5 分钟；采集延迟写入指标。

### 4.3 数据清洗与标准化

- **现状**：校验 OHLC、缺失字段、按时间周期去重。
- **评级**：P2
- **问题**：未识别涨跌停、停盘、集合竞价、夜盘归属交易日。
- **建议**：清洗层加入 `trading_status`、`limit_status`、`trading_day` 字段。

### 4.4 K 线生成逻辑

- **现状**：直接采集外部 K 线，不做 tick -> minute -> day 聚合。
- **评级**：P1
- **问题**：缺少本地可复算链路，数据源修订或缺口难追踪。
- **建议**：短期保留外部 K 线；中期落 tick/minute 原始数据，按交易日历聚合。

### 4.5 合约换月 Pipeline

- **现状**：有 Tushare `fut_mapping` 更新 `varieties.contract_code`。
- **评级**：P1
- **问题**：无 contracts 表、无 rollover 历史、无连续主力 K 线处理。
- **建议**：建立 `contracts`、`contract_rollovers`、`continuous_kline` 或视图。

### 4.6 数据存储

- **现状**：当前 `.env` 指向 PostgreSQL，但代码默认 SQLite；无冷热分层。
- **评级**：P1
- **问题**：高频 K 线无分区，长期会出现大表扫描和归档问题。
- **建议**：PostgreSQL + TimescaleDB 或按月分区；K 线索引包含 `contract_id, period, trading_time DESC`。

### 4.7 实时性与延迟

- **现状**：前端 30 秒轮询，后端实时采集 60 秒，分钟线 15 分钟。
- **评级**：P2
- **延迟分析**：
  - 数据源响应：约 1-5 秒
  - 后端实时采集等待：最高 60 秒
  - 缓存 TTL：5 秒
  - 前端轮询等待：最高 30 秒
  - 用户可见最坏情况：约 95 秒
- **建议**：短期把实时采集改为 15-30 秒；中期通过 SSE 推送报价变化。

### 4.8 备份恢复

- **现状**：compose 有 volume；未见 RPO/RTO、备份任务、恢复演练。
- **评级**：P1
- **建议**：PostgreSQL 每日全量 + WAL 归档；目标 RPO 15 分钟、RTO 1 小时。

## 五、后端迭代方案

### 5.1 迭代目标

本轮后端迭代的目标不是一次性重构全部架构，而是先把生产运行的硬风险压下去，再补齐期货业务的核心数据模型。

目标分三层：

1. **可运行**：PostgreSQL 写入链路稳定，生产不会误用 SQLite，配置不会误判。
2. **可追溯**：合约、换月、K 线历史数据有明确归属。
3. **可扩展**：行情采集、缓存、限流、监控可以支撑后续 SSE/WebSocket 和更高频数据。

### 5.2 第一阶段：P0/P1 稳定性修复

建议周期：1-2 天

#### 任务 1：修复 PostgreSQL upsert dialect

- **改动范围**：
  - `python/data_collector/upsert.py`
  - `python/tests/test_*`
- **实施要点**：
  - 根据 `engine.dialect.name` 选择 PostgreSQL 或 SQLite insert。
  - 保留 SQLite 测试兼容性。
  - 增加 PostgreSQL upsert 集成测试。
- **验收标准**：
  - PostgreSQL 下 `upsert_realtime`、`insert_kline_bulk`、`upsert_fut_daily_bulk` 均可执行。
  - SQLite 测试不回退。

#### 任务 2：生产禁止 SQLite

- **改动范围**：
  - `python/config.py`
  - `.env.example`
  - `README.md` 或部署文档
- **实施要点**：
  - `ENV=production` 时强制 `DATABASE_URL` 不得以 `sqlite` 开头。
  - 统一 `CORS_ORIGINS` 命名。
- **验收标准**：
  - `ENV=production DATABASE_URL=sqlite:///x.db` 导入配置失败。
  - `ENV=production DATABASE_URL=postgresql://...` 正常。

#### 任务 3：修复 CORS 配置不一致

- **改动范围**：
  - `python/main.py`
  - `.env.example`
- **实施要点**：
  - 代码优先读取 `CORS_ORIGINS`，兼容旧的 `ALLOW_ORIGINS`。
  - 生产环境缺失 CORS 配置直接失败。
- **验收标准**：
  - 测试覆盖 `CORS_ORIGINS` 和 `ALLOW_ORIGINS`。
  - 生产无配置时启动失败。

#### 任务 4：缓存 DTO 化

- **改动范围**：
  - `python/routers/realtime.py`
  - `python/services/cache.py`
  - `python/tests/test_p0_fixes.py`
- **实施要点**：
  - 缓存中只存 dict，不存 ORM 实例。
  - 保留 TTL、LRU 和线程锁。
- **验收标准**：
  - 并发读取实时行情无 session 相关异常。
  - API 响应结构不变。

### 5.3 第二阶段：合约与 K 线模型修复

建议周期：3-5 天

#### 任务 5：新增 contracts 表

- **改动范围**：
  - `python/models.py`
  - `python/alembic/versions/*`
  - `python/data_collector/init_varieties.py`
  - `python/schemas.py`
- **实施要点**：
  - `contracts` 表存具体合约。
  - `varieties.contract_code` 暂时保留作为兼容字段，但视为当前主力合约缓存。
  - 初始化时为每个品种创建当前合约记录。
- **验收标准**：
  - `contracts.contract_code` 唯一。
  - 每个初始化品种至少有一个 active/main contract。

#### 任务 6：K 线绑定 contract_id

- **改动范围**：
  - `python/models.py`
  - `python/data_collector/upsert.py`
  - `python/routers/kline.py`
  - `python/alembic/versions/*`
- **实施要点**：
  - `kline_data` 增加 `contract_id`。
  - 新唯一键：`contract_id, period, trading_time`。
  - 旧接口 `/api/kline/{symbol}` 默认查询当前主力合约。
  - 新接口支持按具体合约查询。
- **验收标准**：
  - 同一品种两个合约、同一周期、同一时间 K 线可同时入库。
  - 旧接口前端不破。

#### 任务 7：记录主力合约换月历史

- **改动范围**：
  - `python/models.py`
  - `python/data_collector/pipeline.py`
  - `python/data_collector/scheduler.py`
- **实施要点**：
  - 新增 `contract_rollovers`。
  - `run_fut_mapping()` 发现主力变化时，更新当前合约并插入 rollover 记录。
  - 不再只覆盖 `varieties.contract_code`。
- **验收标准**：
  - 任何主力切换都有审计记录。
  - 历史 K 线不被新合约覆盖。

### 5.4 第三阶段：期货交易日与夜盘建模

建议周期：3-5 天

#### 任务 8：交易日历

- **改动范围**：
  - 新增 `python/services/trading_calendar.py`
  - 新增 `trading_calendar` 表或静态日历数据源
- **实施要点**：
  - 支持国内期货交易所休市日。
  - 支持夜盘归属下一交易日。
- **验收标准**：
  - 21:00-02:30 的夜盘数据能映射到正确 trading_day。
  - 节假日不触发日线同步，或同步任务明确跳过。

#### 任务 9：K 线增加 trading_day/session

- **改动范围**：
  - `python/models.py`
  - `python/data_collector/adapters.py`
  - `python/data_collector/cleaner.py`
- **实施要点**：
  - K 线表增加 `trading_day`、`session`。
  - session 可取 `day`、`night`。
  - 所有 datetime 明确时区策略，建议使用东八区业务时间 + UTC 存储或统一 timezone-aware datetime。
- **验收标准**：
  - 夜盘和日盘可按 session 查询。
  - 日线聚合不会把夜盘错误归到自然日。

#### 任务 10：涨跌停识别

- **改动范围**：
  - `python/models.py`
  - `python/data_collector/cleaner.py`
  - `python/routers/realtime.py`
- **实施要点**：
  - 结合 `fut_price_limits` 识别 `limit_status`。
  - 输出 `up_limit`、`down_limit`、`limit_status`。
- **验收标准**：
  - 当前价等于涨停/跌停价时 API 返回对应状态。

### 5.5 第四阶段：生产化能力

建议周期：5-8 天

#### 任务 11：采集任务独立化

- **改动范围**：
  - Dockerfile / docker-compose
  - `python/main.py`
  - `python/data_collector/scheduler.py`
- **实施要点**：
  - API 容器和 worker 容器拆开。
  - API 默认 `ENABLE_SCHEDULER=0`。
  - worker 单实例运行 scheduler。
- **验收标准**：
  - API 横向扩容不会重复采集。
  - worker 健康状态可见。

#### 任务 12：限流和熔断外部化

- **改动范围**：
  - `python/routers/auth.py`
  - 新增 `python/services/rate_limit.py`
  - 新增 `python/services/circuit_breaker.py`
- **实施要点**：
  - Redis 限流替代进程内 dict。
  - 数据源失败率熔断，避免持续打爆外部 API。
- **验收标准**：
  - 多进程下登录限流一致。
  - 数据源连续失败后进入 cooling 状态。

#### 任务 13：监控与告警

- **改动范围**：
  - `python/main.py`
  - `python/data_collector/pipeline.py`
  - `python/routers/health.py`
- **实施要点**：
  - 增加 `/metrics`。
  - 指标包括 API latency、DB ready、cache size、最近采集时间、采集成功/失败数量。
- **验收标准**：
  - Prometheus 可抓取指标。
  - 采集超过阈值未更新可告警。

### 5.6 第五阶段：实时推送

建议周期：3-5 天

#### 任务 14：SSE 实时行情推送

- **改动范围**：
  - 新增 `python/routers/sse.py`
  - `python/main.py`
  - 前端行情页面
- **实施要点**：
  - 优先 SSE，不急着上 WebSocket。
  - 服务端推送最近变化的 realtime quote。
  - 前端保留轮询作为降级。
- **验收标准**：
  - 浏览器建立 SSE 连接后，行情更新无需等待 30 秒轮询。
  - 断线自动重连。

## 六、建议迭代顺序

| 阶段 | 优先级 | 内容 | 建议周期 |
|------|--------|------|----------|
| 第一阶段 | P0/P1 | PostgreSQL upsert、生产禁 SQLite、CORS、缓存 DTO | 1-2 天 |
| 第二阶段 | P1 | contracts、contract_id K 线、换月历史 | 3-5 天 |
| 第三阶段 | P1/P2 | 交易日历、夜盘、涨跌停 | 3-5 天 |
| 第四阶段 | P2 | worker 独立化、Redis 限流、监控告警 | 5-8 天 |
| 第五阶段 | P2 | SSE 实时推送 | 3-5 天 |

## 七、测试与 CI 建议

### 必须新增的测试

1. PostgreSQL upsert 集成测试。
2. 生产环境 SQLite 禁用测试。
3. CORS 环境变量读取测试。
4. 缓存并发读取 realtime 测试。
5. 同一品种多合约 K 线并存测试。
6. 主力换月历史记录测试。
7. 夜盘 trading_day 归属测试。
8. 涨跌停识别测试。

### 推荐 CI 命令

```bash
cd python
SECRET_KEY=test-secret-key ENV=test pytest tests -q
```

PostgreSQL 集成测试建议增加：

```bash
docker-compose up -d postgres
cd python
DATABASE_URL=postgresql://futures:futures123@localhost:15432/futures_community \
SECRET_KEY=test-secret-key \
ENABLE_SCHEDULER=0 \
pytest tests -q
```

前端至少保留：

```bash
cd frontend
npm run lint
npx tsc --noEmit
```

## 八、上线门禁

生产发布前必须满足：

1. `ENV=production` 时无法使用 SQLite。
2. `SECRET_KEY` 长度不少于 32。
3. `CORS_ORIGINS` 明确配置为真实前端域名。
4. PostgreSQL upsert 测试通过。
5. Alembic 可从空库 `upgrade head`。
6. API 实例不运行 scheduler，采集 worker 单独部署。
7. K 线数据可以按具体合约查询。
8. 备份策略明确，至少有每日备份和一次恢复演练记录。

