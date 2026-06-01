# 期货交流社区

一个前后端分离的期货行情与私密交流社区应用。前端提供登录后的行情工作台、品种筛选、K 线复盘、支撑/阻力标注和个人工作区；后端提供认证、评论、实时行情、K 线、健康检查，以及 Mock / AkShare / Tushare 数据采集流水线。

---

## 当前状态

- 前端：Next.js 14 App Router，默认开发地址 `http://127.0.0.1:3200`
- 后端：FastAPI，默认开发地址 `http://127.0.0.1:8200`
- 数据库：开发可用 SQLite；PostgreSQL 16 通过 `docker-compose.yml` 提供
- K 线：前端使用 `lightweight-charts`，后端支持 `1m/5m/15m/30m/1h/1d/1w`
- 访问控制：主要页面需要登录，未登录时显示登录引导
- 新闻资讯：RSS 源管理与聚合，admin 可配置源，登录用户可浏览
- 交易观点/日记：用户针对品种发表多空观点，记录目标价、止损价和理由，支持事后复盘标记状态

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 14.2.35 + React 18.2 + TypeScript 5.3 + Tailwind CSS 3.4 |
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
├── frontend/
│   ├── app/                     # 页面路由：/、/products、/products/[id]、/workspace、/my-comments、/opinions、/news
│   ├── components/              # 布局、认证、行情、工作区、UI 组件
│   ├── hooks/useMarketPolling.ts# 30 秒行情轮询与刷新状态
│   └── lib/                     # API 客户端与格式化工具
│
├── python/
│   ├── main.py                  # FastAPI 应用入口，默认 127.0.0.1:8200
│   ├── config.py                # .env 加载、安全配置、生产环境约束
│   ├── models.py                # SQLAlchemy 模型
│   ├── routers/                 # auth/comments/varieties/kline/realtime/health/price-levels/settings/news
│   ├── data_collector/          # 在线采集流水线与调度器
│   ├── tushare_pg_ingest/       # 独立 PostgreSQL 历史数据回填脚本
│   ├── scripts/                 # 一次性验证/采集辅助脚本
│   ├── tests/                   # pytest 回归与集成测试
│   └── alembic/                 # 数据库迁移
│
├── docker-compose.yml           # PostgreSQL 16 + Redis 7
├── .env.example                 # 环境变量模板
├── FULLSTACK_REVIEW_AND_ITERATION_PLAN_20260509.md # 全栈评审与迭代路线
├── AGENTS.md                    # AI 编程助手上下文
└── src/main/java/               # 预留目录，目前无 Java 后端
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
ENV=development
HOST=127.0.0.1
PORT=8200
```

说明：
- 生产环境必须使用长度至少 32 的 `SECRET_KEY`，且不能使用 SQLite。
- 后端优先读取 `CORS_ORIGINS`，也兼容旧变量 `ALLOW_ORIGINS`。
- 前端 API 地址由 `NEXT_PUBLIC_API_BASE` 控制，代码默认是 `http://127.0.0.1:8200`。
- 若使用 `DATA_SOURCE=tushare`，需要提供 `TUSHARE_TOKEN`。

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
- API: `http://127.0.0.1:8200`
- Swagger UI: `http://127.0.0.1:8200/docs`
- ReDoc: `http://127.0.0.1:8200/redoc`
- 健康检查: `http://127.0.0.1:8200/health/ready`

启动时会执行：
- `init_db()`：非生产环境自动建表，SQLite 启用 WAL
- `init_varieties()`：初始化/更新品种元数据
- `init_mock_data()`：非生产环境插入开发账号和示例评论
- `start_scheduler()`：按配置启动实时行情、K 线与扩展数据采集

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

支撑/阻力标注通过 `/api/price-levels` 同步后端数据库存储，`localStorage` 仅作为降级缓存。前端错误与 Web Vitals 自动上报到后端 `/api/log/frontend`。

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

前端已配置 Vitest + Playwright 自动化测试（30 files / 179 tests），并配有 `.github/workflows/frontend-ci.yml` 在 PR 时自动执行 lint + build + test + Lighthouse。修改前端后至少运行：

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

Tushare 历史回填脚本位于 `python/tushare_pg_ingest/`，包含日线、周/月线、结算、仓单、持仓、涨跌停、主力映射、周度统计等入口。详见 [python/tushare_pg_ingest/README.md](python/tushare_pg_ingest/README.md)。

---

## 常见注意事项

- `python/init_data.py` 已不是当前主流程的一部分，启动初始化在 `data_collector/init_mock_data.py` 和 `init_varieties.py`。
- `docker-compose.yml` 中 backend 服务仍是注释状态，默认只启动 PostgreSQL 和 Redis。
- 缓存层已实现 Redis 优先 + 内存 LRU 降级，生产环境建议强制 Redis。
- `DATA_SOURCE=auto` 或真实数据源初始化失败时，非生产环境会降级到 Mock；生产环境不允许降级 Mock。
- 当前 Git 工作区可能包含 `.next`、`node_modules`、`venv` 等生成物变更，提交前需要谨慎筛选。
