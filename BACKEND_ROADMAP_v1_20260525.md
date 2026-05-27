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

*文档随迭代进展更新。*
