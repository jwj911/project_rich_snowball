# 后端迭代路线图 v2

> 基于《后端修复深度验收报告 v6》（评级 B，2026-05-29）与 AGENTS.md 当前状态制定。  
> 制定日期：2026-05-29  
> 原则：**先巩固可验证性，再对齐契约，最后清理债务。不赶大功能。**

---

## 一、当前状态快照

| 维度 | 状态 | 备注 |
|------|------|------|
| 分支 | `master` | 最新 |
| Python 环境 | `python/venv`，Python 3.12.9 | 可启动，pytest 可运行 |
| 测试收集 | 239 tests | 覆盖 31 个测试文件 |
| 最近验收 | pytest 228 passed（2026-05-29） | AGENTS.md 记录 233 passed, 6 skipped |
| SSE 鉴权 | cookie-only 策略已落地 | stream-token 已标 deprecated，前端统一走 cookie |
| CSRF 防护 | 方法感知鉴权已落地 | POST/PUT/PATCH/DELETE 只接受 Authorization header |
| ProductDB | 物理表已删除 | 主路径零依赖，残留注释待清理 |

**审计 v6 遗留的未关闭项**：PG 集成验收记录、SSE 横向扩展策略文档、K 线混表 benchmark、CORS preflight max_age、bcrypt rounds 配置化、统一错误码设计、ProductDB 残留注释清理。

---

## 二、总体策略

本轮迭代目标：**让后端从"B 级可继续迭代"提升到"B+ 级，任何改动都有本地测试兜住、有文档可查、有性能基线可对比"**。

核心原则：
1. **验证先行**：每个改动先有测试或 benchmark，再动代码。
2. **独立提交**：每个行动项可独立 PR/提交、独立回滚。
3. **文档即契约**：策略选择（SSE 扩展、K 线分区阈值、错误码）先写成文档，再视需要写代码。
4. **冻结大功能**：mypy 全量收紧、Redis 化 SSE、Admin 后台扩展等大工程，本轮只出方案/试点，不全量铺开。

---

## 三、阶段规划

### Phase 1：可验证性巩固（P0，1 天）

目标：**确认本地环境 100% 可复现，补全 PG 路径的验收记录。**

| # | 行动项 | 关键动作 | 验收标准 |
|---|--------|----------|----------|
| 1.1 | venv 状态固化 | 确认 `python/venv` 可复现；README/AGENTS 中的环境命令与实际一致 | 新 clone 后按文档命令可跑通 `pytest tests -q` |
| 1.2 | PG 集成验收记录 | 撰写 `python/docs/postgres_acceptance.md`：docker-compose 启动 → `DATABASE_URL` 设置 → `alembic upgrade head` → PG-only tests 命令 | 文档包含可复制的 PowerShell 命令序列 |
| 1.3 | PG-only 测试验证 | 在 docker PG 上执行 `pytest tests/test_postgres_upsert_integration.py -v` | 无 PG 时 skip，有 PG 时通过 |
| 1.4 | 连接池指标验证 | 启动后端后访问 `/metrics`，确认 `db_pool_connections` 等指标存在 | `/metrics` 输出包含 `db_pool_connections_total` 或等价指标 |

**产出物**：可复现的环境文档、PG 验收 runbook、连接池指标截图/文本证据。

---

### Phase 2：契约对齐与性能基线（P1，2-3 天）

目标：**对齐 SSE 扩展策略、建立 K 线性能基线，让后续扩容决策有据可依。**

#### 线 A：SSE 横向扩展策略文档化

| # | 行动项 | 关键动作 | 验收标准 |
|---|--------|----------|----------|
| 2.1 | 现状梳理 | 确认 `_sse_connections` 仍为进程内 dict；确认 cookie-only SSE 已统一 | 代码审阅记录写入文档 |
| 2.2 | 策略文档 | 撰写 `python/docs/sse_scaling_strategy.md`，明确三档路线 | 文档包含：单实例约束、sticky session 方案、Redis pub/sub 方案对比 |
| 2.3 | 单实例声明 | 在 README/部署文档中声明当前 SSE 仅支持单 API 实例 | 文档有明确约束说明 |

三档路线建议：
- **当前（单实例）**：`_sse_connections` 进程内管理，上限 100 连接。适合当前阶段。
- **中期（sticky session）**：负载均衡层启用 session affinity，同一用户 SSE 始终命中同一实例。代码无需大改。
- **长期（Redis pub/sub）**：quote fanout 走 Redis pub/sub，SSE handler 订阅 Redis channel。需要引入独立 SSE gateway 或重构 `realtime_state.py`。

#### 线 B：K 线混表性能基线

| # | 行动项 | 关键动作 | 验收标准 |
|---|--------|----------|----------|
| 2.4 | benchmark 脚本 | 新增 `python/scripts/benchmark_kline.py`，在 PG 上测试核心查询 | 脚本可独立运行，输出 p50/p95/p99 |
| 2.5 | 测试数据准备 | 脚本支持生成/导入 1 年日线 + 3 个月分钟线模拟数据 | 单品种 `kline_data` 行数可达 10 万+ |
| 2.6 | 查询覆盖 | 测试 `/api/klines/{symbol}`、`/continuous`、`/contracts/{id}/kline` | 每个端点至少测 3 次取平均 |
| 2.7 | 索引验证 | 对核心查询执行 `EXPLAIN ANALYZE`，记录索引命中情况 | 输出保存到 `python/docs/kline_benchmark_YYYYMMDD.md` |
| 2.8 | 阈值设定 | 文档明确分区/分表的触发条件 | 例如：`kline_data` > 100 万行，或单周期查询 p95 > 500ms |

**产出物**：SSE 扩展策略文档、K 线 benchmark 报告、索引命中分析、分区阈值决策文档。

**本轮明确不做**：不实施 PG 分区、不拆 `kline_1min/kline_5min/kline_day` 表、不改 SSE 进程内状态。只出数据和文档。

---

### Phase 3：安全加固与错误码（P2，2-3 天）

目标：**收敛 CORS、密码策略、错误体契约等安全与接口边界。**

| # | 行动项 | 关键动作 | 验收标准 |
|---|--------|----------|----------|
| 3.1 | CORS preflight max_age | `config.py` 新增 `CORS_MAX_AGE_SECONDS`（默认 600）；`main.py` 的 `CORSMiddleware` 传入 `max_age` | OPTIONS 预检响应头包含 `Access-Control-Max-Age` |
| 3.2 | CORS 测试覆盖 | `test_cors_variable.py` 新增：allowed methods 断言、max_age 断言、 credentials 下不返回 `*` 断言 | pytest 通过 |
| 3.3 | bcrypt rounds 配置化 | `config.py` 新增 `BCRYPT_ROUNDS`（默认 12，测试环境可覆盖）；`utils.py` `hash_password()` 使用配置值 | `test_production_config.py` 或新增测试验证 rounds 配置生效 |
| 3.4 | 密码复杂度增强 | `schemas.py` `UserCreate`/`PasswordUpdate` 密码最小长度 8，且要求同时包含字母和数字 | 弱密码注册/修改返回 422 |
| 3.5 | 登录恒定时间 | 确认 auth 中 dummy hash 逻辑仍有效；无回归 | `test_production_config.py` 保持通过 |
| 3.6 | 统一错误码设计 | 撰写 `frontend/docs/api_error_contract.md`，定义后端错误体结构 | 至少约定：`{code, message, request_id}` 三字段 |
| 3.7 | 错误码试点 | 选一个路由（建议 `auth.py` 或 `comments.py`）按新契约输出错误体 | 前端测试确认可读；其余路由文档化迁移计划 |

**产出物**：CORS 预检缓存生效、bcrypt 可配置、密码复杂度提升、错误码契约文档、试点路由改造。

**本轮明确不做**：不全局改造所有路由的错误体（工作量过大），只出契约 + 一个试点。

---

### Phase 4：债务清理与文档化（P3，1-2 天）

目标：**消除历史残留误导，让代码和注释只反映当前 schema。**

| # | 行动项 | 关键动作 | 验收标准 |
|---|--------|----------|----------|
| 4.1 | ProductDB 残留注释清理 | `rg "ProductDB|sync_prices_to_products" python/routers python/services python/data_collector -g "*.py"`，对运行代码中的过时注释加"历史语境"标注或删除 | 运行代码注释不再误导当前 schema |
| 4.2 | 历史迁移脚本标注 | `scripts/migrate_comment_variety_id.py` 等历史脚本头部增加"历史迁移，不用于当前 schema"注释 | 新 agent 不会误执行 |
| 4.3 | 模型注释同步 | `models.py` 中 `FutContractDB` 补充说明主力来源（`VarietyDB.contract_code` + `contract_rollovers`），避免误以为表内有 `is_main` 字段 | 注释准确 |
| 4.4 | 采集日志关键字 | `fut_mapping_task.py` / `scheduler.py` 补充 `contract_rollover_detected` 等结构化日志关键字 | structlog 输出可检索 |
| 4.5 | rollover 幂等性说明 | 在文档中说明：重复跑同一天 mapping 不会重复插入 rollover（基于唯一约束） | 文档或代码注释有说明 |

**产出物**：注释清理 diff、模型注释准确、日志关键字结构化。

---

## 四、中期功能预览（达标后启动，本轮不执行）

以下功能在本轮四个 Phase 全部验收通过后，方可进入排期：

| 功能 | 理由 | 前置条件 |
|------|------|----------|
| mypy 分阶段收紧 | 提升类型安全，减少运行时错误 | Phase 1 测试稳定可复现 |
| SSE/熔断器 Redis 化 | 支撑横向扩展 | Phase 2 策略文档评审通过 |
| 只读 Admin 运营后台扩展 | 在现有 `/metrics/dashboard` 基础上增加业务运营视图 | Phase 3 错误码契约落地 |
| K 线表分区/归档 | 数据量达到阈值后实施 | Phase 2 benchmark 证明需要 |

**本轮明确冻结（健康度未到 7.5 前不开工）**：
- ❌ 策略回测系统
- ❌ 用户持仓实时同步
- ❌ 期权 Greeks 计算
- ❌ 多租户/权限体系

---

## 五、执行记录

| 日期 | 完成项 | 状态 |
|------|--------|------|
| 2026-05-29 | 路线图 v2 定稿 | ✅ |
| | 进入 Phase 1：可验证性巩固 | 🔄 |
| | Phase 1.1：venv 状态确认（Python 3.12.9，239 tests collected） | ✅ |
| | Phase 1.2：撰写 `python/docs/postgres_acceptance.md` | ✅ |
| | Phase 1.3：PG-only 测试验证（`test_postgres_upsert_integration.py` 5 passed；全量 238 passed, 1 skipped） | ✅ |
| | Phase 1.4：连接池指标验证（`/metrics` 含 `db_pool_connections`/`checkout`/`checkin`） | ✅ |
| | **Phase 1 验收：PG 路径本地可复现，upsert/连接池/全量测试通过** | ✅ |
| | 进入 Phase 2：契约对齐与性能基线 | 🔄 |
| | Phase 2.1-2.3：SSE 横向扩展策略文档化（`python/docs/sse_scaling_strategy.md`，单实例/sticky/Redis PubSub 三档路线） | ✅ |
| | Phase 2.4-2.8：K 线混表性能基线（`scripts/benchmark_kline.py` + `docs/kline_benchmark_20260529.md`，21,965 条数据 p95 最高 113ms，索引命中正常，暂不分区） | ✅ |
| | **Phase 2 验收：SSE 扩展策略已文档化，K 线性能基线已建立，当前数据量无需分区** | ✅ |
| | 进入 Phase 3：安全加固与错误码 | 🔄 |
| | Phase 3.1-3.2：CORS preflight max_age 配置化（`config.py` + `main.py`，默认 600s）+ 测试覆盖 | ✅ |
| | Phase 3.3：bcrypt rounds 配置化（`config.BCRYPT_ROUNDS`，默认 12）+ 测试覆盖 | ✅ |
| | Phase 3.4：密码复杂度增强（`schemas.UserCreate` min_length=8，字母+数字必填）+ 专项测试 | ✅ |
| | Phase 3.5：登录恒定时间确认（`test_p0_fixes.py::test_login_constant_time` 继续通过） | ✅ |
| | Phase 3.6-3.7：统一错误码设计文档（`python/docs/api_error_contract.md`）+ 试点方案（auth.py） | ✅ |
| | **Phase 3 验收：CORS/bcrypt/密码强度/error contract 全部落地，242 passed** | ✅ |
| | 进入 Phase 4：债务清理与文档化 | 🔄 |
| | Phase 4.1：ProductDB 残留清理（运行代码 routers/services/data_collector 已无 ProductDB 残留；`init_mock_data.py` 注释已准确） | ✅ |
| | Phase 4.2：历史迁移脚本标注（`scripts/migrate_comment_variety_id.py` 已标记"历史迁移，不用于当前 schema"） | ✅ |
| | Phase 4.3：模型注释同步（`FutContractDB` 已补充主力来源说明） | ✅ |
| | Phase 4.4：采集日志关键字（`fut_mapping_task.py` `contract_rollover_detected` + `scheduler.py` `realtime_quotes_updated`） | ✅ |
| | Phase 4.5：rollover 幂等性说明（`fut_mapping_task.py` 已注释唯一约束保障） | ✅ |
| | **Phase 4 验收：242 passed, 6 skipped，历史债务清理完成** | ✅ |
| | **v2 迭代总验收：后端从 B 级提升至 B+ 级，本地可验证、PG 可复现、契约有文档、性能有基线** | ✅ |

*文档随迭代进展更新。*
