# AGENTS.md — 期货交流社区

> 本文档面向 AI 编程助手。进入本仓库后，先读这里，再动代码。
>
> **最后更新**：2026-05-09，基于前后端近期迭代后的实际代码。

---

## 项目概览

**期货交流社区**是一个前后端分离的期货行情与私密交流社区应用。当前产品形态更接近“登录后的行情工作台”：用户登录后查看热门期货、筛选品种、进入单品种 K 线复盘、添加本地支撑/阻力位标注、发表评论，并在个人工作区汇总自己的研究上下文。

主要功能：
- 登录/注册/JWT 鉴权，主页面均有登录门禁
- 首页行情工作台：热门品种、领涨观察、30 秒轮询和刷新状态
- 行情中心：搜索、分类、涨跌筛选，按价格/涨跌幅/成交量排序
- 品种详情：实时行情、`lightweight-charts` K 线、技术分析、评论、支撑/阻力标注
- 我的工作区：评论历史、本地价位标注、自选观察入口
- 数据采集：Mock / AkShare / Tushare，多源 fallback，定时刷新实时行情和 K 线
- PostgreSQL 历史回填：`python/tushare_pg_ingest/` 下有独立脚本体系

---

## 技术栈

| 层级 | 技术 | 版本/说明 |
|------|------|-----------|
| 前端 | Next.js App Router | 14.1.0，React 18.2，TypeScript 5.3 |
| 前端样式 | Tailwind CSS | 3.4.1，自定义暗色界面 |
| 图标 | lucide-react | ^0.312.0 |
| K 线图 | lightweight-charts | ^5.2.0 |
| 后端 | Python + FastAPI | Python 3.11/3.12 可运行，FastAPI 0.115 |
| 后端服务器 | Uvicorn | 0.27.0 |
| ORM | SQLAlchemy | 2.0.25 |
| 数据库 | SQLite / PostgreSQL | SQLite 开发零配置；PG 16 通过 compose 提供 |
| 迁移 | Alembic | 1.13.1 |
| 认证 | JWT + OAuth2 密码流 | PyJWT 2.9.0，passlib bcrypt |
| 数据校验 | Pydantic v2 | 2.9.0 |
| 数据采集 | Mock / AkShare / Tushare | `DATA_SOURCE` 控制，非生产可降级 Mock |
| 定时任务 | APScheduler | BackgroundScheduler |
| 缓存 | 内存 LRU | Redis 预留但未接入运行时代码 |

---

## 真实端口与环境

- 后端 `python/main.py` 默认监听 `127.0.0.1:8200`，由 `HOST` / `PORT` 覆盖。
- 前端 `npm run dev` 实际执行 `next dev -H 127.0.0.1 -p 3200`。
- 前端 API 默认值在 `frontend/lib/api.ts`：`NEXT_PUBLIC_API_BASE || http://127.0.0.1:8200`。
- CORS 默认允许 `localhost/127.0.0.1` 的 `3000` 和 `3200`。
- `docker-compose.yml` 中 PostgreSQL 映射为 `15432:5432`，不是 5432。

---

## 目录结构

```text
project_rich_snowball/
├── frontend/
│   ├── app/
│   │   ├── layout.tsx           # 根布局，包裹 AuthProvider
│   │   ├── page.tsx             # 行情工作台，需登录
│   │   ├── products/page.tsx    # 行情中心，搜索/筛选/排序
│   │   ├── products/[id]/page.tsx # 品种详情，K 线/评论/本地标注
│   │   ├── workspace/page.tsx   # 我的工作区
│   │   ├── my-comments/page.tsx # 当前用户评论历史
│   │   └── globals.css
│   ├── components/
│   │   ├── auth/                # AuthProvider、LoginRequired
│   │   ├── layout/AppShell.tsx  # 全局应用壳，左侧导航偏移
│   │   ├── market/              # QuoteCard/Table、PriceChange、技术分析
│   │   ├── ui/                  # Button/Input/EmptyState/ErrorState
│   │   ├── workspace/           # 工作区摘要、标注、评论时间线、自选面板
│   │   ├── Navbar.tsx
│   │   └── KlineChart.tsx       # lightweight-charts 封装
│   ├── hooks/useMarketPolling.ts# 轮询和 heartbeat 状态
│   ├── lib/api.ts               # 统一 API 客户端，含 token 管理
│   └── tests/p0-fixes.test.md   # 人工检查清单
│
├── python/
│   ├── main.py                  # FastAPI 入口、lifespan、CORS、异常处理
│   ├── config.py                # .env 加载、SECRET_KEY/生产环境校验
│   ├── models.py                # SQLAlchemy 模型，20+ 张表
│   ├── schemas.py               # Pydantic v2，请求/响应模型和 XSS 过滤
│   ├── dependencies.py          # get_db、JWT 用户解析
│   ├── utils.py                 # bcrypt、JWT
│   ├── routers/                 # auth/products/comments/varieties/kline/realtime/health/watchlists/price-levels/workspace
│   ├── data_collector/          # 在线采集、清洗、upsert、调度器
│   ├── tushare_pg_ingest/       # 独立历史数据回填脚本
│   ├── scripts/                 # 一次性采集/验证脚本
│   ├── services/cache.py        # 线程安全内存 LRU
│   ├── tests/                   # pytest 测试
│   └── alembic/versions/        # 迁移脚本
│
├── docker-compose.yml           # PostgreSQL 16 + Redis 7，backend 注释
├── .env.example                 # 环境变量模板
├── README.md                    # 面向人类的快速开始
└── src/main/java/               # 预留目录，无 Java 后端
```

---

## 前端开发规则

- 页面和组件目前全部按 Client Component 写法组织，保持 `'use client'` 与 Hooks 风格一致。
- API 调用统一通过 `frontend/lib/api.ts` 的 `api` 实例，不要在页面里散落裸 `fetch`。
- 行情轮询优先使用 `useMarketPolling`，默认 30 秒。
- 色彩语义遵循中国市场惯例：上涨红色，下跌绿色。
- `KlineChart.tsx` 已使用 `lightweight-charts`，不要再按旧文档理解为自研 SVG 蜡烛图。
- 支撑/阻力位已同步后端：`price_levels` 表存储，通过 `/api/price-levels` CRUD；本地存储作为降级/缓存方案保留。
- 主页面登录门禁来自 `AuthProvider` 和 `LoginRequired`。新增需要保护的页面时沿用该模式。
- 修改前端后至少运行 `npx tsc --noEmit`；如涉及样式或路由，也运行 `npm run lint`，必要时用浏览器查看 `127.0.0.1:3200`。

---

## 后端开发规则

- 导入顺序：标准库 → 第三方库 → 本项目模块。
- 数据库会话统一使用 `dependencies.get_db()`，避免手动创建 `SessionLocal()` 后忘记关闭。
- 路由按领域拆分为 `APIRouter`，在 `main.py` 统一挂载。
- 当前有双数据层：
  - `ProductDB` + `/api/products/*` 是前端主流程仍在使用的兼容层。
  - `VarietyDB` / `RealtimeQuoteDB` / `KlineDataDB` + `/api/varieties`、`/api/realtime`、`/api/kline` 是新行情数据层。
  - `scheduler.sync_prices_to_products()` 每 60 秒把 `realtime_quotes` 同步回 `products`。
- 数据采集遵循 `collector -> adapter -> cleaner -> pipeline -> upsert`。
- upsert 逻辑在 `data_collector/upsert.py`，已兼容 SQLite / PostgreSQL 双方言。
- 密码必须用 `utils.hash_password()`，禁止明文、MD5、SHA256。
- JWT 解码捕获 PyJWT 异常，不要裸 `except:`。
- 评论内容通过 Pydantic validator 和 `html.escape()` 做 XSS 过滤，长度限制在 schema 中维护。
- 生产环境约束在 `config.py`：必须设置强 `SECRET_KEY`，且不允许 SQLite。

---

## 数据采集与调度

`data_collector/scheduler.py` 使用延迟初始化 collector，避免导入期就因外部数据源失败导致应用不可启动。

调度任务要点：
- 实时行情：每 60 秒
- 兼容层产品价格同步：每 60 秒
- 日 K：每日 16:05
- 分钟 K：每 15 分钟，走 AkShare 分钟线 pipeline
- 品种元数据：每日 02:00
- Tushare 扩展任务：日线、结算、仓单、持仓、涨跌停、周报等，仅在 Tushare pipeline 可用时注册

`DATA_SOURCE`：
- `mock`：开发默认
- `akshare`：真实行情源之一
- `tushare`：需要 `TUSHARE_TOKEN`
- `auto`：尝试真实源 fallback

非生产环境所有真实 collector 失败时可以降级 Mock；生产环境不允许降级 Mock。

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
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
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

后端测试：

```powershell
cd python
$env:SECRET_KEY="test-secret-key"
$env:ENABLE_SCHEDULER="0"
pytest tests -v
```

---

## 测试现状

后端已有 pytest：
- `test_p0_fixes.py`
- `test_phase1_3_integration.py`
- `test_cors_variable.py`
- `test_kline_seeded_api.py`
- `test_comment_validation_and_pagination.py`
- `test_cache_orm_detached.py`
- `test_postgres_upsert_integration.py`
- `test_production_config.py`

前端仍没有自动化测试框架，只有 `frontend/tests/p0-fixes.test.md` 人工检查清单。前端改动后必须至少做类型检查。

---

## 关键环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `SECRET_KEY` | 是 | JWT 签名密钥，生产环境长度至少 32 |
| `DATABASE_URL` | 否 | 默认 `sqlite:///./futures_community.db` |
| `CORS_ORIGINS` | 生产建议必填 | CORS 白名单，兼容旧变量 `ALLOW_ORIGINS` |
| `DATA_SOURCE` | 否 | `mock` / `akshare` / `tushare` / `auto` |
| `TUSHARE_TOKEN` | Tushare 必填 | Tushare Pro Token |
| `ENABLE_SCHEDULER` | 否 | `1` 启用，`0` 禁用 |
| `ENV` | 否 | `development` / `production` |
| `HOST` / `PORT` | 否 | 后端监听地址，默认 `127.0.0.1:8200` |
| `NEXT_PUBLIC_API_BASE` | 前端可选 | 前端请求后端地址 |

注意：`ACCESS_TOKEN_EXPIRE_MINUTES` 在 `.env.example` 中存在，但当前 `config.py` 写死为 24 小时，尚未从环境变量读取。

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
- Redis 服务可以启动，但应用代码当前使用内存缓存。
- `node_modules`、`.next`、`venv`、数据库文件和日志可能在工作区中产生大量噪声，提交时不要顺手纳入。
- 当前仓库可能已有用户或其他助手留下的未提交变更，修改前后都要用 `git status --short` 观察，不要回滚无关改动。

---

## 文档索引

- `README.md`：面向人类的快速开始与功能概览
- `FULLSTACK_REVIEW_AND_ITERATION_PLAN_20260509.md`：前后端整体评审建议与全栈迭代路线
- `DATA_PIPELINE_AND_POSTGRES_GUIDE.md`：PostgreSQL 与数据流水线运维
- `BACKEND_TECH_REVIEW_AND_ITERATION_PLAN_20260505.md`：后端技术评审与计划
- `BACKEND_COMPREHENSIVE_REVIEW_20260505.md`：后端综合评审
- `BACKEND_ITERATION_PLAN_v7_COMPREHENSIVE.md`：综合迭代计划
- `FRONTEND_ITERATION_PLAN_LIGHTWEIGHT_CHARTS.md`：前端图表迭代背景
- `TUSHARE_POSTGRES_VERIFICATION.md`：Tushare + PostgreSQL 验证记录
- `python/tushare_pg_ingest/README.md`：历史数据回填脚本说明

---

*最后更新：2026-05-09，由 AI 助手根据当前代码树与近期迭代结果整理。*
