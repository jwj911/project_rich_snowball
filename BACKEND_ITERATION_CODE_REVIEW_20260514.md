# 后端迭代代码审查报告（2026-05-14 整合版）

> 审查角色：后端架构与代码审查
> 审查范围：`python/` 下模型层、API 路由层、业务服务层、数据采集/访问层、配置工具、迁移脚本、测试代码。
> 审查目标：识别 P0/P1/P2/P3 风险，区分本次迭代引入与历史遗留，并给出修复优先级与架构路线图。
> **更新说明**：本版本在既有审查基础上，补充了首轮逐文件深度审查中发现的采集层竞态、服务层稳定性、脚本层匹配错误和测试层字段不一致等问题，形成更完整的后端风险视图。

## 结论摘要

本次后端迭代已经补齐了不少关键能力：bcrypt 密码哈希、生产环境禁止 SQLite、统一异常响应、合约表与换月表、SSE 行情推送雏形、调度器健康检查、熔断器、数据质量脚本等。整体方向正确。

但当前仍存在 **5 个必须优先处理的 P0 风险**（既有 3 个 + 补充 2 个）：

1. `kline_data.contract_id` 允许 `NULL`，却被纳入唯一约束，导致 K 线去重在旧数据/未匹配合约数据上失效。
2. 合约换月模型虽已建立，但生命周期、唯一约束、交易日历和主力切换校验不完整，连续 K 线语义仍不够可靠。
3. 部分新增测试绕过 `conftest.py`，直接使用真实 `SessionLocal` 和全局 `TestClient`，可能污染开发库。
4. **（新增）** `scripts/backfill_kline_contract_id.py` 中 SHFE 合约后缀匹配错误（`.SHF` vs `.SHFE`），导致大量上海期货交易所合约无法正确回填 `contract_id`。
5. **（新增）** `data_collector/pipeline.py` 扩展任务（结算/仓单/持仓/涨跌停/周报）使用 list comprehension 逐行适配，单条坏数据会导致整批数百行全部丢失。

综合健康度评分：**6.0/10**（较原 6.5 略下调，因采集层和回填脚本的实际数据风险在本次深度审查中被量化）。安全基础明显改善，但数据语义、采集容错、回填正确性、实时推送治理、测试隔离和生产运行边界还需要加硬约束。

## 审查覆盖文件

### 模型与迁移

- `python/models.py`
- `python/alembic/env.py`
- `python/alembic/versions/*.py`

### API 路由

- `python/routers/auth.py`
- `python/routers/products.py`
- `python/routers/comments.py`
- `python/routers/varieties.py`
- `python/routers/kline.py`
- `python/routers/realtime.py`
- `python/routers/contracts.py`
- `python/routers/watchlists.py`
- `python/routers/price_levels.py`
- `python/routers/workspace.py`
- `python/routers/health.py`

### 服务、采集与工具

- `python/services/cache.py`
- `python/services/continuous_kline.py`
- `python/services/circuit_breaker.py`
- `python/services/metrics.py`
- `python/data_collector/*.py`
- `python/scripts/*.py`
- `python/tushare_pg_ingest/*.py`
- `python/config.py`
- `python/dependencies.py`
- `python/main.py`
- `python/utils.py`
- `python/worker.py`

### 测试

- `python/tests/*.py`

## P0 致命级问题

### P0-1：K 线唯一约束因 nullable `contract_id` 失效

- 优先级：P0
- 状态：本次 Phase 2 引入
- 文件：
  - `python/models.py:188-206`
  - `python/data_collector/upsert.py:112-132`
  - `python/alembic/versions/7a40b39893ea_expand_kline_unique_to_contract_id.py:21-23`
- 现象：
  - `KlineDataDB.contract_id` 定义为 `nullable=True`。
  - 唯一约束为 `(variety_id, contract_id, period, trading_time)`。
  - PostgreSQL 和 SQLite 中，唯一约束不会把多个 `NULL` 当作相等值。
  - 当 `insert_kline_bulk()` 无法匹配合约时，`contract_id=None` 的重复 K 线可持续写入。
- 影响：
  - 历史 K 线、连续 K 线、回测和数据质量报告可能被重复数据污染。
  - 数据量越大，修复成本越高。
- 修复建议：
  1. 先运行回填脚本并清理重复 K 线。
  2. 如果业务要求每条 K 线必须绑定合约，将 `contract_id` 改为非空。
  3. 如果要兼容 legacy/null 数据，在 PostgreSQL 添加部分唯一索引：
     - `(variety_id, period, trading_time) WHERE contract_id IS NULL`
     - `(variety_id, contract_id, period, trading_time) WHERE contract_id IS NOT NULL`
  4. `insert_kline_bulk()` 遇到无法解析 `contract_id` 时应计入 skipped 或写入独立 quarantine 表，不应静默入库。

### P0-2：合约换月设计仍不完整

- 优先级：P0
- 状态：本次 Phase 2 引入，部分历史语义债务延续
- 文件：
  - `python/models.py:144-166`
  - `python/models.py:210-223`
  - `python/data_collector/pipeline.py:435-491`
  - `python/services/continuous_kline.py:39-119`
- 现象：
  - `fut_contracts` 有合约表，但没有完整生命周期状态机。
  - `contract_rollovers` 没有唯一约束，重复运行 mapping 任务可能写入重复换月记录。
  - `run_fut_mapping()` 即使 `new_contract` 未找到，也会写 `new_contract_id=None` 并更新 `variety.contract_code`。
  - 换月 `effective_date` 只来自任务执行日或传入 `trade_date`，没有校验交易日、夜盘归属日、主力判定来源。
  - `get_continuous_kline()` 按换月段拼接，但没有价格前复权/后复权策略，也没有处理缺段和重复段。
- 影响：
  - 连续 K 线可能拼错合约。
  - 复盘、技术指标、回测结果可能失真。
- 修复建议：
  1. `contract_rollovers` 增加唯一约束：`(variety_id, effective_date, new_contract_code)`。
  2. 切换主力前必须校验新合约存在，缺失时中止并记录失败。
  3. 建立合约生命周期字段：`list_date`、`last_trade_date`、`delivery_month`、`contract_type`、`status`。
  4. 引入交易日历和夜盘归属规则。
  5. 连续 K 线接口增加 `adjustment=none|forward|backward` 参数，并明确默认值。

### P0-3：新增测试污染真实开发数据库

- 优先级：P0
- 状态：本次 Phase 2/3 测试代码引入
- 文件：
  - `python/tests/test_contracts.py:12`
  - `python/tests/test_contracts.py:30-45`
  - `python/tests/test_contracts.py:56-68`
  - `python/tests/test_pipeline_rollover.py`
- 现象：
  - 测试文件直接创建 `client = TestClient(app)`。
  - 测试中直接使用 `models.SessionLocal()`，没有使用 `conftest.py` 的内存数据库 fixture。
  - `clean_db()` 调用真实 `init_db()` 并删除真实表数据中的测试 symbol。
  - `test_pipeline_rollover.py` 也直接使用真实 `SessionLocal()`。
- 影响：
  - 本地运行测试会污染 `python/futures_community.db`。
  - 如果 `DATABASE_URL` 指向共享 PostgreSQL，可能污染真实数据。
  - CI 和本地测试结果不可复现。
- 修复建议：
  1. 所有测试统一使用 `client` 和 `db_session` fixture。
  2. 禁止测试文件内全局 `TestClient(app)`。
  3. 禁止测试直接导入生产 `SessionLocal()`。
  4. 增加测试守卫：测试环境若 `DATABASE_URL` 不是 `sqlite:///:memory:` 或临时库则 fail fast。

### P0-4：K 线回填脚本 SHFE 后缀匹配错误（新增）

- 优先级：P0
- 状态：本次 Phase 2 引入
- 文件：
  - `python/scripts/backfill_kline_contract_id.py:55-62`
- 现象：
  - 脚本尝试用 `.SHF` 后缀匹配上海期货交易所合约（如 `TEST2501.SHF`）。
  - 但 `fut_contracts` 表中 SHFE 合约的实际后缀为 `.SHFE`（如 `TEST2501.SHFE`），且 `test_contracts.py` 中也使用 `.SHFE`。
  - 同时，脚本对历史 K 线统一按当前 `variety.contract_code` 回填，未考虑历史换月——历史 K 线本应归属已下市的旧合约，却被错误归到当前主力合约。
- 影响：
  - 大量 SHFE 品种（AU、CU、RB 等）的 K 线 `contract_id` 无法正确回填。
  - 历史数据语义错误直接影响连续 K 线拼接、主力切换判断和数据质量报告的可信度。
- 修复建议：
  1. 修正后缀映射：`SHFE` → `.SHFE`，`CZCE` → `.ZCE`，`DCE` → `.DCE`，`INE` → `.INE`，`GFEX` → `.GFEX`，`CFFEX` → `.CFFEX`。
  2. 增加 exchange→suffix 的显式映射字典，避免硬编码分散在多处。
  3. 回填时按 `trading_time` 范围匹配当时的主力合约，而非只用当前 `variety.contract_code`。
  4. 回填后输出按交易所分组的匹配率报告，低于阈值的品种需人工介入。

### P0-5：Pipeline 扩展任务单行失败导致整批丢失（新增）

- 优先级：P0
- 状态：本次 Phase 3 扩展引入
- 文件：
  - `python/data_collector/pipeline.py`（`run_fut_settle`、`run_fut_wsr`、`run_fut_holding`、`run_fut_price_limit`、`run_fut_weekly_detail`）
- 现象：
  - 上述扩展 pipeline 均使用 list comprehension 进行适配：
    ```python
    rows = [self.adapter(row) for row in raw_rows]
    ```
  - 若 Tushare 返回的某一行存在字段缺失、类型异常或意外空值，`self.adapter(row)` 会抛出异常，导致整个列表推导失败。
  - 结果是：整批数百条合法数据随一条坏数据一起被丢弃。
- 影响：
  - 结算参数、仓单、持仓排名等关键数据大面积缺失。
  - `/health/scheduler` 显示 success，但实际数据未入库，观测失真。
- 修复建议：
  1. 将 list comprehension 改为逐行 `try/except` 循环。
  2. 单条失败时记录 `logger.warning`（含原始行摘要和异常类型），继续处理后续行。
  3. 在 `stats` 中增加 `adapter_failed` 计数。
  4. 失败率超过阈值（如 >10%）时，将整批标记为 `partial_success` 而非 `success`。

## P1 严重级问题

### P1-1：登录门禁与后端 API 鉴权边界不一致

- 状态：历史遗留 + 本次合约/实时接口延续
- 文件：
  - `python/routers/products.py`
  - `python/routers/varieties.py`
  - `python/routers/kline.py`
  - `python/routers/contracts.py`
  - `python/routers/realtime.py`
  - `python/routers/health.py`
- 现象：
  - 前端主页面是登录后工作台，但后端大量行情、合约、K 线 API 可匿名访问。
  - 合约接口测试传了 Authorization header，但路由本身未校验。
- 影响：
  - 私密社区产品边界不一致。
  - 后端 API 可被绕过前端直接访问。
- 修复建议：
  - 明确 public/private API 分层。
  - 若产品定位为登录后工作台，行情、K 线、合约、批量实时接口都应接入 `get_current_user_dependency`。
  - `/health` 保留基础探活，`/health/ready`、`/health/scheduler`、`/metrics` 应限制内网或运维鉴权。

### P1-2：SSE token 放在 query string

- 状态：本次 Phase 3 引入
- 文件：
  - `python/routers/realtime.py:103-118`
- 现象：
  - `/api/realtime/stream?token=...` 使用 query 参数传 JWT。
  - query string 容易进入浏览器历史、代理日志、访问日志、监控系统。
- 影响：
  - token 泄露风险提高。
- 修复建议：
  - 改为短期一次性 stream token。
  - 或使用 HttpOnly Cookie + CSRF 防护。
  - 至少禁止记录该路由 query，且 stream token 有极短 TTL。

### P1-3：SSE 缺少连接治理

- 状态：本次 Phase 3 引入
- 文件：
  - `python/routers/realtime.py:62-99`
- 现象：
  - 无每用户连接数限制。
  - 无 `symbols` 数量上限。
  - 无心跳事件。
  - 无服务端超时。
  - 每 5 秒循环创建 DB session，连接数随客户端数线性增长。
- 影响：
  - 少量恶意或异常客户端即可造成连接、DB session、CPU 压力。
- 修复建议：
  - 限制 `symbols` 长度，例如最大 50。
  - 限制每用户/每 IP SSE 连接数。
  - 增加 heartbeat、idle timeout、断线检测。
  - 长期迁移到 Redis Pub/Sub 或消息队列 fanout。

### P1-4：熔断器统计逻辑不足

- 状态：本次 Phase 3 引入
- 文件：
  - `python/data_collector/pipeline.py:113-137`
  - `python/data_collector/pipeline.py:173-189`
  - `python/services/circuit_breaker.py`
- 现象：
  - `run_realtime()` 内部单品种失败只累加 `stats["failed"]`，不会触发 `record_failure()`。
  - 只要批任务没有抛到外层，就会 `record_success()`。
  - 如果全部 symbol 都失败但异常被内部捕获，熔断器仍会被重置。
- 影响：
  - 外部数据源大面积失败时，熔断器可能失效。
- 修复建议：
  - 用失败率驱动熔断：例如 `failed / total >= 0.5` 记录失败。
  - 全部 skipped 或全部 failed 不应调用 `record_success()`。
  - 记录数据源维度和任务维度的失败状态。

### P1-5：交易日历和夜盘处理缺失

- 状态：历史遗留
- 文件：
  - `python/scripts/data_quality_report.py`
  - `python/data_collector/cleaner.py`
  - `python/data_collector/adapters.py`
- 现象：
  - 数据质量脚本按自然日检查缺失 K 线，没有排除周末、节假日、休市日。
  - 夜盘 21:00-02:30 没有归属到交易日。
  - minute K 线没有 session 校验。
- 影响：
  - 质量报告会产生大量误报。
  - 夜盘数据可能落入错误交易日。
- 修复建议：
  - 引入交易日历表或外部交易日历服务。
  - K 线数据增加 `trade_date` 字段，区别自然时间 `trading_time`。
  - 夜盘按交易所规则归属到下一交易日。

### P1-6：K 线周期枚举不统一

- 状态：历史遗留 + 本次接口延续
- 文件：
  - `python/routers/kline.py`
  - `python/routers/contracts.py`
  - `python/data_collector/scheduler.py`
  - `python/data_collector/adapters.py`
- 现象：
  - 同时存在 `1d`、`D`、`1h`、`60`、`1w`、`W` 等周期表达。
  - 入库和查询使用裸字符串匹配。
- 影响：
  - 同一周期可能被写入多个逻辑分区，前端查询不到数据。
- 修复建议：
  - 建立统一 `KlinePeriod` 枚举。
  - 入库前统一 normalize。
  - 数据库层增加 check constraint。

### P1-7：`watchlists` 缺少数据库唯一约束

- 状态：本次 Phase 1 引入
- 文件：
  - `python/models.py:226-237`
  - `python/routers/watchlists.py:49-54`
- 现象：
  - 创建自选时只在应用层查重。
  - 并发请求可能同时通过查重并写入重复数据。
- 影响：
  - 用户自选列表重复。
- 修复建议：
  - 增加 `UniqueConstraint("user_id", "variety_id")`。
  - 捕获 `IntegrityError` 并返回 409。

### P1-8：生产 CORS 校验不够严格

- 状态：历史遗留
- 文件：
  - `python/main.py:69-82`
- 现象：
  - 生产只要求 `CORS_ORIGINS` 存在。
  - 没有拒绝 `*`、HTTP 明文域名、空白项或本地开发域名。
  - `allow_credentials=True` 时尤其需要严格来源。
- 影响：
  - 生产跨域边界可能被错误配置放宽。
- 修复建议：
  - 生产环境拒绝 `*`。
  - 默认要求 HTTPS origin。
  - 禁止 localhost/127.0.0.1 进入生产 CORS。

### P1-9：异常响应在开发环境返回 traceback

- 状态：历史遗留
- 文件：
  - `python/main.py:164-178`
- 现象：
  - `ENV == "development"` 时返回 exception 和 traceback。
- 影响：
  - 如果部署环境误设为 development，路径、SQL、堆栈会暴露给客户端。
- 修复建议：
  - 改为仅本地 `DEBUG=1` 且 host 为 localhost 时返回 traceback。
  - 其他环境统一只返回 request_id。

### P1-10：批量实时接口没有 symbols 上限

- 状态：本次 Phase 3 引入
- 文件：
  - `python/routers/realtime.py:44-59`
- 现象：
  - `symbols` 可传任意长度列表。
  - 每个 symbol 至少一次品种查询，未做批量 SQL。
- 影响：
  - 可被构造为低成本 DoS。
- 修复建议：
  - Query 参数限制最大长度。
  - 使用一次 SQL 批量查询 varieties 和 realtime_quotes。

### P1-11：密码最小长度仅 6 位（新增）

- 状态：历史遗留
- 文件：
  - `python/schemas.py`（`UserCreate.password`）
- 现象：
  - `Field(..., min_length=6, max_length=128)`。
  - 低于 NIST SP 800-63B 建议的最低 8 位。
- 影响：
  - 金融类社区账户密码策略过弱，易被暴力破解。
- 修复建议：
  - `min_length=6` 改为 `min_length=8`。
  - 同步更新 `test_p0_fixes.py` 中相关边界测试用例。

### P1-12：JWT 默认 24h 有效期且无刷新机制（新增）

- 状态：历史遗留
- 文件：
  - `python/config.py`（`ACCESS_TOKEN_EXPIRE_MINUTES = 1440`）
  - `python/utils.py`（`create_access_token`）
- 现象：
  - Token 默认 24 小时有效，无 `jti` claim，无 Refresh Token。
  - `.env.example` 声称可配 `ACCESS_TOKEN_EXPIRE_MINUTES`，但 `config.py` 未从环境变量读取。
  - 一旦泄露，服务端无法吊销，只能等待自然过期。
- 影响：
  - 泄露 token 可全天使用；移动端长期会话无法安全续期。
- 修复建议：
  - 短期：将默认值降至 60 分钟，并允许从环境变量读取。
  - 中期：引入 Refresh Token 机制（旋转刷新），Access Token 缩短到 15 分钟。
  - 增加 `jti` claim，为后续服务端吊销表预留能力。

### P1-13：Cache Stampede（缓存穿透雪崩）（新增）

- 状态：历史遗留（服务层长期存在）
- 文件：
  - `python/services/cache.py:25-35`
- 现象：
  - `get_cached()` 在锁外执行 `db_fetch_func()`。
  - 并发请求同一 key 且缓存 miss 时，所有线程同时穿透到数据库。
  - 对实时行情等高并发热点 key，可能导致 DB 压力骤增。
- 影响：
  - 行情刷新或首页加载高峰期，缓存反而成为 DB 压力放大器。
- 修复建议：
  - 在锁内增加"正在加载"占位（如 sentinel object），第一个线程执行查询，后续线程等待。
  - 或引入 `cachetools` + `lock` 的 `cached` 装饰器替代手写逻辑。

### P1-14：`refresh_realtime_quotes` session 失效后未回滚（新增）

- 状态：本次 Phase 3 引入
- 文件：
  - `python/data_collector/scheduler.py`（`refresh_realtime_quotes` 任务）
- 现象：
  - `run_realtime()` 在循环中逐 symbol 采集并写入。
  - 单个 symbol 异常被捕获后，当前 session 已进入 "must rollback" 状态。
  - 循环继续到下一个 symbol，下一次 `db.execute()` 会抛出 `InvalidRequestError`，导致**整批剩余 symbol 全部失败**。
- 影响：
  - 一个坏 symbol 污染整个批次，实时行情大面积中断。
- 修复建议：
  - 在逐 symbol `except` 块中加入 `db.rollback()`。
  - 或改为每 symbol 独立 session（性能开销可控，隔离性更好）。

### P1-15：`_ensure_collectors()` 存在竞态条件（新增）

- 状态：本次 Phase 3 引入
- 文件：
  - `python/data_collector/scheduler.py`
- 现象：
  - `_initialized` 是模块级普通 `bool`，无锁保护。
  - `BackgroundScheduler` 使用线程池（默认 10 workers）。
  - 若两个任务同时启动，均可能看到 `_initialized == False`，导致 collector/pipeline 被重复初始化。
- 影响：
  - 重复初始化可能创建多余的数据源连接、浪费配额，甚至引发竞态写入。
- 修复建议：
  - 增加 `threading.Lock()` 保护 check-then-act 逻辑。

### P1-16：`worker.py` 不加载 `.env` 且不处理 SIGTERM（新增）

- 状态：本次 Phase 3 引入
- 文件：
  - `python/worker.py`
- 现象：
  - 模块顶部使用 `os.getenv("SECRET_KEY")`，但从未 `import config` 或 `load_dotenv()`。
  - 依赖 shell 导出环境变量，与主应用（`main.py` 会导入 `config.py` 从而加载 `.env`）行为不一致。
  - 仅捕获 `KeyboardInterrupt`（SIGINT），未注册 `SIGTERM` 处理器。
  - Docker/K8s `docker stop` 发送 SIGTERM，`finally` 块不会执行，`shutdown_scheduler()` 丢失。
- 影响：
  - `.env` 配置在 worker 进程中失效，生产部署容易踩坑。
  - 容器环境无法优雅退出，scheduler 状态丢失，可能导致任务中断或重复执行。
- 修复建议：
  - 顶部增加 `import config`（或显式 `load_dotenv()`）。
  - 注册 `signal.signal(signal.SIGTERM, lambda _s, _f: sys.exit(0))`。
  - 将 `shutdown_scheduler()` 放到信号处理器或 `atexit` 中。

### P1-17：评论无修改/删除接口（新增）

- 状态：历史遗留
- 文件：
  - `python/routers/comments.py`
- 现象：
  - 仅提供 `POST /` 和 `GET /user/{username}`。
  - 用户发布评论后无法修改或删除。
- 影响：
  - 产品功能闭环缺失；用户误发内容后无法自救。
- 修复建议：
  - 增加 `PUT /api/comments/{id}`（仅作者/管理员可修改）。
  - 增加 `DELETE /api/comments/{id}`（仅作者/管理员可删除）。
  - 补充 pytest 覆盖越权场景（用户 A 修改用户 B 的评论应 403）。

### P1-18：`data_collector/scheduler.py` `trade_date` 使用本地时间（新增）

- 状态：历史遗留
- 文件：
  - `python/data_collector/scheduler.py`
- 现象：
  - `sync_fut_*` 任务使用 `datetime.now().strftime("%Y%m%d")`（本地时间）。
  - 若服务器运行在 UTC，中国期货市场 16:00 CST 收盘后，UTC 时间才 08:00，日期仍为前一天。
- 影响：
  - 结算参数、仓单、持仓排名等日终任务可能使用错误日期查询。
- 修复建议：
  - 统一使用 `datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai"))`。
  - 或引入 `trade_date` 计算函数，明确按交易所规则归属。

### P1-19：Prometheus endpoint label 使用完整解析路径（新增）

- 状态：本次 Phase 3 引入
- 文件：
  - `python/main.py:123-128`
- 现象：
  - middleware 中 `endpoint = path` 使用的是解析后的完整路径（如 `/api/products/123`），而非路由模板（`/api/products/{id}`）。
  - 每个不同 ID 都产生新的时间序列。
- 影响：
  - Prometheus cardinality 爆炸，存储和查询性能崩溃。
- 修复建议：
  - 改为 `request.scope.get("route").path`，fallback 到 path。

## P2 重要级问题

### P2-1：连续 K 线查询存在性能风险

- 文件：`python/services/continuous_kline.py:87-119`
- 现象：
  - 每个换月段执行一次查询。
  - 每段 `q.all()` 后 Python 合并排序，再截断 limit。
- 影响：
  - 换月段多、时间范围长时内存和 DB 查询成本升高。
- 建议：
  - 限制 start/end 必填或默认合理窗口。
  - 用 SQL union/window function 下推 limit。
  - 对 `(variety_id, period, contract_id, trading_time)` 建复合索引。

### P2-2：工作区和自选接口存在 N+1 查询

- 文件：
  - `python/routers/workspace.py:34-45`
  - `python/routers/watchlists.py:23-35`
- 现象：
  - 每条 watchlist 单独查询 variety。
- 影响：
  - 自选列表增长后接口延迟上升。
- 建议：
  - 使用 `selectinload(WatchlistDB.variety)`。
  - 或显式 join 后组装响应。

### P2-3：Prometheus 指标标签仍可能高基数

- 文件：`python/main.py:123-128`
- 现象：
  - 注释说使用路由路径，但实际使用 `request.url.path`。
  - `/api/products/1`、`/api/products/2` 会成为不同 label。
- 影响：
  - Prometheus time series 膨胀。
- 建议：
  - 使用 `request.scope["route"].path`，fallback 到 path。

### P2-4：`/metrics` 和 `/health/scheduler` 公开暴露内部信息

- 文件：
  - `python/main.py:133-136`
  - `python/routers/health.py:55-114`
- 现象：
  - 指标、调度任务名、数据源、错误统计均匿名可读。
- 影响：
  - 攻击者可获取内部拓扑和数据源状态。
- 建议：
  - 生产环境限制内网访问。
  - 或加运维 token。

### P2-5：时间类型混用 naive 和 aware datetime

- 文件：
  - `python/models.py`
  - `python/data_collector/pipeline.py`
  - `python/data_collector/adapters.py`
- 现象：
  - 模型默认多用 `datetime.datetime.now`。
  - pipeline 记录任务使用 `datetime.now(timezone.utc)`。
  - adapters 解析出来多为 naive datetime。
- 影响：
  - 跨时区部署、交易日归属、排序比较可能出现隐性 bug。
- 建议：
  - 统一 UTC aware datetime。
  - DB 使用 timezone-aware 类型。
  - 对交易时间单独保存本地交易所时间和交易日。

### P2-6：输入验证对部分路径参数不够严格

- 文件：
  - `python/routers/varieties.py`
  - `python/routers/realtime.py`
  - `python/routers/contracts.py`
- 现象：
  - `symbol`、`exchange` 等没有统一格式约束。
  - `symbols` 列表没有长度、单项长度和字符集约束。
- 影响：
  - 查询放大、日志噪声、缓存 key 污染。
- 建议：
  - 增加 symbol 正则：`^[A-Z]{1,6}$` 或兼容合约代码。
  - 对列表长度和单项长度设上限。

### P2-7：`CommentCreate` validator 对非字符串输入处理不够干净

- 文件：`python/schemas.py:48-56`
- 现象：
  - `mode="before"` 下，如果传入非字符串，仍会调用 `html.escape(v)`。
- 影响：
  - 可能返回不一致的 validation error。
- 建议：
  - 改为 `mode="after"`。
  - 或先判断 `isinstance(v, str)`，非字符串直接抛 `ValueError`。

### P2-8：慢查询日志可能输出 SQL 片段

- 文件：`python/models.py:42-46`
- 现象：
  - 慢查询日志输出 `statement[:500]`。
- 影响：
  - 虽然 SQLAlchemy 参数化通常不会带参数，但仍可能暴露表结构和业务字段。
- 建议：
  - 生产环境只记录 route、duration、statement hash。
  - 详细 SQL 放 debug 或受控开关。

### P2-9：数据采集任务状态统计只取最近 20 条

- 文件：`python/routers/health.py:64-99`
- 现象：
  - 最近 24h 统计实际只基于 `.limit(20)`。
- 影响：
  - 高频任务下成功率统计不真实。
- 建议：
  - 使用 SQL 聚合统计 24h 全量。
  - 列表展示再单独 limit 10。

### P2-10：缺少统一 Repository/DAO 层

- 文件：`python/routers/*.py`, `python/data_collector/*.py`
- 现象：
  - 路由直接操作 ORM。
  - 工作区、自选、价位标注重复组装响应。
- 影响：
  - 鉴权、分页、错误处理和预加载策略容易分散。
- 建议：
  - 先为用户私有资源提取 repository/service。
  - 统一所有权校验函数。

### P2-11：连续 K 线 `datetime.min` naive/aware 比较风险（新增）

- 状态：本次 Phase 2 引入
- 文件：
  - `python/services/continuous_kline.py:66`
- 现象：
  - 代码使用 `datetime.min`（naive，无时区）与 DB 中的 `effective_date` 或 `trading_time` 比较。
  - 若 DB 字段为 timezone-aware，会抛出 `TypeError: can't compare offset-naive and offset-aware datetimes`。
  - SQLAlchemy filter `trading_time >= datetime.min` 在 PostgreSQL 中也可能报错。
- 影响：
  - 连续 K 线服务在某些数据条件下会直接崩溃。
- 修复建议：
  - 将 `datetime.min` 替换为 `datetime(1970, 1, 1, tzinfo=timezone.utc)`。
  - 或在比较前统一将 DB 值转为 naive（不推荐）。

### P2-12：注册/price_levels 等无 `IntegrityError` 处理（新增）

- 状态：历史遗留
- 文件：
  - `python/routers/auth.py`
  - `python/routers/price_levels.py`
- 现象：
  - `auth.py` 注册使用"读-然后-写"模式，无 serializable 隔离。
  - `price_levels.py` 虽有 DB 唯一约束，但也未处理 `IntegrityError`。
  - 并发请求下可能抛出未捕获的 `IntegrityError`，返回 HTTP 500 而非 409。
- 修复建议：
  - 捕获 `IntegrityError`，返回 `409 Conflict`。
  - 或依赖 DB 唯一约束 + `INSERT ... ON CONFLICT DO NOTHING` 模式。

### P2-13：`html.escape()` 导致 React 双转义（新增）

- 状态：历史遗留
- 文件：
  - `python/schemas.py`
- 现象：
  - Pydantic validator 在 `mode="before"` 中对评论/标注内容执行 `html.escape()`。
  - 前端 React 默认已转义文本节点，导致用户看到字面 `&lt;`、`&gt;`、`&amp;`。
- 影响：
  - 用户体验下降；数学表达式、URL 等显示异常。
- 修复建议：
  - 若已知前端为 React，后端只做 XSS 输出过滤（不在存储层转义）。
  - 或前端使用 `dangerouslySetInnerHTML`（不推荐）。
  - 最佳方案：后端移除 `html.escape()` 存储转义，改在 API 响应序列化时做必要过滤。

### P2-14：`run_realtime` N+1 SELECT（新增）

- 状态：历史遗留
- 文件：
  - `python/data_collector/pipeline.py`
- 现象：
  - `upsert_realtime` 每品种执行一次 `SELECT ... FROM varieties WHERE symbol = ?`。
  - 100+ 品种每分钟产生 100+ 次多余 DB 查询。
- 修复建议：
  - 批量查询：一次 `SELECT` 查出全部目标品种的 `variety_id`。
  - 或建立 `symbol -> variety_id` 的进程内缓存（TTL 较长，因为品种元数据变化极少）。

### P2-15：`cleaner.py` 拒绝负价格和裸 `int()` 转换（新增）

- 状态：历史遗留
- 文件：
  - `python/data_collector/cleaner.py`
- 现象：
  - `_valid_ohlc` 拒绝 `high/low/open/close < 0`。
  - 某些利率期货/价差合约可合法为负（中国期货当前罕见，但非不可能）。
  - `clean_realtime` 使用裸 `int(data["volume"])`，若 adapter 传入 float string（如 `"123.0"`）会崩溃。
- 修复建议：
  - `_valid_ohlc` 将负价格检查改为按品种配置（默认拒绝，允许配置豁免）。
  - `clean_realtime` 使用 `_to_int` 或 `int(float(v))` 做防御转换。

### P2-16：K-line upsert 静默忽略修正（新增）

- 状态：历史遗留
- 文件：
  - `python/data_collector/upsert.py`
- 现象：
  - K-line 使用 `on_conflict_do_nothing()`。
  - 上游数据源修正历史 bar（如结算价调整、成交量修正）时，无法覆盖旧数据。
- 修复建议：
  - 提供可选的 `on_conflict_do_update` 模式（按更新时间或数据源优先级判断）。
  - 或至少对最近 N 天的数据使用 update 策略。

### P2-17：`adapters.py` `_parse_datetime` 时区解析不完整（新增）

- 状态：历史遗留
- 文件：
  - `python/data_collector/adapters.py`
- 现象：
  - `_parse_datetime` 无法解析带时区偏移的 ISO 8601 字符串（如 `2024-01-01T00:00:00+08:00`），返回 `None`。
- 影响：
  - 若上游 API 调整返回格式，时间戳会静默丢失。
- 修复建议：
  - 支持 `fromisoformat` 或 `dateutil.parser.isoparse`。

### P2-18：测试字段名不一致与死测试（新增）

- 状态：混合（Phase 2 引入 + 历史遗留）
- 文件：
  - `python/tests/test_contracts.py`
  - `python/tests/test_p0_fixes.py`
- 现象：
  - `test_contracts.py` 中 `_get_or_create_user` 使用 `password_hash=`，而 `_create_test_user` 使用 `hashed_password=`。
  - `test_p0_fixes.py` 中 `test_get_db_session_closes_connection` 因 `init_data.py` 已过时而被永久跳过。
- 修复建议：
  - 统一测试 helper 字段名，与 `models.py` 保持一致。
  - 清理或迁移已跳过的死测试。

## P3 优化级问题

### P3-1：中文文本和注释出现大量乱码

- 文件：多处，包括 `models.py`、`main.py`、`schemas.py`、测试文件
- 影响：
  - 维护成本高。
  - 错误消息和 API 文档不可读。
- 建议：
  - 全仓统一 UTF-8。
  - 修复已损坏中文字符串。
  - CI 增加编码检查。

### P3-2：类型注解覆盖不足

- 文件：多处
- 现象：
  - 服务层大量返回 `dict`。
  - collector/adapter 返回结构没有 TypedDict 或 Pydantic model。
- 建议：
  - 为 market data rows 定义 TypedDict。
  - 分阶段引入 `mypy` 或 `pyright`。

### P3-3：测试覆盖缺少真实并发和数据迁移场景

- 文件：`python/tests`
- 现象：
  - 有功能测试，但缺少并发写、迁移前后数据兼容、SSE 连接压力、K 线重复防护测试。
- 建议：
  - 增加并发创建 watchlist/price_level 测试。
  - 增加 nullable contract_id 重复插入回归测试。
  - 增加 Alembic upgrade/downgrade smoke test。

### P3-4：日志体系还不完整

- 文件：多处
- 现象：
  - 登录、数据修改、价位标注、自选变更没有审计日志。
  - 没有日志轮转配置。
- 建议：
  - 引入结构化日志。
  - 关键操作记录 user_id、request_id、resource_id、action。
  - 生产使用轮转或集中日志。

### P3-5：OpenAPI 文档可读性受乱码影响

- 文件：`python/routers/*.py`
- 建议：
  - 修复 tags、description、detail 文本编码。
  - 为关键接口补充 response examples。

### P3-6：`services/continuous_kline.py` 边界与排序问题（新增）

- 状态：本次 Phase 2 引入
- 现象：
  - 连续 K 线使用 `< query_end`（严格小于），主力 K 线使用 `<= end`（包含等于），边界不一致。
  - `all_rows[:limit]` 在内存中截断，分钟线 + 多年数据可能加载数十万行。
  - `sort(key=lambda x: x["time"])` 对 ISO 8601 字符串排序，混合时区格式时可能出错。
- 建议：
  - 统一边界语义（推荐左闭右开 `[start, end)`）。
  - 大时间范围查询在数据库层用 `LIMIT` 下推。
  - 排序使用 `datetime` 对象而非字符串。

### P3-7：`services/metrics.py` 多进程指标丢失与死指标（新增）

- 状态：本次 Phase 3 引入
- 现象：
  - `prometheus_client` 默认 registry 仅暴露当前进程内存指标。
  - `uvicorn --workers N` 时每次 `/metrics` 只能随机命中一个 worker。
  - `cache_operations_total` 已定义但 `cache.py` 从未 `inc()`。
- 建议：
  - 使用 `prometheus_client.multiprocess.MultiProcessCollector`（需设置 `PROMETHEUS_MULTIPROC_DIR`）。
  - 或在 `cache.py` 中接入指标计数。

### P3-8：`models.py` 架构小缺陷（新增）

- 状态：历史遗留 + Phase 1 引入
- 现象：
  - `WatchlistDB` 存在死列 `resistance_level`、`support_level`（从未被路由使用）。
  - `OpinionDB` 有模型但无路由，死 schema。
  - `_IS_SQLITE` 在导入时求值，若 `DATABASE_URL` 被 monkey-patch 后失效。
  - 热点查询路径缺少复合索引（`CommentDB(product_id, created_at)`、`PriceLevelDB(user_id, created_at)`）。
- 建议：
  - 清理死列/死表（或补充路由实现）。
  - 使用 `functools.lru_cache` 包装 engine 创建，延迟求值。
  - 增加复合索引迁移。

### P3-9：`data_collector/upsert.py` 死代码（新增）

- 状态：历史遗留
- 现象：
  - `upsert_fut_contract_bulk` 已定义但从未被 pipeline/scheduler 调用。
- 建议：
  - 清理或接入合约同步 pipeline。

### P3-10：熔断器缺少 HALF_OPEN 与读操作副作用（新增）

- 状态：本次 Phase 3 引入
- 现象：
  - 熔断器只有 OPEN/CLOSED 二态，冷却结束后立即全量放行。
  - `is_circuit_open()` 在读取时自动重置失败计数，语义不纯。
- 建议：
  - 引入 HALF_OPEN 状态，冷却结束后仅允许有限探测请求。
  - 将状态清理逻辑拆分到 `record_success()` 中。

## 逐层评价

### 数据库模型层

优点：

- 用户、评论、品种、实时行情、K 线、合约、换月、价位标注、自选等核心实体已具备。
- PostgreSQL 连接池配置有 `pool_pre_ping` 和 `pool_recycle`。
- 生产环境禁止 SQLite。

主要风险：

- K 线 nullable contract 唯一键失效。
- 合约生命周期模型不完整。
- 部分业务唯一性只靠应用层（watchlists 缺 DB 约束）。
- 时间字段没有统一 timezone。
- 死列/死表表面（`WatchlistDB.resistance_level`、`OpinionDB`）。
- 热点查询缺少复合索引。

### API 接口层

优点：

- FastAPI 路由按领域拆分。
- 用户私有资源的 CRUD 基本有越权保护。
- 输入分页参数多数有边界。
- 全局异常响应已统一。

主要风险：

- 登录门禁和后端 API 鉴权边界不一致。
- SSE token 和连接治理不足。
- 批量查询接口缺少数量上限。
- 部分健康/指标接口暴露内部信息。
- 评论无修改/删除接口。
- `html.escape()` 导致前端双转义。

### 业务服务层

优点：

- 连续 K 线服务独立出来，方向正确。
- 缓存使用锁保护，避免 ORM detached 实例缓存。
- 熔断器有最小实现。

主要风险：

- 连续 K 线语义仍缺复权、交易日历、缺段处理，且存在 naive/aware 时间比较崩溃风险。
- 熔断器失败统计不准确，缺少 HALF_OPEN。
- 服务层返回 dict，缺少明确 DTO。
- Cache Stampede 无防护。
- 多进程场景 Prometheus 指标不完整。

### 数据访问与采集层

优点：

- upsert 使用 SQLAlchemy dialect insert，没有明显 SQL 注入。
- collector -> adapter -> cleaner -> pipeline 分层清晰。
- 外部数据源 fallback 和生产禁 mock 方向正确。

主要风险：

- 无法解析合约时仍可能写入 `contract_id=None` K 线。
- 周期规范不统一。
- 夜盘和交易日归属缺失。
- **单行坏数据导致整批丢失**（扩展 pipeline）。
- **session 失效后未回滚，污染整批实时行情**。
- **collector 初始化存在竞态条件**。
- `_record_run` 掩盖部分失败，健康检查统计失真。
- `trade_date` 使用本地时间，跨时区部署时日期错误。

### 工具与配置层

优点：

- `SECRET_KEY` 必填。
- 生产环境密钥长度检查。
- 生产环境禁止 SQLite。
- Scheduler 默认禁用，worker 独立入口方向正确。

主要风险：

- CORS 生产配置缺少严格校验（未拒绝 `*`）。
- development traceback 可能因环境误配泄露。
- 日志轮转和结构化日志缺失。
- **worker 不加载 `.env`，SIGTERM 未处理**。
- JWT 默认 24h 且无刷新机制。
- 密码最小长度仅 6 位。

### 测试代码

优点：

- 已覆盖认证、缓存、价格标注、自选、合约、SSE、调度健康等路径。

主要风险：

- 部分测试没有使用隔离 fixture，会污染真实数据库。
- 缺少并发/迁移/数据完整性测试。
- 测试文件中存在错误字段 `hashed_password` 的废弃 helper。
- **永久跳过的死测试未清理**。

## 问题汇总表

| 优先级 | 数量 | 说明 |
|---|---:|---|
| P0 | 5 | 必须立即修复。新增 K 线回填脚本匹配错误、Pipeline 整批丢失，与既有 K 线唯一约束、合约换月语义、测试污染并列 |
| P1 | 19 | 本周内修复。涵盖鉴权、SSE、熔断、交易日历、CORS、唯一约束、密码策略、Token 机制、Cache Stampede、采集竞态、worker 信号、评论闭环、Prometheus cardinality 等 |
| P2 | 18 | 迭代内修复。涵盖性能、观测、输入验证、DAO 抽象、连续 K 线稳定性、双转义、N+1、适配器健壮性等 |
| P3 | 10 | 长期优化。涵盖编码、类型、测试覆盖、日志、文档、死代码清理、熔断器 HALF_OPEN、指标多进程等 |

## 本周必须修复 TOP 10

1. 修复 `kline_data.contract_id NULL` 唯一约束漏洞，并清理已产生的重复数据。
2. **修正 `backfill_kline_contract_id.py` SHFE 后缀匹配错误（`.SHF` → `.SHFE`），验证回填覆盖率。**
3. **将 Pipeline 扩展任务（结算/仓单/持仓等）从 list comprehension 改为逐行容错，避免整批丢失。**
4. 将 `test_contracts.py`、`test_pipeline_rollover.py` 迁移到内存库 fixture，禁止测试污染真实库。
5. 明确并落地行情、合约、K 线接口的鉴权策略（public vs private 分层）。
6. 将 SSE token 从 query string 迁移到更安全机制，并增加连接数、symbols 数量、心跳、超时限制。
7. **修复 `refresh_realtime_quotes` session 失效后未回滚问题（单 symbol 异常不污染整批）。**
8. **修复 `_ensure_collectors()` 竞态条件（加锁）和 `worker.py` 的 `.env` 加载 + SIGTERM 处理。**
9. 修正熔断器失败统计逻辑（按失败率触发，全部失败不应记 success）。
10. `watchlists` 增加数据库唯一约束并处理并发 409；统一 K 线 period 枚举与入库规范。

## 架构改进路线图

### 近期：1 周内

- 修复 P0 数据完整性、测试隔离和采集容错问题。
- 强化 API 鉴权边界。
- 给 SSE 和批量查询加限流与参数上限。
- 增加数据库唯一约束和并发测试。
- **修复 worker.py 配置加载和信号处理，确保生产容器可优雅退出。**

### 中期：2-4 周

- 建立统一 K 线周期枚举和交易日历模块。
- 把合约生命周期、换月、连续 K 线复权策略做成领域服务。
- 采集任务状态和熔断状态从内存迁到 Redis 或 PostgreSQL。
- 将行情推送从 API 进程内循环升级为 Redis Pub/Sub 或消息队列 fanout。
- **引入 Refresh Token，缩短 Access Token 至 15 分钟。**
- **提取 Repository/Service 层，消解 Router N+1 和手动构造响应。**

### 长期：1-2 个季度

- K 线大表按周期和时间分区，或迁移到 TimescaleDB hypertable。
- 建立数据质量平台：缺口、重复、异常 OHLC、延迟、数据源可用性统一监控。
- 引入结构化审计日志和请求链路追踪。
- 路由层瘦身，建立 repository/service/DTO 分层。
- 推进 `ruff`、`mypy`、迁移 smoke test、并发测试进入 CI。

## 安全维度检查结果

| 维度 | 结论 |
|---|---|
| 密码安全 | ⚠️ bcrypt 随机盐正确，但最小长度仅 6 位，弱于现代标准。 |
| SQL 注入 | ✅ 主运行路径基本合格。未发现用户输入拼接 SQL。 |
| 权限验证 | ⚠️ 用户私有资源基本合格；行情/合约/K 线读接口鉴权边界需确认并加强。 |
| SQLite 并发安全 | ✅ 生产已禁止 SQLite；开发默认 SQLite 仍不适合并发采集和压测。 |
| 合约换月 | ⚠️ 有表和基础服务，但语义完整性不足，回填脚本有匹配错误。 |
| 实时推送 | ⚠️ 已有 SSE 雏形，但 token 和连接治理不足。 |
| CORS | ⚠️ 生产要求配置存在，但缺少严格校验（未拒绝 `*`）。 |
| 缓存线程安全 | ⚠️ 内存缓存有锁保护，基本合格；但存在 Cache Stampede，多进程不共享是后续架构限制。 |
| Token 安全 | ⚠️ 24h 默认有效期过长，无刷新机制，无服务端吊销能力。 |
| 测试隔离 | ❌ 部分测试使用真实 SessionLocal，可能污染开发库。 |

## 建议执行顺序

1. **先修测试隔离**，确保后续修复不会污染真实库。
2. **修 K 线唯一键、回填脚本和 Pipeline 容错**，保护历史数据可信度和采集稳定性。
3. **修合约换月约束和主力切换校验**。
4. **收紧 API 鉴权和 CORS**。
5. **治理 SSE 和批量行情接口**。
6. **修复 worker.py 生产运行边界**（.env、信号、优雅退出）。
7. 引入交易日历和 period normalize。
8. 优化查询性能和观测指标。

---

本报告基于 2026-05-14 工作区当前代码树的两轮深度审查生成。第一轮侧重模型/路由/服务/采集/脚本的逐文件风险识别；第二轮侧重既有审查文档的交叉验证与补充。最终归因以 git 历史和 PR 范围为准。
