# 后端全面技术评审报告

> 评审日期：2026-05-05
> 评审范围：`python/` 后端全量代码、数据模型、采集 Pipeline、API 层、安全机制、测试体系、部署配置
> 代码总行数：约 5,569 行（含测试约 646 行，占比 11.6%）
> 评审依据：实际源码逐文件审查 + `BACKEND_TECH_REVIEW_AND_ITERATION_PLAN_20260505.md` 参考对照

---

## 一、执行摘要

当前后端已完成基础安全加固（bcrypt、JWT 异常捕获、SQLite WAL、进程内限流、缓存锁），数据流水线也已从早期脚本式演进为 `Collector → Adapter → Cleaner → Upsert → Pipeline` 的链路化架构，支持 Tushare / AkShare / Mock 多源切换和自动 fallback。15+ 张业务表覆盖了品种、实时行情、K 线、评论、用户、扩展期货数据（结算、仓单、持仓、涨跌停、周报）等维度。

**但系统距离生产就绪仍有显著差距。** 核心风险集中在：

1. **P0 — PostgreSQL 兼容性断裂**：`upsert.py` 硬编码 SQLite dialect，若 `.env` 切至 PostgreSQL，全部批量写入操作会直接崩溃。
2. **P1 — 期货业务模型缺失**：无合约表、无换月历史、无交易日历、无夜盘归属，K 线按品种混存导致换月后历史数据语义混乱。
3. **P1 — 配置与部署陷阱**：生产环境未禁止 SQLite；CORS 变量名不一致；Alembic 版本硬编码导致迁移漂移。
4. **P1 — 数据精度与缓存安全**：金融字段大量使用 `Float`；缓存存储 ORM 实例存在 detached session 风险。
5. **P2 — 单体扩展瓶颈**：APScheduler 内嵌于 API 进程，多实例部署会重复采集；无 Prometheus 指标、无外部限流/熔断。

---

## 二、架构评审

### 2.1 整体分层（评级：P2）

**现状**：FastAPI Router 直接操作 SQLAlchemy Model，无 Service / Repository 抽象层。数据采集有清晰的 Pipeline 链路，但业务 API 层仍是"Router → ORM"的扁平结构。

**问题**：
- 评论、认证、行情查询逻辑较薄，短期可接受；但合约管理、换月、连续 K 线、交易日历等期货核心领域会迅速膨胀，扁平结构难以维护。
- `routers/comments.py:46` 直接 `.all()` 无分页；`routers/kline.py` 直接 `.limit(1000)` 无超时保护。
- 数据校验散落在 Pydantic Schema、Cleaner、Router 三处，缺少统一业务规则引擎。

**建议**：
- 新增 `services/market_data.py`、`repositories/kline_repo.py`，Router 只做参数解析、认证校验和响应转换。
- 评论、K 线、品种查询统一走 Repository，支持分页、游标、过滤条件的标准化。

**优先级**：长期（第二阶段起逐步引入）。

---

### 2.2 依赖注入 / 控制反转（评级：P2）

**现状**：
- API 层使用 `Depends(get_db)`，通过 yield + finally 保证会话关闭。
- Pipeline 和 Scheduler 直接创建 `SessionLocal()`，模块级 `_build_collectors()` 在导入时即执行。

**问题**：
- `data_collector/scheduler.py:118` `_build_collectors()` 在模块导入时运行，若 Tushare Token 无效或网络不可达，应用启动即失败。`RuntimeError("No data collector is available")` 会阻断整个后端启动。
- Pipeline 中每次 run 都新建 `SessionLocal()`，和 API 层会话工厂不一致，测试替换成本高。
- `data_collector/pipeline.py:29` `_record_run()` 使用独立 `SessionLocal()` 记录采集批次，虽避免了事务干扰，但和主 session 不共享连接池配置。

**建议**：
- Pipeline 构造函数注入 `session_factory`，测试可注入内存 DB 或 PostgreSQL 测试库。
- `_build_collectors()` 延迟到首次调度任务执行时初始化，或捕获异常后降级为 Mock，保证应用始终可启动。

**优先级**：本迭代（第一阶段）。

---

### 2.3 单体架构与调度器（评级：P2）

**现状**：单体 FastAPI + APScheduler `BackgroundScheduler` 内嵌采集任务。

**问题**：
- 生产多实例部署时，每个实例都会启动 scheduler，导致实时行情、K 线同步任务重复执行，数据冲突、外部 API 配额翻倍消耗。
- `main.py:39` `if ENABLE_SCHEDULER:` 仅通过环境变量控制，缺少运行时的 leader 选举机制。
- `health.py:33` `scheduler_ok = ENABLE_SCHEDULER` 的 readiness 语义有问题：若管理员主动禁用 scheduler（纯 API 模式）， readiness 返回 `False`，导致编排平台（K8s）认为服务不健康，这是错误的。

**建议**：
- 短期保持单体，但生产部署时 API 容器设置 `ENABLE_SCHEDULER=0`。
- 中期拆分独立 `worker` 容器运行 scheduler，通过 docker-compose 或 K8s Deployment 单副本保证唯一性。
- readiness 探针应检查 scheduler 进程健康状态（如最近心跳时间），而非仅检查配置开关。

**优先级**：本迭代（第一阶段配置修正，第四阶段容器拆分）。

---

### 2.4 API 设计与兼容性（评级：P2）

**现状**：
- `/api/products/*` 是旧兼容层，`/api/varieties`、`/api/realtime`、`/api/kline` 是新数据层。
- `scheduler.py:205` `sync_prices_to_products()` 每 60 秒将 `realtime_quotes` 同步回 `products`，保证旧页面数据新鲜。

**问题**：
- K 线接口 `/api/kline/{symbol}` 只按品种 symbol 查询，不能指定具体合约。换月后 `AU2506` 和 `AU2512` 的 K 线混存在同一 `variety_id` 下，接口返回的数据语义不清。
- 旧兼容层 `ProductDB` 和新数据层 `VarietyDB` / `RealtimeQuoteDB` 字段类型不一致（`ProductDB.current_price` 是 `Float`，`RealtimeQuoteDB.pre_settlement` 是 `Numeric`），同步时存在隐式类型转换。
- `routers/products.py:33` 商品详情页评论查询 `.limit(100)` 但无分页参数；`routers/comments.py:46` 用户评论历史 `.all()` 无分页。

**建议**：
- 新增 `/api/contracts/{contract_code}/kline` 和 `/api/varieties/{symbol}/continuous-kline`。
- 旧接口 `/api/kline/{symbol}` 默认查询当前主力合约，通过 `contract_id` 过滤，保证前端不破。
- 所有列表接口统一 `skip/limit`，默认 100，上限 1000。

**优先级**：本迭代（第二阶段）。

---

### 2.5 认证授权体系（评级：P2）

**现状**：JWT + OAuth2 密码流；bcrypt 带随机盐；登录限流 10 req/60s；恒定时间比较防御时序攻击。

**问题**：
- 前端 token 存储在 `localStorage`（由 `lib/api.ts` 管理），XSS 攻击后可被窃取。
- 无 refresh token 机制，`ACCESS_TOKEN_EXPIRE_MINUTES=1440`（24 小时）过长，且无法主动吊销。
- `dependencies.py:22` `get_current_user()` 捕获 `PyJWTError` 和 `ValueError` 后返回 `None`，但未区分 token 过期、签名无效、格式错误等具体原因，不利于审计。

**建议**：
- 生产环境改用 HttpOnly + SameSite=Strict Cookie，或至少缩短 access token 有效期至 15-30 分钟，引入 refresh token 轮换机制。
- `get_current_user()` 增加结构化错误码（`TOKEN_EXPIRED`、`TOKEN_INVALID`），供上层返回更精确的 401 响应。

**优先级**：长期（第四阶段）。

---

### 2.6 限流、熔断、降级（评级：P1）

**现状**：
- `auth.py` 有进程内 IP 限流（固定窗口，10 req/60s）。
- Tushare 采集器有指数退避重试。
- `_MappedFallbackCollector` 支持多源自动 fallback。

**问题**：
- 进程内 `_rate_limit_store` 在多实例部署下完全失效，同一用户可通过不同容器绕过限流。
- 无数据源级别的熔断机制：Tushare/AkShare 连续失败时，系统会持续尝试，浪费配额、拉长接口延迟。
- 无降级策略：当所有外部数据源失效时，除了 fallback 到 Mock，没有"返回缓存中最后一次有效数据"的显式降级路径。
- 限流窗口是固定窗口，非滑动窗口，边界突刺无法防御。

**建议**：
- 引入 Redis 分布式限流（`services/rate_limit.py`），替代进程内 dict。
- 为每个数据源实现熔断器（`services/circuit_breaker.py`）：失败率超过 50%（5 次/10 次）时进入 Open 状态，冷却 60 秒后进入 Half-Open 探测。
- 实时行情 API 增加"返回缓存数据 + 标注 stale"的降级响应。

**优先级**：本迭代（第一阶段限流外部化设计，第四阶段实现）。

---

### 2.7 日志、监控、链路追踪（评级：P2）

**现状**：使用 Python 标准 logging；采集批次写入 `data_ingestion_runs`；有 `/health` 和 `/health/ready` 探针。

**问题**：
- 无 Prometheus 指标暴露，无法监控 API latency、QPS、错误率、DB 连接池状态。
- 无请求 ID（correlation ID），日志分散在多行，难以串联一次完整请求。
- `pipeline.py` 中 `logger.critical(f"Realtime pipeline aborted: {e}", exc_info=True)` 会在异常时打印完整堆栈，但无结构化字段（如 `symbol`, `job_name`, `run_id`），不利于日志聚合查询。
- 无慢查询日志：SQLAlchemy 未配置 `echo="debug"` 或慢查询阈值。

**建议**：
- 接入 `prometheus-fastapi-instrumentator`，暴露 `/metrics`。
- 关键指标：API latency histogram、DB query duration、cache hit/miss rate、scheduler last_run_timestamp、采集 success/fail/skip counter。
- 为每个请求生成 `X-Request-ID`，通过 FastAPI middleware 注入上下文。
- SQLAlchemy 事件监听慢查询（> 500ms）记录 warning 日志。

**优先级**：长期（第四阶段）。

---

### 2.8 部署架构与配置管理（评级：P1）

**现状**：
- Dockerfile 使用 Python 3.11 slim，暴露 8000。
- docker-compose.yml 有 PostgreSQL 16 + Redis 7，但 backend 服务已注释。
- `.env.example` 默认 SQLite，`config.py` 回退 SQLite。

**问题**：
- `ENV=production` 时未强制 `DATABASE_URL` 为 PostgreSQL，生产可能误用 SQLite。
- `docker-compose.yml` 中 DB 密码为弱默认值 `futures123`。
- `main.py:62` 读取 `CORS_ORIGINS` 环境变量，`.env.example:25` 写的是 `ALLOW_ORIGINS`，用户复制后修改了错误的变量名，CORS 实际回退默认值，存在跨域配置误判风险。
- 无健康检查 readiness/liveness 的 HTTP 探针配置示例（K8s / docker-compose healthcheck）。

**建议**：
- `ENV=production` 时强制校验 `DATABASE_URL` 不以 `sqlite` 开头，否则启动失败。
- 统一 CORS 变量名，或代码兼容读取两个变量名（优先 `CORS_ORIGINS`，兼容 `ALLOW_ORIGINS`）。
- 生产密码通过云服务商密钥管理（AWS Secrets Manager / Azure Key Vault）注入，不从 `.env` 读取。
- 补充 docker-compose healthcheck：`test: ["CMD", "curl", "-f", "http://localhost:8000/health"]`。

**优先级**：立即（第一阶段）。

---

## 三、代码质量评审

### 3.1 P0：PostgreSQL 下 upsert 必然崩溃

- **位置**：`python/data_collector/upsert.py:2`
- **代码**：`from sqlalchemy.dialects.sqlite import insert`
- **影响**：`upsert_realtime`、`insert_kline_bulk`、`upsert_fut_daily_bulk`、`upsert_fut_settle_bulk`、`upsert_fut_price_limit_bulk` 均使用 `on_conflict_do_update` / `on_conflict_do_nothing`，在 PostgreSQL 下执行会抛出 `CompileError`。
- **根因**：`.env` 已提供 PostgreSQL 配置选项，且当前生产环境计划使用 PostgreSQL，但 upsert 模块未做方言适配。
- **修复难度**：低。根据 `engine.dialect.name` 动态选择 `sqlite.insert` 或 `postgresql.insert`。
- **自动化**：CI 必须增加 PostgreSQL 服务容器，跑 upsert 集成测试。

### 3.2 P1：生产环境未禁止 SQLite

- **位置**：`python/config.py:10`、`python/models.py:12`
- **代码**：`DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./futures_community.db")`
- **影响**：生产环境若未配置 `DATABASE_URL`，会静默回退 SQLite，导致 WAL 模式、连接池、并发写入均不符合生产要求。
- **修复**：`ENV=production` 且 `DATABASE_URL.startswith("sqlite")` 时直接抛出 `ValueError`。

### 3.3 P1：K 线按品种混存，无合约维度

- **位置**：`python/models.py:144` `KlineDataDB`
- **代码**：`variety_id + period + trading_time` 构成唯一键。
- **影响**：`AU2506` 和 `AU2512` 的日线数据会落在同一 `variety_id=AU` 下，换月后历史 K 线语义混乱，无法区分具体合约。
- **修复**：新增 `contracts` 表，`kline_data` 增加 `contract_id`，唯一键改为 `contract_id, period, trading_time`。

### 3.4 P1：主力合约切换无历史记录

- **位置**：`python/data_collector/pipeline.py:382` `run_fut_mapping()`
- **代码**：仅 `variety.contract_code = contract_code`，无切换历史、无连续合约衔接。
- **影响**：用户无法追溯"何时从 AU2506 切换到 AU2512"，连续 K 线拼接缺少依据。
- **修复**：新增 `contract_rollovers` 表，保存 `old_contract_code/new_contract_code/effective_date/source`。

### 3.5 P1：Alembic 版本硬编码导致漂移

- **位置**：`python/models.py:41`
- **代码**：`INSERT OR IGNORE INTO alembic_version (version_num) VALUES ('7a8e00d86747')`
- **影响**：仓库已有后续迁移脚本（5 个），新库 `alembic_version` 被固定为旧版本，`alembic upgrade head` 会跳过中间迁移，导致 schema 不完整。
- **修复**：应用启动不写死 `alembic_version`；首次部署使用 `alembic upgrade head` 管理 schema。

### 3.6 P1：CORS 环境变量名不一致

- **位置**：`python/main.py:62`、`.env.example:25`
- **代码**：`os.getenv("CORS_ORIGINS", "...")` vs `ALLOW_ORIGINS=http://localhost:3000`
- **影响**：用户按 `.env.example` 配置后，CORS 实际仍使用默认值，生产环境若未严格校验，可能出现跨域配置失效。
- **修复**：代码兼容读取两个变量名；生产环境缺失 CORS 配置直接失败。

### 3.7 P1：缓存存储 ORM 实例

- **位置**：`python/routers/realtime.py:17`、`python/services/cache.py:37`
- **代码**：`get_cached("realtime:{symbol}", _fetch)` 中 `_fetch` 返回 `RealtimeQuoteDB` ORM 实例。
- **影响**：ORM 实例绑定原始 session，跨请求复用时可能出现 `DetachedInstanceError`；多线程环境下 session 不安全。
- **修复**：缓存纯 dict 或 Pydantic DTO，`_fetch` 返回后显式转换为 plain dict。

### 3.8 P1：金融字段大量使用 Float

- **位置**：`python/models.py:75` `ProductDB.current_price`（Float）、`python/models.py:150` `KlineDataDB.open_price`（Float）、`python/data_collector/cleaner.py:41` 清洗后仍转 float。
- **影响**：浮点数二进制精度问题在盈亏、保证金、结算类计算中会累积误差。行情展示可接受，但结算参数必须精确。
- **修复**：
  - 资金类字段（`settle`、`margin_rate`、`commission`、`pre_settlement`、`up_limit`、`down_limit`）统一改为 `Numeric(18, 6)`。
  - 行情展示类字段（`current_price`、`open`、`high`、`low`、`close`）可保留 `Float` 或改为 `Numeric(18, 4)`，视业务精度要求。
  - Cleaner 层清洗后返回 `Decimal` 而非 `float`。

### 3.9 P2：评论空白内容可绕过

- **位置**：`python/schemas.py:42`
- **代码**：`min_length=1` 在校验器之前执行；validator 先 `strip()` 再 `html.escape()`；`"   "` 会通过 `min_length=1`，strip 后变成空字符串入库。
- **修复**：validator 中 `strip()` 后增加空内容检查：`if not v: raise ValueError("评论内容不能为空")`。

### 3.10 P2：评论历史无分页

- **位置**：`python/routers/comments.py:46`
- **代码**：`.all()`
- **影响**：数据量大时一次性加载全部评论，内存和响应时间均会恶化。
- **修复**：增加 `skip/limit` 参数，默认 100，上限 1000。

### 3.11 P2：通用异常处理器过度吞异常

- **位置**：`python/main.py:105`
- **代码**：`@app.exception_handler(Exception)` 返回统一 500，不暴露任何内部信息。
- **影响**：开发/测试环境难以定位问题；生产环境若未配置 Sentry 等外部监控，完全丢失异常上下文。
- **修复**：`ENV=development` 时返回异常类型和堆栈；生产环境仅记录日志，响应仍统一 500。

### 3.12 P2：调度器启动即失败风险

- **位置**：`python/data_collector/scheduler.py:107`
- **代码**：`if not entries: raise RuntimeError("No data collector is available")`
- **影响**：模块导入时即执行，若 Tushare Token 无效、AkShare 依赖缺失、MockCollector 初始化失败，整个 FastAPI 应用无法启动。
- **修复**：延迟初始化，首次调度任务执行时再构建 collector；或捕获异常后降级为 MockCollector 并告警。

---

## 四、数据模型评审

### 4.1 模型总览

当前 15+ 张表，覆盖：
- 用户与认证：`users`
- 旧兼容层：`products`、`comments`
- 新数据层：`varieties`、`realtime_quotes`、`kline_data`
- 扩展期货数据：`fut_daily_data`、`fut_settle`、`fut_weekly_detail`、`fut_wsr`、`fut_holding`、`fut_price_limits`、`fut_index`
- 用户业务：`watchlists`、`opinions`
- 运维：`data_ingestion_runs`、`alembic_version`

### 4.2 核心缺陷

| 表 | 问题 | 严重程度 |
|----|------|----------|
| `varieties` | 只有当前 `contract_code`，无合约历史、无到期日跟踪 | P1 |
| `kline_data` | 唯一键为 `variety_id+period+trading_time`，换月后不同合约 K 线冲突 | P1 |
| `products` | 与新模型 `realtime_quotes` 字段类型不一致（Float vs Numeric） | P2 |
| `fut_settle` | 结算费率等字段用 Float，应 Numeric | P1 |
| `fut_price_limits` | `up_limit`/`down_limit` 用 Float，应 Numeric | P1 |
| `fut_daily_data` | `amount` 用 Float，应 Numeric | P1 |
| `realtime_quotes` | `current_price` 用 Float，期货价格精度要求下可接受但非最佳 | P2 |
| `watchlists` | `resistance_level`/`support_level` 用 Numeric(15,4)，正确 | 正常 |

### 4.3 缺失模型

| 缺失表 | 业务必要性 | 建议周期 |
|--------|-----------|----------|
| `contracts` | 合约生命周期管理、K 线归属 | 第二阶段 |
| `contract_rollovers` | 主力换月历史、连续 K 线拼接 | 第二阶段 |
| `trading_calendar` | 交易日/休市日、夜盘归属 | 第三阶段 |
| `continuous_kline` | 主力连续/指数连续 K 线 | 第三阶段 |
| `data_source_health` | 数据源健康状态、熔断记录 | 第四阶段 |

---

## 五、数据 Pipeline 评审

### 5.1 Pipeline 架构

```text
APScheduler (BackgroundScheduler)
  -> _MappedFallbackCollector (多源 fallback)
    -> Collector.fetch_realtime / fetch_kline / fetch_daily ...
  -> Adapter (字段映射)
  -> Cleaner (OHLC 校验、去重)
  -> Upsert (SQLite dialect — 危险)
  -> PostgreSQL / SQLite
```

### 5.2 采集频率与实时性

| 任务 | 频率 | 延迟分析 |
|------|------|----------|
| 实时行情 | 60 秒 | 数据源响应 1-5s + 采集间隔 60s + 缓存 TTL 5s + 前端轮询 30s = 最坏 95s |
| 分钟 K 线 | 15 分钟 | AkShare 专用，仅 1m，limit=5 |
| 日线 K 线 | 16:05 (Cron) | Tushare，limit=30 |
| 期货日线扩展 | 16:10 (Cron) | 近 10 天数据 |
| 结算参数 | 16:15 (Cron) | 当日数据 |
| 仓单/持仓/涨跌停 | 16:20-16:30 (Cron) | 当日数据 |
| 主力合约映射 | 每日 | 仅更新 varieties.contract_code |

**问题**：
- 实时行情 60 秒间隔对交易类场景过慢，但当前是社区展示，可接受。若未来开放实时提醒，需缩短至 15-30 秒或推流。
- 分钟线只采集 limit=5，即最近 5 条，历史缺口无法回补。
- 所有 Cron 任务固定在 16:00 后密集执行，若交易所延迟发布数据，可能采集空值。

### 5.3 Cleaner 质量

**优点**：
- `clean_realtime` 校验必填字段、价格正数、OHLC 一致性。
- `clean_kline` 按 `trading_time+period` 去重、排序、缺失字段跳过。

**不足**：
- 未识别涨跌停、停盘、集合竞价状态。
- 未处理夜盘数据归属交易日问题（21:00-02:30 的数据应归属下一交易日）。
- 未对异常大值/小值做阈值过滤（如价格为 0 或体积为负数）。
- 时区处理不一致：`clean_realtime` 使用 `timezone.utc`，但期货业务时间是东八区。

### 5.4 Upsert 质量

**严重问题（P0）**：硬编码 SQLite dialect，PostgreSQL 下全部崩溃。

**中等问题（P1）**：
- `upsert_fut_weekly_detail_bulk`、`upsert_fut_wsr_bulk`、`upsert_fut_holding_bulk` 使用逐行 `query().first()` 检查存在性，而非批量 upsert，性能差。
- `insert_kline_bulk` 使用 `on_conflict_do_nothing`，不更新已有数据。若数据源修正历史 K 线，数据库不会同步。

### 5.5 数据源 Fallback

`_MappedFallbackCollector` 设计良好：按 Tushare → AkShare → Mock 顺序尝试，单个失败自动切换。

但缺少：
- 失败率统计和熔断。
- 数据源降级时的用户可见通知（如 API 响应中标注 `data_source: "mock"`）。

---

## 六、安全评审

### 6.1 已修复（良好）

- ✅ `SECRET_KEY` 强制环境变量注入，生产长度 ≥32。
- ✅ 密码使用 bcrypt（passlib），带随机盐。
- ✅ JWT 解码捕获 `PyJWTError`，不裸 `except`。
- ✅ 评论 XSS 过滤：`html.escape()` + `min_length/max_length`。
- ✅ 登录限流：IP 级 10 req/60s，恒定时间比较防御时序攻击。
- ✅ CORS 已配置（但变量名不一致）。

### 6.2 待修复

| 问题 | 位置 | 严重度 |
|------|------|--------|
| Token 存 localStorage，XSS 可窃取 | 前端 `lib/api.ts` | P2 |
| 无 refresh token，无法吊销 | `config.py:16` | P2 |
| 评论接口 `/api/comments/user/{username}` 无需登录 | `routers/comments.py:40` | P2 |
| 无全局请求日志/审计 | 缺失 | P2 |
| docker-compose DB 密码弱默认 | `docker-compose.yml` | P1 |

---

## 七、测试评审

### 7.1 现状

- `tests/conftest.py`：内存 SQLite + TestClient + `seed_varieties` fixture，隔离良好。
- `tests/test_p0_fixes.py`：~380 行，覆盖 SECRET_KEY、bcrypt、XSS、JWT、缓存并发、限流、健康探针。
- `tests/test_phase1_3_integration.py`：~270 行，覆盖表存在性、Schema/API 集成、旧 API 兼容。

### 7.2 缺失测试

| 测试 | 优先级 | 说明 |
|------|--------|------|
| PostgreSQL upsert 集成测试 | P0 | 唯一阻断生产的缺陷 |
| 生产环境 SQLite 禁用测试 | P1 | 配置校验 |
| CORS 变量名读取测试 | P1 | 配置一致性 |
| 缓存 ORM detached 测试 | P1 | 并发请求 `/api/realtime` |
| 多合约 K 线并存测试 | P1 | 业务正确性 |
| 主力换月历史记录测试 | P1 | 业务正确性 |
| 夜盘 trading_day 归属测试 | P1 | 业务正确性 |
| 涨跌停识别测试 | P1 | 业务正确性 |
| Pipeline 异常降级测试 | P2 | 可靠性 |
| 数据源熔断测试 | P2 | 可靠性 |
| 健康探针 scheduler 语义测试 | P2 | 运维正确性 |
| 评论空白内容 422 测试 | P2 | 输入校验 |

---

## 八、前端交互评审

### 8.1 API 契约

- 前端 30 秒轮询 `/api/realtime/{symbol}` 和 `/api/products`。
- K 线图使用 `/api/kline/{symbol}?period=1h&limit=100`。
- 评论使用 `/api/comments`（POST，需登录）和 `/api/comments/user/{username}`（GET，公开）。

### 8.2 问题

- 轮询模式下，最坏延迟约 95 秒（见 5.2），用户可能看到明显滞后的行情。
- 前端无 SSE/WebSocket 支持，无法接收实时推送。
- K 线图接口无合约选择，换月后前端展示的数据会"跳跃"（不同合约价格差异）。
- 评论接口无分页，用户评论多时会返回大量数据。

---

## 九、问题汇总与优先级矩阵

| 编号 | 问题 | 严重度 | 阶段 | 修复难度 |
|------|------|--------|------|----------|
| 1 | PostgreSQL upsert 崩溃 | P0 | 第一阶段 | 低 |
| 2 | 生产未禁止 SQLite | P1 | 第一阶段 | 低 |
| 3 | CORS 变量名不一致 | P1 | 第一阶段 | 低 |
| 4 | 缓存 ORM 实例 | P1 | 第一阶段 | 低 |
| 5 | Alembic 版本硬编码 | P1 | 第一阶段 | 低 |
| 6 | 调度器启动即失败 | P1 | 第一阶段 | 低 |
| 7 | 健康探针 scheduler 语义错误 | P1 | 第一阶段 | 低 |
| 8 | 金融字段 Float → Numeric | P1 | 第二阶段 | 中 |
| 9 | 无合约表，K 线混存 | P1 | 第二阶段 | 高 |
| 10 | 主力换月无历史 | P1 | 第二阶段 | 中 |
| 11 | 无交易日历/夜盘建模 | P1 | 第三阶段 | 高 |
| 12 | 进程内限流失效 | P1 | 第四阶段 | 中 |
| 13 | 无数据源熔断 | P1 | 第四阶段 | 中 |
| 14 | APScheduler 多实例重复 | P2 | 第四阶段 | 中 |
| 15 | 无 Prometheus 监控 | P2 | 第四阶段 | 低 |
| 16 | 评论空白绕过 | P2 | 第一阶段 | 低 |
| 17 | 评论历史无分页 | P2 | 第一阶段 | 低 |
| 18 | 通用异常过度吞信息 | P2 | 第一阶段 | 低 |
| 19 | Token 存 localStorage | P2 | 第四阶段 | 中 |
| 20 | 前端无 SSE 推送 | P2 | 第五阶段 | 中 |

---

## 十、评审结论

当前后端在**开发演示环境**下运行良好，安全基础已打牢，Pipeline 链路清晰，多源采集有 fallback。但从**生产运行**和**期货业务正确性**两个维度看，系统存在 1 个 P0 阻断缺陷、12 个 P1 高风险问题、以及多个 P2 体验与扩展性问题。

**必须立即处理 P0（PostgreSQL upsert）**，否则生产环境无法运行。

**第一阶段（1-2 天）** 应把 P0 + 所有低难度 P1/P2（配置、缓存、Alembic、健康探针、评论分页、空白校验）全部修复，使系统达到"可稳定运行"状态。

**第二阶段（3-5 天）** 补全合约模型和 K 线归属，解决期货数据的历史可追溯性。

**第三至五阶段** 依次补齐交易日历、生产化能力（worker 拆分、Redis 限流、监控）、实时推送。

---

*评审完成时间：2026-05-05*
*评审人：AI 编程助手（基于源码逐文件审查）*
