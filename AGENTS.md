<!-- AGENTS.md — 期货交流社区 -->

> 本文档面向 AI 编程助手。进入本仓库后，先读这里，再动代码。
>
> **最后更新**：2026-06-24（基于 master 分支当前代码校验重写）

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

**当前阶段**：Phase 5「CI/运维与架构优化」已完成（2026-06-05）。后端架构审计 v7 评级 **B-**（无 P0 阻塞项，6 个 P1、10 个 P2）；前端 Roadmap v8 目标评级 **A-**，已按 Sprint 2/3 完成体验优化与架构清理。

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
| 表单 | react-hook-form | ^7.76.0 |
| 消息提示 | sonner | ^2.0.7 |
| 性能采集 | web-vitals | ^5.2.0 |
| 前端测试 | Vitest + @testing-library/react + jsdom | Vitest ^4.1.6，33 个测试文件 |
| E2E 测试 | Playwright | ^1.60.0，7 个文件（auth.setup.ts + 6 个 spec） |
| 性能基线 | Lighthouse | ^13.3.0，`npm run lighthouse` |
| 后端框架 | Python + FastAPI | Python >=3.11，FastAPI 0.136.3 |
| 后端服务器 | Uvicorn | 0.30.6 |
| ORM | SQLAlchemy | 2.0.25 |
| 数据库 | SQLite / PostgreSQL | SQLite 开发零配置；PG 16 通过 compose 提供，映射端口 15432 |
| 迁移 | Alembic | 1.13.1，当前 46 个迁移文件 |
| 认证 | JWT + OAuth2 密码流 | PyJWT 2.13.0，passlib bcrypt，access token 默认 15 分钟，refresh token 默认 7 天 |
| 数据校验 | Pydantic v2 | 2.9.0 |
| 数据采集 | Mock / AkShare / Tushare | `DATA_SOURCE` 控制，非生产可降级 Mock |
| 定时任务 | APScheduler | BackgroundScheduler |
| 缓存 | Redis 优先 + 内存 LRU 降级 | `services/cache.py` 线程安全实现；Redis 可接入，内存作为降级 |
| 可观测性 | Prometheus 风格指标 + structlog 结构化日志 | `services/metrics.py` + `services/logging_config.py` |
| 限流 | 内存/Redis 滑动窗口 | `middleware/rate_limit.py`，覆盖所有写入端点 |

---

## 真实端口与环境

- 后端 `python/main.py` 默认监听 `127.0.0.1:8401`，由 `HOST` / `PORT` 环境变量覆盖。
- 前端 `npm run dev` 实际执行 `next dev -H 127.0.0.1 -p 3200`。
- 前端 API 默认值在 `frontend/lib/api/request.ts`：`NEXT_PUBLIC_API_BASE || http://127.0.0.1:8401`。
- CORS 默认允许 `localhost/127.0.0.1` 的 `3000` 和 `3200`。
- `docker-compose.yml` 中 PostgreSQL 映射为 `15432:5432`，不是 5432。
- Redis 映射为 `6379:6379`。

---

## 目录结构

```text
project_rich_snowball/
├── frontend/
│   ├── app/                        # 11 个页面路由
│   │   ├── layout.tsx              # 根布局，包裹 AuthProvider + ErrorBoundary + WebVitalsReporter + Toaster
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
│   │   ├── error.tsx / global-error.tsx / not-found.tsx
│   │   └── globals.css
│   ├── components/                 # 50+ 个组件文件
│   │   ├── auth/                   # AuthProvider、LoginModal、RegisterModal、LoginRequired
│   │   ├── layout/AppShell.tsx     # 全局应用壳，左侧导航偏移
│   │   ├── market/                 # QuoteCard/Table、PriceChange、PriceFlash、TechnicalAnalysisPanel
│   │   ├── product/                # ProductHeader、ContractSelector、KlineSection、LevelEditor 等
│   │   ├── kline/                  # KlineChart、KlineChartHeader、CrosshairTooltip、LevelChips、AnnotationContextMenu
│   │   ├── activity/               # RefreshStatus、RealtimeStatusBar、MarketClosedBanner、MarketSessionBadge
│   │   ├── ui/                     # Button/Input/EmptyState/ErrorState/Dialog/Toast/MetricCard
│   │   ├── workspace/              # 工作区摘要、标注、评论时间线、自选面板
│   │   ├── opinion/                # 观点卡片、创建/编辑表单
│   │   ├── metrics/                # 运营指标图表
│   │   ├── Navbar.tsx / ErrorBoundary.tsx / WebVitalsReporter.tsx / DynamicToaster.tsx
│   │   └── ...
│   ├── hooks/                      # 15+ 个自定义 hook
│   │   ├── useMarketPolling.ts     # 轮询和 heartbeat 状态
│   │   ├── usePriceLevels.ts       # 价位标注后端同步与 localStorage 降级
│   │   ├── useRealtimeQuotes.ts    # 实时行情 hook（SSE 优先，HTTP 轮询降级）
│   │   ├── useProductDetail.ts     # 品种详情数据获取
│   │   ├── useProductKline.ts      # K 线数据获取
│   │   ├── useProductListRealtime.ts # 品种列表实时监听
│   │   ├── useProductPolling.ts    # 品种轮询
│   │   ├── useWatchlistRealtime.ts # 自选实时监听
│   │   ├── useDebouncedValue.ts    # 通用防抖（搜索输入等）
│   │   ├── useKlineChart.ts        # K 线图表交互
│   │   ├── useKlinePriceLines.ts   # K 线价格线管理
│   │   ├── usePriceLines.ts        # 价格线通用 hook
│   │   ├── useAnnotationMenu.ts    # 标注菜单交互
│   │   ├── useMediaQuery.ts        # 响应式断点
│   │   ├── usePreferences.ts       # 用户偏好设置
│   │   └── ...
│   ├── lib/
│   │   ├── api/                    # 模块化 API 客户端
│   │   │   ├── client.ts           # ApiService 统一入口
│   │   │   ├── transport.ts        # RequestCore 底层 fetch + token 管理
│   │   │   ├── request.ts          # 请求封装与拦截
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
│   │   │   ├── errors.ts           # API 错误类型
│   │   │   └── index.ts            # API 模块统一导出
│   │   ├── format.ts               # 价格/日期格式化（含 formatPricePayload）
│   │   ├── indicators.ts           # 技术指标计算
│   │   ├── kline.ts / klineChart.ts / klineData.ts
│   │   ├── vitals.ts               # Web Vitals 上报
│   │   ├── sentry-lite.ts          # 轻量异常捕获，同时上报后端
│   │   ├── swr-hooks.ts            # SWR 封装 hook（含 useMarketStatus）
│   │   ├── realtimeStore.ts        # SSE 实时行情状态管理
│   │   ├── trading-calendar.ts / trading-hours.ts
│   │   └── constants.ts
│   ├── tests/                      # Vitest 单元测试（33 个测试文件）
│   │   ├── setup.ts
│   │   ├── app/                    # 页面测试
│   │   ├── components/             # 组件测试
│   │   ├── hooks/                  # Hook 测试
│   │   └── lib/                    # 工具函数测试
│   ├── e2e/                        # Playwright E2E 测试
│   │   ├── auth.setup.ts           # 登录态复用
│   │   ├── auth.spec.ts            # 认证流程
│   │   ├── market.spec.ts          # 行情页面
│   │   ├── product-detail.spec.ts  # 品种详情
│   │   ├── metrics.spec.ts         # 运营指标面板
│   │   ├── news.spec.ts            # 新闻资讯
│   │   └── performance.spec.ts     # 性能断言（已迁移到 Lighthouse）
│   ├── scripts/
│   │   └── lighthouse-baseline.js  # Lighthouse 性能基线脚本
│   ├── next.config.js              # standalone、安全响应头、Bundle 预算
│   ├── tailwind.config.js          # 暗色主题、up/down 自定义颜色
│   ├── tsconfig.json               # strict、@/* 路径别名
│   ├── vitest.config.ts            # Vitest + jsdom + @vitejs/plugin-react
│   ├── playwright.config.ts        # E2E、auth.setup 依赖、webServer
│   └── package.json
│
├── python/
│   ├── errors.py                   # ErrorCode(StrEnum) 统一业务错误码
│   ├── main.py                     # FastAPI 入口、lifespan、CORS、异常处理、Prometheus 中间件
│   ├── config.py                   # .env 加载、SECRET_KEY/生产环境校验、所有环境变量默认值
│   ├── dependencies.py             # get_db、JWT 用户解析（含 CSRF 防护）
│   ├── models.py                   # SQLAlchemy 模型，28 张表
│   ├── schemas.py                  # Pydantic v2，请求/响应模型和 XSS 过滤
│   ├── utils.py                    # bcrypt、JWT encode/decode
│   ├── worker.py                   # 独立 scheduler 入口，不启动 FastAPI
│   ├── pyproject.toml              # Ruff + mypy 配置
│   ├── requirements.txt            # 直接依赖
│   ├── requirements.lock           # 全锁定依赖（CI 安装源）
│   ├── Dockerfile                  # python:3.11-slim，非 root 用户
│   ├── alembic.ini                 # Alembic 配置
│   ├── alembic/
│   │   ├── env.py                  # 从 config.py 读取 DATABASE_URL
│   │   └── versions/               # 46 个迁移脚本
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
│   │   ├── cache.py                # 线程安全内存 LRU + Redis 优先
│   │   ├── circuit_breaker.py      # 数据源熔断器
│   │   ├── continuous_kline.py     # 主力连续 K 线拼接
│   │   ├── metrics.py              # Prometheus 指标
│   │   ├── logging_config.py       # structlog 结构化日志配置
│   │   ├── trading_calendar.py     # 交易日历
│   │   ├── ai_chat.py              # AI 助手 OpenAI 兼容调用
│   │   ├── news_fetcher.py         # RSS 新闻抓取与 AI 解读
│   │   ├── redis_client.py         # Redis 连接
│   │   ├── realtime_state.py       # 实时行情共享状态
│   │   ├── domain/                 # 领域服务层
│   │   │   ├── repositories/       # 数据访问层
│   │   │   ├── comment_service.py
│   │   │   ├── opinion_service.py  # 交易观点领域服务（试点）
│   │   │   ├── price_level_service.py
│   │   │   ├── watchlist_service.py
│   │   │   ├── workspace_service.py
│   │   │   └── exceptions.py       # ServiceError 体系
│   │   └── ...
│   ├── middleware/
│   │   └── rate_limit.py           # 限流中间件
│   ├── tushare_pg_ingest/          # 独立历史数据回填脚本
│   ├── scripts/                    # 一次性采集/验证/回填脚本
│   ├── tests/                      # pytest 测试（40 个测试文件）
│   ├── data/                       # 静态 CSV/手续费/交易日历
│   └── docs/                       # 架构决策、运维手册、API 契约
│
├── docker-compose.yml              # PostgreSQL 16 + Redis 7 + backend 服务
├── .env.example                    # 环境变量模板
├── .github/workflows/              # CI/CD
│   ├── backend-ci.yml
│   ├── frontend-ci.yml
│   └── update-calendar.yml
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
- 价格格式化：
  - 显示使用 `formatPrice(value, precision)`。
  - 构造 API payload 必须使用 `formatPricePayload(price, precision)`，不要直接用 `toFixed(2)`。
- 支撑/阻力位已同步后端：`price_levels` 表存储（含 `scope` 和 `contract_id`，支持 continuous/main/contract 三种口径隔离），通过 `/api/price-levels` CRUD；`frontend/hooks/usePriceLevels.ts` 封装了后端同步逻辑，按 K 线 source 隔离，本地存储作为降级/缓存方案保留（key 格式 `price-levels:v2:{userId}:{symbol}:{scope}:{contractId}`）。
- 主页面登录门禁来自 `AuthProvider` 和 `LoginRequired`。新增需要保护的页面时沿用该模式。
- 实时行情 Store 语义：`realtimeStore.ts` 的 `notifyAll` 同时提供 `snapshot`（全量）和 `delta`（增量）；`useRealtimeQuotes.ts` 明确区分增量合并与全量替换场景。订阅 symbol 数组请用 `useMemo` 避免无意义重连。
- 搜索输入统一使用 `useDebouncedValue.ts`，默认 250ms，消除请求洪峰和 UI 闪烁。
- 修改前端后至少运行 `npx tsc --noEmit`；如涉及样式或路由，也运行 `npm run lint`，必要时用浏览器查看 `127.0.0.1:3200`。
- 前端已配置 Vitest + Playwright + `.github/workflows/frontend-ci.yml`（lint + build + test + Lighthouse），但 `npm run test` 在 Windows 上可能因路径解析问题偶发失败（`/@fs/D:/...` 映射已知问题）。

### 前端关键配置

- `next.config.js`：`output: 'standalone'`；全局安全响应头（CSP、`X-Frame-Options: DENY`、`Referrer-Policy`、`Permissions-Policy`）；CSP 当前允许 `'unsafe-eval'` 和 `'unsafe-inline'` 以兼容 lightweight-charts 和 Next.js；Bundle 预算红线为任意路由 First Load JS 不得超过 180 kB。
- `tailwind.config.js`：暗色主题，自定义 `up`（红色系）、`down`（绿色系）。
- `tsconfig.json`：`"strict": true`，`"@/*": ["./*"]` 路径别名，`moduleResolution: "bundler"`。
- `playwright.config.ts`：`baseURL: http://127.0.0.1:3200`，`auth.setup.ts` 为前置依赖，`webServer` 自动运行 `npm run dev`。

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
- 全局限流中间件覆盖所有写入端点（POST/PUT/PATCH/DELETE），默认 60 秒窗口内 100 请求；高成本 GET（`/api/realtime/batch`、`/api/realtime/stream`）有独立限流窗口。
- 每个请求都有 `X-Request-ID`，通过 `request_id_middleware` 注入，structlog 上下文自动绑定。
- Prometheus 指标通过 `prometheus_middleware` 自动收集，排除 `/metrics`、`/docs`、`/redoc`、`/openapi.json`。
- **错误码契约**（2026-06-04）：`python/errors.py` 定义 `ErrorCode(StrEnum)`，30+ 稳定业务错误码；`ServiceError` 及其子类（`NotFoundError`、`ForbiddenError` 等）携带 `code` 参数；全局 exception handler 统一返回 `{code, message, errors, timestamp}`。新增 router 业务错误优先使用 `ServiceError` 而非裸 `HTTPException`。

### 后端关键配置

- `pyproject.toml`：项目名 `futures-community-api`，版本 `2.0.0`，`requires-python = ">=3.11"`。
- Ruff：`target-version = "py311"`，`line-length = 120`，启用 `E,W,F,I,N,UP,B,C4,SIM`，忽略 `E501`。
- mypy：`python_version = "3.11"`，排除了 `data_collector/`（除 `pipeline_tasks`）、`routers/`、`models.py`、`tests/`、`alembic/` 等目录，用于规避 SQLAlchemy 1.x 类型误报。
- `requirements.txt` 记录直接依赖，`requirements.lock` 为 CI 安装源（全锁定）。

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

### 后端文档目录

`python/docs/` 存放架构决策、运维手册和 API 契约文档：
- `api_error_contract.md`：统一业务错误码契约（`errors.py` 配套文档）
- `kline_partitioning.md`：K 线表 LIST+RANGE 分区策略与冷数据归档方案
- `sse_scaling_strategy.md`：SSE 单实例限制、sticky session、cookie-only 鉴权部署约束
- `observability_runbook.md`：可观测性运维手册（指标、日志、告警）
- `postgres_acceptance.md` / `postgres_backup_runbook.md`：PostgreSQL 验收与备份手册
- `productdb_sunset_plan.md`：ProductDB 退场完整计划与验证清单
- `settings_api.md`：用户偏好设置 API 设计文档
- `kline_benchmark_20260529.md`：K 线性能基准测试记录

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
.\.venv\Scripts\python.exe worker.py
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

后端已有 pytest（40 个测试文件，约 389 个测试函数）：
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
- `test_rate_limit_redis.py`
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
- Vitest 单元测试：`frontend/tests/` 下 33 个测试文件
- Playwright E2E：`frontend/e2e/` 下 7 个文件（auth.setup.ts + 6 个 spec）
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
| `PORT` | 否 | `8401` | 后端监听端口 |
| `REALTIME_REFRESH_INTERVAL_SECONDS` | 否 | `60` | 实时行情刷新间隔（秒） |
| `CACHE_MAX_SIZE` | 否 | `1024` | 内存缓存最大条目数 |
| `CACHE_DEFAULT_TTL_SECONDS` | 否 | `5` | 内存缓存默认 TTL（秒） |
| `RATE_LIMIT_WINDOW_SECONDS` | 否 | `60` | 限流时间窗口（秒） |
| `RATE_LIMIT_MAX_REQUESTS` | 否 | `100` | 限流窗口内最大请求数 |
| `PIPELINE_COMMIT_BATCH_SIZE` | 否 | `50` | Pipeline 批量提交大小 |
| `CIRCUIT_FAILURE_THRESHOLD` | 否 | `0.5` | 熔断器失败阈值比例 |
| `REDIS_URL` | 否 | — | Redis 连接串，留空则使用内存 LRU 降级 |
| `NEXT_PUBLIC_API_BASE` | 前端可选 | `http://127.0.0.1:8401` | 前端请求后端地址 |
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
- 后端端口不是 8000，而是 `127.0.0.1:8401`，除非 `HOST` / `PORT` 覆盖。
- `docker-compose.yml` 的 PostgreSQL 暴露端口是 15432。
- Redis 服务可以启动，缓存层已实现 Redis 优先 + 内存 LRU 降级。
- `node_modules`、`.next`、`venv`、数据库文件和日志可能在工作区中产生大量噪声，提交时不要顺手纳入。
- 当前仓库可能已有用户或其他助手留下的未提交变更，修改前后都要用 `git status --short` 观察，不要回滚无关改动。
- Windows 上 `python/main.py` 已 patch `asyncio.proactor_events._ProactorBasePipeTransport._call_connection_lost` 以抑制无害的 `ConnectionResetError 10054` 噪音，不要移除此 patch。
- **错误码契约**：新增业务错误优先使用 `python/errors.py` 中的 `ErrorCode` 和 `ServiceError`，避免裸 `HTTPException` 导致前端无法稳定分支处理。
- **docker-compose backend**：backend 服务已在 compose 中启用（2026-06-05），启动 `docker-compose up -d` 会同时拉起 postgres、redis 和 backend。
- **SSE 不原生水平扩展**：`_sse_connections` 为进程内内存，多实例部署需 sticky session 或 Redis pub/sub，详见 `python/docs/sse_scaling_strategy.md`。
- **生产环境 scheduler**：`ENABLE_SCHEDULER=1` 仅作本地便利；生产应运行独立 `python/worker.py`，避免 API 进程混入定时任务。

---

## CI/CD 与容器化

- **GitHub Actions**：
  - `.github/workflows/backend-ci.yml`：pytest + ruff + pip-audit + Alembic 迁移一致性检查 + pytest-cov（阈值 30%），使用 `requirements.lock`，Python 3.12，CI 内嵌 PostgreSQL service
  - `.github/workflows/frontend-ci.yml`：`npm ci` → `tsc --noEmit` → `npm run lint` → `npm run build` → `npm run test` → Lighthouse 基线
  - `.github/workflows/update-calendar.yml`：每年 1 月 1 日自动更新交易日历（cron），也支持手动触发

- **Dockerfile**：`python/Dockerfile`
  - 基于 `python:3.11-slim`
  - 创建非 root 用户 `app`
  - 健康检查：`curl -f http://localhost:8401/health || exit 1`
  - 默认 CMD 为 `uvicorn main:app --host 0.0.0.0 --port 8401`
  - 生产建议使用 gunicorn + uvicorn worker

- **docker-compose.yml**：
  - `postgres`：PostgreSQL 16-alpine，端口 15432，用户 `futures`/`futures123`
  - `redis`：Redis 7-alpine，端口 6379，AOF 持久化
  - `backend`：FastAPI 服务，端口 8401，依赖 postgres 和 redis，带健康检查

---

## 代码风格

- **Python**：Ruff（line-length 120，target py311）
  - 启用规则：E, W, F, I, N, UP, B, C4, SIM
  - 忽略：E501（由 line-length 控制）
  - Docstring 风格：Google
  - 格式化：双引号字符串，空格缩进
  - mypy：py311，但排除了 `data_collector/`（除 pipeline_tasks 外）、`routers/`、`models.py`、`tests/`、`alembic/` 等目录（SQLAlchemy 1.x 类型误报兼容策略）
  - 配置位置：`python/pyproject.toml`

- **前端**：ESLint（`next/core-web-vitals`），无 Prettier 配置
  - Tailwind 自定义颜色：`up`（红色系）、`down`（绿色系）反映中国市场惯例
  - Bundle Budget 红线：任意路由 First Load JS 不得超过 180 kB（见 `next.config.js` 注释）

---

## 安全注意事项

- **生产环境强制要求**：
  - `SECRET_KEY` 长度 >= 32
  - 必须使用 PostgreSQL（禁止 SQLite）
  - `CORS_ORIGINS` 必填，禁止 `*`、禁止 `http://`、禁止 localhost/127.0.0.1
  - `/docs`、`/redoc`、`/openapi.json` 在生产环境应关闭
- **密码**：必须使用 `utils.hash_password()`（bcrypt），禁止明文、MD5、SHA256。
- **XSS**：评论内容通过 Pydantic validator + `html.escape()` 过滤，长度限制在 schema 中维护。
- **JWT**：解码必须捕获 PyJWT 异常，禁止裸 `except:`。
- **CORS**：`allow_credentials=True`，因此生产环境不允许通配符 origin。
- **CSP**：前端有 Content-Security-Policy 响应头，但当前允许 `unsafe-eval` 和 `unsafe-inline`（为兼容 lightweight-charts 和 Next.js）。
- **CSRF 防护**（2026-05-29）：`dependencies.py` 方法感知鉴权，POST/PUT/PATCH/DELETE 必须携带 `Authorization: Bearer` header，不接受 `access_token` cookie 回退；GET/HEAD 保持兼容。
- **Metrics**：`/metrics` 端点限制为可信内网 IP，外网返回 403。
- **前端日志**：`POST /api/log/frontend` 必须鉴权并忽略客户端传入的 `user_id`；需限制 payload 大小、深度与 key 数量，防止日志注入与存储滥用。
- **RSS/新闻源**：添加外部 RSS URL 时必须校验协议与主机（拒绝 private/local/link-local/file 等危险目标），抓取时设置显式超时，防止 SSRF 与 worker 阻塞；admin 手动触发抓取接口（`/api/news/fetch`、`/api/news/sources/{id}/fetch`）已通过 `BackgroundTasks` 后台化，不再阻塞 HTTP 请求。
- **实时行情批量**：`/api/realtime/batch` 应对 symbol 数量做上限控制（建议 ≤50/100），避免超大数据库查询。
- **登录/注册限流**：当前使用 Redis 优先 + 内存降级的 `check_rate_limit`，action key 独立为 `auth:register` / `auth:login`。

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
- SSE 连接为进程内状态，单实例或 sticky session 部署

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
- `OpinionService` 作为 service 层试点，router 仅负责 HTTP 契约转换

**前端**
- `/opinions` 页面：双标签页「全部观点」+「我的观点」
- 筛选：品种、方向、状态

### News（新闻资讯）— 已完成（2026-05-30）

**后端**
- `NewsSourceDB` / `NewsArticleDB` 模型
- RSS 抓取 + AI 摘要（`services/news_fetcher.py`）
- Router `/api/news`：源管理 + 文章列表 + 单篇摘要
- **手动抓取后台化**（2026-06-24）：`/api/news/fetch` 与 `/api/news/sources/{id}/fetch` 改为通过 `BackgroundTasks` 提交后台任务，立即返回 `NewsFetchTaskResponse`，不再同步阻塞 HTTP 请求；新增 `fetch_source_background` / `fetch_all_enabled_sources_background` 函数，内部独立创建 `SessionLocal` 会话

**前端**
- `/news` 页面：来源筛选 + 标题搜索 + AI 解读
- 搜索输入已接入 `useDebouncedValue`

### 前端 Sprint 2：体验优化 — 已完成（2026-06-04）

- **搜索防抖**（P2-1）：新建 `useDebouncedValue.ts`，products 和 news 页面搜索输入防抖 250ms，消除请求洪峰和 UI 闪烁
- **Token 安全评估**（P2-2）：选择方案 C（保守），新建 `frontend/docs/SECURITY_RISKS.md` 记录 RISK-001（access token 存 localStorage）及后续行动项
- **实时行情 Store 语义清晰化**（P2-3）：`realtimeStore.ts` 的 `notifyAll` 同时提供 `snapshot`（全量）和 `delta`（增量），`useRealtimeQuotes.ts` 明确区分增量合并与全量替换场景
- **Lighthouse 端口基线修复**（P2-4）：`.lighthouse/latest.json` url 修正为 `http://127.0.0.1:3200`，与 `npm run dev` 实际端口一致
- **验证**：`npx tsc --noEmit` 通过，`npm run lint` 通过，`useDebouncedValue.test.ts` 5 个测试通过

### 前端 Sprint 3：架构清理 — 已完成（2026-06-05）

- **导航组件去重**（P3-1）：删除死代码 `SideNav.tsx` 和 `MobileNav.tsx`（无任何页面引用）；`Navbar.tsx` 从 `navigation.ts` 导入 `isActivePath`，消除内联重复定义。遵循"如无必要勿增实体"，不强行拆分 Navbar
- **测试覆盖补齐**（P3-2）：新建 `e2e/metrics.spec.ts`（3 个测试：未登录门禁 + 已登录直达不跳转 + 指标卡片显示）、`e2e/news.spec.ts`（5 个测试：未登录门禁 + 已登录加载 + 搜索框防抖）
- **验证**：`npx tsc --noEmit` 通过，`npm run lint` 通过，32 个测试文件 / 189 个单元测试通过

### 后端 Roadmap V3 阶段四：扩展性与限流 — 已完成（2026-06-05）

- **高成本 GET 限流**：`/api/realtime/batch`（60s/100req）、`/api/realtime/stream`（60s/30req）增加独立限流窗口
- **SSE 独立限流**：按 IP 限流，超限时返回 429 而非静默断开
- **登录/注册限流 Redis 化**：与全局限流 middleware 统一，使用 `check_rate_limit`（Redis 优先+内存降级）；action key 独立（`auth:register`/`auth:login`）
- **Redis 空值标记修复**：用常量字符串 `__CACHE_EMPTY__` 替代 dict 对象，穿透防护在 Redis 路径稳定
- **SSE query token 移除**：标记 `deprecated=True`；鉴权改为 cookie 优先，token 仅降级兼容
- **测试**：新增 `test_rate_limit_redis.py`（7 个测试），383 passed, 6 skipped, 0 failed

### 后端 Roadmap V3 阶段五：CI/运维与架构优化 — 已完成（2026-06-05）

- **CI 增强**：backend-ci.yml 增加 Alembic 迁移一致性检查（CI 内嵌 PostgreSQL service）+ pytest-cov（阈值 30%）
- **运维文档补齐**：`python/docs/sse_scaling_strategy.md`（SSE 部署约束）、`python/docs/kline_partitioning.md`（K 线表分区策略）
- **交易日历预测告警**：`services/trading_calendar.py` 使用预测年份时输出 warning 日志
- **Service 层试点**：`routers/opinions.py` 提取 `OpinionService`，router 仅负责 HTTP 契约转换
- **compose backend service**：取消 backend 注释，配置健康检查、环境变量、端口映射
- **测试**：383 passed, 6 skipped, 0 failed

---

## 待处理 P1 事项（来自后端架构审计 v7）

以下事项在当前代码中已有对应测试或部分修复，但仍是生产就绪前需要持续关注的高优先级项：

1. **前端日志鉴权与 payload 限制**：`frontend_logs.py` 已鉴权，但需继续限制单条日志大小、JSON 深度、自定义 key 数量，防止存储滥用。
2. ~~**RSS URL 校验与抓取超时**：`news_fetcher.py` 已显式拒绝非 http/https 及内网/本地/link-local 地址，httpx 请求超时 10s、最大重定向 3 次，并由 schema 层前置校验。~~ **已修复**。
3. **价位标注并发重复**：`price_levels` 表已建立 partial unique index，确保 `(variety_id, type, price, scope, contract_id)` 在 `contract_id IS NULL` 分支唯一。
4. **评论外键冲突**：删除品种或合约时需保证关联评论有级联或软删除策略，避免 500。
5. **实时行情批量 symbol 上限**：`/api/realtime/batch` 应对请求 symbol 数量做硬性上限。
6. **交易观点 reason 字段清洗**：与评论一致，使用 `html.escape()` 或等价 sanitize，防止 XSS。

新功能开发时应优先处理上述安全/稳定性项，并补充对应 pytest / 单元测试。

---

## 待处理 P2 风险接受项（来自后端架构审计 v7）

以下问题已被识别，但在当前阶段作为**风险接受项**处理，不影响当前产品形态上线；后续可按业务增长逐步推进：

1. **API 版本治理**：当前所有接口统一在 `/api/` 前缀下，无 `/api/v1` 版本隔离。后续若出现 breaking change，建议通过网关路由或新增版本前缀治理。
2. **`kline_data` 表分区/归档**：K 线数据目前单表存储，PostgreSQL 大数据量场景下需按 `trading_time` + `period` 做 range partition 并冷数据归档。方案已记录在 `python/docs/kline_partitioning.md`。
3. **RSS fetch 后台化**：~~`/api/news/sources/{id}/fetch` 在 API 请求内同步执行，慢源可能导致请求超时。~~ **已修复（2026-06-24）**：手动触发接口改为 `BackgroundTasks` 异步执行。
4. **自动备份/恢复演练**：`python/docs/postgres_backup_runbook.md` 已提供手动 runbook，但尚未自动化。建议后续补充定时备份脚本与恢复演练。

> 注：上述列表随修复迭代更新；已修复项保留 ~~删除线~~ 以便追溯。
