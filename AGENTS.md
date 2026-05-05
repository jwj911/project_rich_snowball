# AGENTS.md — 期货交流社区

> 本文档面向 AI 编程助手。如果你正在阅读本文件，说明你对本项目一无所知。下文将提供足够的信息，让你安全、有效地修改代码。

---

## 项目概述

**期货交流社区**是一个前后端分离的全栈 Web 应用，用于展示中国期货品种实时行情数据，并支持用户注册、登录、评论交流。

主要功能：
- 首页展示热门期货品种卡片，30 秒轮询实时价格
- 品种详情页展示 K 线图（自研 SVG 蜡烛图）、支撑位/阻力位、用户评论
- 用户系统：注册、登录（JWT）、个人评论历史
- 数据采集：定时刷新实时行情、同步日 K 线

---

## 技术栈

| 层级 | 技术 | 版本/说明 |
|------|------|-----------|
| 前端 | Next.js (App Router) | 14.1.0，React 18.2，TypeScript 5.3 |
| 前端样式 | Tailwind CSS | 3.4.1，自定义暗色主题 |
| 前端图标 | lucide-react | ^0.312.0 |
| 后端 | Python + FastAPI | 3.11 + 0.109 |
| 后端服务器 | Uvicorn | 0.27.0 |
| ORM | SQLAlchemy | 2.0.25 |
| 数据库 | SQLite（默认） | `futures_community.db`，开发零配置 |
| 数据库（可选）| PostgreSQL | 16，通过 docker-compose 提供 |
| 迁移工具 | Alembic | 1.13.1 |
| 认证 | JWT + OAuth2 密码流 | PyJWT 2.8.0，bcrypt 哈希 |
| 数据采集 | AkShare / MockCollector | 模拟数据用于开发测试 |
| 定时任务 | APScheduler | 3.10+，BackgroundScheduler |
| 缓存 | 内存字典（默认 5s TTL）| Redis 预留但未接入代码 |

---

## 目录结构

```
project_rich_snowball/
├── frontend/                    # Next.js 前端（端口 3000）
│   ├── app/                     # App Router 页面
│   │   ├── layout.tsx           # 根布局（zh-CN、暗色背景）
│   │   ├── page.tsx             # 首页：热门品种网格 + 轮询
│   │   ├── products/
│   │   │   ├── page.tsx         # 全部品种列表（支持排序）
│   │   │   └── [id]/page.tsx    # 品种详情：K 线、评论、支撑/阻力
│   │   ├── my-comments/page.tsx # 当前用户评论历史
│   │   └── globals.css          # Tailwind 导入、JetBrains Mono 字体
│   ├── components/
│   │   ├── Navbar.tsx           # 顶部导航 + 登录/注册弹窗
│   │   └── KlineChart.tsx       # 自研 SVG 蜡烛图（无外部图表库）
│   ├── lib/
│   │   └── api.ts               # 统一 API 客户端类（含 token 管理）
│   ├── tests/
│   │   └── p0-fixes.test.md     # 前端 P0 测试检查清单（人工）
│   ├── package.json
│   ├── next.config.js           # 仅开启 reactStrictMode
│   ├── tsconfig.json            # 标准 Next.js 配置，路径别名 `@/*`
│   ├── tailwind.config.js       # 自定义颜色：up/down/card/background
│   └── postcss.config.js
│
├── python/                      # FastAPI 后端（端口 8000）
│   ├── main.py                  # 应用入口：lifespan、CORS、路由挂载
│   ├── config.py                # 环境变量加载（.env），SECRET_KEY 强制校验
│   ├── models.py                # SQLAlchemy ORM：8 张表定义
│   ├── schemas.py               # Pydantic v2：请求/响应模型、XSS 过滤
│   ├── dependencies.py          # get_db()、JWT 用户解析、auth 依赖
│   ├── utils.py                 # bcrypt 密码哈希、JWT token 生成
│   ├── requirements.txt         # 12 项核心依赖
│   ├── Dockerfile               # Python 3.11 slim，暴露 8000
│   ├── alembic.ini              # 迁移配置（默认 SQLite）
│   ├── futures_community.db     # SQLite 数据库文件（自动生成）
│   │
│   ├── routers/                 # FastAPI 路由模块（按领域拆分）
│   │   ├── auth.py              # 注册、登录（OAuth2）、/me
│   │   ├── products.py          # /api/products（兼容层）
│   │   ├── comments.py          # /api/comments（需登录）
│   │   ├── varieties.py         # /api/varieties（新品种主 API）
│   │   ├── kline.py             # /api/kline/{symbol}
│   │   └── realtime.py          # /api/realtime/{symbol}（带缓存）
│   │
│   ├── data_collector/          # 数据流水线
│   │   ├── base.py              # BaseCollector 抽象接口
│   │   ├── mock_collector.py    # 随机游走生成 10 个品种的 OHLCV
│   │   ├── akshare_collector.py # 接入 akshare 真实行情（预留）
│   │   ├── cleaner.py           # 数据校验：OHLC 检查、去重、类型转换
│   │   ├── upsert.py            # SQLite upsert 实时行情、K 线批量插入
│   │   ├── scheduler.py         # 30s 实时刷新、30s 兼容同步、日 K 线 16:05
│   │   ├── init_mock_data.py    # 首次运行种子：10 品种、3 用户、5 评论
│   │   └── init_varieties.py    # 品种元数据初始化
│   │
│   ├── services/
│   │   └── cache.py             # 内存缓存（TTL 默认 5 秒）
│   │
│   ├── tests/
│   │   ├── test_p0_fixes.py     # 安全/配置回归测试（254 行）
│   │   └── test_phase1_3_integration.py  # Schema/API 集成测试（272 行）
│   │
│   └── alembic/                 # 数据库迁移脚本目录
│       ├── env.py
│       └── versions/
│
├── src/main/java/...            # Java 包结构预留，**无任何实质代码**
│
├── docker-compose.yml           # PostgreSQL 16 + Redis 7（后端服务已注释）
├── .env.example                 # 环境变量模板
├── .env                         # 当前生效的环境变量（不在版本控制中）
└── README.md                    # 面向人类的快速开始指南
```

---

## 构建与运行命令

### 后端

```bash
cd python

# 1. 创建虚拟环境（Windows）
python -m venv venv
venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 确保项目根目录有 .env 文件（可复制 .env.example）
#    必须设置 SECRET_KEY，否则启动报错 ValueError

# 4. 启动服务
python main.py
# 输出：Uvicorn running on http://0.0.0.0:8000
# 首次启动会自动 init_db() + init_mock_data() + start_scheduler()
```

后端 API 文档：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 前端

```bash
cd frontend

# 1. 安装依赖
npm install

# 2. 启动开发服务器
npm run dev
# 输出：localhost:3000

# 其他命令
npm run build      # 生产构建
npm run lint       # ESLint
npx tsc --noEmit   # TypeScript 类型检查（无 emit）
```

### 数据库迁移（Alembic）

```bash
cd python
alembic revision --autogenerate -m "描述"
alembic upgrade head
```

### Docker Compose（可选基础设施）

```bash
# 启动 PostgreSQL + Redis（后端服务在 compose 中已注释掉）
docker-compose up -d postgres redis
```

---

## 测试说明

### 后端测试

所有后端测试使用 **pytest**，测试前必须设置 `SECRET_KEY` 环境变量。

```bash
cd python
pip install pytest httpx

# P0 安全回归测试
SECRET_KEY=test-secret-key pytest tests/test_p0_fixes.py -v

# 阶段一/三集成测试（Schema + API 行为 + 向后兼容）
SECRET_KEY=test-secret-key pytest tests/test_phase1_3_integration.py -v
```

**测试覆盖重点**：
- `test_p0_fixes.py`：SECRET_KEY 强制校验、bcrypt 哈希、XSS 过滤、JWT 过期/无效处理、注册→登录→评论端到端流程
- `test_phase1_3_integration.py`：9 张业务表存在性、索引、唯一约束、外键关系、旧 API 兼容

### 前端测试

目前**无自动化测试框架**。`frontend/tests/p0-fixes.test.md` 是一份人工检查清单。

---

## 代码风格指南

### Python 后端

- **导入顺序**：标准库 → 第三方库 → 本项目模块
- **数据库会话**：一律使用 `dependencies.get_db()`（yield + finally close），禁止手动 `SessionLocal()` 后不关闭
- **路由组织**：每个领域一个 `APIRouter` 文件，在 `main.py` 中统一 `include_router`
- **模型双轨制**：
  - `ProductDB` + `/api/products/*` 是**旧兼容层**，供现有前端页面调用
  - `VarietyDB` / `RealtimeQuoteDB` / `KlineDataDB` + `/api/varieties`、`/api/realtime`、`/api/kline` 是**新数据层**
  - `scheduler.py` 每 30 秒将 `realtime_quotes` 同步回 `products`，保证旧页面数据新鲜
- **安全**：
  - 密码必须用 `utils.hash_password()`（bcrypt），禁止明文或 SHA256
  - 用户输入（评论等）用 Pydantic `field_validator` + `html.escape()` 做 XSS 过滤
  - JWT 解码捕获 `PyJWTError`，禁止裸 `except:`
- **异常处理**：数据采集中允许单品种失败继续下一品种；API 层返回合适的 HTTP 状态码

### TypeScript 前端

- **组件类型**：所有页面和组件使用 `'use client'` + React Hooks（useState、useEffect）
- **API 调用**：禁止直接 `fetch`，统一通过 `lib/api.ts` 中的 `api` 实例
- **轮询模式**：首页和品种列表使用 `setInterval(..., 30000)`，组件卸载时 `clearInterval`
- **颜色语义**：中国市场惯例 —— `up` = 红色（`#ef4444`），`down` = 绿色（`#22c55e`）
- **暗色主题**：全局背景 `background: #0f172a`，卡片 `card: #1e293b`

---

## 关键配置与环境变量

项目根目录的 `.env` 文件（复制 `.env.example` 后修改）：

| 变量 | 必需 | 说明 |
|------|------|------|
| `SECRET_KEY` | ✅ | JWT 签名密钥，**生产环境必须修改** |
| `DATABASE_URL` | ✅ | SQLite 默认 `sqlite:///./futures_community.db`；切 PG 时改 `postgresql://...` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ❌ | JWT 过期时间，默认 1440（24 小时） |
| `ALLOW_ORIGINS` | ❌ | CORS 白名单，默认 `http://localhost:3000,http://127.0.0.1:3000` |
| `REDIS_URL` | ❌ | 留空则使用内存缓存 |
| `REALTIME_INTERVAL` | ❌ | 实时行情刷新间隔（秒），默认 30 |
| `ENABLE_SCHEDULER` | ❌ | `1` 启用定时任务（默认），`0` 禁用 |

**注意**：`python/config.py` 会在导入时从 `.env` 加载变量；若 `SECRET_KEY` 未设置，直接抛出 `ValueError`。

---

## 安全注意事项

1. **SECRET_KEY**：生产环境必须使用强随机字符串，且不可泄露。
2. **密码存储**：系统已统一使用 bcrypt（带随机盐），旧代码中的 SHA256 必须替换。
3. **XSS**：评论内容通过 Pydantic 自动转义 HTML 实体（`<script>` → `&lt;script&gt;`），长度限制 1~2000 字符。
4. **CORS**：后端已配置 `allow_origins`，生产环境应收紧为前端真实域名。
5. **数据库连接**：SQLite 开发时使用 `check_same_thread=False`；生产切 PostgreSQL 时移除该参数。
6. **Docker Compose**：`backend` 服务当前被注释，直接启用前需确认 `SECRET_KEY` 已通过环境变量注入。

---

## 开发账号（首次启动自动创建）

| 用户名 | 密码 |
|--------|------|
| `trader001` | `password123` |
| `investor_wang` | `password123` |
| `futures_master` | `password123` |

---

## 常见陷阱

- **导入 `main.py` 前未设置 `SECRET_KEY`**：任何导入 `config.py` 的测试或脚本都会立即报错。测试文件顶部必须有 `os.environ.setdefault("SECRET_KEY", "...")`。
- **`init_data.py` 已废弃**：README 中提到的 `python/init_data.py` 数据模型与当前 `models.py` 不兼容，如需使用请手动调整。
- **Java 目录为空**：`src/main/java/` 仅为预留包结构，不存在任何 Java 后端代码。
- **Redis 未接入**：`docker-compose.yml` 中启动了 Redis，但后端代码中 Redis 依赖已注释（`# redis>=5.0.0`），实际使用内存缓存。
- **定时任务控制**：后台调度器仅在 lifespan 中启动；设置 `ENABLE_SCHEDULER=0` 可禁用，方便纯 API 测试。

---

## 文档索引

项目根目录包含大量设计/评审文档，按需查阅：

- `README.md` — 面向新成员的快速开始
- `DATA_PIPELINE_DESIGN.md` — 数据流水线 v2.0 架构设计
- `BACKEND_ITERATION_PLAN*.md` / `BACKEND_REVIEW_REPORT*.md` — 迭代计划与代码评审记录
- `TEST_PLAN*.md` / `TEST_CASES.md` — 测试策略与用例

---

*最后更新：由 AI 助手根据项目实际代码生成。*
