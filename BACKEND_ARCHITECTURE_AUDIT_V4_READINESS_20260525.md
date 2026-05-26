# 后端整体架构审计报告 v4

> 审计目标：判断当前后端是否准备好承接下一阶段功能迭代，并给后端 agent 提供可执行的还债清单。
>
> 审计日期：2026-05-25
> 审计分支：master
> 审计范围：`python/` 后端主应用、数据采集、调度、领域服务、测试、依赖与运维配置。

---

## 执行摘要

- **综合健康度评分**：6.2 / 10
- **技术债务总量**：高债务 1 项，中债务 7 项，低债务 2 项
- **决策建议**：B - 先进行 1 到 3 周还债迭代，再承接大功能
- **一句话结论**：后端已经从“能跑”进化到“有分层、有测试、有观测雏形”，但测试环境不可复现、数据采集/K 线复杂度偏高、实时推送和双数据层会拖慢下一阶段功能迭代。

建议策略：

1. 小型低风险功能可以继续，例如只读 Admin 页面、SSO 初版调研。
2. 多租户、回测、持仓实时同步、期权 Greeks 不建议直接开工。
3. 先用一个还债迭代修复测试可复现性、SSE token、采集调度复杂度和 Python 依赖审计。

---

## 一、六维评分详情

| 维度 | 权重 | 评分 | 结论 |
|------|------|------|------|
| 可维护性 | 20% | 6.0 | 有 router/service/repository 分层，但采集调度和连续 K 线核心函数偏复杂。 |
| 可扩展性 | 20% | 6.0 | 无模块循环依赖；但 `ProductDB` 兼容层和新行情层并存，长期会拖慢演进。 |
| 性能与稳定性 | 20% | 6.5 | 有连接池、索引、缓存、熔断和指标；但调度全量扫描、SSE 进程内状态仍是隐患。 |
| 安全与合规 | 15% | 6.5 | JWT、bcrypt、refresh token 轮转、生产 CORS 检查较好；Python 依赖审计未跑通。 |
| 测试覆盖 | 15% | 5.5 | 测试文件较多，但当前本地测试环境不可复现，且无后端 CI workflow。 |
| 文档与可观测性 | 10% | 6.5 | README、OpenAPI、request_id、structlog、Prometheus 指标具备；缺报警/SLO/tracing。 |

**加权总分：6.2 / 10**

### 1. 可维护性：6.0 / 10

得分点：

- 路由按领域拆分，`routers/` 覆盖 auth、products、comments、varieties、kline、realtime、contracts、watchlists、price-levels、workspace、health。
- 部分业务已经下沉到 `services/domain/*` 和 repository 层，例如 product、comment、price level、watchlist、workspace。
- 配置集中在 `python/config.py`，生产环境校验 SECRET_KEY、SQLite、CORS。

扣分项：

- `python/data_collector/scheduler.py` 约 716 行，承担 collector 初始化、fallback、调度注册、各类同步任务。
- `python/data_collector/pipeline.py` 约 692 行，多个 pipeline 方法结构重复，且 `run_fut_mapping` 同时处理映射、合约、rollover 和事务。
- `python/services/continuous_kline.py` 中连续 K 线逻辑复杂度偏高。
- 当前环境读取时，部分中文注释/字符串出现乱码，增加交接和排障成本。

证据：

- `python/data_collector/scheduler.py:110`，`_ensure_collectors()` 负责延迟初始化、真实源 fallback、Mock 降级和多个 pipeline 实例创建。
- `python/data_collector/pipeline.py:581`，`run_fut_mapping()` 静态近似圈复杂度约 24。
- `python/services/continuous_kline.py:99`，`get_continuous_kline()` 约 157 行，静态近似圈复杂度约 20。

### 2. 可扩展性：6.0 / 10

得分点：

- 静态 import 图未发现模块级循环依赖。
- 新增标准 CRUD 的路径比较清楚：model/schema/router/service/repository/test。
- Collector 体系已有 `BaseCollector`、Mock、AkShare、Tushare 和 fallback collector 雏形。

扣分项：

- `ProductDB` 兼容层仍是前端主流程的一部分，新数据层 `VarietyDB`、`RealtimeQuoteDB`、`KlineDataDB` 并存。
- `sync_prices_to_products()` 将新行情同步回旧 `products` 表，说明领域模型尚未完全收敛。
- 新增复杂数据源仍需要改 `scheduler.py`、`pipeline.py`、adapter、collector、调度注册，范围超过理想 3 个文件。

证据：

- `python/models.py:97`，`ProductDB`。
- `python/models.py:133`，`VarietyDB`。
- `python/models.py:186`，`RealtimeQuoteDB`。
- `python/models.py:207`，`KlineDataDB`。
- `python/data_collector/scheduler.py:308`，`sync_prices_to_products()`。

### 3. 性能与稳定性：6.5 / 10

得分点：

- PostgreSQL engine 配置了 `pool_size=10`、`max_overflow=20`、`pool_pre_ping=True`。
- `models.py` 有慢查询日志 hook。
- K 线、结算、持仓、仓单等关键表已配置多个唯一约束和索引。
- 缓存层有 Redis 优先、内存 LRU fallback、TTL jitter、击穿防护。
- 数据源熔断器已存在，连续失败后冷却。

扣分项：

- 多个调度任务仍全量加载品种并循环调用外部源或数据库。
- 熔断器和 SSE 连接表均为进程内内存，多 worker / 多实例部署时状态不共享。
- SSE 当前仍依赖长连接内存状态，不适合直接横向扩展。

证据：

- `python/models.py:31`，PostgreSQL engine 连接池配置。
- `python/models.py:48`，SQLAlchemy 慢查询监听。
- `python/services/cache.py:40`，`get_cached()`。
- `python/services/circuit_breaker.py:9`，进程内熔断状态。
- `python/data_collector/scheduler.py:254`，`refresh_realtime_quotes()` 全量 `VarietyDB.all()`。
- `python/data_collector/scheduler.py:285`，`sync_daily_kline()` 全量 `VarietyDB.all()`。
- `python/routers/realtime.py:29`，进程内 `_sse_connections`。

### 4. 安全与合规：6.5 / 10

得分点：

- 密码使用 bcrypt。
- Access token / refresh token 分离，refresh token hash 后入库，并有轮转逻辑。
- 生产环境要求强 SECRET_KEY，禁止 SQLite，禁止 HTTP/localhost/wildcard CORS。
- `npm audit --omit=dev` 本次运行结果：0 vulnerabilities。

扣分项：

- Python 依赖审计未稳定跑通。
- `requirements.txt` 有范围版本，无法使用 `pip-audit --disable-pip --no-deps` 直接审计。
- Cookie auth 场景下未见显式 CSRF 策略。当前 `SameSite=Lax` 降低风险，但不能替代明确 CSRF 威胁模型。
- `/health/scheduler` 公开返回调度任务历史、熔断状态、缓存状态，生产环境建议至少限制内网或加鉴权。

证据：

- `python/utils.py:10`，`hash_password()` 使用 bcrypt。
- `python/utils.py:36`，`hash_refresh_token()` 使用 SHA-256 存储 refresh token hash。
- `python/routers/auth.py:49`，refresh token HttpOnly cookie。
- `python/routers/auth.py:195`，refresh token 轮转。
- `python/config.py:28`，生产 SECRET_KEY 长度校验。
- `python/config.py:32`，生产禁止 SQLite。
- `python/main.py:162`，生产 CORS 校验。
- `python/routers/health.py:63`，公开 scheduler health。

### 5. 测试覆盖：5.5 / 10

得分点：

- 当前仓库有 26 个 `python/tests/test_*.py` 文件。
- 覆盖 watchlists、price levels、workspace、contracts、scheduler health、circuit breaker、metrics、refresh token、realtime SSE、data quality 等。

扣分项：

- 本地无法稳定运行测试。
- 仓库 venv 的解释器路径失效。
- 系统 Anaconda Python 缺项目依赖，强行挂 venv site-packages 后遇到 pydantic_core 二进制扩展不匹配。
- `.github/workflows/` 仅看到 `update-calendar.yml`，未见后端 pytest CI。

复现命令与结果：

```powershell
cd python
$env:SECRET_KEY="test-secret-key-for-audit"
$env:ENABLE_SCHEDULER="0"
python -m pytest tests -q
```

结果：系统 Python 缺 `dotenv`。

```powershell
.\venv\Scripts\python.exe -m pytest tests -q
```

结果：venv 指向的 Python 解释器不可用。

```powershell
$env:PYTHONPATH="D:\Code\project_rich_snowball\python\venv\Lib\site-packages"
python -m pytest tests -q
```

结果：`pydantic_core._pydantic_core` 缺失，二进制扩展不匹配。

### 6. 文档与可观测性：6.5 / 10

得分点：

- README 包含技术栈、启动、测试、PostgreSQL、数据采集说明。
- FastAPI 自动 OpenAPI 文档在非生产环境启用。
- 已接入 request_id middleware、structlog、Prometheus 指标。
- `/metrics` 限制本地/内网可信访问。

扣分项：

- 缺统一错误码注册表。
- 缺 tracing backend，异步采集和 API 请求无法串完整链路。
- 缺报警分级、SLO、容量基线、恢复演练文档。

证据：

- `python/main.py:197`，`request_id_middleware()`。
- `python/main.py:214`，`prometheus_middleware()`。
- `python/main.py:242`，`/metrics`。
- `python/services/logging_config.py:47`，structlog processors。
- `python/services/metrics.py:10`，HTTP request counter。

---

## 二、技术债务热力图

| 模块 | 债务等级 | 具体表现 | 代码位置 | 最小复现方式 | 阻塞功能 | 建议还债方案 |
|------|----------|----------|----------|--------------|----------|--------------|
| 测试/工具链 | 高 | 当前机器无法稳定运行测试，CI 也未覆盖后端测试 | `python/requirements.txt`、`python/pyproject.toml`、`.github/workflows/` | 运行 `python -m pytest tests -q` 或 `.\venv\Scripts\python.exe -m pytest tests -q` | 所有高风险功能 | 重建 venv，固定 Python 版本，补 GitHub Actions 后端 CI。 |
| 数据采集调度 | 中 | 单文件大、全局状态多、collector/pipeline/scheduler 耦合 | `python/data_collector/scheduler.py:110`、`python/data_collector/pipeline.py:581` | 静态扫描复杂度，或新增一个数据源需改多处核心文件 | 多交易所、历史回填扩展 | 引入 source registry、job registry、pipeline task config。 |
| 连续 K 线 | 中 | 核心函数过长，分段循环查库，后续回测会放大复杂度 | `python/services/continuous_kline.py:99` | 构造多个 rollover 段请求连续 K 线 | 回测、历史分析 | 拆 segment builder、query service、adjustment service。 |
| SSE 实时推送 | 中 | Cookie-only 场景下 generator 使用 query token，可能传空 token | `python/routers/realtime.py:242`、`python/routers/realtime.py:285` | EventSource 只带 cookie、不带 query token | WebSocket/SSE 正式化 | 传 `effective_token`，补 cookie-only SSE 测试。 |
| 双行情数据层 | 中 | `ProductDB` 和新行情模型长期并存，靠 scheduler 同步 | `python/models.py:97`、`python/data_collector/scheduler.py:308` | 修改 realtime quote 后需等待或触发 sync | Admin、多租户、权限 | 制定兼容层退场计划，前端逐步转向 varieties/realtime。 |
| 安全依赖审计 | 中 | `pip-audit` 无法稳定完成；范围版本阻断 no-pip 模式 | `python/requirements.txt:5` | `uvx pip-audit -r requirements.txt --no-deps --disable-pip` | 上线合规 | 使用 lock 文件或 pip-tools 生成精确 pin。 |
| 可观测性运维 | 中 | 有指标但无报警、SLO、trace | `python/services/metrics.py`、`python/main.py:197` | 搜索 `.github` 和运维文档，未见报警配置 | 生产运营 | 补 Grafana/Prometheus 规则、runbook、慢查询报表。 |
| 类型质量 | 中 | mypy 排除 routers/services/data_collector，大量核心代码未受类型约束 | `python/pyproject.toml:53` | 查看 exclude 列表 | 新人接手、重构 | 分阶段移除 exclude，先覆盖 domain services。 |
| 健康接口暴露 | 低 | `/health/scheduler` 公开内部任务、熔断状态 | `python/routers/health.py:63` | 未登录访问 `/health/scheduler` | 安全合规 | 生产环境加内网限制或管理鉴权。 |
| 脚本/临时文件沉淀 | 低 | 根目录和 `python/scripts` 存在较多一次性脚本和报告 | `python/scripts/*`、根目录报告文件 | `git status --short` 可见大量未跟踪产物 | 维护体验 | 分类归档 scripts，更新 `.gitignore`。 |

---

## 三、演进能力评估

| 新功能 | 依赖模块 | Readiness | 阻塞点 | 预估成本 | 风险等级 | 建议 |
|--------|----------|-----------|--------|----------|----------|------|
| 多交易所接入 | 数据采集、品种管理 | 6 / 10 | collector 有雏形，但 scheduler/pipeline 全局耦合重 | 5-8 人天 | 中 | 先抽 source registry 与 job config。 |
| 期权 Greeks 计算 | 定价模型、风险引擎 | 3 / 10 | 无期权合约模型、定价模型、风险上下文 | 15-25 人天 | 高 | 新建独立 bounded context，不混入现有行情 pipeline。 |
| 用户持仓实时同步 | 用户体系、消息推送 | 4 / 10 | 无账户/持仓/事件/幂等任务模型 | 12-20 人天 | 高 | 先设计持仓模型和异步同步机制。 |
| 策略回测系统 | 历史数据、执行引擎 | 4 / 10 | K 线服务面向页面展示，未形成回测级数据查询服务 | 15-30 人天 | 高 | 先拆历史行情 query service 和数据切片接口。 |
| 实时 WebSocket 推送 | 网关层、消息队列 | 6 / 10 | SSE 可用但进程内状态不适合横向扩展 | 5-10 人天 | 中 | 修 SSE bug，再评估 Redis pub/sub 或消息队列。 |
| 多租户/权限体系 | 认证、数据隔离 | 3 / 10 | 无 tenant_id、RBAC、数据隔离策略 | 15-25 人天 | 高 | 需要迁移策略，不能直接在现有表上硬加。 |
| Admin 运营后台 | 管理接口、查询 | 6 / 10 | 缺 admin role、audit log、管理接口隔离 | 6-12 人天 | 中 | 可先做只读后台，避免写操作。 |
| 第三方登录/SSO | 认证体系 | 6 / 10 | auth 较集中，refresh 可复用；缺 provider/account binding | 5-8 人天 | 中 | 加 OAuth provider 表和账号绑定表。 |

---

## 四、Top 10 代码质量问题

1. `python/routers/realtime.py:285` - SSE generator 传入 `token` 而非 `effective_token`，cookie-only 场景可能失败。建议改为传 `effective_token` 并补测试。优先级：P1。
2. `python/venv/` - venv 解释器路径失效，本地无法运行 pytest。建议删除重建 venv 或文档化统一 Python 版本。优先级：P0。
3. `python/data_collector/pipeline.py:581` - `run_fut_mapping` 复杂度高，承担映射、合约、rollover、事务。建议拆服务。优先级：P1。
4. `python/services/continuous_kline.py:99` - 连续 K 线核心函数过长，扩展回测会困难。建议拆 segment/query/adjustment。优先级：P1。
5. `python/data_collector/scheduler.py:254` - 多个任务全量加载品种，10 倍数据量下会压 DB 和外部源。建议分页或按活跃合约筛选。优先级：P1。
6. `python/models.py:97` - `ProductDB` 兼容层与新行情模型长期并存，领域语义重复。建议制定退场计划。优先级：P1。
7. `python/routers/health.py:63` - scheduler health 公开返回内部任务状态与熔断状态。生产环境建议鉴权或内网限制。优先级：P2。
8. `python/services/circuit_breaker.py:9` - 熔断器为进程内内存，多 worker 状态不一致。建议 Redis 化。优先级：P2。
9. `python/pyproject.toml:53` - mypy 排除核心目录，类型检查保护有限。建议先纳入 domain services。优先级：P2。
10. `python/requirements.txt:5` - 依赖有范围版本，Python 依赖审计不稳定。建议生成 lock 文件并纳入 CI。优先级：P1。

---

## 五、风险矩阵

| 风险项 | 当前状态 | 缓解方案 | 优先级 |
|--------|----------|----------|--------|
| 数据库连接池耗尽 | PG 池 10+20，但无压测基线和连接池指标 | 加压测、连接池监控、慢查询榜 | P1 |
| 缓存降级打 DB | Redis 可降级内存，但多进程不共享 | 生产强制 Redis，监控 hit rate 和 fallback 次数 | P2 |
| 消息队列积压 | 当前无消息队列 | 引入队列前先设计 DLQ、retry、lag 指标 | P3 |
| 数据丢失 | APScheduler 进程内任务，无持久队列 | 关键采集任务引入任务表、幂等键、重试策略 | P1 |
| 级联故障 | 有 collector fallback/熔断，但进程内 | 熔断状态 Redis 化，外部源隔离限流 | P2 |
| 敏感日志泄露 | structlog 有脱敏，但 scripts 多 print | 日志扫描，生产禁跑调试脚本 | P2 |
| 备份失效 | 代码层无恢复演练证据 | 补 PG 备份与恢复 runbook，做恢复演练 | P1 |
| 时钟漂移 | 时间统一有 UTC helper，但无 NTP 运维检查 | 部署文档要求 NTP/chrony，日志记录时区 | P3 |

---

## 六、决策建议与行动项

**建议等级：B - 先进行还债迭代。**

不建议立刻开以下高复杂功能：

- 多租户/权限体系
- 策略回测系统
- 用户持仓实时同步
- 期权 Greeks 计算

可以小步推进的低风险功能：

- 只读 Admin 运营后台
- 第三方登录/SSO 技术预研
- 健康检查和指标面板增强

### 还债迭代建议排期

| 行动项 | 建议负责人 | 截止日期 | 验收标准 |
|--------|------------|----------|----------|
| 重建后端 venv 与 CI | 后端 agent | 3 天 | 本地和 CI 均可执行 `pytest tests -q`，且通过。 |
| 修复 SSE token bug | 后端 agent | 1 天 | query token 和 cookie-only 两种 SSE 测试通过。 |
| 建立 Python 依赖审计 | 后端 agent | 3 天 | 有 lock 文件或 hash requirements，`pip-audit` 可稳定执行。 |
| 拆采集 pipeline/scheduler 第一阶段 | 后端 agent | 1-2 周 | collector registry/job registry 落地；核心函数复杂度下降。 |
| 连续 K 线服务拆分 | 后端 agent | 1 周 | segment builder、query、adjustment 拆分并保持现有测试通过。 |
| 梳理 ProductDB 退场计划 | 后端 agent + 前端 agent | 1 周 | 文档列出前端依赖、迁移接口、兼容窗口和验收清单。 |
| 补生产观测 runbook | 后端 agent | 1 周 | QPS、latency、error rate、DB pool、采集失败均有监控/告警建议。 |

---

## 七、给后端 Agent 的执行顺序

### Step 1：先让测试可信

目标：任何后续改动都必须能被测试兜住。

必做：

1. 重建本地 venv。
2. 确认 `python -m pytest tests -q` 可运行。
3. 新增 `.github/workflows/backend-ci.yml`，至少跑：
   - 安装依赖
   - 设置 `SECRET_KEY`
   - 设置 `ENABLE_SCHEDULER=0`
   - 执行 `pytest tests -q`
4. 避免把 SQLite db、venv、缓存、临时报告加入提交。

验收：

```powershell
cd python
$env:SECRET_KEY="test-secret-key"
$env:ENABLE_SCHEDULER="0"
pytest tests -q
```

### Step 2：修复 SSE cookie-only bug

目标：修正当前明确的行为缺陷。

问题位置：

- `python/routers/realtime.py:242`
- `python/routers/realtime.py:285`

建议修复：

- `effective_token = token or access_token` 后，创建 `StreamingResponse` 时传入 `effective_token`。
- 补充测试：仅通过 `access_token` cookie 访问 `/api/realtime/stream`。

验收：

- 现有 `test_realtime_sse.py` 通过。
- 新增 cookie-only 场景测试通过。

### Step 3：依赖审计可复现

目标：让安全扫描成为稳定流程。

当前问题：

- `pip-audit -r requirements.txt` 在当前环境尝试构建 numpy metadata 失败。
- `pip-audit --no-deps --disable-pip` 又因范围版本无法继续。

建议方案：

1. 使用 `pip-tools` 或 `uv pip compile` 生成精确版本锁文件。
2. CI 中跑 `pip-audit` 针对锁文件。
3. 保留 `requirements.in` 或当前 `requirements.txt` 作为人工维护入口。

验收：

```powershell
pip-audit -r requirements.lock
```

### Step 4：采集调度拆分

目标：降低新增数据源/新增采集任务的改动半径。

建议拆分：

- `collector_registry.py`：负责根据 `DATA_SOURCE` 生成 collector fallback 链。
- `job_registry.py`：声明 scheduler job id、trigger、handler、max_instances、misfire。
- `pipeline_tasks/`：将 fut_daily、settle、wsr、holding、price_limit、mapping 拆成独立任务对象。

验收：

- 新增一个数据源时不需要改 `start_scheduler()` 主体。
- 新增一个采集任务时不需要改 `_ensure_collectors()` 主体。
- 现有 scheduler health 测试通过。

### Step 5：连续 K 线拆分

目标：为回测和历史分析打基础。

建议拆分：

- `build_rollover_segments()`
- `query_segment_klines()`
- `apply_backward_adjustment()`
- `attach_contract_metadata()`

验收：

- 对外接口不变。
- 现有 contracts/kline 测试通过。
- 核心函数不超过 80 行，复杂度降到 15 以下。

### Step 6：ProductDB 兼容层退场计划

目标：降低双数据层造成的长期演进成本。

建议输出：

- 当前前端依赖 `ProductDB` 的 API 清单。
- 对应的新 API 替代路径。
- 兼容窗口。
- 数据迁移或读路径切换方案。
- 删除 `sync_prices_to_products()` 的前置条件。

---

## 八、本次审计已执行的命令摘要

```powershell
git branch
git status --short
rg --files python
python -m compileall -q python
npm.cmd audit --omit=dev
uvx pip-audit -r requirements.txt
uvx pip-audit -r requirements.txt --no-deps --disable-pip
```

重要结果：

- 当前分支为 `master`。
- `npm audit --omit=dev`：0 vulnerabilities。
- `python -m compileall -q python`：代码可解析，`.pytest_cache` 有权限提示但不影响代码编译结论。
- `pytest` 未能在当前本地环境跑通，原因是 Python/venv/二进制依赖环境不可复现。
- `pip-audit` 未稳定跑通，原因包括 requirements 中文注释编码、numpy metadata 构建、范围版本无法 no-pip 审计。

---

*本报告由架构审计 Prompt v4 生成，并整理为后端 agent 可执行的迭代文档。后续 agent 执行时应以代码实际情况为准，优先修复 P0/P1，避免顺手重构无关模块。*
