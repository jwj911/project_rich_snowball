<!-- .agents/project.md — 项目概览、技术栈与目录结构 -->

> 面向 AI 编程助手的项目全景说明。如需操作命令、安全规范或 Agent 细节，请查看同目录下的其他分文档。

## 项目定位

**期货交流社区**（产品名「倍增计划」）是一个前后端分离的期货行情与私密交流社区应用。当前产品形态为“登录后的行情工作台”：用户登录后查看热门期货、筛选品种、进入单品种 K 线复盘、添加云端支撑/阻力位标注、发表评论、记录交易观点、管理模拟持仓与策略、设置价格预警、与 AI 助手及专项 Agent 对话，并在个人工作区汇总自己的研究上下文。

## 当前阶段

- Phase 5「策略优化与性能调优」**已完成**（2026-07-04）。全部子任务：
  - 5-1 系统现状检查与规划
  - 5-2 策略参数优化引擎（参数网格搜索 + 综合评分 + 敏感性矩阵）
  - 5-3 策略信号可视化（K 线叠加买卖信号标记）
  - 5-4 性能优化（回测结果 5 分钟 LRU 缓存 + 缓存 key 哈希）
  - 5-5 监控告警与日志增强（回测/优化失败自动告警 + 结构化日志）
  - 5-6 全量测试 + 提交到 master（历史基线）
- **Agent 系统 Phase 0~2 已完成**（2026-07-04）：DataAgent、TechAnalysisAgent、RiskManagementAgent 已上线，前端 Chat 页支持 8 种模式切换（AI 助手 / 数据助手 / 技术分析 / 风控管理 / 分析流水线 / 回测 / 策略编排 / 因子挖掘），执行过程通过 SSE 流式展示。
- 近期新增：策略工作台（`/strategies`）、策略参数优化（`/strategies/{id}/optimize`）、回测信号可视化（K 线叠加标记）、预警中心（`/alerts`）、Agent 工作台（`/agents`）。
- **当前质量基线（2026-07-19）**：后端本地 `965 passed, 8 skipped, 0 failed`；覆盖率 `71.97%`；前端 Vitest `195 passed, 0 failed`；Python Ruff、TypeScript、ESLint 和 production build 均通过。
- **远程验收**：Backend CI #22 与 Frontend CI #28（run `29670891119`）的 Alembic、PostgreSQL pytest、API smoke、Ruff、`pip-audit`、Chromium Playwright、Vitest 和 Lighthouse 全部通过。
- **当前迭代**：Phase 0、Phase 1 和 Phase 2 已完成，下一阶段进入 Phase 3 文档与发布治理。

## 主要功能模块

- 登录/注册/JWT 鉴权（支持 access token + refresh token 双令牌），主页面均有登录门禁。
- 首页行情工作台：热门品种、领涨观察、30 秒轮询和刷新状态。
- 行情中心：搜索、分类、涨跌筛选，按价格/涨跌幅/成交量排序。
- 品种详情：实时行情、`lightweight-charts` K 线、技术分析、评论、支撑/阻力标注、合约切换（主力/连续/具体合约）。
- 交易观点：用户针对品种发表多空观点，记录目标价、止损价和理由，支持事后复盘标记状态。
- 模拟持仓 / 策略工作台：虚拟交易记录，支持做多/做空、盈亏计算、策略生成与回测跟踪。
- 价格预警 / 预警中心：用户为品种设置 above/below 价格预警，实时行情刷新时自动检测触发。
- AI 助手：用户与大模型对话，自动检索实时行情和交易观点作为上下文。
- **Agent 系统**：按功能能力拆分的专项 Agent（Data / TechAnalysis / RiskManagement），前端 Chat 页支持模式切换与流式执行过程展示。
- 新闻资讯：RSS 源管理与聚合，支持 AI 新闻解读。
- 我的工作区：评论历史、云端价位标注、自选观察入口。
- 运营指标面板：`/metrics` 展示用户数/评论数/采集健康度。
- 数据采集：Mock / AkShare / Tushare，多源 fallback + 熔断器，定时刷新实时行情和 K 线。
- PostgreSQL 历史回填：`python/tushare_pg_ingest/` 下有独立脚本体系。

## 技术栈

| 层级 | 技术 | 版本/说明 |
|------|------|-----------|
| 前端框架 | Next.js App Router | 14.2.35，`output: 'standalone'` |
| 前端 UI | React | 18.2.0，TypeScript 5.3.3 |
| 前端样式 | Tailwind CSS | 3.4.1，自定义暗色界面，上涨红色/下跌绿色 |
| 字体/图标 | geist / lucide-react | ^1.7.2 / ^0.312.0 |
| K 线图 | lightweight-charts | ^5.2.0 |
| 数据获取 | SWR | ^2.4.1 |
| 表单 | react-hook-form | ^7.76.0 |
| 消息提示 | sonner | ^2.0.7 |
| 性能采集 | web-vitals | ^5.2.0 |
| 前端测试 | Vitest + @testing-library/react + jsdom | Vitest ^4.1.6，约 35 个测试/辅助文件 |
| E2E 测试 | Playwright | ^1.60.0，7 个文件（auth.setup.ts + 6 个 spec） |
| 性能基线 | Lighthouse | ^13.3.0，`npm run lighthouse` |
| 后端框架 | Python + FastAPI | Python >=3.11，FastAPI 0.136.3 |
| 后端服务器 | Uvicorn | 0.30.6 |
| ORM | SQLAlchemy | 2.0.25 |
| 数据库 | SQLite / PostgreSQL | SQLite 开发零配置；PG 16 通过 compose 提供，映射端口 15432 |
| **迁移** | Alembic | 1.13.1，当前 59 个迁移文件；head 为 `f7a8b9c0d1e2` |
| 认证 | JWT + OAuth2 密码流 | PyJWT 2.13.0，passlib bcrypt，access token 默认 15 分钟，refresh token 默认 7 天 |
| 数据校验 | Pydantic v2 | 2.9.0 |
| 数据采集 | Mock / AkShare / Tushare | `DATA_SOURCE` 控制，非生产可降级 Mock |
| 定时任务 | APScheduler | BackgroundScheduler |
| 缓存 | Redis 优先 + 内存 LRU 降级 | `services/cache.py` 线程安全实现；Redis 可接入，内存作为降级 |
| 可观测性 | Prometheus 风格指标 + structlog 结构化日志 | `services/metrics.py` + `services/logging_config.py` |
| 限流 | 内存/Redis 滑动窗口 | `middleware/rate_limit.py`，覆盖所有写入端点 |
| **Agent 技术指标** | **numpy + pandas** | **后端纯 numpy/pandas 指标库（`python/lib/technical_indicators.py`）：SMA/EMA/RSI/MACD/BOLL/KDJ/ATR/CCI/OBV/ADX/WR/量比 + 万因子精选27个** |
| **因子引擎** | **services/agent/factor_engine + lib/technical_indicators.py** | **万因子精选27个（L1 预置）+ 用户自定义DSL（L2 动态）** |
| **Agent LLM 调用** | **OpenAI 兼容 API** | **复用 `services/ai_chat.py`，Agent 通过 `services/agent/llm_client.py` 统一调用** |

## 目录结构

```text
project_rich_snowball/
├── frontend/
│   ├── app/                        # 15 个页面路由
│   │   ├── layout.tsx              # 根布局，包裹 AuthProvider + ErrorBoundary + WebVitalsReporter + Toaster
│   │   ├── page.tsx                # 行情工作台，需登录
│   │   ├── products/page.tsx       # 行情中心，搜索/筛选/排序
│   │   ├── products/[id]/page.tsx  # 品种详情，K 线/评论/合约切换/标注/合约历史
│   │   ├── workspace/page.tsx      # 我的工作区
│   │   ├── my-comments/page.tsx    # 当前用户评论历史
│   │   ├── metrics/page.tsx        # 运营指标面板
│   │   ├── news/page.tsx           # 新闻资讯
│   │   ├── settings/page.tsx       # 个人设置
│   │   ├── chat/page.tsx           # AI 助手对话（8 种模式切换）
│   │   ├── portfolio/page.tsx      # 模拟持仓（视图保留，部分能力并入策略工作台）
│   │   ├── opinions/page.tsx       # 交易观点
│   │   ├── strategies/page.tsx     # 策略工作台
│   │   ├── alerts/page.tsx         # 预警中心
│   │   ├── agents/page.tsx         # Agent 工作台
│   │   └── agents/detail/page.tsx  # Agent 任务详情
│   ├── components/                 # 约 58 个组件文件
│   ├── hooks/                      # 15 个自定义 hook
│   ├── lib/                        # API 客户端、工具函数、常量
│   ├── tests/                      # Vitest 单元测试
│   ├── e2e/                        # Playwright E2E 测试
│   ├── next.config.js / tailwind.config.js / tsconfig.json / vitest.config.ts / playwright.config.ts
│   └── package.json
├── python/
│   ├── main.py                     # FastAPI 入口
│   ├── config.py                   # 环境变量与配置
│   ├── dependencies.py             # get_db、JWT 用户解析
│   ├── models.py                   # SQLAlchemy 模型，33 张表
│   ├── schemas.py                  # Pydantic v2，79 个请求/响应模型
│   ├── errors.py                   # ErrorCode 统一业务错误码
│   ├── routers/                    # 24 个领域路由
│   ├── services/                   # 业务服务层
│   │   ├── agent/                  # Agent 系统核心模块
│   │   ├── backtest/               # 回测引擎
│   │   └── domain/                 # 领域服务层
│   ├── data_collector/             # 在线采集、清洗、upsert、调度器
│   ├── lib/                        # 技术指标库
│   ├── middleware/                 # 限流、API 版本映射
│   ├── tests/                      # pytest 测试
│   ├── alembic/                    # 数据库迁移
│   └── docs/                       # 架构决策、运维手册、API 契约
├── docker-compose.yml
├── .env.example
├── .github/workflows/              # CI/CD
└── README.md / AGENTS.md
```
