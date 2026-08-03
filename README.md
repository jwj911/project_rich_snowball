# 期货交流社区

一个前后端分离的期货行情与私密交流社区应用。前端提供登录后的行情工作台、品种筛选、K 线复盘、支撑/阻力标注和个人工作区；后端提供认证、评论、实时行情、K 线、健康检查，以及 Mock / AkShare / Tushare 数据采集流水线。

---

## 当前状态

- 前端：Next.js 15 App Router，默认开发地址 `http://127.0.0.1:3200`
- 后端：FastAPI，默认开发地址 `http://127.0.0.1:8401`
- 数据库：开发可用 SQLite；PostgreSQL 16 通过 `docker-compose.yml` 提供
- K 线：前端使用 `lightweight-charts`，后端支持 `1m/5m/15m/30m/1h/1d/1w`
- 访问控制：主要页面需要登录，未登录时显示登录引导
- 新闻资讯：RSS 源管理与聚合，支持用户自建 RSS 源 + AI 新闻解读，登录用户可浏览
- 交易观点/日记：用户针对品种发表多空观点，记录目标价、止损价和理由，支持事后复盘标记状态
- 价格预警：用户为品种设置 above/below 价格预警，实时行情刷新时自动检测触发
- 模拟持仓：用户创建虚拟交易记录，支持做多/做空、盈亏计算与复盘统计
- AI 助手：用户与大模型对话，自动检索实时行情和交易观点作为上下文
- K 线存储：R8 已提供只读容量门禁、默认 dry-run 的影子分区 DDL、隔离迁移演练和管理员
  存储概况；活动 `kline_data` 仍未分区。
- 当前迭代：R11“目标环境 S1 部署与完整业务周期观测”独立规格已完成并批准，但 operator
  gate 仍为 `blocked`。当前
  [R11 记录](docs/releases/20260803_r11_s1_production_observation.md)类型为
  `blocked planning record`，不是工程基线或生产发布；真实 production 环境、四类责任人、
  deploy/rollback SHA、镜像 digest、UTC 窗口和仓库外证据目录均未提供，未执行 preflight、
  备份、恢复、部署、canary、完整窗口或 production R10 report。R10
  `non-production engineering baseline` 保持不变；R12/S2 与 R13/S3 均未启动。治理顺序见
  [Post-R9 计划](docs/iteration_plan_20260802_post_r9.md)，R11 边界见
  [R11 spec](.trae/specs/conduct-r11-production-observation/spec.md)。
- R9 工程状态：
  [CSP Report-Only 观测闭环](docs/releases/20260802_r9_csp_report_only_observability.md)
  已完成 S1 工程实现、审查修复、本地验证、增强版浏览器回归和远端 CI 工程门禁。页面同时
  返回原值不变的强制 CSP 与只上报的候选策略；报告端点支持 legacy/Reporting API、8 KiB
  上限、20 条批量、采样、限流、URL 脱敏、独立 `trace_id` 和低基数指标。R9 尚未生产
  部署，也未完成真实完整业务周期观测。
- R10 本地验证：聚焦测试
  `375 passed, 5 skipped, 1 warning`，后端全量
  `1421 passed, 22 skipped, 103 warnings`；本地 PostgreSQL 不可用，相关集成用例保持明确
  skip。
- R10 远端验证：
  [Backend CI run 30791923945（attempt 1）](https://github.com/jwj911/project_rich_snowball/actions/runs/30791923945)
  成功；R9/R10 gate 为 `268 passed, 1 warning`，全量为
  `1442 passed, 1 skipped, 103 warnings`，coverage `77.38%`。Alembic、PostgreSQL API
  smoke、Ruff check/format（122 files）和 `pip-audit` 均成功；首次运行即通过，没有修复
  提交。这些远端工程结果与上述本地结果分列，均不构成生产证据或 S2 准入。
- R9 历史本地质量基线：独立审查修复前的后端全量为
  `1177 passed, 18 skipped, 0 failed, 103 warnings`；修复后受影响聚焦回归为
  `85 passed, 1 skipped, 0 failed`，Ruff check/format 通过。唯一 skip 是新增 PostgreSQL
  持久化专项，本地无隔离 PostgreSQL；修复后的完整全量和 PostgreSQL 专项由 Backend CI
  复核。
- 审查增强前的前端 CSP 配置 `21 passed`、全量 Vitest `35 files / 223 passed`、production
  build 和基础版 R9 Playwright `3 passed` 均通过，最大 First Load JS 为 `157 kB`。增加
  并发 401 单飞刷新和 SSE 首次断线重连后，本地通过 Playwright `--list`、TypeScript 与
  ESLint；增强版实际浏览器结果以 Frontend CI 为准，不计入本地执行。
- R9 本地实现提交为 `723ba9b949bccf7c96798d2f45388731350eacd3`，本地验证文档提交为
  `37fc8008a74c1b74c48f74aac5e3267c8a29e5b6`，CI 稳定性修复提交为
  `c7a721a04f58caa51860be67d870855663186a14`。回滚点为 R9 启动文档提交
  `756ca605613ba2a4f76919e913e1264e3f9d2a1b`。
- [Backend CI run 30739553595](https://github.com/jwj911/project_rich_snowball/actions/runs/30739553595)
  成功：`R9 CSP contract gate 39 passed`，包含 PostgreSQL 持久化集成测试；完整后端测试约
  `1195 passed, 1 skipped`。
- [Frontend CI run 30740784839](https://github.com/jwj911/project_rich_snowball/actions/runs/30740784839)
  成功：Vitest、production build、R9 E2E `3 passed`、全量 Playwright `43 passed` 和
  Lighthouse 均通过。
- 上一迭代：R8 已完成
  [K 线分区生命周期准备](docs/releases/20260802_r8_kline_partition_lifecycle.md)工程验证；
  实现提交为 `41c79f1e`，最终验证提交为 `68386c51`。
- [Backend CI #38](https://github.com/jwj911/project_rich_snowball/actions/runs/30732688519)
  成功：R8 专项 `45 passed`，远程全量 `1174 passed, 1 skipped`，覆盖率 `75.98%`。
- R8 未切换活动表、未归档或删除冷数据，也未执行生产恢复演练，当前不是生产已分区或生产
  已发布状态；R9 不改变该非生产边界。
- 当前强制 CSP 仍包含兼容 Next.js 与图表运行时所需的 `unsafe-inline` / `unsafe-eval`。
  R9 的 Report-Only `script-src 'self'` 只收集违规；在取得并归类真实完整业务周期报告前
  不得进入 S2 nonce/hash 强制收紧。现有 `localStorage` token、Bearer 写请求与 CSRF 拒绝
  cookie-only 写请求的边界保持不变。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 15.5.22 + React 18.2 + TypeScript 5.3 + Tailwind CSS 3.4 |
| 图表与图标 | `lightweight-charts`、`lucide-react` |
| 后端 | Python 3.12 + FastAPI 0.136.3 + Uvicorn 0.30.6 |
| ORM / 迁移 | SQLAlchemy 2.0 + Alembic |
| 数据库 | SQLite（默认开发）/ PostgreSQL 16（可选） |
| 认证 | JWT + OAuth2 密码流 + bcrypt |
| 数据采集 | MockCollector / AkShare / Tushare |
| 定时任务 | APScheduler |
| 缓存 | Redis 优先 + 内存 LRU 降级（`services/cache.py`） |

---

## 项目结构

```text
project_rich_snowball/
├── frontend/                     # Next.js 15 前端
│   ├── app/                      # 页面路由
│   ├── components/               # React 组件（图表、行情、工作区、UI）
│   ├── hooks/                    # 自定义 Hooks（行情轮询、K线、实时推送）
│   ├── lib/                      # API 客户端、格式化、实时 Store
│   ├── tests/                    # Vitest + Playwright 测试
│   └── docs/                     # 前端专项文档
│
├── python/                       # FastAPI 后端
│   ├── main.py                   # 应用入口
│   ├── config.py                 # 环境配置
│   ├── models.py / schemas.py    # ORM 模型 / Pydantic Schema
│   ├── routers/                  # API 路由（auth/varieties/kline/realtime/agents/…）
│   ├── services/                 # 业务逻辑（Agent、回测、因子挖掘、R10 CSP 证据）
│   ├── data_collector/           # 数据采集流水线与调度器
│   ├── middleware/               # 中间件（限流、API 版本映射）
│   ├── scripts/                  # 工具脚本（回填、迁移、验收、离线证据报告）
│   ├── tests/                    # pytest 测试（R9 审查修复前全量：1177 passed, 18 skipped）
│   └── alembic/                  # 数据库迁移
│
├── quantative_tools/             # 量化分析工具集
│   ├── factors/                  # 因子定义（28个）
│   ├── signals/                  # 择时信号
│   ├── strategy/                 # 选股策略
│   └── reports/                  # 因子分析报告
│
├── docs/                         # 项目文档
│   ├── release_checklist_20260719.md # 当前发布检查与回滚清单
│   ├── iteration_plan_20260802_post_r9.md # Post-R9 治理顺序与准入门禁
│   ├── releases/20260803_r11_s1_production_observation.md # R11 受阻规划记录
│   ├── iteration_plan_20260724_follow_up.md # R1-R9 已完成历史事实源
│   ├── phase4_private_data_access_boundary.md # Agent 私有数据访问边界
│   ├── r3_raw_contract_market_panel.md # 多视图日频研究宽表
│   ├── releases/                  # 逐版本工程基线与生产发布记录
│   ├── phase4_sql_ast_readonly.md # Agent SQL AST 只读校验记录
│   ├── guides/                   # 技术参考（API 参考、数据管道、版本指南）
│   ├── archive/                  # 历史审计/路线图归档
│   └── audit_cleanup_20260705.md # 文件审计与清理追踪
│
├── .agents/                      # AI 助手分册文档
├── .github/workflows/            # CI/CD（后端测试、前端测试、交易日历更新）
├── docker-compose.yml            # PostgreSQL 16 + Redis 7
├── .env.example                  # 环境变量模板
├── AGENTS.md                     # AI 编程助手入口索引
└── README.md                     # 本文件
```

---

## 环境变量

复制 `.env.example` 为 `.env`，至少确认以下变量：

```env
DATABASE_URL=sqlite:///./futures_community.db
SECRET_KEY=change-this-to-a-real-secret
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3200,http://127.0.0.1:3200
DATA_SOURCE=mock
ENABLE_SCHEDULER=1
REDIS_URL=redis://localhost:6379/0
SSE_DEPLOYMENT_MODE=single
ENV=development
RELEASE_COMMIT=
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8401
CSP_REPORT_SAMPLE_RATE=1
HOST=127.0.0.1
PORT=8401
```

说明：
- 生产环境必须使用长度至少 32 的 `SECRET_KEY`，且不能使用 SQLite。
- 后端优先读取 `CORS_ORIGINS`，也兼容旧变量 `ALLOW_ORIGINS`。
- 前端 API 地址由 `NEXT_PUBLIC_API_BASE` 控制，代码默认是 `http://127.0.0.1:8401`。
- `CSP_REPORT_SAMPLE_RATE` 控制合法 CSP 报告的确定性采样，取值必须在 `[0, 1]`，默认
  `1`；`0` 表示全部采样丢弃，`1` 表示全部进入持久化尝试。
- `CSP_REPORT_URL` 可选；未设置时使用 `NEXT_PUBLIC_API_BASE` 的 origin 加
  `/api/log/csp-report`。覆盖值必须是无凭据、query、fragment 的绝对 HTTP(S) URL。
- `RELEASE_COMMIT` 是 API 运行时 CSP 证据归属，可选；非空时必须是完整 40 位十六进制 Git
  SHA。缺失不会阻止 S1 报告接收，但新记录的 release 为空，R10 不能据此形成
  `ready_for_review`。Compose 对 backend 和 worker 均按可选值传递。
- 若使用 `DATA_SOURCE=tushare`，需要提供 `TUSHARE_TOKEN`。
- 生产必须显式提供 `REDIS_URL` 和 `SSE_DEPLOYMENT_MODE=single|sticky`。Redis 只共享
  realtime quotes 更新时间戳；本轮未实现 Pub/Sub 或跨实例连接管理。

---

## 启动后端

```powershell
cd D:\Code\project_rich_snowball\python
python -m venv venv
venv\Scripts\activate
pip install -r requirements.lock
python main.py
```

默认服务地址：
- API: `http://127.0.0.1:8401`
- Swagger UI: `http://127.0.0.1:8401/docs`
- ReDoc: `http://127.0.0.1:8401/redoc`
- 健康检查: `http://127.0.0.1:8401/health/ready`

启动时会执行：
- `init_db()`：非生产环境自动建表，SQLite 启用 WAL
- `init_varieties()`：初始化/更新品种元数据
- `init_mock_data()`：非生产环境插入开发账号和示例评论
- `start_scheduler()`：按配置启动实时行情、K 线与扩展数据采集

---

## R10 CSP 证据离线 CLI

R10 通过后端服务层读取 R9 已脱敏的 `csp-violation` 记录，并由
[`python/scripts/csp_evidence_report.py`](python/scripts/csp_evidence_report.py) 生成低敏
JSON；没有新增管理员或其他 HTTP API。生产操作者应在仓库外准备 context、catalog 和 report
路径，且不得把这些文件提交到版本控制。CLI 强制 report path 位于仓库外；context/catalog
也按运维约束放在仓库外并显式传入。

```powershell
cd D:\Code\project_rich_snowball\python
$evidenceRoot = Join-Path $env:TEMP "rich-snowball-r10"
New-Item -ItemType Directory -Force $evidenceRoot | Out-Null
$contextPath = Join-Path $evidenceRoot "context.json"
$catalogPath = Join-Path $evidenceRoot "catalog.json"
$reportPath = Join-Path $evidenceRoot "report.json"

.\.venv\Scripts\python.exe scripts/csp_evidence_report.py `
  --database-url $env:DATABASE_URL `
  --context-path $contextPath `
  --catalog-path $catalogPath `
  --report-path $reportPath
$LASTEXITCODE
```

`DATABASE_URL` 是 `--database-url` 的唯一回退。单次执行固定为最长 31 天、最多 50,000 条记录、
最多 500 个聚合组、最多 30 秒，报告不超过 256 KiB。退出码 `0` 至 `4` 依次表示
`ready_for_review`、`insufficient_evidence`、`blocked`、`failed` 和
`report_write_failed`；本地/CI synthetic 证据的预期结果是 `insufficient_evidence` 和
退出码 `1`，不是生产成功。

R10 没有新增数据库表或 Alembic 迁移，也没有改变强制 CSP、Report-Only 策略、认证、
`localStorage` token、Bearer 写请求或 cookie-only 写请求拒绝边界。

R11 当前只完成规格和文档规划。有效观测必须覆盖至少 5 个实际交易日、连续至少 7 个自然日，
并完成固定 14 项核心流程、同窗业务 HTTP 与六类 CSP outcome 核对、仓库外 artifact 安全
保管及回滚验证。operator gate 输入未齐备前不得运行上述 CLI 生成 production report，也不得
执行任何生产 preflight、备份、恢复、迁移或部署。

---

## 启动前端

```powershell
cd D:\Code\project_rich_snowball\frontend
npm install
npm run dev
```

默认服务地址：`http://127.0.0.1:3200`

常用命令：

```powershell
npm run build
npm run lint
npx tsc --noEmit
```

---

## 页面与功能

| 路径 | 说明 |
|------|------|
| `/` | 登录后的行情工作台，展示热门品种、领涨观察、刷新状态 |
| `/products` | 行情中心，支持搜索、分类筛选、涨跌筛选和排序 |
| `/products/[id]` | 品种详情，展示实时行情、K 线、技术分析、评论、支撑/阻力标注、合约切换历史 |
| `/workspace` | 我的工作区，聚合评论历史、云端价位标注和自选观察入口 |
| `/my-comments` | 当前用户评论历史 |
| `/metrics` | 运营指标面板（用户数/评论数/采集健康度） |
| `/news` | 新闻资讯，支持来源筛选和标题搜索 |
| `/settings` | 个人设置（主题/通知/轮询间隔/语言） |

- 搜索防抖：`products` 和 `news` 页面搜索输入使用 `useDebouncedValue`（250ms），避免请求洪峰
- 实时行情 Store：`realtimeStore.ts` 同时提供全量 snapshot 和增量 delta，`useRealtimeQuotes` 明确区分增量合并与全量替换
- 导航组件：`Navbar.tsx` 统一桌面/移动端导航，`navigation.ts` 集中管理导航配置与 `isActivePath`
- 支撑/阻力标注通过 `/api/price-levels` 同步后端数据库存储，`localStorage` 仅作为降级缓存。前端错误与 Web Vitals 自动上报到后端 `/api/log/frontend`。

---

## API 概览

| 接口 | 说明 |
|------|------|
| `POST /api/auth/register` | 注册，IP 级限流 |
| `POST /api/auth/login` | 登录，OAuth2 表单，返回 JWT |
| `GET /api/auth/me` | 当前用户信息 |
| `GET /api/varieties` | 品种列表（搜索/筛选/排序/统计） |
| `GET /api/varieties/{symbol}` | 品种详情 |
| `GET /api/varieties/{symbol}/detail` | 品种详情含评论 |
| `POST /api/comments` | 发表评论，需要登录 |
| `GET /api/comments/user/{username}` | 用户评论历史 |
| `GET /api/realtime/{symbol}` | 实时行情单品种查询，带内存缓存 |
| `GET /api/realtime/batch` | 批量实时行情 |
| `GET /api/realtime/stream` | SSE 实时行情推送 |
| `GET /api/klines/{symbol}` | K 线数据，支持 `period` 和 `limit` |
| `GET /api/klines/{symbol}/continuous` | 连续 K 线 |
| `GET /api/klines/{symbol}/main` | 主力合约 K 线 |
| `GET /api/contracts/{contract_id}/kline` | 具体合约 K 线 |
| `GET /api/price-levels` | 云端支撑/阻力位标注 |
| `GET /api/contracts/rollovers` | 合约切换历史 |
| `GET /api/settings` / `PUT /api/settings` | 用户偏好设置 |
| `GET /api/news/sources` / `GET /api/news/articles` | 新闻源与文章 |
| `POST /api/log/frontend` | 前端日志与 Web Vitals 上报 |
| `POST /api/log/csp-report` | 匿名 CSP 违规报告；8 KiB、批量、采样、限流和脱敏边界 |
| `GET /health` / `/health/ready` / `/health/scheduler` | 存活、就绪、调度器状态 |

---

## 开发账号

非生产环境首次初始化会创建：

| 用户名 | 密码 |
|--------|------|
| `trader001` | `password123` |
| `investor_wang` | `password123` |
| `futures_master` | `password123` |

---

## 测试

后端使用 pytest（**请使用项目内独立 venv，不要使用全局 Anaconda 环境**）：

```powershell
cd D:\Code\project_rich_snowball\python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
$env:SECRET_KEY="test-secret-key"
$env:ENABLE_SCHEDULER="0"
.\.venv\Scripts\python.exe -m pytest tests -v
```

环境校验：
```powershell
.\.venv\Scripts\python.exe -c "import sqlalchemy; print(sqlalchemy.__version__)"
# 应输出 >= 2.0.25
```

重点测试文件：
- `test_p0_fixes.py`：安全、配置、登录、评论、缓存、健康检查回归
- `test_phase1_3_integration.py`：Schema、模型关系、新旧 API 兼容
- `test_cors_variable.py`：`CORS_ORIGINS` / `ALLOW_ORIGINS` 兼容
- `test_kline_seeded_api.py`：K 线 API 行为
- `test_comment_validation_and_pagination.py`：评论校验和分页
- `test_cache_orm_detached.py`：缓存避免 ORM detached session
- `test_postgres_upsert_integration.py`：PostgreSQL upsert 集成
- `test_production_config.py`：生产环境安全约束

R10 本地聚焦测试为 `375 passed, 5 skipped, 1 warning`，后端全量为
`1421 passed, 22 skipped, 103 warnings`。本地 PostgreSQL 不可用，R10/R9 PostgreSQL 集成
用例保持明确 skip。远端
[Backend CI run 30791923945（attempt 1）](https://github.com/jwj911/project_rich_snowball/actions/runs/30791923945)
已成功：R9/R10 gate `268 passed, 1 warning`；全量
`1442 passed, 1 skipped, 103 warnings`，coverage `77.38%`；Alembic、PostgreSQL API
smoke、Ruff check/format（122 files）和 `pip-audit` 均成功，且没有修复提交。

R9 独立审查修复前的历史后端全量为
`1177 passed, 18 skipped, 0 failed, 103 warnings`。修复后受影响聚焦回归为
`85 passed, 1 skipped, 0 failed`，Ruff check/format 通过；唯一 skip 是新增 PostgreSQL
CSP 持久化专项，本地无隔离 PostgreSQL。审查修复后的完整后端全量由
[Backend CI run 30739553595](https://github.com/jwj911/project_rich_snowball/actions/runs/30739553595)
复核，`R9 CSP contract gate 39 passed`，包含 PostgreSQL 持久化集成测试；完整后端测试约
`1195 passed, 1 skipped`。

前端已配置 Vitest + Playwright 自动化测试。R9 CSP 配置测试为 `21 passed`；全量 Vitest
为 `35 files / 223 passed`，TypeScript、ESLint 和 production build 通过，最大 First Load JS
为 `157 kB`；以上浏览器执行中，审查增强前的基础版 R9 Playwright 为 `3 passed`。增加并发
401 单飞刷新和 SSE 首次断线重连后，增强版已通过 Playwright `--list`、TypeScript 与
ESLint；增强版实际浏览器执行未计入本地结果，由远端 Frontend CI 验证。
`.github/workflows/frontend-ci.yml` 在 PR 时执行 lint、type-check、build、Vitest 和 Lighthouse
路由趋势 artifact，并由独立 job 执行 PostgreSQL、Alembic、backend 和 Chromium Playwright
smoke。[Frontend CI run 30740784839](https://github.com/jwj911/project_rich_snowball/actions/runs/30740784839)
已通过 Vitest、production build、R9 E2E `3 passed`、全量 Playwright `43 passed` 和
Lighthouse。
Backend CI 工作流已加入 R10 synthetic evidence 契约；
[run 30791923945（attempt 1）](https://github.com/jwj911/project_rich_snowball/actions/runs/30791923945)
已成功覆盖依赖锁、R7 placeholder preflight、Alembic、R8 K 线只读容量预检与影子分区
演练、R9/R10 CSP gate、PostgreSQL pytest/API smoke、Ruff 和 `pip-audit`，没有修复提交。
[Backend CI #38](https://github.com/jwj911/project_rich_snowball/actions/runs/30732688519)
仍是 R8 历史成功证据；R9 远端门禁以 run `30739553595` 和 `30740784839` 为准。R9
本地/CI 合成报告不是生产 SLO，也不能替代真实完整业务周期的 Report-Only 归类。R9 尚未
生产部署，S2 nonce/hash 强制 CSP 与 S3 内存 access token 均未启动；强制 CSP 未收紧，
`localStorage` token 风险未关闭。
修改前端后至少运行：

```powershell
cd D:\Code\project_rich_snowball\frontend
npx tsc --noEmit
npm run lint
npm run test
```

性能基线（Lighthouse）：

```powershell
cd D:\Code\project_rich_snowball\frontend
npm run build
npm start
# 另一终端
npm run lighthouse
```

Lighthouse 输出核心 Web Vitals（FCP、LCP、TBT、CLS、SI）到 `.lighthouse/latest.json`。
同时写入可按路由和提交聚合的 `.lighthouse/lighthouse-trend.json` 与
`.lighthouse/lighthouse-history.json`；CI artifact 保留 90 天。

---

## PostgreSQL 与历史数据

启动基础设施：

```powershell
cd D:\Code\project_rich_snowball
docker-compose up -d postgres redis
```

本仓库的 PostgreSQL 端口映射为 `15432:5432`。使用 PG 时常见连接串：

```env
DATABASE_URL=postgresql://futures:futures123@localhost:15432/futures_community
```

迁移：

```powershell
cd D:\Code\project_rich_snowball\python
alembic upgrade head
```

当前 Alembic head 为 `c0d1e2f3a4b5`，共 61 个迁移版本；其中
`fut_main_daily_data` 使用 `(variety_id, ts_code, period, trade_date)` 作为幂等唯一键，
`agent_market_panel_daily` 使用 `(data_view, variety_id, contract_id, period, trading_date)` 作为重建唯一键。

Tushare 历史回填脚本位于 `python/tushare_pg_ingest/`，包含日线、周/月线、结算、仓单、持仓、涨跌停、主力映射、周度统计等入口。详见 [python/tushare_pg_ingest/README.md](python/tushare_pg_ingest/README.md)。

---

## 常见注意事项

- `python/init_data.py` 已不是当前主流程的一部分，启动初始化在 `data_collector/init_mock_data.py` 和 `init_varieties.py`。
- `docker-compose.yml` 提供 backend + 独立 worker；backend 使用 `ENABLE_SCHEDULER=0`，worker 是生产环境唯一的 scheduler owner。
- worker 成功刷新 realtime quotes 后向 Redis 写入只含 UTC 时间戳的共享标记；API 使用本地/
  共享标记中的较新值驱动 SSE。Redis 不可用时按 60 秒有界周期刷新。
- SSE 连接注册、每用户旧连接取消和全局连接上限仍为实例内状态；生产只支持
  `single|sticky`，尚未实现 Pub/Sub 或跨实例连接管理。
- `DATA_SOURCE=auto` 或真实数据源初始化失败时，非生产环境会降级到 Mock；生产环境不允许降级 Mock。
- 数据管道与 PostgreSQL 配置详见 [docs/guides/DATA_PIPELINE_AND_POSTGRES_GUIDE.md](docs/guides/DATA_PIPELINE_AND_POSTGRES_GUIDE.md)。
- Tushare 验证指南详见 [docs/guides/TUSHARE_POSTGRES_VERIFICATION.md](docs/guides/TUSHARE_POSTGRES_VERIFICATION.md)。
- 后端 API 参考详见 [docs/guides/BACKEND_API_REFERENCE_FOR_FRONTEND.md](docs/guides/BACKEND_API_REFERENCE_FOR_FRONTEND.md)。
- 当前 Git 工作区可能包含 `.next`、`node_modules`、`venv` 等生成物变更，提交前需要谨慎筛选。
