# 后端修复深度验收报告 v6.1

> 审计日期：2026-05-30  
> 审计对象：`master` 分支当前后端代码、相关测试、前端接口消费路径  
> 审计定位：基于 `BACKEND_ARCHITECTURE_REVIEW_OUTLINE_20260529.md` 和历史 v3/v5/v6 报告，对后续修复做证据链复核，并给后端 agent 形成可执行修复清单。  
> 重要边界：本次审计只新增本文档，没有修改业务代码。

---

## 0. 执行摘要

总体评级：**B（可继续迭代，但需要一次“还债 + 契约收口”小迭代）**

核心结论：

- P0 主体已经稳住：生产禁 SQLite、合约换月、SSE 推送、CORS、bcrypt、缓存 Redis 化等都有明确代码证据。
- 仍有 3 个需要后端 agent 优先处理的问题：
  1. **本地后端测试环境不可复现**：`python/.venv` 仍指向失效的 `C:\Users\34226\AppData\Local\Programs\Python\Python312\python.exe`，代表 pytest 未能运行。
  2. **Metrics dashboard 只有登录鉴权，没有 admin/RBAC**：普通登录用户可访问平台总用户数、活跃度、采集健康和熔断状态。
  3. **品种详情评论 N+1 仍在**：`/api/varieties/{symbol}/detail` 查询评论后访问 `c.user.username`，但评论查询未预加载 `user`。
- 另外有 2 个中优先级债务：
  - `ServiceError` 没有全局 exception handler，HTTP 错误体 `code` 仍多为状态码字符串。
  - SSE 仍是单实例能力，`_sse_connections` 和 `_last_update_time` 为进程内状态；已有策略文档，但代码未 Redis/pubsub 化。
- 前端消费验证总体良好：合约、K 线、SSE、批量行情、价位标注 scope/contract_id 均已消费。代表前端 Vitest 通过：4 files / 32 tests passed。

证据链统计：

| 类型 | 数量 | 说明 |
|---|---:|---|
| 完整闭环 | 9 | 合约换月、夜盘交易日、CORS、bcrypt、缓存、price_levels scope、ProductDB 退场等 |
| 缺运行证据 | 1 | 本地后端 pytest 因 venv 损坏无法运行 |
| 缺权限边界 | 1 | metrics dashboard 仅登录可见，无 admin/RBAC |
| 缺性能修复 | 1 | varieties detail 评论 N+1 |
| 缺统一契约 | 1 | ServiceError/error code 体系 |
| 文档约束替代代码 | 1 | SSE 横向扩展 |

---

## 1. 关键发现

### 1.1 Metrics dashboard 权限不足

评级：**半吊子（🚧）**

当前状态：

- `python/routers/metrics_dashboard.py` 的三个接口都只使用 `Depends(get_current_user_dependency)`：
  - `GET /metrics/dashboard`
  - `GET /metrics/dashboard/activity`
  - `GET /metrics/dashboard/collection`
- `python/tests/test_metrics_dashboard.py` 只验证“未登录 401、登录后 200”，没有普通用户 403 或 admin 200 的用例。

影响：

- 任意登录用户可以看到平台级敏感运营数据，包括：
  - 用户总数 / 当日新增 / 本周新增
  - 评论数 / 价位标注数 / 自选数
  - 采集成功率 / 最近采集任务 / 熔断器状态

建议修复：

1. 增加最小权限 dependency，例如 `require_admin_user`。
2. 权限来源可以先走简单策略：
   - JWT `role=admin`，或
   - 环境变量 `ADMIN_USERNAMES`，或
   - `UserDB` 增加 `role` 字段（若要长期使用，需 Alembic 迁移）。
3. 补测试：
   - 未登录访问 401。
   - 普通登录用户访问 403。
   - admin 用户访问 200。

验收标准：

- 普通登录用户不能访问 `/metrics/dashboard*`。
- admin 用户能访问并保持原响应结构。
- 前端若已有 `/metrics` 页面，应能处理 403。

---

### 1.2 品种详情评论 N+1 未修

评级：**半吊子（🚧）**

当前状态：

- 位置：`python/routers/varieties.py`
- `get_variety_detail()` 查询评论：
  - `db.query(CommentDB).filter(...).order_by(...).offset(...).limit(...).all()`
- 响应构造中访问：
  - `c.user.username if c.user else "未知用户"`
- 但评论查询没有 `joinedload(CommentDB.user)` 或 `selectinload(CommentDB.user)`。

影响：

- 评论列表每多一个不同用户，可能额外触发一次 user 查询。
- 默认 `comment_limit=100`，最坏情况下详情页会放大为 1 + 100 次查询。

建议修复：

1. 在评论查询上增加预加载：
   - `options(joinedload(CommentDB.user))`，或
   - `options(selectinload(CommentDB.user))`
2. 若同时访问 price level，可顺手预加载 `price_level`。
3. 补测试：
   - 最低要求：详情接口仍返回 username。
   - 更好：用 SQLAlchemy event 统计查询数量，确保评论数增加不会线性增加查询次数。

验收标准：

- `/api/varieties/{symbol}/detail` 评论响应保持兼容。
- 评论数量增加时 SQL 查询数量不随评论条数线性增长。

---

### 1.3 本地后端测试环境不可复现

评级：**半吊子（🚧）**

本次执行命令：

```powershell
cd D:\Code\project_rich_snowball\python
$env:SECRET_KEY='test-secret-key-for-review-local-development-42'
$env:ENABLE_SCHEDULER='0'
$env:SSE_TEST_MODE='1'
.\.venv\Scripts\python.exe -m pytest tests/test_production_config.py tests/test_contracts.py tests/test_realtime_sse.py tests/test_csrf_protection.py tests/test_cors_variable.py tests/test_price_levels.py tests/test_metrics_dashboard.py tests/test_trading_date.py -q --tb=short
```

结果：

```text
Unable to create process using '"C:\Users\34226\AppData\Local\Programs\Python\Python312\python.exe" -m pytest ...'
```

补充验证：

- `python/.venv/Scripts/python.exe` 存在，但启动器绑定了失效的 Python 绝对路径。
- Codex bundled Python 可启动，但没有安装项目依赖，例如 SQLAlchemy。
- `.github/workflows/backend-ci.yml` 已使用 `requirements.lock` 安装并运行 pytest/ruff/pip-audit，CI 配置方向正确，但本机运行证据缺失。

建议修复：

1. 重建项目内 venv，不提交 venv：

```powershell
cd D:\Code\project_rich_snowball\python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
```

2. 跑代表测试：

```powershell
$env:SECRET_KEY='test-secret-key-for-local-development-42'
$env:ENABLE_SCHEDULER='0'
$env:SSE_TEST_MODE='1'
.\.venv\Scripts\python.exe -m pytest tests/test_production_config.py tests/test_contracts.py tests/test_realtime_sse.py tests/test_csrf_protection.py tests/test_cors_variable.py tests/test_price_levels.py tests/test_metrics_dashboard.py tests/test_trading_date.py -q --tb=short
```

3. 若要完整验收，再跑：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --tb=short
```

验收标准：

- 新 clone 或本地重建后，按 README/AGENTS 命令可跑后端测试。
- 不依赖全局 Anaconda 或机器绝对路径。
- `python/.venv/` 和 `python/venv/` 保持 git ignore，不纳入提交。

---

## 2. P0 验收

### 2.1 SQLite -> PostgreSQL 切换

评级：**勉强完成（⚠️）**

证据链：

| 环节 | 状态 | 证据 |
|---|---|---|
| 生产禁 SQLite | 已落地 | `python/config.py`：`ENV=production` 且 `DATABASE_URL.startswith("sqlite")` 时抛错 |
| `.env.example` PG 示例 | 已落地 | `.env.example` 使用 `postgresql://futures:futures123@localhost:15432/futures_community` |
| docker compose PG | 已落地 | `docker-compose.yml` 有 PostgreSQL 16 服务，映射 `15432:5432` |
| 连接池 | 已落地 | `python/models.py` 非 SQLite 使用 `pool_size=10`, `max_overflow=20`, `pool_pre_ping=True` |
| 连接池指标 | 已落地 | `python/services/metrics.py` 定义 `db_pool_connections` 等指标 |
| PG 验收文档 | 已落地 | `python/docs/postgres_acceptance.md` |
| 本地运行证据 | 缺失 | 本机 `.venv` 损坏，无法跑代表 pytest |

判定：

- 生产边界已经是架构级修复。
- 开发/测试仍保留 SQLite，这是合理的 local fallback，但不能替代 PG 验收。
- 当前最大问题不是代码路径，而是本地运行证据链断了一环。

后端 agent 建议：

- 先修 venv，再执行 `python/docs/postgres_acceptance.md` 中的 PG 验收。

---

### 2.2 合约换月设计

评级：**高质量完成（✅）**

证据链：

| 环节 | 状态 | 证据 |
|---|---|---|
| 合约表 | 已落地 | `FutContractDB` / `fut_contracts` |
| 换月表 | 已落地 | `ContractRolloverDB` / `contract_rollovers` |
| K 线合约隔离 | 已落地 | `KlineDataDB.contract_id` 非空，唯一约束含 `contract_id` |
| 连续 K 线拼接 | 已落地 | `services/continuous_kline.py` |
| API | 已落地 | `/api/contracts`, `/api/contracts/{id}/kline`, `/api/klines/{symbol}/continuous`, `/main` |
| 测试 | 已落地 | `python/tests/test_contracts.py` |
| 前端消费 | 已落地 | `frontend/hooks/useProductKline.ts`, `frontend/lib/kline.ts` |

判定：

- DB -> service -> API -> frontend 基本闭环。
- `FutContractDB` 没有 `is_main` 字段，但模型 docstring 已明确主力来源是 `VarietyDB.contract_code` 与 rollover 链，不算缺陷。

---

### 2.3 SSE / 实时推送

评级：**勉强完成（⚠️）**

证据链：

| 环节 | 状态 | 证据 |
|---|---|---|
| SSE endpoint | 已落地 | `GET /api/realtime/stream` |
| cookie-only 鉴权 | 已落地 | `effective_token = token or access_token` |
| stream-token | 已废弃 | `POST /api/realtime/stream-token` 标记 `deprecated=True` |
| 前端消费 | 已落地 | `new EventSource(..., { withCredentials: true })` |
| fallback | 已落地 | 前端 SSE 失败后使用 `getRealtimeBatch()` |
| URL 截断 | 已落地 | 前端 symbol 数量 > 30 时省略 symbols 参数 |
| 横向扩展 | 未根治 | `_sse_connections` 和 `_last_update_time` 仍为进程内状态 |
| 策略文档 | 已落地 | `python/docs/sse_scaling_strategy.md` |

判定：

- 单实例可用，前后端契约已收敛到 cookie-only。
- 多实例扩展靠文档约束，不是代码根治。

后端 agent 建议：

- 当前不必急着 Redis 化，但部署文档必须明确单实例/sticky session 限制。
- 如果宣称支持横向扩展，必须补 Redis pub/sub 或等价方案。

---

## 3. P1 验收

| 问题 | 评级 | 结论 |
|---|---|---|
| K 线混表 | ⚠️ 勉强完成 | 仍是 `kline_data` 单表，但已有索引、contract_id 隔离、PG benchmark。当前数据量 p95 < 500ms，暂不需要分区。 |
| 夜盘交易日归属 | ✅ 高质量完成 | `to_trading_date()` + `trading_date` 字段 + cleaner 接入 + 测试覆盖。 |
| 缓存线程安全 | ✅ 高质量完成 | Redis 优先 + 内存 LRU 降级 + RLock + per-key lock + 防穿透/击穿/雪崩。 |
| CORS 配置 | ✅ 高质量完成 | 生产限制、methods、expose headers、`max_age` 均已落地。 |
| 密码哈希强度 | ✅ 高质量完成 | bcrypt rounds 配置化，默认 12；密码复杂度 min 8 + 字母 + 数字。 |
| Metrics dashboard 权限 | 🚧 半吊子 | 仅登录鉴权，无 admin/RBAC。 |
| varieties detail N+1 | 🚧 半吊子 | 评论未预加载 user。 |

---

## 4. P2 抽样验收

| 项 | 评级 | 证据与说明 |
|---|---|---|
| 采集器重试/降级 | ✅ | collector registry + circuit breaker + Redis/内存熔断状态。 |
| API 错误码统一 | ⚠️ | 错误体结构统一，但 HTTPException `code=str(status_code)`，业务 code 不统一。 |
| 分页/响应边界 | ✅ | varieties/contracts/price_levels/watchlists 等有 skip/limit 与 header。 |
| 环境变量完整性 | ✅ | `.env.example` 覆盖 PG、CORS、SECRET、DATA_SOURCE、Redis 等关键项。 |
| 日志规范 | ⚠️ | structlog 已接入，但仍有 f-string 日志和部分非结构化 error。 |
| 数据库索引 | ✅ | 核心表有复合索引；K 线 benchmark 证明当前索引命中。 |
| mypy 收紧 | ⚠️ | `pipeline_tasks` 等有进展，但 `models.py`、`routers/`、domain services 仍大范围忽略。 |

---

## 5. 前端消费验证

| 需求项 | 后端交付 | 前端消费 | 契约状态 | 结论 |
|---|---|---|---|---|
| 合约列表 | 是 | 是 | `getContracts(varietyId, { limit })` 对齐 | ✅ |
| 单合约 K 线 | 是 | 是 | `contract_id + period + limit` 对齐 | ✅ |
| 连续 K 线 | 是 | 是 | `/api/klines/{symbol}/continuous` 对齐 | ✅ |
| 主力 K 线 | 是 | 是 | `/api/klines/{symbol}/main` 对齐 | ✅ |
| SSE 推送 | 是 | 是 | `EventSource` + cookie-only 对齐 | ✅ |
| stream-token | 是 | deprecated | 前后端均标 deprecated，不作为主路径 | ✅ |
| 实时 batch fallback | 是 | 是 | `getRealtimeBatch()` 对齐 | ✅ |
| 产品分页 | 是 | 是 | `skip/limit` + `X-Total-Count` 对齐 | ✅ |
| price_levels scope/contract | 是 | 是 | `scope` / `contract_id` 对齐 | ✅ |
| market/status | 是 | 是 | `useMarketStatus()` 消费 | ✅ |
| 统一错误码 | 部分 | 部分 | 前端支持 `ApiError.code`，后端 code 不统一 | ⚠️ |
| metrics dashboard | 是 | 是 | 功能可用，但权限模型不合格 | 🚧 |

前端代表测试已执行：

```powershell
cd frontend
npm.cmd run test -- --run tests/hooks/useRealtimeQuotes.test.tsx tests/hooks/useProductKline.test.tsx tests/hooks/usePriceLevels.test.tsx tests/lib/api.test.ts
```

结果：

```text
Test Files  4 passed (4)
Tests       32 passed (32)
```

---

## 6. 修复质量汇总

| 等级 | P0 | P1 | P2/债务 | 合计 |
|---|---:|---:|---:|---:|
| ✅ 高质量完成 | 1 | 4 | 4 | 9 |
| ⚠️ 勉强完成 | 2 | 1 | 3 | 6 |
| 🚧 半吊子 | 0 | 2 | 2 | 4 |
| ❌ 未开始 | 0 | 0 | 0 | 0 |
| 🔥 负优化 | 0 | 0 | 0 | 0 |

---

## 7. 给后端 agent 的修复清单

请后端 agent 按以下顺序处理，不要一次性大重构。每项独立提交、独立验证。

| # | 行动项 | 优先级 | 建议负责人 | 验收标准 |
|---|---|---|---|---|
| 1 | 修复本地 `.venv` 可运行性 | P0 | 后端 agent | 能用项目 venv 跑通代表 pytest；文档命令可复制执行 |
| 2 | Metrics dashboard 增加 admin/RBAC | P1 | 后端 agent | 未登录 401、普通用户 403、admin 200；前端能处理 403 |
| 3 | 修复 varieties detail 评论 N+1 | P1 | 后端 agent | 查询预加载 user；评论数增加不线性增加 SQL 查询 |
| 4 | 增加 `ServiceError` 全局 handler | P1 | 后端 agent | 业务错误输出稳定 `{code,message}`；现有 router 不回退成 500 |
| 5 | 错误码契约收口 | P2 | 后端 + 前端 agent | 写入 `python/docs/api_error_contract.md` 并至少改造 1-2 条主路径 |
| 6 | SSE 部署约束补到 README/运维文档 | P2 | 后端 agent | 明确单实例/sticky session；未 Redis 化前不宣称横向扩展完成 |
| 7 | mypy 分阶段收紧 | P2 | 后端 agent | 从低 SQLAlchemy 误报模块开始，避免大范围 ignore 继续扩大 |

---

## 8. 后端 agent 可直接使用的评审 Prompt

```markdown
请基于 `BACKEND_FIX_ACCEPTANCE_AUDIT_V6_1_20260530.md` 做一次后端全面评审并修复。

要求：

1. 先复核报告中的证据是否准确，不准确处请指出文件和行号。
2. 按 P0/P1/P2 顺序修复，不要一次性重构。
3. 每个行动项必须独立提交、独立验证。
4. 第一优先级是修复本地后端测试环境不可复现：
   - 重建项目内 `.venv`
   - 安装 `requirements.lock`
   - 跑通代表 pytest
5. 第二优先级是修复 metrics dashboard 权限：
   - 普通登录用户不能访问
   - admin 用户可以访问
   - 补测试覆盖
6. 第三优先级是修复 varieties detail 评论 N+1：
   - 使用 joinedload/selectinload 预加载 user
   - 保持响应契约不变
   - 补测试
7. 然后处理 `ServiceError` 全局 handler 和错误码契约。
8. SSE 横向扩展暂不要求代码 Redis 化，但必须补部署约束文档。

每修一项必须给出：

- 修改文件
- 关键代码说明
- 测试命令
- 测试结果
- 是否影响前端契约
```

---

## 9. 最终决策

当前后端不是“不能继续”，而是“可以继续，但别把债务藏到下一轮功能下面”。

建议先做一次 2-4 天的小迭代：

1. 恢复本地可验证性。
2. 补 metrics dashboard admin 权限。
3. 修 varieties detail N+1。
4. 收口 ServiceError/error code。

完成后再进入只读 Admin、SSE Redis 化、mypy 收紧或新功能，会稳很多。

---

*报告生成：2026-05-30，由 Codex 基于当前 master 静态审计 + 前端代表测试生成。*
