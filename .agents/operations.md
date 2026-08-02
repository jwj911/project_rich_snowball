<!-- .agents/operations.md — 运维、CI/CD、环境变量与代码风格 -->

## 常用命令速查

### 后端

```powershell
cd python
python -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -r requirements.lock
$env:SECRET_KEY='change-this-to-a-real-secret'
.venv/Scripts/python.exe main.py
```

独立 worker（不启动 FastAPI，只跑 scheduler）：

```powershell
cd python
.venv/Scripts/python.exe worker.py
```

### 前端

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
npx playwright test # E2E 测试；需要后端 8401 和前端 3200
```

Playwright 运行说明：

- `frontend/playwright.config.ts` 在本地复用 `127.0.0.1:3200`，CI 中由 `webServer` 启动前端；
- `auth.setup.ts` 使用开发账号 `trader001/password123`，后端应先完成 SQLite Mock 初始化或 PostgreSQL migration；
- 本地若 Next dev 首次编译超过 120 秒，应先单独访问 `http://127.0.0.1:3200/` 确认 HTTP 已返回，再复跑测试；不要把端口监听但不返回 HTTP 的进程视为服务就绪；
- CI 额外执行 PostgreSQL + Alembic + backend + Chromium smoke，结果以 GitHub Actions 为准。

性能基线：

```powershell
cd frontend
npm run build
npm start
# 另一终端
npm run lighthouse
```

### 后端测试

```powershell
cd python
python -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -r requirements.lock
$env:SECRET_KEY='test-secret-key'
$env:ENABLE_SCHEDULER='0'
.venv/Scripts/python.exe -m pytest tests -v
```

环境校验：

```powershell
.venv/Scripts/python.exe -c 'import sqlalchemy; print(sqlalchemy.__version__)'
# 应输出 >= 2.0.25
```

### Ruff 格式化与检查

```powershell
cd python
ruff check .
ruff format .
```

### 生产发布只读预检

在已注入真实生产配置和发布元数据的受控环境中执行：

```powershell
cd python
.venv/Scripts/python.exe scripts/release_preflight.py --report-path release_preflight_report.json
```

预检固定执行 11 项检查并输出带独立 `trace_id` 的脱敏 JSON。退出码 `0` 表示通过，`1`
表示门禁失败，`2` 表示报告写入失败。命令除写入指定报告外，不连接或修改数据库、Redis、
部署状态及发布清单。CI 使用 placeholder 输入只验证 CLI/报告契约，不得作为生产证据。

### K 线存储与影子分区

容量预检默认只读，只允许写显式报告文件：

```powershell
cd python
.venv/Scripts/python.exe scripts/kline_storage_preflight.py `
  --report-path "$env:TEMP\r8-kline-storage.json"
```

分区规划和迁移演练默认 dry-run：

```powershell
.venv/Scripts/python.exe scripts/manage_kline_partitions.py `
  --shadow-table kline_data_shadow_r8
.venv/Scripts/python.exe scripts/rehearse_kline_partition.py `
  --source-table kline_data `
  --shadow-table kline_data_shadow_rehearsal
```

实际执行必须使用隔离 PostgreSQL，并显式增加 `--apply --confirm`；演练通常同时使用
`--cleanup`。活动表 `kline_data` 不能作为 DDL 目标。R8 不提供 rename/swap 或冷数据删除
命令，完整边界见
[`python/docs/kline_partitioning.md`](../python/docs/kline_partitioning.md)。

### CSP Report-Only 观测

R9 实际暴露的计数器为 `csp_reports_total{outcome}`，固定 outcome 为 `received`、
`accepted`、`sampled`、`rejected`、`rate_limited`、`persist_failed`。初始 PromQL
建议：

```promql
increase(csp_reports_total{outcome="persist_failed"}[5m]) > 0
```

任一持久化失败立即告警，并用安全日志中的 `trace_id` 和异常类型排障，不查询或输出原始报告。
拒绝与限流异常上升可从以下 15 分钟比例开始，业务基线形成后再调整 `10%` 和 `20` 的初始阈值：

```promql
(
  sum(increase(csp_reports_total{outcome=~"rejected|rate_limited"}[15m]))
  /
  clamp_min(sum(increase(csp_reports_total{outcome="received"}[15m])), 1)
  > 0.10
)
and
sum(increase(csp_reports_total{outcome="received"}[15m])) > 20
```

Dashboard 同时展示接受量与非报告业务 HTTP 流量的比例：

```promql
sum(increase(csp_reports_total{outcome="accepted"}[30m]))
/
clamp_min(
  sum(increase(http_requests_total{endpoint!="/api/log/csp-report"}[30m])),
  1
)
```

`accepted` 按报告条目计数，`http_requests_total` 按 HTTP 请求计数，Reporting API 批量会使
二者不具备一一对应关系；该比值只用于同部署、同窗口的趋势对比。接受量突增必须结合部署、
页面流量和 directive 归类排查，不能仅凭绝对报告数判断策略可收紧。本地和 CI synthetic 报告
只验证接收契约，不是生产 SLO；真实完整业务周期报告未归类前不得进入 S2。

## 关键环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `SECRET_KEY` | 是 | — | JWT 签名密钥，生产环境长度至少 32 |
| `DATABASE_URL` | 否 | `sqlite:///./futures_community.db` | 数据库连接串 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 否 | `15` | Access token 过期时间（分钟） |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 否 | `7` | Refresh token 过期时间（天） |
| `CORS_ORIGINS` | 生产必填 | `localhost/127.0.0.1:3000,3200` | 生产只允许显式 HTTPS 来源，禁止通配符、localhost 和 loopback；兼容旧变量 `ALLOW_ORIGINS` |
| `DATA_SOURCE` | 生产必填 | `mock` | `mock` / `akshare` / `tushare` / `auto`；生产预检拒绝 `mock` |
| `TUSHARE_TOKEN` | Tushare 必填 | — | Tushare Pro Token |
| `ENABLE_SCHEDULER` | 否 | `0` | `1` 启用，`0` 禁用（API 默认禁用） |
| `ENV` | 否 | `development` | `development` / `production` |
| `SSE_DEPLOYMENT_MODE` | 生产必填 | 非生产默认 `single` | 生产只接受 `single` 或 `sticky`；不代表已具备跨实例连接管理 |
| `HOST` | 否 | `127.0.0.1` | 后端监听地址 |
| `PORT` | 否 | `8401` | 后端监听端口 |
| `REALTIME_REFRESH_INTERVAL_SECONDS` | 否 | `60` | 实时行情刷新间隔（秒） |
| `CACHE_MAX_SIZE` | 否 | `1024` | 内存缓存最大条目数 |
| `CACHE_DEFAULT_TTL_SECONDS` | 否 | `5` | 内存缓存默认 TTL（秒） |
| `RATE_LIMIT_WINDOW_SECONDS` | 否 | `60` | 限流时间窗口（秒） |
| `RATE_LIMIT_MAX_REQUESTS` | 否 | `100` | 限流窗口内最大请求数 |
| `PIPELINE_COMMIT_BATCH_SIZE` | 否 | `50` | Pipeline 批量提交大小 |
| `CIRCUIT_FAILURE_THRESHOLD` | 否 | `0.5` | 熔断器失败阈值比例 |
| `REDIS_URL` | 生产必填 | — | 缓存及 realtime UTC 时间戳共享标记；运行中不可用时 SSE 每 60 秒有界刷新 |
| `RELEASE_COMMIT` | 发布预检必填 | — | 待发布 Git 提交 |
| `RELEASE_WINDOW_UTC` | 发布预检必填 | — | UTC 时间点或 `start/end` 区间 |
| `RELEASE_OWNER` | 发布预检必填 | — | 发布负责人 |
| `ROLLBACK_OWNER` | 发布预检必填 | — | 回滚负责人 |
| `RELEASE_PREFLIGHT_REPORT_PATH` | 否 | `release_preflight_report.json` | 脱敏预检报告输出路径 |
| `NEXT_PUBLIC_API_BASE` | 前端可选 | `http://127.0.0.1:8401` | 前端请求后端地址 |
| `CSP_REPORT_URL` | 前端可选 | API origin + `/api/log/csp-report` | Report-Only 上报地址；只允许无凭据、query、fragment 的绝对 HTTP(S) URL |
| `CSP_REPORT_SAMPLE_RATE` | 否 | `1` | 合法 CSP 报告确定性采样率，必须为 `[0, 1]` 内有限数 |
| `OPENAI_API_KEY` | AI 可选 | — | OpenAI 兼容 API Key |
| `OPENAI_BASE_URL` | AI 可选 | `https://api.openai.com/v1` | OpenAI 兼容 Base URL |
| `OPENAI_MODEL` | AI 可选 | `gpt-4o-mini` | 对话模型 |
| `CHAT_MAX_HISTORY` | AI 可选 | `20` | 最大对话历史条数 |
| `BCRYPT_ROUNDS` | 否 | `12` | bcrypt 密码哈希轮数 |
| `CORS_MAX_AGE_SECONDS` | 否 | `600` | CORS preflight 缓存时间 |

## 端口说明

- 后端 `python/main.py` 默认监听 `127.0.0.1:8401`，由 `HOST` / `PORT` 环境变量覆盖。
- 前端 `npm run dev` 实际执行 `next dev -H 127.0.0.1 -p 3200`。
- 前端 API 默认值在 `frontend/lib/api/request.ts`：`NEXT_PUBLIC_API_BASE || http://127.0.0.1:8401`。
- CORS 默认允许 `localhost/127.0.0.1` 的 `3000` 和 `3200`。
- `docker-compose.yml` 中 PostgreSQL 映射为 `15432:5432`。
- Redis 映射为 `6379:6379`。

## 开发账号

非生产环境首次初始化会创建：

| 用户名 | 密码 |
|--------|------|
| `trader001` | `password123` |
| `investor_wang` | `password123` |
| `futures_master` | `password123` |

## CI/CD 与容器化

### GitHub Actions

- `.github/workflows/backend-ci.yml`：依赖锁检查 + R7 placeholder preflight + Alembic +
  R8 K 线 PostgreSQL 门禁 + R9 CSP 接收契约 + PostgreSQL pytest/API smoke + Ruff
  check/format + `pip-audit`，pytest-cov 阈值为 40%。
  [R9 Backend CI run 30739553595](https://github.com/jwj911/project_rich_snowball/actions/runs/30739553595)
  成功，PostgreSQL CSP 专项 `21 passed`，远端全量约 `1195 passed, 1 skipped`。
- `.github/workflows/frontend-ci.yml`：`npm ci` → `tsc --noEmit` → ESLint → R9 双 CSP
  响应头门禁 → build → Vitest → Lighthouse；独立 job 执行 PostgreSQL/Alembic/backend、
  R9 认证/刷新/SSE/Bearer 定向浏览器门禁及完整 Chromium Playwright smoke。
  [R9 Frontend CI run 30740784839](https://github.com/jwj911/project_rich_snowball/actions/runs/30740784839)
  成功，Vitest、build、R9 增强版 E2E `3 passed`、全量 Playwright `43 passed` 与
  Lighthouse 均通过。
- R9 实现提交为 `723ba9b949bccf7c96798d2f45388731350eacd3`，本地验证文档提交为
  `37fc8008a74c1b74c48f74aac5e3267c8a29e5b6`，CI 稳定性修复提交为
  `c7a721a04f58caa51860be67d870855663186a14`。本地验证与远端 CI 分别作为本地和远端
  工程证据，均不代表生产部署或生产 SLO；完整业务周期观测未完成，S2/S3 未启动，强制 CSP
  未收紧，`localStorage` access token 风险未关闭。
- Lighthouse 采集 `home` / `products` 命名路由，记录 commit 和 CI 元数据；workflow 会恢复最近的
  `lighthouse-trend-history` artifact，并上传新的趋势/历史/最新 JSON，保留 90 天。
- `.github/workflows/update-calendar.yml`：每年 1 月 1 日自动更新交易日历（cron），也支持手动触发。
- 发布前按 [`docs/release_checklist_20260719.md`](../docs/release_checklist_20260719.md) 执行质量、迁移、权限、备份和回滚检查。
- 每次工程基线或生产发布都在 [`docs/releases/README.md`](../docs/releases/README.md) 下新增记录；工程基线不得替代生产发布验收。

### Dockerfile

`python/Dockerfile`：

- 基于 `python:3.11-slim`
- 创建非 root 用户 `app`
- 健康检查：`curl -f http://localhost:8401/health || exit 1`
- 默认 CMD 为 `uvicorn main:app --host 0.0.0.0 --port 8401`
- 生产建议使用 gunicorn + uvicorn worker

### docker-compose.yml

- `postgres`：PostgreSQL 16-alpine，端口 15432，用户 `futures`/`futures123`
- `redis`：Redis 7-alpine，端口 6379，AOF 持久化
- `backend`：FastAPI 服务，端口 8401，依赖 postgres 和 redis，带健康检查，scheduler 关闭
- `worker`：唯一 scheduler owner；与 backend 显式共享 `REDIS_URL` 和 `SSE_DEPLOYMENT_MODE`

## 代码风格

### Python

- Ruff（line-length 120，target py311）
  - 启用规则：E, W, F, I, N, UP, B, C4, SIM
  - 忽略：E501（由 line-length 控制）
  - Docstring 风格：Google
  - 格式化：双引号字符串，空格缩进
  - mypy：py311，但排除了 `data_collector/`（除 pipeline_tasks 外）、`routers/`、`models.py`、`tests/`、`alembic/` 等目录（SQLAlchemy 1.x 类型误报兼容策略）
  - 配置位置：`python/pyproject.toml`

### 前端

- ESLint（`next/core-web-vitals`），无 Prettier 配置
- Tailwind 自定义颜色：`up`（红色系）、`down`（绿色系）反映中国市场惯例
- Bundle Budget 红线：任意路由 First Load JS 不得超过 180 kB（见 `next.config.js` 注释）
