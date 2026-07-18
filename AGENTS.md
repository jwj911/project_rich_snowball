<!-- AGENTS.md — 期货交流社区 -->

> 本文档面向 AI 编程助手。进入本仓库后，先读这里，再动代码。
>
> **最后更新**：2026-07-18（Phase 0 可运行性收口完成）

---

## 项目概述

**期货交流社区**（产品名「倍增计划」）是一个前后端分离的期货行情与私密交流社区应用。当前产品形态为“登录后的行情工作台”：用户登录后可查看热门期货品种、筛选行情、进入单品种 K 线复盘、添加云端支撑/阻力位标注、发表评论、记录交易观点、管理模拟持仓与策略、设置价格预警、与 AI 助手及专项 Agent 对话，并在个人工作区汇总自己的研究上下文。

### 当前阶段

- **Phase 5「策略优化与性能调优」已完成**（2026-07-04）：参数网格搜索、策略信号 K 线叠加可视化、回测 5 分钟 LRU 缓存、监控告警增强、全量测试通过。
- **Agent 系统 Phase 0~2 已完成**并接入真实 SSE 进度流：DataAgent、DataQualityAgent、TechAnalysisAgent、RiskManagementAgent、AnalysisPipelineAgent、StrategyCompilerAgent、BacktestAgent、FactorMiningAgent、TraderAgent 已上线。
- **策略进化（Strategy Evolution）已落地**：GA 进化循环、GP 因子生成、Pareto 适应度、贝叶斯优化、策略生命周期追踪。
- **近期新增功能**：策略工作台 `/strategies`、策略参数优化、回测信号可视化、预警中心 `/alerts`、Agent 工作台 `/agents`、交易员 Agent `trader`。
- **测试状态**：最近一次全量后端测试为 `961 passed, 6 skipped, 0 failed`；前端 Vitest 为 `192 passed, 0 failed`。Python `ruff check .`、前端 TypeScript、ESLint 和 production build 均通过。
- **文件审计**：2026-07-05 完成 Phase 1/2 清理，根目录精简至 7 个文件，文档迁入 `docs/guides/`、`docs/archive/` 与 `quantative_tools/reports/`，详见 [docs/audit_cleanup_20260705.md](docs/audit_cleanup_20260705.md)。

### 主要功能模块

| 模块 | 说明 |
|------|------|
| 认证 | JWT + OAuth2 密码流 + bcrypt，access token + refresh token 双令牌，refresh token 存 HttpOnly cookie |
| 行情工作台 | 首页热门品种、领涨观察、轮询刷新状态 |
| 行情中心 | `/products` 搜索、分类、涨跌筛选、排序 |
| 品种详情 | `/products/[id]` 实时行情、K 线、技术分析、评论、支撑/阻力标注、合约切换（主力/连续/具体合约） |
| 交易观点 | 针对品种发表多空观点，记录目标价、止损价、理由，支持事后复盘 |
| 模拟持仓 / 策略 | 虚拟交易记录、盈亏计算、策略生成、回测跟踪、参数优化、策略进化 |
| 价格预警 | above/below 价格预警，实时行情刷新时触发 |
| AI 助手 / Agent | Chat 页多模式对话，Agent 工作台管理任务，执行过程 SSE 流式展示 |
| 新闻资讯 | RSS 源管理、聚合与 AI 解读 |
| 工作区 / 设置 | 个人评论历史、云端价位标注、自选观察、偏好设置 |
| 运营指标 | `/metrics` 用户数/评论数/采集健康度 |
| 数据采集 | Mock / AkShare / Tushare，多源 fallback + 熔断器，定时刷新 |

---

## 文档导航

本仓库采用「总-分-总」结构：根目录 `AGENTS.md` 保留高频总览；详细内容拆分至 `.agents/` 目录下的主题分册。需要深入了解时请按主题跳转：

| 分册 | 说明 |
|------|------|
| [.agents/project.md](.agents/project.md) | 项目概览、技术栈、目录结构 |
| [.agents/backend.md](.agents/backend.md) | 后端开发规则、错误码/限流/测试、关键配置 |
| [.agents/frontend.md](.agents/frontend.md) | 前端开发规则、关键配置、组件/Hooks/API 约定 |
| [.agents/data.md](.agents/data.md) | 数据采集与调度、PostgreSQL 与历史回填、后端文档目录 |
| [.agents/operations.md](.agents/operations.md) | 环境变量、构建/运行/测试命令、CI/CD、代码风格 |
| [.agents/security.md](.agents/security.md) | 生产环境强制要求、CSRF/XSS/SSRF、部署安全 |
| [.agents/agents.md](.agents/agents.md) | Agent 系统架构、Agent 划分、开发约束 |
| [.agents/roadmap.md](.agents/roadmap.md) | 模块演进状态、待处理 P1/P2 事项 |

技术参考文档：

| 文档 | 说明 |
|------|------|
| [docs/guides/DATA_PIPELINE_AND_POSTGRES_GUIDE.md](docs/guides/DATA_PIPELINE_AND_POSTGRES_GUIDE.md) | 数据管道与 PostgreSQL 配置 |
| [docs/guides/TUSHARE_POSTGRES_VERIFICATION.md](docs/guides/TUSHARE_POSTGRES_VERIFICATION.md) | Tushare 数据验证 |
| [docs/guides/BACKEND_API_REFERENCE_FOR_FRONTEND.md](docs/guides/BACKEND_API_REFERENCE_FOR_FRONTEND.md) | 后端 API 参考（前端用） |
| [docs/guides/BACKEND_API_VERSIONING_GUIDE.md](docs/guides/BACKEND_API_VERSIONING_GUIDE.md) | API 版本迁移指南 |

历史审计与路线图归档在 [docs/archive/](docs/archive/)，因子分析报告在 [quantative_tools/reports/](quantative_tools/reports/)。

---

## Git 工作流约定

- **默认在 `master` 分支工作**。每次新对话开始时，先执行 `git branch` 确认当前分支。
- 如果当前不在 `master`，**立即提醒用户**，并在征得同意后切换到 `master`（切换前用 `git stash` 保存未提交修改）。
- 如有明确需求要在其他分支操作，按用户指令执行。
- 修改前后都要用 `git status --short` 观察，不要回滚无关改动。当前仓库可能已有用户或其他助手留下的未提交变更。
- **分支陷阱**：`codex/new_fronted` 等历史分支曾执行 `git filter-branch`，部分文件（如 `tushare_pg_ingest/*.py`）在那些分支上被移除。需要这些文件时务必在 `master` 上操作。

---

## 技术栈与架构

### 后端（`python/`）

| 层级 | 技术 | 版本/说明 |
|------|------|-----------|
| 语言 | Python | >= 3.11 |
| 框架 | FastAPI | 0.136.3 |
| 服务器 | Uvicorn | 0.30.6 |
| ORM | SQLAlchemy | 2.0.25 |
| 迁移 | Alembic | 1.13.1，当前 58 个迁移脚本 |
| 校验 | Pydantic | v2 2.9.0 |
| 认证 | JWT + OAuth2 密码流 | PyJWT 2.13.0，bcrypt via passlib |
| 数据库 | SQLite / PostgreSQL | 开发默认 SQLite；PG 16 通过 docker-compose 提供，映射端口 15432 |
| 数据采集 | Mock / AkShare / Tushare | `DATA_SOURCE` 控制，非生产可降级 Mock |
| 定时任务 | APScheduler | BackgroundScheduler |
| 缓存 | Redis 优先 + 内存 LRU 降级 | `services/cache.py` |
| 可观测性 | Prometheus 风格指标 + structlog | `services/metrics.py` + `services/logging_config.py` |
| 限流 | 内存/Redis 滑动窗口 | `middleware/rate_limit.py` |
| 技术指标 | numpy + pandas | `python/lib/technical_indicators.py` |

### 前端（`frontend/`）

| 层级 | 技术 | 版本/说明 |
|------|------|-----------|
| 框架 | Next.js App Router | 14.2.35，`output: 'standalone'` |
| UI | React + TypeScript | React 18.2.0，TypeScript 5.3.3 |
| 样式 | Tailwind CSS | 3.4.1，自定义暗色主题，上涨红色/下跌绿色 |
| 字体/图标 | geist / lucide-react | ^1.7.2 / ^0.312.0 |
| K 线图 | lightweight-charts | ^5.2.0 |
| 数据获取 | SWR | ^2.4.1 |
| 表单 | react-hook-form | ^7.76.0 |
| 消息提示 | sonner | ^2.0.7 |
| 性能采集 | web-vitals | ^5.2.0 |
| 单元测试 | Vitest + @testing-library/react + jsdom | Vitest ^4.1.6，33 个测试文件，192 个测试 |
| E2E 测试 | Playwright | ^1.60.0，6 个 spec 文件 + `auth.setup.ts` |
| 性能基线 | Lighthouse | `npm run lighthouse` |

### 基础设施

- **PostgreSQL**：`postgres:16-alpine`，端口 `15432:5432`
- **Redis**：`redis:7-alpine`，端口 `6379:6379`
- **后端**：默认监听 `127.0.0.1:8401`
- **前端**：默认监听 `127.0.0.1:3200`

---

## 代码组织

### 顶层结构

```text
d:\Code\project_rich_snowball/
├── .agents/                  # AI 助手分册文档（8 个 md）
├── .github/workflows/        # CI/CD（backend-ci / frontend-ci / update-calendar）
├── docs/                     # 项目文档：guides / archive / 审计与迭代计划
├── frontend/                 # Next.js 14 前端
├── python/                   # FastAPI 后端
├── quantative_tools/         # 量化因子/信号/策略/报告
├── AGENTS.md                 # 本文件
├── README.md                 # 人类可读项目说明
├── docker-compose.yml        # PG + Redis + backend
├── .env / .env.example       # 环境变量
├── .pre-commit-config.yaml   # pre-commit hooks
└── ...
```

### 后端目录（`python/`）

| 目录/文件 | 说明 |
|-----------|------|
| `main.py` | FastAPI 应用入口、lifespan、中间件、全局异常处理 |
| `config.py` | 环境变量与配置中心，`SECRET_KEY` 为必需 |
| `dependencies.py` | `get_db()`、JWT 解析、CSRF 感知鉴权 |
| `models.py` | SQLAlchemy ORM 模型，50+ 张表 |
| `schemas.py` | Pydantic v2 请求/响应模型 |
| `errors.py` | `ErrorCode` 统一业务错误码与 `ServiceError` |
| `utils.py` | bcrypt、JWT、refresh token、UTC 时间工具 |
| `worker.py` | 独立 scheduler worker 入口 |
| `routers/` | 25 个 FastAPI 领域路由模块 |
| `services/` | 业务服务层：agent/、backtest/、domain/、cache、metrics、news_fetcher 等 |
| `services/agent/` | Agent 系统核心：core.py、executor.py、llm_client.py、各功能 Agent、trader/、factor_engine/、risk_management/、analysis/、evolution/ |
| `data_collector/` | 采集器注册、pipeline、scheduler、adapter、cleaner、upsert、mock/akshare/tushare 采集器 |
| `lib/` | 纯 numpy/pandas 技术指标库 `technical_indicators.py` |
| `middleware/` | `api_version.py`（`/api/v1/*` 映射）、`rate_limit.py` |
| `scripts/` | 运维/回填/迁移/验收脚本 |
| `tests/` | 85 个 pytest 测试文件 + `conftest.py` |
| `alembic/` | 58 个 Alembic 迁移版本 |
| `tushare_pg_ingest/` | Tushare 历史数据回填脚本体系 |
| `docs/` | 后端专项技术文档 |

### 前端目录（`frontend/`）

| 目录/文件 | 说明 |
|-----------|------|
| `app/` | Next.js App Router 页面路由（15+ 个页面） |
| `components/` | React 组件（约 58 个），按功能分子目录 |
| `hooks/` | 自定义 React Hooks（行情轮询、K 线、实时推送等） |
| `lib/` | API 客户端、类型、工具函数、实时 Store、常量 |
| `lib/api/` | 领域 API 模块与 `client.ts` 统一 `api` 实例 |
| `tests/` | Vitest 单元/集成测试（33 个文件） |
| `e2e/` | Playwright E2E 测试（6 个 spec + auth.setup.ts） |
| `scripts/` | Lighthouse 基线脚本 |
| `docs/` | 前端专项文档 |

### 量化工具（`quantative_tools/`）

| 目录 | 说明 |
|------|------|
| `factors/` | 因子定义（万因子精选 + 自定义） |
| `signals/` | 择时信号（CCI、KDJ、RSV、均线、布林带、海龟等） |
| `strategy/` | 选股/选期策略示例 |
| `reports/` | 因子分析报告 |

---

## 关键配置文件

| 文件 | 作用 |
|------|------|
| `python/pyproject.toml` | 后端项目元数据、Ruff 与 mypy 配置 |
| `python/requirements.txt` | 后端直接依赖 |
| `python/requirements.lock` | CI 安装源（全锁定） |
| `python/alembic.ini` / `alembic/env.py` | Alembic 迁移配置 |
| `frontend/package.json` | 前端依赖与脚本 |
| `frontend/next.config.js` | standalone 输出、安全响应头、Bundle 预算红线 180 kB |
| `frontend/tsconfig.json` | strict、bundler moduleResolution、`@/*` 路径别名 |
| `frontend/tailwind.config.js` | 暗色主题、中国市场语义色 `up`（红）/`down`（绿） |
| `frontend/vitest.config.ts` | Vitest + jsdom + `@/` 别名 |
| `frontend/playwright.config.ts` | E2E baseURL `127.0.0.1:3200`，自动运行 `npm run dev` |
| `docker-compose.yml` | PostgreSQL 16 + Redis 7 + backend |
| `.env.example` | 环境变量模板 |
| `.pre-commit-config.yaml` | Ruff、通用 hooks、ESLint |

---

## 构建与运行命令

### 启动后端

```powershell
cd python
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.lock
$env:SECRET_KEY='change-this-to-a-real-secret'
.venv\Scripts\python.exe main.py
```

默认监听 `http://127.0.0.1:8401`；生产环境 `/docs`、`/redoc` 自动关闭。

启动时会执行：
- `init_db()`：建表；生产走 Alembic，开发/测试走 `Base.metadata.create_all()`
- `init_varieties()`：初始化/更新品种元数据
- 非生产环境 `init_mock_data()`：插入开发账号与示例评论
- `ENABLE_SCHEDULER=1` 时启动后台调度器并延迟执行首次数据采集

### 启动独立 Worker

```powershell
cd python
.venv\Scripts\python.exe worker.py
```

### 启动前端

```powershell
cd frontend
npm install
npm run dev
```

默认监听 `http://127.0.0.1:3200`。

### 启动基础设施（PostgreSQL + Redis）

```powershell
docker-compose up -d postgres redis
```

使用 PostgreSQL 时常见连接串：

```env
DATABASE_URL=postgresql://futures:futures123@localhost:15432/futures_community
```

### 数据库迁移

```powershell
cd python
alembic upgrade head
```

---

## 测试策略与命令

### 后端测试

```powershell
cd python
$env:SECRET_KEY='test-secret-key'
$env:ENABLE_SCHEDULER='0'
.venv\Scripts\python.exe -m pytest tests -v
```

- `conftest.py` 强制设置测试环境变量，创建临时 SQLite 文件数据库，提供 `db_session`、`client`、`auth_headers`、`admin_headers` 等 fixtures。
- 重点覆盖：认证/CSRF/CORS、Agent 系统、回测/策略/因子、行情/K 线/实时推送、数据质量、生产配置约束。

### 前端测试

```powershell
cd frontend
npm run test        # Vitest 单元/集成测试
npx playwright test # E2E 测试
```

Playwright E2E 依赖前端服务已启动；`auth.setup.ts` 会先登录并保存 storage state。

### 代码风格检查

后端：

```powershell
cd python
ruff check .
ruff format .
```

前端：

```powershell
cd frontend
npx tsc --noEmit
npm run lint
```

### 性能基线

```powershell
cd frontend
npm run build
npm start
# 另一终端
npm run lighthouse
```

输出到 `.lighthouse/latest.json`。

---

## 代码风格指南

### Python

- **格式化**：Ruff，`line-length = 120`，target Python 3.11。
- **启用规则**：`E,W,F,I,N,UP,B,C4,SIM`；忽略 `E501`。
- **Docstring**：Google 风格。
- **字符串**：双引号，空格缩进。
- **导入顺序**：标准库 → 第三方 → 本项目。
- **mypy**：py311，忽略缺失导入；`models.py`、`routers/`、`tests/`、`alembic/`、`data_collector/` 旧模块等暂时排除。
- **配置位置**：`python/pyproject.toml`。

### TypeScript / 前端

- **Lint**：ESLint `next/core-web-vitals`。
- **严格模式**：`tsconfig.json` 中 `strict: true`。
- **路径别名**：`@/*` 映射项目根。
- **样式**：Tailwind CSS；语义色 `up`（红/涨）、`down`（绿/跌）符合中国市场惯例。
- **Bundle 预算**：任意路由 First Load JS 不得超过 180 kB（见 `next.config.js`）。

### 通用约定

- 后端新增业务错误优先使用 `python/errors.py` 的 `ErrorCode` 和 `ServiceError`，避免裸 `HTTPException`。
- 价格显示用 `formatPrice()`，API payload 用 `formatPricePayload()`。
- K 线 markers 使用 lightweight-charts v5 插件方式 `createSeriesMarkers(series)`，禁止对 `candleSeries` 强转调用 `setMarkers`。
- 新增 Agent 继承 `BaseAgent`；Tool 用 `@register_tool` 注册；步骤写入 `agent_task_steps`。
- 后端统一使用 `dependencies.get_db()` 获取数据库会话，禁止手动创建后忘记关闭。
- 密码必须用 `utils.hash_password()`（bcrypt），禁止明文/MD5/SHA256。
- JWT 异常必须捕获 `PyJWTError`，禁止裸 `except:`。

---

## 安全注意事项

### 生产环境强制要求

- `SECRET_KEY` 长度 ≥ 32。
- 必须使用 PostgreSQL，禁止 SQLite。
- `CORS_ORIGINS` 必填，禁止 `*`、禁止 `http://`、禁止 localhost/127.0.0.1。
- `/docs`、`/redoc`、`/openapi.json` 在生产环境关闭。

### 认证与鉴权

- 写接口（POST/PUT/PATCH/DELETE）必须显式携带 `Authorization: Bearer` header；CSRF 防护下不接受 cookie 回退。
- GET/HEAD 可回退到 `access_token` cookie 保持兼容。
- refresh token 以 HttpOnly cookie 返回，生产环境 `secure=True, samesite=lax`。
- 登录/注册使用独立限流 key（`auth:register` / `auth:login`）。

### XSS / SSRF / 输入安全

- 评论/交易观点 `reason` 通过 Pydantic validator + `html.escape()` 过滤。
- 前端日志端点 `/api/log/frontend` 必须鉴权、限制 payload 大小/深度/key 数量。
- RSS URL 校验协议与主机，拒绝内网/local/link-local/file，抓取显式超时。
- `/metrics` 仅限可信内网 IP，外网返回 403。

### 部署安全

- SSE 连接状态为进程内内存，多实例需 sticky session 或 Redis pub/sub。
- 生产环境 scheduler 应运行独立 `python/worker.py`，避免 API 进程混入定时任务。
- Docker 镜像使用非 root 用户 `app`，带健康检查。

---

## 部署与 CI/CD

### GitHub Actions

| Workflow | 触发条件 | 内容 |
|----------|----------|------|
| `.github/workflows/backend-ci.yml` | `python/**`、`docker-compose.yml`、workflow 本身变更 | Python 3.12，内嵌 PG service，安装 `requirements.lock`，Alembic `upgrade head`，pytest + coverage（阈值 30%），ruff lint，pip-audit 安全扫描 |
| `.github/workflows/frontend-ci.yml` | `frontend/**`、workflow 本身变更 | Node 20，`npm ci` → `tsc --noEmit` → `npm run lint` → `npm run build` → `npm run test` → Lighthouse 基线 |
| `.github/workflows/update-calendar.yml` | 每年 1 月 1 日 cron + manual | 更新交易日历 `python/data/trading_calendar.json` 并提交 |

### Docker

- **`python/Dockerfile`**：基于 `python:3.11-slim`，非 root `app` 用户，健康检查 `curl -f http://localhost:8401/health`，默认 `uvicorn main:app --host 0.0.0.0 --port 8401`。
- **`docker-compose.yml`**：PG + Redis + backend，backend 带健康检查与依赖条件。

---

## 核心约定总结

1. **分支**：默认 `master`，开工前 `git branch` 确认；修改前后 `git status --short`。
2. **API 调用**：前端统一走 `frontend/lib/api/client.ts` 的 `api` 实例；后端新接口优先 `/api/v1/*`（`ApiVersionMiddleware` 透明映射到 `/api/*`）。
3. **数据库**：后端统一使用 `dependencies.get_db()`；生产必须用 PostgreSQL。
4. **鉴权**：写接口必须 `Authorization: Bearer`；密码必须 bcrypt；JWT 异常必须捕获。
5. **错误处理**：新增业务错误优先使用 `python/errors.py` 中的 `ErrorCode` 和 `ServiceError`。
6. **格式化**：价格显示用 `formatPrice()`，API payload 用 `formatPricePayload()`；K 线 markers 用 lightweight-charts v5 插件方式。
7. **Agent**：确定性计算优先；新增 Agent 继承 `BaseAgent`；Tool 用 `@register_tool` 注册；步骤写入 `agent_task_steps`。
8. **修改后验证**：前端跑 `tsc --noEmit` + `lint` + `test`；后端跑相关 pytest + `ruff check .`。

---

## 常见陷阱

- 导入任何依赖 `config.py` 的模块前必须有 `SECRET_KEY`，测试中通常用环境变量设置。
- README 旧说法里的 `python/init_data.py` 已过时，主流程使用 `data_collector/init_mock_data.py`。
- 前端端口不是默认 3000，而是 `127.0.0.1:3200`。
- 后端端口不是 8000，而是 `127.0.0.1:8401`，除非 `HOST` / `PORT` 覆盖。
- `docker-compose.yml` 的 PostgreSQL 暴露端口是 15432。
- `node_modules`、`.next`、`venv`、数据库文件和日志可能在工作区中产生大量噪声，提交时不要顺手纳入。
- 当前仓库可能已有用户或其他助手留下的未提交变更，修改前后都要用 `git status --short` 观察，不要回滚无关改动。
- Windows 上 `python/main.py` 已 patch `asyncio.proactor_events._ProactorBasePipeTransport._call_connection_lost` 以抑制无害的 `ConnectionResetError 10054` 噪音，不要移除此 patch。
- `DATA_SOURCE=auto` 或真实数据源初始化失败时，非生产环境会降级到 Mock；生产环境不允许降级 Mock。

---

> 详细规则、演进状态与专项说明请查看 [.agents/](.agents/) 下的分册文档。
