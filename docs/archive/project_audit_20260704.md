# 项目全面审计报告 — `project_rich_snowball`

> **历史归档（2026-07-19）**：本报告对应 2026-07-04 的项目状态，已由当前审计计划取代。当前状态请查看 [`../iteration_plan_20260718_project_audit.md`](../iteration_plan_20260718_project_audit.md)。
>
**审计日期:** 2026-07-04 | **总提交数:** 210 → 214 (已迭代) | **Python 文件:** ~280 个 | **前端 TS/TSX 文件:** ~173 个

---

## 修复进度总览 (2026-07-04 迭代)

| 优先级 | 已完成 | 未完成 |
|--------|--------|--------|
| P0 | B1 (死代码) | A1 (Tushare token — 明确跳过) |
| P1 | B2 (重复 model_config), B3 (agents 测试), B4 (PG SQL) | — |
| P2 | B5 (init_db 统一), ALL1 (pre-commit) | B6, B7, F1, F2 |
| P3 | — | B8–B14, F3 |

详见 [§八 Action Items](#八改进建议优先级-action-items)。

---

## 一、项目概况

| 维度 | 后端 | 前端 |
|------|------|------|
| 语言/框架 | Python 3.12 + FastAPI 0.136 | TypeScript + Next.js 14.2 (App Router) |
| 数据库 | SQLAlchemy 2.0 + SQLite/PostgreSQL 16 | — |
| 测试 | pytest (63 文件, 523 passed) | Vitest (37 文件) + Playwright (6 spec) |
| CI/CD | GitHub Actions (backend + frontend) | GitHub Actions |
| 代码质量 | Ruff + mypy | ESLint |
| 迁移 | Alembic (53 个迁移文件) | — |

---

## 二、需立即处理的问题 (CRITICAL/HIGH)

### 🔴 1. 本地 `.env` 含真实 Tushare API Token

`D:\Code\project_rich_snowball\.env` 第 18 行包含真实的 Tushare API token。好消息是该文件已在 `.gitignore` 中（第 54 行: `.env`），经确认 **未** 被 git 追踪。但依然建议：
- 在 Tushare 后台轮换该 token，确保即使曾经短暂暴露也不会被滥用
- 确认 `.env.example` 模板中没有残留真实值

### 🟠 2. ~~`main.py` 存在死代码~~ ✅ 已修复 (#3f4627ae)

`python/main.py:112-115` — `_error_response` 函数中第 111 行 `return` 之后的第 112-115 行是不可达代码，是重构遗留物：

```python
return JSONResponse(content=content, status_code=status_code, **kwargs)
return JSONResponse(          # ← 永远不会执行
    status_code=status_code,
    content=content,
)
```

### 🟠 3. ~~`schemas.py` 重复的 `model_config`~~ ✅ 已修复 (#3f4627ae)

`python/schemas.py:204-206` — `VarietyWithQuoteResponse` 类中 `model_config = ConfigDict(from_attributes=True)` 被定义了两次。

### 🟠 4. `eval()` 沙箱风险

`python/services/agent/factor_engine/dsl.py:314-318` — `evaluate_factor` 使用 `compile()` + `eval()` 执行因子公式。虽然有 AST 白名单 (`_ALLOWED_AST_NODES`) 和 `{"__builtins__": {}}` 限制，但 `ast.Call` 在白名单中，理论上存在沙箱逃逸可能。测试代码已覆盖 `__import__('os').system('ls')` 攻击向量，当前防护需持续审计。

---

## 三、数据层问题

### 🟠 5. 数据摄入静默丢数据

`python/data_collector/upsert.py` — `insert_kline_bulk()` 在 `contract_code` 无法匹配到 `FutContractDB` 时静默丢弃该行，仅打 WARNING 日志。即如果合约元数据未先入库，对应的 K 线数据就会丢失。

**修复建议:** 将未匹配的 `contract_code` 收集后写入死信表或返回给调用方，由上层决定是否重试/告警。

### 🟠 6. `varieties.contract_code` 缺少唯一约束

`python/models.py:189` — 模型定义中 `contract_code` 设置了 `unique=True`，但迁移 `2f4b824f1162` 创建的是 **非唯一索引** `ix_varieties_contract_code`。模型定义与数据库实际 schema 不一致。

**修复建议:** 创建新迁移添加唯一约束，或确认业务上不需要唯一约束后修正模型定义。

### 🟠 7. `FutTradeFeeDB` 仍使用 Float

`python/models.py:717-731` — 在其他价格表都已迁移到 `Numeric` 之后，`FutTradeFeeDB` 仍有多列使用 `Float`，存在浮点精度风险。

**修复建议:** 创建迁移将 `FutTradeFeeDB` 的价格列统一改为 `Numeric`。

### 🟠 8. 多表缺少行级数据溯源

`kline_data` 和 `fut_daily_data` 表没有 `data_source` 列（`realtime_quotes` 有），无法追踪每条数据记录的来源。

**修复建议:** 为 `kline_data` 和 `fut_daily_data` 添加 `data_source` 列。

### 🟠 9. ~~`init_db()` 与 Alembic 双路径~~ ✅ 已修复 (#02a9771)

`python/models.py:127-135` — 开发环境使用 `Base.metadata.create_all()` 直接建表，生产环境使用 `alembic upgrade head`。这已经导致过 schema 漂移（迁移 `52512a652797` 修复了 Float vs Numeric 问题）。

**修复建议:** 所有环境统一走 `alembic upgrade head`，废弃 `init_db()` 中的 `create_all` 路径。

**✅ 已修复:** 生产环境走 Alembic，非生产保留 create_all 快速建表（历史迁移含 PG 特有语法，SQLite 无法执行）。

---

## 四、代码质量问题

### 🟡 10. 异常静默吞没 (7 处)

| 文件 | 行号 | 问题 |
|------|------|------|
| `python/models.py` | 77-79 | `except Exception: pass` — 连接池指标获取失败静默忽略 |
| `python/services/agent/risk_management_agent.py` | 128-129 | DB 查询失败完全静默 |
| `python/services/news_fetcher.py` | 36, 205, 220 | RSS 抓取错误完全静默 |
| `python/tushare_pg_ingest/fetch_zz1000_option_spot.py` | 92-93 | 期权数据抓取静默失败 |
| `python/scripts/import_factor_pack.py` | 383 | 导入失败静默跳过 |

**修复建议:** 最低限度加 `logger.exception()` 记录完整 traceback，关键路径应考虑重试或告警。

### 🟡 11. ~~PostgreSQL 不兼容的 SQL~~ ✅ 已修复 (#3f4627ae)

`python/services/agent/risk_management_agent.py:98` — `WHERE v.is_active = 1` 在 SQLite 中有效，但在 PostgreSQL 中应写为 `WHERE v.is_active IS TRUE`。

**✅ 已修复:** 改为 `WHERE v.is_active IS TRUE`。

### 🟡 12. Redis 客户端全局状态无锁保护

`python/services/redis_client.py:25-28` — `_redis_client`, `_redis_available`, `_redis_last_check` 是模块级全局变量，无同步机制。在多 worker 模式下不构成实际问题，但在线程模式下存在竞态条件。

### 🟡 13. 重复的 IP 检查逻辑

`python/middleware/rate_limit.py:77` 和 `python/routers/health.py:18` — `_is_trusted_proxy` 和 `_is_trusted_health_client` 有相似逻辑但独立维护。

**修复建议:** 提取为 `utils.py` 中的公共函数 `is_trusted_client()`。

### 🟡 14. `PriceLevelBatchItem` 与 `PriceLevelCreate` 完全重复

`python/schemas.py:258` vs `python/schemas.py:403` — 两者字段完全相同，代码注释承认这是"有意为之的语义一致性"，但维护负担翻倍。

### 🟡 15. 类型标注债务

12+ 处 `# type: ignore` 注释散布在代码中。`pyproject.toml` 中 mypy 排除了 `models.py`, `routers/`, `tests/`, `alembic/`, `scripts/`, `data_collector/` 等大量目录。

---

## 五、测试与 CI 评估

### ✅ 做得好的
- **后端 523 个测试全部通过**，零失败零跳过
- CI 已配置完整：后端 CI 含 migration → test → lint → pip-audit；前端 CI 含 typecheck → lint → build → test → Lighthouse
- 测试覆盖了安全维度 (CSRF, CORS, 密码强度, 限流)
- 前端有 E2E 测试 (Playwright, 6 个 spec)
- 测试数据工厂 (`frontend/tests/fixtures/index.ts`) 设计良好

### 🟡 需改进

| 缺口 | 影响 |
|------|------|
| 无 pre-commit hooks | 脏代码可以直接提交 | ✅ 已安装 (#4288441) |
| `tests/` 目录被 Ruff 和 mypy 排除 | 测试代码本身质量无保障 |
| 无覆盖率门槛执行 | 虽然有 `--cov-fail-under=30` 但门槛偏低 |
| `routers/agents.py` 无测试 | Agent API 是核心功能 | ✅ 已补齐 21 用例 (#e9558cd) |
| `data_collector/` 大部分无测试 | 数据管道是命脉 |
| 9/11 前端页面无页面级测试 | 策略工作台(895行)等大页面无覆盖 |
| 无迁移测试 | 53 个迁移的前向/后向兼容性未验证 |
| 无压力/负载测试 | 不确定系统承载上限 |

---

## 六、文档与架构

### ✅ 优势
- 文档非常完善：`AGENTS.md` (58KB), API 参考, 架构审计, 迭代路线图, 数据管道指南
- 代码组织清晰：routers → services/domain → repositories 分层合理
- Git 提交遵循 Conventional Commits 规范
- Repository 模式 + 依赖注入
- 缓存层设计完善 (Redis + LRU 双级, 防雪崩/穿透/击穿)
- 熔断器保护外部 API 调用
- 结构化日志 (structlog) + Prometheus 指标

### 🟡 可改进
- `models.py` 单文件包含全部 33 个模型 (1015 行)，建议按领域拆分
- `data_tools.py` (968 行) 是最大的单文件，建议拆分
- 前端 `strategies/page.tsx` (895 行) 和 `alerts/page.tsx` (514 行) 过大
- `AGENTS.md` (58KB) 过于庞大，建议拆分为主题索引 + 子文档

---

## 七、安全评估

| 检查项 | 状态 |
|--------|------|
| 硬编码密钥在 VCS 中 | ⚠️ `.env` 在 `.gitignore` 中但含真实 token (未入库) |
| CI 中硬编码密码 | ⚠️ `backend-ci.yml` 含 `futures123` (CI 隔离, 风险可控) |
| SQL 注入 | ✅ 参数化查询为主，Agent SQL 工具有白名单 + 验证 |
| XSS 防护 | ✅ `sanitize_html_text()` 对所有用户文本做 HTML 转义 |
| CSRF 防护 | ✅ 有 CSRF 中间件 + 测试 |
| 限流 | ✅ 有 IP/用户级限流中间件 |
| `eval()` 使用 | ⚠️ 因子 DSL 中使用，有沙箱但需持续审计 |
| 密码存储 | ✅ bcrypt |
| JWT | ✅ 有刷新令牌轮换机制 |
| 依赖漏洞扫描 | ✅ CI 中 `pip-audit` |

---

## 八、改进建议优先级 (Action Items)

| 优先级 | 编号 | 建议 | 涉及端 | 工作量 | 状态 |
|--------|------|------|--------|--------|------|
| **P0** | A1 | 轮换 `.env` 中的 Tushare token | 运维 | 5 分钟 | ⏭️ 跳过 |
| **P0** | B1 | 删除 `main.py:112-115` 死代码 | 后端 | 1 分钟 | ✅ #3f4627ae |
| **P1** | B2 | 修复 `schemas.py:206` 重复 `model_config` | 后端 | 1 分钟 | ✅ #3f4627ae |
| **P1** | B3 | 补 `routers/agents.py` 测试 | 后端 | 2-4 小时 | ✅ #e9558cd2 |
| **P1** | B4 | 修复 PostgreSQL 不兼容 SQL (`is_active = 1` → `IS TRUE`) | 后端 | 5 分钟 | ✅ #3f4627ae |
| **P2** | B5 | 统一 `init_db()` 与 Alembic，消除双路径 schema 管理 | 后端 | 2 小时 | ✅ #02a9771 |
| **P2** | ALL1 | 安装 pre-commit hooks (Ruff + ESLint) | 全栈 | 1 小时 | ✅ #4288441 |
| **P2** | B6 | 为 `data_collector/` 补齐测试 | 后端 | 4-8 小时 | 🔲 |
| **P2** | B7 | 拆分 `models.py` 按领域 | 后端 | 4 小时 | 🔲 |
| **P2** | F1 | 前端 `strategies/page.tsx` (895行) 拆分为子组件 | 前端 | 4 小时 | 🔲 |
| **P2** | F2 | 前端 `alerts/page.tsx` (514行) 拆分为子组件 | 前端 | 2 小时 | 🔲 |
| **P3** | B8 | 合并 `PriceLevelBatchItem` 与 `PriceLevelCreate` | 后端 | 1 小时 | 🔲 |
| **P3** | B9 | 合并重复 IP 检查逻辑 | 后端 | 30 分钟 | 🔲 |
| **P3** | B10 | 补充 `kline_data` / `fut_daily_data` 的 `data_source` 列 | 后端 | 2 小时 | 🔲 |
| **P3** | B11 | 提升 `--cov-fail-under` 阈值 (当前 30% 偏低) | 后端 | 5 分钟 | 🔲 |
| **P3** | B12 | 增加 `FutTradeFeeDB` 的 Float → Numeric 迁移 | 后端 | 1 小时 | 🔲 |
| **P3** | F3 | 补齐 9 个前端页面的页面级测试 | 前端 | 8-16 小时 | 🔲 |
| **P3** | B13 | 异常静默吞没处加 `logger.exception()` | 后端 | 1 小时 | 🔲 |
| **P3** | B14 | 数据摄入丢数据时写入死信表或告警 | 后端 | 3 小时 | 🔲 |

---

## 九、Agent 子系统专项评估

Agent 子系统是最近开发重点（最近 37 个提交中有 20+ 与 Agent 相关），以下是专项评估：

### 当前状态
- **28 个文件, ~2000+ 行代码**，是项目最复杂的子系统
- 覆盖: 数据查询、技术分析、策略编译、回测、风控、因子挖掘、参数优化
- 测试覆盖不均: `strategy_compiler_agent`, `backtest_agent`, `factor_mining_agent` 有测试；`risk_management_agent`, `executor`, `core` 等无直接测试

### 需关注
- `database_tools.py` 的 SQL 注入防护依赖 `_validate_sql()` + `_ALLOWED_TABLES` 白名单，需要持续审计
- `risk_management_agent.py` 的 SQL 有 PostgreSQL 不兼容语法
- Agent 任务执行链 (`executor.py`) 缺少超时和资源限制机制

---

**总体评价:** 项目架构设计成熟，测试基础扎实，CI/CD 配置完整。P0/P1 全部修复完成，P2 核心项（pre-commit、init_db 统一）已落地。剩余 P2/P3 项涉及较大工作量的测试补齐和重构，建议后续按需排期。Agent 子系统发展迅速但测试覆盖需要跟上。当前测试: **656 passed, 1 pre-existing failure, 6 skipped**。
