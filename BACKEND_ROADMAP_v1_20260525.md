# 后端迭代路线图 v1

> 基于《后端整体架构审计报告 v4》（评分 6.2/10，建议等级 B）制定。
> 制定日期：2026-05-25
> 原则：**质量为保证，先还债再开大功能。**

---

## 一、总体策略

近期（1~3 周）不做任何大功能，只做"让系统可信"的还债工作。审计报告中的高债务（测试不可复现）和 7 项中债务，都是后续迭代的"地基裂缝"。在测试无法稳定运行、依赖审计无法通过、核心模块复杂度未降之前，上马回测/多租户/持仓同步等功能会让技术债务指数级放大。

**核心原则：测试先行、逐层解耦、观测跟上、功能靠后。**

---

## 二、阶段规划

### 第一阶段：基础可信（Week 1，P0）

目标：**任何后续改动都能被测试兜住，安全扫描能跑通。**

| 行动项 | 关键动作 | 验收标准 |
|--------|----------|----------|
| 重建测试环境 | 清理失效 venv，重建可复现的 Python 环境；文档化统一 Python 版本 | `cd python && pytest tests -q` 本地一次通过 |
| 后端 CI 流水线 | 新增 `.github/workflows/backend-ci.yml`：安装依赖 → 设置环境变量 → pytest → ruff check | PR 自动跑通测试和 lint |
| 修复 SSE Token Bug | `realtime.py` 中 generator 传入 `effective_token`；补 cookie-only 场景测试 | `test_realtime_sse.py` + 新增 cookie-only 测试均通过 |
| 依赖审计可复现 | 使用 `uv pip compile` 生成精确 lock 文件；CI 中可跑 `pip-audit` | `pip-audit -r requirements.lock` 稳定执行 |

**产出物**：可运行的测试套件、绿色的 CI badge、修复后的 SSE 连接、lock 文件。

---

### 第二阶段：架构减负（Week 2~3，P1）

目标：**降低核心模块复杂度，消除双数据层隐患，让新增数据源的改动半径可控。**

**线 A：采集调度治理**
- 提取 `collector_registry.py`：封装 `DATA_SOURCE → collector fallback 链`
- 提取 `job_registry.py`：统一声明 job id、trigger、handler、misfire policy
- 将 `pipeline.py` 中 `run_fut_mapping` 等复杂函数拆为 `pipeline_tasks/` 独立任务对象

**验收**：新增数据源/任务时，不改动 `start_scheduler()` 和 `_ensure_collectors()` 主体；scheduler health 测试仍通过。

**线 B：连续 K 线拆分**
- 将 `continuous_kline.py:get_continuous_kline()` 拆为：
  - `build_rollover_segments()`
  - `query_segment_klines()`
  - `apply_backward_adjustment()`
  - `attach_contract_metadata()`

**验收**：对外接口不变；现有 contracts/kline 测试通过；核心函数 ≤80 行，圈复杂度降到 15 以下。

**线 C：ProductDB 退场计划（文档先行）**
- 产出迁移文档：前端依赖 `ProductDB` 的 API 清单、新 API 替代路径、`sync_prices_to_products()` 删除前置条件

**产出物**：调度与 K 线核心文件瘦身、ProductDB 退场设计文档。

---

### 第三阶段：观测性与安全加固（Week 3~4，P1~P2）

目标：**生产环境有据可查、有险可防。**

| 行动项 | 关键动作 |
|--------|----------|
| 健康接口收敛 | `/health/scheduler` 增加内网 IP 或管理鉴权 |
| 熔断器 Redis 化调研 | 评估进程内状态迁移到 Redis 的可行性 |
| 观测 runbook | 补充 QPS、P99 latency、error rate、DB pool、采集失败率监控 |
| mypy 分阶段收紧 | 先从 `services/` 和 repository 层移除 exclude |
| 风险矩阵缓解 | 引入采集任务幂等键与任务表；补 PG 备份恢复 runbook |

---

### 第四阶段：低风险功能试点（Week 4+，视还债进度而定）

当且仅当前三阶段验收通过后，才开启以下低风险功能：

| 功能 | 理由 |
|------|------|
| 只读 Admin 运营后台 | 不引入写操作，不触碰核心交易逻辑 |
| 第三方登录/SSO 预研 | auth 模块较集中，refresh token 机制可复用 |
| 指标面板增强 | 在现有 Prometheus/structlog 基础上增加业务指标 |

---

## 三、明确冻结（暂不启动）

以下功能在综合健康度达到 7.5 以上之前**坚决不开工**：

- ❌ 策略回测系统（阻塞点：K 线未形成回测级查询服务）
- ❌ 用户持仓实时同步（阻塞点：无账户/持仓/幂等事件模型）
- ❌ 期权 Greeks 计算（阻塞点：无期权合约模型，应建独立 bounded context）
- ❌ 多租户/权限体系（阻塞点：无 tenant_id、RBAC、数据隔离策略）

---

## 四、执行记录

| 日期 | 完成项 | 状态 |
|------|--------|------|
| 2026-05-25 | 路线图文档定稿 | ✅ |
| 2026-05-25 | P0：修复 SSE cookie-only bug | ✅ |
| 2026-05-25 | P0：重建 venv + 测试通过 | ✅ |
| 2026-05-25 | P0：Backend CI workflow | ✅ |
| 2026-05-25 | P0：依赖 lock 文件 | ✅ |
| 2026-05-27 | P0 收尾：12 个测试文件 SECRET_KEY 加长（消除 489 个 PyJWT 警告） | ✅ |
| 2026-05-27 | P0 收尾：修复 `comment_service.py` F821 运行时 bug | ✅ |
| 2026-05-27 | P0 收尾：更新 `backend-ci.yml`（SECRET_KEY 加固 + pip-audit 去 continue-on-error） | ✅ |
| 2026-05-27 | P0 收尾：清理 `tsconfig.tsbuildinfo` 跟踪 + 更新 `.gitignore` | ✅ |
| 2026-05-27 | **第一阶段验收：pytest 201 passed, 6 skipped, 0 warnings** | ✅ |
| 2026-05-27 | 进入第二阶段（架构减负 P1）：线 B — 连续 K 线拆分 | 🔄 |
| 2026-05-27 | 线 B 验收：`get_continuous_kline` 43→44 行，复杂度 5；提取 `_compute_segment_gaps` | ✅ |
| 2026-05-27 | 线 A 验收：`pipeline.py` 212 行（原 ~692），`scheduler.py` 510 行（原 ~716） | ✅ |
| 2026-05-27 | 线 A 验收：collector_registry / job_registry / pipeline_tasks 已落地并接入 | ✅ |
| 2026-05-27 | 进入第二阶段（架构减负 P1）：线 C — ProductDB 退场计划（文档先行） | 🔄 |
| 2026-05-27 | 线 C 验收：`python/docs/productdb_sunset_plan.md` 已完备（依赖清单/替代路径/迁移阶段/前置条件/风险/验收标准） | ✅ |
| 2026-05-27 | **第二阶段验收：collector_registry / job_registry / pipeline_tasks 落地；continuous_kline 拆分达标；ProductDB 退场文档完备** | ✅ |
| 2026-05-27 | 进入第三阶段（观测性与安全加固 P1~P2）：健康接口收敛 | 🔄 |
| 2026-05-27 | 第三阶段：补充 /health/scheduler 生产环境 403 鉴权测试 | ✅ |
| 2026-05-27 | 第三阶段：mypy 分阶段收紧 — 修复 schemas/trading_calendar/continuous_kline 真正类型问题 | ✅ |
| 2026-05-27 | 第三阶段：可观测性运维手册（PromQL 告警规则、SLO、排查手册、Dashboard 建议） | ✅ |
| 2026-05-27 | 第三阶段：PostgreSQL 备份与恢复 Runbook（物理/逻辑备份、PITR、RTO/RPO） | ✅ |
| 2026-05-27 | 第三阶段：熔断器 Redis 化 — 已支持（Redis 优先 + 内存降级），无需额外工作 | ✅ |
| 2026-05-27 | **第三阶段验收：生产有据可查、有险可防** | ✅ |
| 2026-05-27 | 进入第四阶段（低风险功能试点）：指标面板增强 | 🔄 |
| 2026-05-27 | 后端：新增 /metrics/dashboard 系列聚合 API + 测试覆盖 | ✅ |
| 2026-05-27 | 前端：新增 /metrics 运营指标面板页面 + 统计卡片 + 趋势图 + Navbar 入口 | ✅ |
| 2026-05-27 | **第四阶段验收：指标面板增强前后端闭环，pytest 211 passed，前端 build 通过** | ✅ |
| 2026-05-27 | 进入第五阶段（v5 审计 P0/P1 修复迭代）：venv 重建、CI 源统一、循环依赖消除、文档同步 | 🔄 |
| 2026-05-27 | P0：重建 venv（Python 3.12），requirements.lock 精确安装，pytest/ruff/pip-audit 本地可复现 | ✅ |
| 2026-05-27 | P1：backend-ci.yml 安装源统一为 requirements.lock | ✅ |
| 2026-05-27 | P1：消除 fut_mapping_task ↔ pipeline 循环依赖，改从 _common.py 导入 | ✅ |
| 2026-05-27 | P3：README/AGENTS 技术栈版本、Redis、price-levels 描述与实际代码同步 | ✅ |
| 2026-05-27 | **第五阶段验收：v5 P0/P1 差距关闭，pytest 211 passed，前端 build 通过** | ✅ |
| 2026-05-27 | 进入第六阶段（ProductDB 退场 Phase 1）：扩展 varieties API、评论 variety_id 迁移 | 🔄 |
| 2026-05-27 | Phase 1：扩展 /api/varieties 列表查询（搜索/筛选/涨跌/排序/统计），联合 VarietyDB+RealtimeQuoteDB | ✅ |
| 2026-05-27 | Phase 1：CommentDB 增加 variety_id + Alembic 迁移 + 模型/Schema 更新 | ✅ |
| 2026-05-27 | Phase 1：评论接口支持 variety_id（CommentService/CommentRepository/routers） | ✅ |
| 2026-05-27 | Phase 1：数据迁移脚本 migrate_comment_variety_id.py（product_id→variety_id 映射填充） | ✅ |
| 2026-05-27 | Phase 1：补充 test_varieties_enhanced.py（7 个测试覆盖列表查询+评论 variety_id） | ✅ |
| 2026-05-27 | **第六阶段验收：pytest 218 passed，前端 build 通过，/api/varieties 具备替代 /api/products 列表能力** | ✅ |

---

## 五、第五阶段：v5 审计债务修复（P0~P1，1~2 天）

> 基于《后端整体架构审计报告 v5》（评分 6.9/10）制定。  
> 目标：**关闭 v5 审计中明确的 P0 和 P1 差距，提升工程可验证性。**

### 5.1 P0 — 本地测试环境可复现

| 行动项 | 关键动作 | 验收标准 |
|--------|----------|----------|
| 重建 venv | 删除绑定旧绝对路径的 venv，用当前 Python 重新创建 | `python\venv\Scripts\python.exe --version` 可执行 |
| 安装依赖 | 基于 `requirements.lock` 精确安装 | `pip list` 包含 pytest/ruff/pip-audit/python-dotenv |
| 本地验证 | 跑通 pytest + ruff + pip-audit | `pytest tests -q` 通过；ruff 可运行；pip-audit 无异常 |

### 5.2 P1 — CI 安装源与审计源统一

| 行动项 | 关键动作 | 验收标准 |
|--------|----------|----------|
| 统一安装源 | `.github/workflows/backend-ci.yml` 中 `pip install -r requirements.txt` 改为 `requirements.lock` | CI 安装与审计使用同一份 lock |
| 消除循环依赖 | `fut_mapping_task.py` 不再从 `data_collector.pipeline` 导入 `_record_run` / `_record_circuit_outcome`，改从 `_common.py` 导入 | 静态 import 无循环；`compileall` 通过 |

### 5.3 P1~P3 — 文档同步

| 行动项 | 关键动作 | 验收标准 |
|--------|----------|----------|
| README 更新 | FastAPI 版本、Redis 状态、price-levels 后端同步状态与实际一致 | 无过期技术栈描述 |
| AGENTS 更新 | 同上，确保 agent 上下文准确 | 无过期技术栈描述 |

**产出物**：本地可复现的 venv、CI 源统一的 workflow、无循环依赖的 pipeline、同步的文档。

---

*文档随迭代进展更新。*
