# 后续迭代计划：安全边界、数据基础与发布收口

> 计划日期：2026-07-24
> 当前状态：R1、R2 已完成；R3 前两项已完成，后续子项执行中
> 适用范围：Phase 4 后续安全回归、数据基础、策略验证、前端质量和生产发布治理
> 上一份事实源：[`iteration_plan_20260718_project_audit.md`](iteration_plan_20260718_project_audit.md)

## 1. 当前基线

截至 2026-07-25，项目已经完成：

- Phase 0 可运行性收口、Phase 1 行情读模型收敛、Phase 2 执行可靠性与生产拓扑；
- Phase 3 文档与发布治理，包括发布清单、工程基线记录和历史计划归档；
- Phase 4 Agent SQL AST 只读校验；
- Phase 4 私有数据 `user_id` owner 谓词 AST 改写。

当前可复现工程基线：

- 后端：`1017 passed, 1 skipped, 0 failed`，coverage 历史基线 `71.97%`；
- 前端：Vitest `195 passed, 0 failed`；
- 全仓库 Ruff、TypeScript、ESLint、production build 和既有 CI 证据均通过；
- 以上均为工程基线，不等同于生产发布。生产发布仍需逐项执行
  [`release_checklist_20260719.md`](release_checklist_20260719.md)。

## 2. 已完成项与旧清单校正

原 `.agents/roadmap.md` 中的部分 P1 项已经在代码中完成，本计划不重复排期：

| 事项 | 当前结论 | 证据 |
|---|---|---|
| 前端日志 payload 大小限制 | 已完成 8KB、嵌套深度和 key 数量限制 | `python/routers/frontend_logs.py`、`python/schemas.py` |
| 实时行情批量 symbol 上限 | 已完成，batch 与 SSE 共用 50 个上限 | `MarketDataService.get_realtime_batch()` |
| 品种删除时评论外键 | 已完成 `ON DELETE CASCADE` | `python/models.py`、级联测试 |
| 交易观点 `reason` 清洗 | 已完成请求 schema 层 HTML 清洗 | `python/schemas.py` |
| Agent SQL AST 只读校验 | 已完成 | `docs/phase4_sql_ast_readonly.md` |
| 私有数据 owner 谓词 AST 改写 | 已完成，复杂 PostgreSQL 语义回归待补 | `docs/releases/20260722_phase4_user_scope.md` |

## 3. 后续迭代队列

### R1：PostgreSQL 私有查询语义回归（P0，已完成）

**目标**：证明 AST owner 改写不仅能生成预期 SQL，而且能在 PostgreSQL 上正确执行并保持结果隔离。

范围：

1. 新增 PostgreSQL 专项测试，使用独立测试用户和唯一测试数据；
2. 覆盖私有表 LEFT JOIN，确认 owner 条件进入 `ON` 而不是错误收紧到 `WHERE`；
3. 覆盖 CTE、子查询和 UNION，确认每个 SELECT 作用域都注入当前用户；
4. 覆盖 `agent_task_steps` 的 `EXISTS` 父任务 owner 关联；
5. 保留 SQLite 单元测试，形成“AST 结构断言 + PostgreSQL 执行断言”两层证据。

验收：

- PostgreSQL 专项测试在目标数据库迁移到 head 后通过；
- 返回结果只包含当前用户数据；
- 无 `database is locked`、SQL 方言错误或 LEFT JOIN 语义回归；
- 本地无 PostgreSQL 时测试明确 skip，不伪造通过。

### R2：私有数据访问边界收敛（P1，已完成）

**目标**：评估通用 SQL 工具继续承载用户私有数据的必要性，逐步将高风险读路径收敛到显式 repository/API。

范围：

- 盘点 `_PRIVATE_TABLES` 的访问者、字段和最小查询需求；
- 对工作区、策略、回测、Agent 任务等稳定领域优先提供显式只读查询接口；
- 通用 SQL 工具保留公共行情/基本面数据和经过审计的只读私有查询；
- 输出一份决策记录，明确保留、迁移和淘汰边界，不在没有调用方证据时大规模重构。

实施结果：

- 新增 [`phase4_private_data_access_boundary.md`](phase4_private_data_access_boundary.md)，
  固定通用 SQL、领域 API 与后续 repository 的职责边界；
- 私有表 owner policy 收敛为 `_PRIVATE_TABLE_USER_COLUMNS`，补入
  `frontend_logs` 与 `user_preferences`；
- `news_sources` 与 `news_articles` 移出通用 SQL 白名单，继续通过受鉴权新闻 API
  访问；
- SQLite 与 PostgreSQL 回归均覆盖新增 policy。

验收：

- 每个私有表都有 owner 保护策略和测试归属；
- 新增 repository/API 不绕过现有鉴权、限流和审计；
- SQL 工具白名单、文档和 Agent 工具描述同步更新。

### R3：数据基础与可复现性（P1，执行中）

**目标**：让数据质量检查结果能支持连续合约、因子和回测的可复现输入。

顺序：

1. 落地 `raw_contract` 日级宽表的最小 schema、血缘字段和幂等键；
2. 明确具体合约、主力日线、连续合约之间的来源优先级和重建规则；
3. 增加采集失败记录、可恢复重试和数据质量快照；
4. 将 Data Catalog / DataQualityAgent 的覆盖范围接入宽表与连续数据。

第一项实施结果：

- 新增 `agent_market_panel_daily`，第一版只物化 `raw_contract`、`1d` 视图；
- 从 `kline_data` 构建 OHLCV，并以 `fut_daily_data` 补充成交额、持仓和结算价；
- 派生字段、字段级 `source_flags`、`quality_status` 与幂等重建已落地；
- Data Catalog、数据质量检查和手工重建脚本已接入；
- 详细记录：[`r3_raw_contract_market_panel.md`](r3_raw_contract_market_panel.md)。

第二项实施结果：

- 宽表构建复用 `data_ingestion_runs`，每次尝试保留状态、窗口、计数与共享 `trace_id`；
- 仅对数据库连接类异常执行指数退避重试，确定性数据错误即时结束；
- 成功批次写入不含原始行情样本的质量快照；失败批次仅记录异常类型与诊断标识；
- `--dry-run` 在保存点中运行且不写入宽表或批次记录；
- 自动调度暂不接入，等待连续/复权视图明确日线依赖顺序后统一实现。

后续子项：

1. 实现主力连续与复权视图，并记录换月血缘；
2. 将显式 `data_view` 接入 FactorMiningAgent 与 BacktestAgent。

验收：

- 同一输入重复运行不会产生重复数据；
- 每条派生数据可追溯到原始合约、来源和生成时间；
- 回测前置检查能区分缺失、过期和质量异常，而不是只返回空数据。

### R4：策略验证闭环（P1）

**目标**：避免策略编译结果与回测实际执行语义不一致。

范围：

- 让回测引擎真正消费策略 DSL 的 `transform`（至少覆盖
  `multiply_indicator2`）；
- 增加编译器输出到回测执行器的端到端测试；
- 实现策略进化预留的 walk-forward 分析；
- 将样本内/样本外、数据覆盖和质量提示写入回测报告。

验收：

- DSL 中每个已允许的 transform 都有执行侧实现或被明确拒绝；
- walk-forward 结果可持久化、可查询、可解释；
- 不把样本外验证缺失误报为策略通过。

### R5：前端质量与观测趋势（P2）

**目标**：在后端安全和数据基础稳定后，继续降低页面级性能与可访问性风险。

范围：

- 建立 Lighthouse 跨提交趋势，而不是只保存单次 JSON；
- 按实际品种规模评估行情列表虚拟滚动；
- 补齐详情页实时行情、评论、标注和错误态的页面级测试；
- 评估 CSP 与 access token 存储风险的后续迁移方案。

验收：

- 关键页面在 CI 中有稳定 smoke；
- 性能回归能关联到提交和路由；
- 新增安全策略不破坏 SSE、登录和 API 请求。

### R6：真实发布窗口（P1，按需）

**目标**：将工程基线转化为可审计的生产发布记录。

前置条件：

- R1 至少完成并保留 PostgreSQL 证据；
- 生产迁移、备份恢复、readiness、权限、scheduler owner、前端 smoke 和 Lighthouse 均在发布窗口重新执行；
- 从 [`release_checklist_20260719.md`](release_checklist_20260719.md) 复制清单，新增
  `docs/releases/YYYYMMDD_<short-slug>.md`；
- 未执行的生产项保持未勾选，不能用历史 CI 结果替代。

## 4. 本轮执行拆分

R1 与 R2 保持原子化执行：

1. `test(security): add PostgreSQL owner-scope regressions`
2. `test(security): close generic SQL private-table policy gaps`
3. `docs: record PostgreSQL owner-scope and private-boundary evidence`

每个提交都要先通过对应定向测试和 Ruff；R3 的数据 schema 与采集管道不与本轮
安全边界改动混在同一批。

## 5. 风险与停止条件

- PostgreSQL 专项测试依赖已迁移到 head 的目标数据库；未满足时只能记录为阻塞，不能改成 SQLite 伪回归；
- 测试数据使用唯一用户名和 symbol，并在 fixture teardown 中显式清理；
- 日志和测试输出不得记录原始行情代码、价格或 Provider Token；
- 发现 AST 改写在 PostgreSQL 与 SQLite 语义不一致时，暂停 R2，先修复并补齐安全回归。

## 6. 状态记录

| 迭代 | 状态 | 记录 |
|---|---|---|
| R1 PostgreSQL 私有查询语义回归 | 已完成 | 本文件、第 7 节 |
| R2 私有数据访问边界收敛 | 已完成 | `phase4_private_data_access_boundary.md` |
| R3 数据基础与可复现性 | 执行中（前两项完成） | `r3_raw_contract_market_panel.md` |
| R4 策略验证闭环 | 待开始 | 依赖 R3 数据口径 |
| R5 前端质量与观测趋势 | 待开始 | 与 R3/R4 可并行 |
| R6 真实发布窗口 | 按需 | 依赖发布窗口和前置证据 |

## 7. R1 执行记录（2026-07-24）

已完成：

- 新增 `python/tests/test_postgres_database_tools_scope.py`；
- 覆盖 LEFT JOIN 的 `ON` owner 条件、CTE/UNION 作用域隔离和
  `agent_task_steps` 的父任务 `EXISTS` 过滤；
- 已启动独立 PostgreSQL 测试库，从空库执行 Alembic 到 `f7a8b9c0d1e2`；
- owner-scope 专项回归：`4 passed, 0 skipped`；
- 数据库工具、PostgreSQL owner-scope 与既有 PostgreSQL upsert 回归合计：
  `50 passed, 0 skipped`；
- 新增测试文件 Ruff 检查通过，`git diff --check` 通过。

隔离测试库只用于本轮验证。已有开发库检测到 Alembic marker 落后于实际 schema，
因此未被重置、stamp 或修改。

## 8. R2 执行记录（2026-07-24）

- owner policy 与边界决策见
  [`phase4_private_data_access_boundary.md`](phase4_private_data_access_boundary.md)；
- 数据库工具与 PostgreSQL owner-scope 定向回归：`61 passed, 0 failed`；
- 本轮代码变更后的全量后端回归：`1006 passed, 1 skipped, 0 failed`；
- 全仓库 Ruff：通过；`git diff --check`：通过。

## 9. R3 第一项执行记录（2026-07-24）

- 新增 raw_contract 日频研究宽表、Alembic migration、可重跑构建服务与运维脚本；
- SQLite 与 PostgreSQL 定向回归：`14 passed, 0 failed`；
- 干净 PostgreSQL 数据库已成功迁移到 `a1c2d3e4f5a6`；
- 全量后端回归：`1012 passed, 1 skipped, 0 failed`；全仓库 Ruff 通过；
- 连续合约、复权视图、构建调度与 Agent 消费侧仍保持未实施，不与本批混合。

## 10. R3 第二项执行记录（2026-07-25）

- `run_raw_contract_daily_panel_build()` 复用 `data_ingestion_runs`，记录每次构建尝试；
- 成功批次保存写入/删除统计、质量状态、分数、日期覆盖与 issue code 快照；
- 失败批次通过共享 `trace_id`、异常类型、尝试次数和退避元数据提供可追溯诊断，不保存
  原始行情或异常原文；
- 仅连接与可操作性数据库错误参与指数退避；确定性数据问题立即终止；
- `--dry-run` 已验证不写入宽表或批次记录；
- SQLite 定向回归：`17 passed`；PostgreSQL 空库迁移和专项回归：`2 passed`；
- PostgreSQL 模式全量后端回归：`1017 passed, 1 skipped, 0 failed`；全仓库 Ruff 通过。
