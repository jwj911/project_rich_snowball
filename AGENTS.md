<!-- AGENTS.md — 期货交流社区 -->

> 本文档面向 AI 编程助手。进入本仓库后，先读这里，再动代码。
>
> **最后更新**：2026-06-04（含 Sprint 2 完成），基于 master 分支当前代码。

---

## Git 工作流约定

- **默认在 `master` 分支工作**。每次新对话开始时，先执行 `git branch` 确认当前分支。
- 如果当前不在 `master`，**立即提醒用户**，并在征得同意后切换到 `master`（切换前用 `git stash` 保存未提交修改）。
- 如有明确需求要在其他分支操作，按用户指令执行。
- 修改前后都要用 `git status --short` 观察，不要回滚无关改动。
- **分支陷阱**：`codex/new_fronted` 等历史分支曾执行 `git filter-branch`，部分文件（如 `tushare_pg_ingest/*.py`）在那些分支上被移除。需要这些文件时务必在 `master` 上操作。

---

## 项目概览

**期货交流社区**（产品名「倍增计划」）是一个前后端分离的期货行情与私密交流社区应用。当前产品形态为"登录后的行情工作台"：用户登录后查看热门期货、筛选品种、进入单品种 K 线复盘、添加云端支撑/阻力位标注、发表评论、记录交易观点、管理模拟持仓、设置价格预警、与 AI 助手对话，并在个人工作区汇总自己的研究上下文。

主要功能模块：
- 登录/注册/JWT 鉴权（支持 access token + refresh token 双令牌），主页面均有登录门禁
- 首页行情工作台：热门品种、领涨观察、30 秒轮询和刷新状态
- 行情中心：搜索、分类、涨跌筛选，按价格/涨跌幅/成交量排序
- 品种详情：实时行情、`lightweight-charts` K 线、技术分析、评论、支撑/阻力标注、合约切换（主力/连续/具体合约）
- 交易观点：用户针对品种发表多空观点，记录目标价、止损价和理由，支持事后复盘标记状态
- 模拟持仓：虚拟交易记录，支持做多/做空、盈亏计算与复盘统计
- 价格预警：用户为品种设置 above/below 价格预警，实时行情刷新时自动检测触发
- AI 助手：用户与大模型对话，自动检索实时行情和交易观点作为上下文
- 新闻资讯：RSS 源管理与聚合，支持 AI 新闻解读
- 我的工作区：评论历史、云端价位标注、自选观察入口
- 运营指标面板：`/metrics` 展示用户数/评论数/采集健康度
- 数据采集：Mock / AkShare / Tushare，多源 fallback + 熔断器，定时刷新实时行情和 K 线
- PostgreSQL 历史回填：`python/tushare_pg_ingest/` 下有独立脚本体系

---

## 技术栈

| 层级 | 技术 | 版本/说明 |
|------|------|-----------|
| 前端框架 | Next.js App Router | 14.2.35，`output: 'standalone'` |
| 前端 UI | React | 18.2.0，TypeScript 5.3.3 |
| 前端样式 | Tailwind CSS | 3.4.1，自定义暗色界面，上涨红色/下跌绿色 |
| 图标 | lucide-react | ^0.312.0 |
| K 线图 | lightweight-charts | ^5.2.0 |
| 数据获取 | SWR | ^2.4.1 |
| 消息提示 | sonner | ^2.0.7 |
| 前端测试 | Vitest + @testing-library/react + jsdom | Vitest 4.1.6，约 39 个测试文件 |
| E2E 测试 | Playwright | ^1.60.0，5 个文件（auth.setup.ts + 4 个 spec） |
| 性能基线 | Lighthouse | ^13.3.0，`npm run lighthouse` |
| 后端框架 | Python + FastAPI | Python >=3.11，FastAPI 0.136.3 |
| 后端服务器 | Uvicorn | 0.30.6 |
| ORM | SQLAlchemy | 2.0.25 |
| 数据库 | SQLite / PostgreSQL | SQLite 开发零配置；PG 16 通过 compose 提供，映射端口 15432 |
| 迁移 | Alembic | 1.13.1，当前共 45 个迁移文件 |
| 认证 | JWT + OAuth2 密码流 | PyJWT 2.13.0，passlib bcrypt，access token 默认 15 分钟，refresh token 默认 7 天 |
| 数据校验 | Pydantic v2 | 2.9.0 |
| 数据采集 | Mock / AkShare / Tushare | `DATA_SOURCE` 控制，非生产可降级 Mock |
| 定时任务 | APScheduler | BackgroundScheduler |
| 缓存 | Redis 优先 + 内存 LRU 降级 | `services/cache.py` 线程安全实现；Redis 可接入，内存作为降级 |
| 可观测性 | Prometheus 风格指标 + structlog 结构化日志 | `services/metrics.py` + `services/logging_config.py` |
| 限流 | 内存滑动窗口 | `middleware/rate_limit.py`，覆盖所有写入端点 |

---

## 真实端口与环境

- 后端 `python/main.py` 默认监听 `127.0.0.1:8200`，由 `HOST` / `PORT` 环境变量覆盖。
- 前端 `npm run dev` 实际执行 `next dev -H 127.0.0.1 -p 3200`。
- 前端 API 默认值在 `frontend/lib/api/transport.ts`：`NEXT_PUBLIC_API_BASE || http://127.0.0.1:8200`。
- CORS 默认允许 `localhost/127.0.0.1` 的 `3000` 和 `3200`。
- `docker-compose.yml` 中 PostgreSQL 映射为 `15432:5432`，不是 5432。
- Redis 映射为 `6379:6379`。

---

## 目录结构

```text
project_rich_snowball/
├── frontend/
│   ├── app/
│   │   ├── layout.tsx              # 根布局，包裹 AuthProvider + ErrorBoundary + WebVitalsReporter
│   │   ├── page.tsx                # 行情工作台，需登录
│   │   ├── products/page.tsx       # 行情中心，搜索/筛选/排序
│   │   ├── products/[id]/page.tsx  # 品种详情，K 线/评论/合约切换/标注/合约历史
│   │   ├── workspace/page.tsx      # 我的工作区
│   │   ├── my-comments/page.tsx    # 当前用户评论历史
│   │   ├── metrics/page.tsx        # 运营指标面板
│   │   ├── news/page.tsx           # 新闻资讯
│   │   ├── settings/page.tsx       # 个人设置
│   │   ├── chat/page.tsx           # AI 助手对话
│   │   ├── portfolio/page.tsx      # 模拟持仓
│   │   ├── opinions/page.tsx       # 交易观点
│   │   └── globals.css
│   ├── components/
│   │   ├── auth/                   # AuthProvider、LoginModal、RegisterModal、LoginRequired
│   │   ├── layout/AppShell.tsx     # 全局应用壳，左侧导航偏移
│   │   ├── market/                 # QuoteCard/Table、PriceChange、PriceFlash、TechnicalAnalysisPanel
│   │   ├── product/                # ProductHeader、ContractSelector 等
│   │   ├── kline/                  # KlineChart、KlineSection、KlinePieces
│   │   ├── activity/               # RefreshStatus、RealtimeStatusBar 等状态组件
│   │   ├── ui/                     # Button/Input/EmptyState/ErrorState/Dialog/Toast
│   │   ├── workspace/              # 工作区摘要、标注、评论时间线、自选面板
│   │   ├── opinion/                # 观点卡片、创建/编辑表单
│   │   ├── metrics/                # 运营指标图表
│   │   └── Navbar.tsx
│   ├── hooks/                      # 16 个自定义 hook
│   │   ├── useMarketPolling.ts     # 轮询和 heartbeat 状态
│   │   ├── usePriceLevels.ts       # 价位标注后端同步与 localStorage 降级
│   │   ├── useRealtimeQuotes.ts    # 实时行情 hook
│   │   ├── useProductDetail.ts     # 品种详情数据获取
│   │   ├── useProductKline.ts      # K 线数据获取
│   │   ├── useWatchlistRealtime.ts # 自选实时监听
│   │   ├── useDebouncedValue.ts    # 通用防抖（搜索输入等）
│   │   └── ...
│   ├── lib/
│   │   ├── api/                    # 模块化 API 客户端
│   │   │   ├── client.ts           # ApiService 统一入口
│   │   │   ├── transport.ts        # RequestCore 底层 fetch + token 管理
│   │   │   ├── auth.ts             # AuthCore 登录/注册/token 刷新
│   │   │   ├── market.ts           # 行情/K线/合约 API
│   │   │   ├── workspace.ts        # 工作区/标注/自选 API
│   │   │   ├── products.ts         # 品种/评论 API
│   │   │   ├── portfolio.ts        # 模拟持仓 API
│   │   │   ├── price_alerts.ts     # 价格预警 API
│   │   │   ├── opinions.ts         # 交易观点 API
│   │   │   ├── chat.ts             # AI 助手 API
│   │   │   ├── news.ts             # 新闻 API
│   │   │   ├── settings.ts         # 设置 API
│   │   │   ├── metrics.ts          # 运营指标 API
│   │   │   ├── logging.ts          # 前端日志上报
│   │   │   ├── types.ts            # 共享类型定义
│   │   │   └── errors.ts           # API 错误类型
│   │   ├── format.ts               # 价格/日期格式化（含 formatPricePayload）
│   │   ├── vitals.ts               # Web Vitals 上报
│   │   ├── sentry-lite.ts          # 轻量异常捕获，同时上报后端
│   │   ├── swr-hooks.ts            # SWR 封装 hook（含 useMarketStatus）
│   │   └── realtimeStore.ts        # SSE 实时行情状态管理
│   ├── tests/                      # Vitest 单元测试（约 39 个文件）
│   │   ├── setup.ts
│   │   ├── components/             # 组件测试
│   │   ├── hooks/                  # Hook 测试
│   │   └── lib/                    # 工具函数测试
│   └── e2e/                        # Playwright E2E 测试
│       ├── auth.setup.ts           # 登录态复用
│       ├── auth.spec.ts            # 认证流程
│       ├── market.spec.ts          # 行情页面
│       ├── product-detail.spec.ts  # 品种详情
│       └── performance.spec.ts     # 性能断言（已迁移到 Lighthouse）
│
├── python/
│   ├── main.py                     # FastAPI 入口、lifespan、CORS、异常处理、Prometheus 中间件
│   ├── config.py                   # .env 加载、SECRET_KEY/生产环境校验、所有环境变量默认值
│   ├── models.py                   # SQLAlchemy 模型，28 张表
│   ├── schemas.py                  # Pydantic v2，请求/响应模型和 XSS 过滤
│   ├── dependencies.py             # get_db、JWT 用户解析（含 CSRF 防护）
│   ├── utils.py                    # bcrypt、JWT encode/decode
│   ├── worker.py                   # 独立 scheduler 入口，不启动 FastAPI
│   ├── routers/                    # 19 个领域路由
│   │   ├── auth.py
│   │   ├── chat.py
│   │   ├── comments.py
│   │   ├── contracts.py
│   │   ├── frontend_logs.py
│   │   ├── health.py
│   │   ├── kline.py
│   │   ├── market.py
│   │   ├── metrics_dashboard.py
│   │   ├── news.py
│   │   ├── opinions.py
│   │   ├── portfolio.py
│   │   ├── price_alerts.py
│   │   ├── price_levels.py
│   │   ├── realtime.py
│   │   ├── settings.py
│   │   ├── varieties.py
│   │   ├── watchlists.py
│   │   └── workspace.py
│   ├── data_collector/             # 在线采集、清洗、upsert、调度器
│   │   ├── scheduler.py
│   │   ├── pipeline.py
│   │   ├── pipeline_tasks/         # Tushare 批量任务拆分
│   │   ├── collectors/             # mock、akshare、tushare
│   │   ├── adapters/
│   │   ├── cleaners/
│   │   ├── upsert.py               # 兼容 SQLite/PostgreSQL 双方言
│   │   ├── init_mock_data.py
│   │   └── init_varieties.py
│   ├── services/
│   │   ├── cache.py                # 线程安全内存 LRU
│   │   ├── circuit_breaker.py      # 数据源熔断器
│   │   ├── continuous_kline.py     # 主力连续 K 线拼接
│   │   ├── metrics.py              # Prometheus 指标
│   │   ├── logging_config.py       # structlog 结构化日志配置
│   │   ├── trading_calendar.py     # 交易日历
│   │   ├── ai_chat.py              # AI 助手 OpenAI 兼容调用
│   │   ├── news_fetcher.py         # RSS 新闻抓取与 AI 解读
│   │   ├── domain/                 # 领域服务层
│   │   │   ├── repositories/       # 数据访问层
│   │   │   ├── comment_service.py
│   │   │   ├── price_level_service.py
│   │   │   ├── watchlist_service.py
│   │   │   ├── workspace_service.py
│   │   │   └── exceptions.py       # ServiceError 体系
│   │   └── ...
│   ├── middleware/
│   │   └── rate_limit.py           # 限流中间件
│   ├── tushare_pg_ingest/          # 独立历史数据回填脚本
│   ├── scripts/                    # 一次性采集/验证/回填脚本
│   ├── tests/                      # pytest 测试（41 个测试文件）
│   └── alembic/versions/           # 45 个迁移脚本
│
├── docker-compose.yml              # PostgreSQL 16 + Redis 7，backend 服务已注释
├── Dockerfile                      # python:3.11-slim，非 root 用户
├── .env.example                    # 环境变量模板
├── pyproject.toml                  # Ruff + mypy 配置
├── README.md                       # 面向人类的快速开始
└── ...                             # 审计/评审文档
```

---

## 前端开发规则

- 页面和组件目前全部按 Client Component 写法组织，保持 `'use client'` 与 Hooks 风格一致。
- API 调用统一通过 `frontend/lib/api/client.ts` 的 `api` 实例，不要在页面里散落裸 `fetch`。
- 行情轮询优先使用 `useMarketPolling`，默认 30 秒。
- 色彩语义遵循中国市场惯例：上涨红色，下跌绿色。
- `KlineChart.tsx` 已使用 `lightweight-charts` v5.2.0，不要再按旧文档理解为自研 SVG 蜡烛图。
- 支撑/阻力位已同步后端：`price_levels` 表存储（含 `scope` 和 `contract_id`，支持 continuous/main/contract 三种口径隔离），通过 `/api/price-levels` CRUD；`frontend/hooks/usePriceLevels.ts` 封装了后端同步逻辑，按 K 线 source 隔离，本地存储作为降级/缓存方案保留（key 格式 `price-levels:v2:{userId}:{symbol}:{scope}:{contractId}`）。
- 主页面登录门禁来自 `AuthProvider` 和 `LoginRequired`。新增需要保护的页面时沿用该模式。
- 修改前端后至少运行 `npx tsc --noEmit`；如涉及样式或路由，也运行 `npm run lint`，必要时用浏览器查看 `127.0.0.1:3200`。
- 前端已配置 Vitest + Playwright + `.github/workflows/frontend-ci.yml`（lint + build + test + Lighthouse），但 `npm run test` 在 Windows 上可能因路径解析问题偶发失败（`/@fs/D:/...` 映射已知问题）。

---

## 后端开发规则

- 导入顺序：标准库 → 第三方库 → 本项目模块。
- 数据库会话统一使用 `dependencies.get_db()`，避免手动创建 `SessionLocal()` 后忘记关闭。
- 路由按领域拆分为 `APIRouter`，在 `main.py` 统一挂载。
- **ProductDB 已完全退场**（2026-05-28）：物理表已删除，`comments.product_id` 列已删除，所有前后端代码、测试、schema 已清理。品种数据统一走 `VarietyDB` / `RealtimeQuoteDB` / `KlineDataDB` + `/api/varieties`、`/api/realtime`、`/api/klines`。
- **CSRF 防护**（2026-05-29）：`dependencies.py` 方法感知鉴权，POST/PUT/PATCH/DELETE 只接受 `Authorization: Bearer` header，GET/HEAD 保持 cookie 兼容。
- 数据采集遵循 `collector -> adapter -> cleaner -> pipeline -> upsert`。
- upsert 逻辑在 `data_collector/upsert.py`，已兼容 SQLite / PostgreSQL 双方言。
- 密码必须用 `utils.hash_password()`，禁止明文、MD5、SHA256。
- JWT 解码捕获 PyJWT 异常，不要裸 `except:`。
- 评论内容通过 Pydantic validator 和 `html.escape()` 做 XSS 过滤，长度限制在 schema 中维护。
- 生产环境约束在 `config.py`：必须设置强 `SECRET_KEY`（>=32 字符），且不允许 SQLite。
- 全局限流中间件覆盖所有写入端点（POST/PUT/PATCH/DELETE），默认 60 秒窗口内 100 请求。
- 每个请求都有 `X-Request-ID`，通过 `request_id_middleware` 注入，structlog 上下文自动绑定。
- Prometheus 指标通过 `prometheus_middleware` 自动收集，排除 `/metrics`、`/docs`、`/redoc`、`/openapi.json`。

---

## 数据采集与调度

`data_collector/scheduler.py` 使用延迟初始化 collector，避免导入期就因外部数据源失败导致应用不可启动。

调度任务要点：
- 实时行情：每 60 秒（可通过 `REALTIME_REFRESH_INTERVAL_SECONDS` 调整）
- 兼容层产品价格同步：每 60 秒
- 日 K：每日 16:05
- 分钟 K：每 15 分钟，走 AkShare 分钟线 pipeline
- 品种元数据：每日 02:00
- Tushare 扩展任务：日线、结算、仓单、持仓、涨跌停、周报等，仅在 Tushare pipeline 可用时注册
- 价格预警检测：`refresh_realtime_quotes` 成功后遍历未触发预警与 `RealtimeQuoteDB.current_price` 比较

`DATA_SOURCE`：
- `mock`：开发默认
- `akshare`：真实行情源之一
- `tushare`：需要 `TUSHARE_TOKEN`
- `auto`：尝试真实源 fallback

非生产环境所有真实 collector 失败时可以降级 Mock；生产环境不允许降级 Mock。

数据源熔断器（`services/circuit_breaker.py`）：连续失败 5 次后冷却 10 分钟。

---

## PostgreSQL 与历史回填

基础设施：

```powershell
docker-compose up -d postgres redis
```

PostgreSQL 连接串：

```env
DATABASE_URL=postgresql://futures:futures123@localhost:15432/futures_community
```

迁移：

```powershell
cd python
alembic upgrade head
```

`python/tushare_pg_ingest/` 是独立于应用启动流程的历史数据回填工具。常用脚本包括：
- `ingest_daily.py`：日线/周线/月线，写入 `fut_daily_data`
- `ingest_settle.py`：结算参数
- `ingest_wsr.py`：仓单日报
- `ingest_holding.py`：持仓排名
- `ingest_price_limit.py`：涨跌停价格
- `ingest_mapping.py`：主力映射，更新 `varieties.contract_code`
- `ingest_weekly_detail.py`：周度交易统计
- `ingest_all.py`：保守总入口
- `ingest_commission_9qihuo.py`：九期网/AKShare 手续费与保证金

运行前阅读 `python/tushare_pg_ingest/README.md`。

---

## 构建与运行命令

后端：

```powershell
cd python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
$env:SECRET_KEY="change-this-to-a-real-secret"
.\.venv\Scripts\python.exe main.py
```

独立 worker（不启动 FastAPI，只跑 scheduler）：

```powershell
cd python
python worker.py
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

类型检查与构建：

```powershell
cd frontend
npx tsc --noEmit
npm run lint
npm run build
```

前端测试：

```powershell
cd frontend
npm run test        # Vitest 单元测试
npx playwright test # E2E 测试
```

性能基线：

```powershell
cd frontend
npm run build
npm start
# 另一终端
npm run lighthouse
```

后端测试（**请使用项目内独立 venv，不要使用全局 Anaconda 环境**）：

```powershell
cd python
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

Ruff 格式化与检查：

```powershell
cd python
ruff check .
ruff format .
```

---

## 测试现状

后端已有 pytest（41 个测试文件）：
- `test_p0_fixes.py`
- `test_phase1_3_integration.py`
- `test_cors_variable.py`
- `test_kline_seeded_api.py`
- `test_comment_validation_and_pagination.py`
- `test_cache_orm_detached.py`
- `test_postgres_upsert_integration.py`
- `test_production_config.py`
- `test_watchlists.py`
- `test_price_levels.py`
- `test_workspace.py`
- `test_workspace_api.py`
- `test_contracts.py`
- `test_pipeline_rollover.py`
- `test_circuit_breaker.py`
- `test_scheduler_health.py`
- `test_realtime_batch.py`
- `test_realtime_sse.py`
- `test_backfill_kline_contract_id.py`
- `test_data_quality.py`
- `test_metrics.py`
- `test_ondelete_cascade.py`
- `test_products_query.py`
- `test_rate_limit_middleware.py`
- `test_refresh_token.py`
- `test_trading_date.py`
- `test_csrf_protection.py`
- `test_frontend_logs.py`
- `test_frontend_logs_query.py`
- `test_metrics_dashboard.py`
- `test_varieties_enhanced.py`
- `test_service_error_handler.py`
- `test_settings.py`
- `test_news.py`
- `test_opinions.py`
- `test_chat.py`
- `test_portfolio.py`
- `test_price_alerts.py`
- `test_password_strength.py`

前端测试：
- Vitest 单元测试：`frontend/tests/` 下约 39 个测试文件
- Playwright E2E：`frontend/e2e/` 下 5 个文件（auth.setup.ts + 4 个 spec）
- Lighthouse 性能基线：`npm run lighthouse` 测量首页未登录态 Web Vitals（FCP/LCP/TBT/CLS/SI），报告输出到 `.lighthouse/latest.json`
- 注意：`npm run test` 在 Windows 上可能因 Vitest 路径解析问题偶发失败（已知问题，见 `FRONTEND_QUALITY_AUDIT_V3_20260525.md`）

---

## 关键环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `SECRET_KEY` | 是 | — | JWT 签名密钥，生产环境长度至少 32 |
| `DATABASE_URL` | 否 | `sqlite:///./futures_community.db` | 数据库连接串 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 否 | `15` | Access token 过期时间（分钟） |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 否 | `7` | Refresh token 过期时间（天） |
| `CORS_ORIGINS` | 生产建议必填 | `localhost/127.0.0.1:3000,3200` | CORS 白名单，兼容旧变量 `ALLOW_ORIGINS` |
| `DATA_SOURCE` | 否 | `mock` | `mock` / `akshare` / `tushare` / `auto` |
| `TUSHARE_TOKEN` | Tushare 必填 | — | Tushare Pro Token |
| `ENABLE_SCHEDULER` | 否 | `0` | `1` 启用，`0` 禁用（API 默认禁用） |
| `ENV` | 否 | `development` | `development` / `production` |
| `HOST` | 否 | `127.0.0.1` | 后端监听地址 |
| `PORT` | 否 | `8200` | 后端监听端口 |
| `REALTIME_REFRESH_INTERVAL_SECONDS` | 否 | `60` | 实时行情刷新间隔（秒） |
| `CACHE_MAX_SIZE` | 否 | `1024` | 内存缓存最大条目数 |
| `CACHE_DEFAULT_TTL_SECONDS` | 否 | `5` | 内存缓存默认 TTL（秒） |
| `RATE_LIMIT_WINDOW_SECONDS` | 否 | `60` | 限流时间窗口（秒） |
| `RATE_LIMIT_MAX_REQUESTS` | 否 | `100` | 限流窗口内最大请求数 |
| `PIPELINE_COMMIT_BATCH_SIZE` | 否 | `50` | Pipeline 批量提交大小 |
| `CIRCUIT_FAILURE_THRESHOLD` | 否 | `0.5` | 熔断器失败阈值比例 |
| `NEXT_PUBLIC_API_BASE` | 前端可选 | `http://127.0.0.1:8200` | 前端请求后端地址 |
| `OPENAI_API_KEY` | AI 可选 | — | OpenAI 兼容 API Key |
| `OPENAI_BASE_URL` | AI 可选 | `https://api.openai.com/v1` | OpenAI 兼容 Base URL |
| `OPENAI_MODEL` | AI 可选 | `gpt-4o-mini` | 对话模型 |
| `CHAT_MAX_HISTORY` | AI 可选 | `20` | 最大对话历史条数 |

---

## 开发账号

非生产环境首次初始化会创建：

| 用户名 | 密码 |
|--------|------|
| `trader001` | `password123` |
| `investor_wang` | `password123` |
| `futures_master` | `password123` |

---

## 常见陷阱

- 导入任何依赖 `config.py` 的模块前必须有 `SECRET_KEY`，测试中通常用环境变量设置。
- README 旧说法里的 `python/init_data.py` 已过时，主流程使用 `data_collector/init_mock_data.py`。
- 前端端口不是默认 3000，而是 `127.0.0.1:3200`。
- 后端端口不是 8000，而是 `127.0.0.1:8200`，除非 `HOST` / `PORT` 覆盖。
- `docker-compose.yml` 的 PostgreSQL 暴露端口是 15432。
- Redis 服务可以启动，缓存层已实现 Redis 优先 + 内存 LRU 降级。
- `node_modules`、`.next`、`venv`、数据库文件和日志可能在工作区中产生大量噪声，提交时不要顺手纳入。
- 当前仓库可能已有用户或其他助手留下的未提交变更，修改前后都要用 `git status --short` 观察，不要回滚无关改动。
- Windows 上 `python/main.py` 已 patch `asyncio.proactor_events._ProactorBasePipeTransport._call_connection_lost` 以抑制无害的 `ConnectionResetError 10054` 噪音，不要移除此 patch。

---

## CI/CD 与容器化

- **GitHub Actions**：
  - `.github/workflows/backend-ci.yml`：pytest + ruff + pip-audit，使用 `requirements.lock`，Python 3.12
  - `.github/workflows/frontend-ci.yml`：`npm ci` → `tsc --noEmit` → `npm run lint` → `npm run build` → `npm run test` → Lighthouse 基线
  - `.github/workflows/update-calendar.yml`：每年 1 月 1 日自动更新交易日历（cron），也支持手动触发

- **Dockerfile**：`python/Dockerfile`
  - 基于 `python:3.11-slim`
  - 创建非 root 用户 `app`
  - 健康检查：`curl -f http://localhost:8200/health || exit 1`
  - 默认 CMD 为 `uvicorn main:app --host 0.0.0.0 --port 8200`
  - 生产建议使用 gunicorn + uvicorn worker

- **docker-compose.yml**：
  - `postgres`：PostgreSQL 16-alpine，端口 15432，用户 `futures`/`futures123`
  - `redis`：Redis 7-alpine，端口 6379，AOF 持久化
  - `backend`：**已注释掉**，尚未在 compose 中启用

---

## 代码风格

- **Python**：Ruff（line-length 120，target py311）
  - 启用规则：E, W, F, I, N, UP, B, C4, SIM
  - 忽略：E501（由 line-length 控制）
  - Docstring 风格：Google
  - 格式化：双引号字符串，空格缩进
  - mypy：py311，但排除了 `data_collector/`、`routers/`、`models.py`、`tests/`、`alembic/` 等目录（SQLAlchemy 1.x 类型误报兼容策略）

- **前端**：ESLint（`next/core-web-vitals`），无 Prettier 配置
  - Tailwind 自定义颜色：`up`（红色系）、`down`（绿色系）反映中国市场惯例
  - Bundle Budget 红线：任意路由 First Load JS 不得超过 180 kB（见 `next.config.js` 注释）

---

## 安全注意事项

- **生产环境强制要求**：
  - `SECRET_KEY` 长度 >= 32
  - 必须使用 PostgreSQL（禁止 SQLite）
  - `CORS_ORIGINS` 必填，禁止 `*`、禁止 `http://`、禁止 localhost/127.0.0.1
- **密码**：必须使用 `utils.hash_password()`（bcrypt），禁止明文、MD5、SHA256。
- **XSS**：评论内容通过 Pydantic validator + `html.escape()` 过滤，长度限制在 schema 中维护。
- **JWT**：解码必须捕获 PyJWT 异常，禁止裸 `except:`。
- **CORS**：`allow_credentials=True`，因此生产环境不允许通配符 origin。
- **CSP**：前端有 Content-Security-Policy 响应头，但当前允许 `unsafe-eval` 和 `unsafe-inline`（为兼容 lightweight-charts 和 Next.js）。
- **CSRF 防护**（2026-05-29）：`dependencies.py` 方法感知鉴权，POST/PUT/PATCH/DELETE 必须携带 `Authorization: Bearer` header，不接受 `access_token` cookie 回退；GET/HEAD 保持兼容。
- **Metrics**：`/metrics` 端点限制为可信内网 IP，外网返回 403。

---

## 主要模块演进状态

### Phase 1~3：用户工作区、合约 K 线、生产边界 — 已完成

- `price_levels` / `watchlists` / `workspace` 云端同步闭环
- `contract_rollovers` + 连续 K 线拼接 + 合约切换
- 独立 worker、`ENABLE_SCHEDULER=0` 默认、数据源熔断、数据质量检查

### Phase 4：ProductDB 全面退场 — 已完成（2026-05-28）

- 删除 `products` 物理表及所有废弃代码，品种数据统一走 `VarietyDB`
- pytest 全部通过

### 前端监控闭环 — 已完成（2026-06-01）

- 后端：`POST /api/log/frontend` + `FrontendLogDB` + Alembic 迁移
- `sentry-lite.ts` + `lib/vitals.ts`：无论 Sentry 是否启用，总是同时发送到后端日志端点
- 后端 `GET /api/log/frontend` 支持 admin 查询全部 / 普通用户查询自己的日志

### CSRF 防护 — 已完成（2026-05-29）

- 后端 `dependencies.py` 方法感知鉴权
- `test_csrf_protection.py` 10 个测试覆盖写接口拒绝/读接口兼容

### SSE 鉴权统一 — 已完成（2026-05-29）

- 方案 B：废弃 stream-token，SSE 鉴权统一走 cookie-only 路径
- `/api/realtime/stream-token` endpoint 标记 `deprecated=True`

### 交易时段 badge 后端权威化 — 已完成（2026-05-29）

- `useMarketStatus()` SWR hook 统一消费 `/api/market/status`
- `MarketSessionBadge` 和 `MarketClosedBanner` 共用同一份后端状态

### 价位标注 batch scope/contract 补齐 — 已完成（2026-05-29）

- `PriceLevelBatchItem` schema 与单条在 scope/contract_id 语义上完全一致
- 重复检测 key 扩展为 `(variety_id, type, price, scope, contract_id)`

### Lighthouse 性能基线 — 已完成（2026-05-29）

- `scripts/lighthouse-baseline.js`：headless Chrome 测量首页未登录态性能
- 报告保存到 `.lighthouse/latest.json`
- `frontend-ci.yml` 集成 Lighthouse，build 后自动跑基线

### 标注价格精度统一 — 已完成（2026-05-29）

- `formatPricePayload(price, precision)` 专用于 API payload 格式化
- `usePriceLevels` 创建/迁移标注时使用 `formatPricePayload()` 替代 `toFixed(2)`

### SSE URL 截断 — 已完成（2026-05-29）

- `frontend/lib/realtimeStore.ts`：`buildSseUrl` 当 symbol 数量 >30 时省略 `symbols` 参数
- 后端 `symbols` 为空时自动订阅全部活跃品种

### 精度中立化 — 已完成（2026-05-29）

- K 线价格显示统一使用 `formatPrice`，支持品种级别 `price_precision` 配置
- `CrosshairTooltip`、`KlineChartHeader`、`PriceChange` 等组件接入精度配置

### AI Chat（期货助手）— 已完成（2026-06-01）

**后端**
- `ChatMessageDB` 模型 + Alembic 迁移
- Router `/api/chat`：历史记录查询 + 发送消息 + 清空对话
- AI 服务 `services/ai_chat.py`：OpenAI 兼容 API，自动检索 `RealtimeQuoteDB` + `OpinionDB` 作为上下文
- 未配置时返回友好提示（不阻断应用启动）

**前端**
- `/chat` 页面：ChatGPT 风格对话界面
- 导航：`secondaryNavGroups` 新增「AI 助手」

### Portfolio（模拟持仓）— 已完成（2026-06-01）

**后端**
- `TradeRecordDB` 模型 + Alembic 迁移
- Router `/api/portfolio`：列表（含实时浮动盈亏）+ 创建 + 平仓 + 删除
- 盈亏公式：`long: (exit - entry) * qty * multiplier`，`short: (entry - exit) * qty * multiplier`

**前端**
- `/portfolio` 页面：盈亏统计面板 + 交易卡片列表
- 导航：`secondaryNavGroups` 新增「模拟持仓」

### Price Alert（价格预警）— 已完成（2026-06-01）

**后端**
- `PriceAlertDB` 模型 + Alembic 迁移
- Router `/api/price-alerts`：CRUD + 触发查询
- Scheduler 集成：`refresh_realtime_quotes` 成功后调用 `_check_price_alerts()`

**前端**
- API 层：`lib/api/price_alerts.ts`
- 品种详情页 `PriceAlertPanel`：表单 + 列表 + 删除

### Opinions（交易观点/日记）— 已完成（2026-05-30）

**后端**
- `opinions` 表 + 生命周期字段（`status/closed_at/actual_outcome`）
- Router `/api/opinions`：公开列表 + 个人时间线 + CRUD

**前端**
- `/opinions` 页面：双标签页「全部观点」+「我的观点」
- 筛选：品种、方向、状态

### News（新闻资讯）— 已完成（2026-05-30）

**后端**
- `NewsSourceDB` / `NewsArticleDB` 模型
- RSS 抓取 + AI 摘要（`services/news_fetcher.py`）
- Router `/api/news`：源管理 + 文章列表 + 单篇摘要

**前端**
- `/news` 页面：来源筛选 + 标题搜索 + AI 解读

### 前端 Sprint 2：体验优化 — 已完成（2026-06-04）

- **搜索防抖**（P2-1）：新建 `useDebouncedValue.ts`，products 和 news 页面搜索输入防抖 250ms，消除请求洪峰和 UI 闪烁
- **Token 安全评估**（P2-2）：选择方案 C（保守），新建 `frontend/docs/SECURITY_RISKS.md` 记录 RISK-001（access token 存 localStorage）及后续行动项
- **实时行情 Store 语义清晰化**（P2-3）：`realtimeStore.ts` 的 `notifyAll` 同时提供 `snapshot`（全量）和 `delta`（增量），`useRealtimeQuotes.ts` 明确区分增量合并与全量替换场景
- **Lighthouse 端口基线修复**（P2-4）：`.lighthouse/latest.json` url 修正为 `http://127.0.0.1:3200`，与 `npm run dev` 实际端口一致
- **验证**：`npx tsc --noEmit` 通过，`npm run lint` 通过，`useDebouncedValue.test.ts` 5 个测试通过
