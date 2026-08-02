# 后续迭代计划：安全边界、数据基础与发布收口

> 计划日期：2026-07-24
> 当前状态：R1 至 R8 工程项已完成；R8 为 K 线分区生命周期准备，活动表尚未切换
> 适用范围：Phase 4 后续安全回归、数据基础、策略验证、前端质量和生产发布治理
> 上一份事实源：[`iteration_plan_20260718_project_audit.md`](iteration_plan_20260718_project_audit.md)

## 1. 当前基线

截至 2026-08-02，项目已经完成：

- Phase 0 可运行性收口、Phase 1 行情读模型收敛、Phase 2 执行可靠性与生产拓扑；
- Phase 3 文档与发布治理，包括发布清单、工程基线记录和历史计划归档；
- Phase 4 Agent SQL AST 只读校验；
- Phase 4 私有数据 `user_id` owner 谓词 AST 改写。

当前可复现工程基线：

- 后端：R8 本地全量 `1157 passed, 18 skipped, 0 failed`；
- Ruff check/format 与 diff check 均通过；
- Backend CI 已加入 R8 PostgreSQL 16 的只读容量预检、全部周期别名/DEFAULT 路由、影子
  复制、失败回滚和资源残留门禁；首次结果在实现提交推送后回填；
- 前端本轮无变更且未重跑。Next.js 15.5.22、Vitest `202 passed, 0 failed`、Playwright
  `40 passed`、TypeScript、ESLint、production build、双路由 Lighthouse 和生产依赖审计
  均为 R6 历史基线；
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

### R3：数据基础与可复现性（P1，已完成）

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

R3.3 至 R3.6 实施结果：

1. 物化 `main_continuous`、`main_back_adjusted`、`main_forward_adjusted`；
   每行保留实际合约、换月 ID、累计调整、算法、换月列表和构建 trace；
2. Data Catalog、DataQualityService 和 DataQualityAgent 支持按
   `data_view + period` 检查，并覆盖连续日期、OHLC、血缘、非正复权价格和换月关联；
3. FactorMiningAgent 与 BacktestAgent 仅在显式请求时消费研究宽表，报告和缓存键记录
   视图、合约、质量、窗口和 trace；`raw_contract` 必须指定合约；
4. `worker.py` 独占 `market_panel_daily` 调度，16:18 在日线与结算任务后执行，使用 20
   交易日预热窗口，并在迟到换月记录出现时回推到最早影响日。

验收：

- 同一输入重复运行不会产生重复数据；
- 每条派生数据可追溯到原始合约、来源和生成时间；
- 回测前置检查能区分缺失、过期和质量异常，而不是只返回空数据。

### R4：策略验证闭环（P1，已完成）

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

执行记录见 [`r4_dsl_walk_forward_validation.md`](r4_dsl_walk_forward_validation.md)。

### R5：前端质量与观测趋势（P2，已完成）

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

执行记录见 [`r5_frontend_quality_observability.md`](r5_frontend_quality_observability.md)。

### R6：真实发布窗口（P1，发布候选已完成）

**目标**：将工程基线转化为可审计的生产发布记录。

前置条件：

- R1 至少完成并保留 PostgreSQL 证据；
- 生产迁移、备份恢复、readiness、权限、scheduler owner、前端 smoke 和 Lighthouse 均在发布窗口重新执行；
- 从 [`release_checklist_20260719.md`](release_checklist_20260719.md) 复制清单，新增
  `docs/releases/YYYYMMDD_<short-slug>.md`；
- 未执行的生产项保持未勾选，不能用历史 CI 结果替代。

发布候选实施结果：

- 隔离 PostgreSQL 候选库从空库迁移到 `c0d1e2f3a4b5`，并完成 `pg_dump -Fc` /
  `pg_restore` 恢复演练与核心表计数核对；
- readiness、scheduler 禁用、行情、实时数据、管理员与普通用户权限 smoke 通过；
- scheduler 停止改用 APScheduler 支持的 `shutdown(wait=True)`，并增加重复停止回归；
- Compose 强制提供生产密钥、CORS 来源与真实数据源，API/worker 维持单 scheduler owner；
- Next.js 升级到 15.5.22，安全版本 override、production build、40 项 Playwright、
  双路由 Lighthouse 和生产依赖审计通过；
- 记录见
  [`releases/20260727_r6_release_candidate.md`](releases/20260727_r6_release_candidate.md)。

真实生产凭据、HTTPS CORS、生产迁移/备份/部署、回滚负责人和生产 SSE 多实例策略仍未验证，
因此 R6 只能标记为发布候选，不能标记为生产已发布。

### R7：生产发布门禁与 SSE 更新信号（P1，工程基线已完成）

**目标**：把生产发布输入转化为只读、可审计门禁，并让独立 worker 与 API 共享 realtime
quotes 更新信号，同时保持不具备分布式连接管理时的部署边界。

实施结果：

1. 新增 11 项只读预检：`ENV=production`、PostgreSQL、至少 32 字符密钥、安全 HTTPS
   CORS、非 mock 数据源、Redis、发布提交、UTC 发布窗口、发布负责人、回滚负责人和
   `SSE_DEPLOYMENT_MODE=single|sticky`；
2. 每次预检输出独立 `trace_id` 和脱敏结构化 JSON；除报告文件外，不修改数据库、Redis、
   部署状态或发布清单；
3. worker 成功刷新 realtime quotes 后更新本地状态，并向 Redis 写入仅含 UTC 时间戳的
   共享标记；API 使用本地/共享标记中的较新值决定 SSE 查询和推送；
4. Redis 不可用时保留本地状态，按 60 秒有界周期重新查询；恢复后自动回到共享标记路径；
5. 生产 SSE 只支持 `single|sticky`。本轮未实现 Redis Pub/Sub、跨实例连接注册、全局连接
   上限或跨实例旧连接取消；
6. 主提交为 `753a599bab95ffc7205823f445f2b980d3c3e1fc`，Ruff CI 修复后的最终提交为
   `b6cd75756b960eeba169c92531dbcfc3cd6b706a`；
7. 完整证据见
   [`releases/20260730_r7_release_gates.md`](releases/20260730_r7_release_gates.md)。

真实生产凭据、生产部署、发布前备份与恢复验证、发布/回滚负责人仍未完成，因此 R7
只能标记为工程基线或发布候选，不能标记为生产已发布。

### R8：K 线分区生命周期准备（P2，工程实现已完成）

**目标**：在不切换活动表、不删除冷数据的前提下，用真实容量证据和隔离 PostgreSQL 演练
建立可审计的分区生命周期准备能力。

实施结果：

1. 新增只读容量预检，采集方言、版本、行数、表/索引大小、周期分布、时间边界、分区状态、
   未来月份覆盖和 `EXPLAIN` 摘要；固定阈值为 1 亿行、100 GiB 和分钟查询 P99 500 ms；
2. 每次预检输出独立 `trace_id` 和脱敏 JSON；SQLite 返回基础统计及
   `unsupported_for_partitioning`，不执行 PostgreSQL 专有 SQL；
3. benchmark 默认只读，空库明确失败；只有非生产隔离环境显式 `--seed` 才生成 BENCH 数据；
4. 影子 DDL 与当前 `KlineDataDB` 字段、精度、时区、`trading_date`、非空条件和级联外键
   一致，按周期 LIST、分钟月份 RANGE 和 DEFAULT 组织；
5. 生命周期命令和迁移演练默认 dry-run；活动表、非法标识符、非 PostgreSQL 和缺失确认参数
   均被硬拒绝；
6. 演练验证总数、周期计数、时间边界、自然键、sequence、外键、核心查询、
   `ON CONFLICT DO NOTHING`、级联及实际 `EXPLAIN` 裁剪；失败由事务回滚；
7. 管理员存储概况使用 60 秒 TTL 和 PostgreSQL 系统目录估算，Prometheus scrape 不触发
   容量统计；
8. Backend CI 使用 PostgreSQL 16 执行 R8 专项门禁，并断言没有影子表或 sequence 残留。

本地证据为 `1157 passed, 18 skipped, 0 failed`，Ruff check/format 与 diff check 通过。
其中新增的 3 个真实 PostgreSQL 用例在本机明确 skip，不以 SQLite 或 fake 结果替代远程
PostgreSQL 证据。

完整记录见
[`releases/20260802_r8_kline_partition_lifecycle.md`](releases/20260802_r8_kline_partition_lifecycle.md)。
活动表切换、冷数据导出/删除、对象存储归档及生产恢复演练不属于 R8。

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
| R3 数据基础与可复现性 | 已完成 | `r3_raw_contract_market_panel.md` |
| R4 策略验证闭环 | 已完成 | `r4_dsl_walk_forward_validation.md` |
| R5 前端质量与观测趋势 | 已完成 | `r5_frontend_quality_observability.md` |
| R6 真实发布窗口 | 发布候选已完成 | `releases/20260727_r6_release_candidate.md`；生产部署待执行 |
| R7 生产发布门禁与 SSE 更新信号 | 工程基线已完成 | `releases/20260730_r7_release_gates.md`；真实生产操作待执行 |
| R8 K 线分区生命周期准备 | 工程实现已完成 | `releases/20260802_r8_kline_partition_lifecycle.md`；生产切换/归档待执行 |

工程侧下一项是推送 R8 并取得 PostgreSQL 16 CI 证据。生产侧仍需取得真实生产凭据和负责人，
在真实窗口完成备份恢复、部署与 smoke；K 线达到阈值后另立活动表切换和冷归档规格。

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

## 11. R3.3 至 R3.6 执行记录（2026-07-26）

- 新增 `c0d1e2f3a4b5`，为 `agent_market_panel_daily` 追加换月、复权与 build trace 血缘；
- 连续、前复权和后复权视图由 `raw_contract` 与 `contract_rollovers` 重建，不改变既有产品
  连续 K 线 API；
- 宽表质量、目录和 DataQualityAgent 已按视图隔离，并检查连续日期、OHLC、换月和血缘；
- 新增显式研究数据选择器；FactorMiningAgent 与 BacktestAgent 维持默认 K 线语义，仅在
  请求中明确 `data_view` 时改走宽表，`raw_contract` 强制要求 `contract_code`；
- 新增多视图重建 CLI 与独立 worker 的 `market_panel_daily` 任务，调度窗口、迟到换月回推、
  `max_instances=1`、`coalesce=True` 均有回归覆盖；
- SQLite 相关定向回归：`59 passed, 2 skipped`；空 PostgreSQL 库已升级至
  `c0d1e2f3a4b5`，宽表 DDL 与数据选择专项：`5 passed`，隔离库已删除；
- SQLite 全量后端回归：`1015 passed, 14 skipped, 0 failed`；全仓 Ruff 通过；
- 生产发布检查仍需按发布窗口单独执行。

## 12. R4 执行记录（2026-07-26）

- 新增共享 transform 契约：compiler 输出 canonical `multiply_indicator2`，
  `multiply_value` 仅保持兼容；未知 transform、缺少 `indicator2`、非有限或非正乘数均显式拒绝；
- `StrategyValidator`、`run_dsl_backtest()`、引擎条件求值和可读解释复用同一右侧
  `indicator2 * value` 语义，并补齐 compiler 到 backtest engine 的回归；
- 新增按已观测日线建立的 expanding / rolling walk-forward 服务，窗口不足、执行失败和
  非日线均返回明确的未通过状态，不能误报为 OOS 通过；
- `StrategyLifecycleDB.walk_forward_metrics` 已接入首次登记、后续更新、摘要和 evolution
  API 查询；策略回测 API 的结果快照也保存该报告；
- BacktestAgent 与 StrategyEvolutionAgent 报告展示数据覆盖、质量提示和
  walk-forward 诊断；进化报告不再把全历史搜索后的留出段复测描述为独立 OOS；
- 日线窗口查询按 `trading_date` 包含首尾交易日，旧数据行才回退 SQL 日期表达式。
- SQLite 全量后端：`1026 passed, 15 skipped, 0 failed`；隔离 PostgreSQL 数据库从空库升级至
  `c0d1e2f3a4b5` 后专项回归：`3 passed`；`ruff check .`、`py_compile` 与
  `git diff --check` 通过，验证库已删除。

## 13. R5 执行记录（2026-07-26）

- Lighthouse 采集改为固定命名路由集，结果包含 route、commit SHA、CI run/attempt、ref、
  时间与跨提交 delta；CI 恢复并上传可合并的 90 天趋势 artifact；
- 行情中心保持每页 20 条的服务端分页；已记录超过 100 行、无限滚动或可复现性能回归时的
  虚拟滚动重评估条件，当前不引入虚拟列表依赖；
- 详情页恢复单品种实时行情读取，在失败时明确显示最近收盘数据降级状态；评论、标注和详情请求
  失败均有页面级行为和 Playwright route-interception 回归；
- refresh 轮换同步写入 SSE 使用的 access cookie，logout 同时清理 access/refresh cookies；
  CSP 和 localStorage access token 的 Report-Only、nonce/hash、内存 token 与 cookie-only
  写请求边界已形成分阶段迁移与停止条件；
- 详细记录：[`r5_frontend_quality_observability.md`](r5_frontend_quality_observability.md)。

## 14. R6 发布候选执行记录（2026-07-27）

- 候选代码提交为 `c5e1a545544e602c24f2e31ca256c37a7511b8ef`；
- 空 PostgreSQL 候选库迁移、逻辑备份、隔离恢复和 API/权限 smoke 已完成；
- 本轮后端全量回归为 `1031 passed, 15 skipped, 0 failed`，全仓 Ruff 通过；
- Next.js 15.5.22 production build 的最大 First Load JS 为 157 kB；Vitest 202 项、
  Playwright 40 项及 `home` / `products` Lighthouse 均通过；
- `npm audit --omit=dev` 为 0；本地 `pip-audit` 因 Windows 进程异常内存申请失败，
  以后端 CI 的同锁文件结果为远程门禁；
- 完整证据、CI 链接、回滚点和未完成生产项见
  [`releases/20260727_r6_release_candidate.md`](releases/20260727_r6_release_candidate.md)。
- Backend CI #31 与 Frontend CI #33 均成功，Lighthouse 趋势 artifact 已上传。

## 15. R7 生产发布门禁执行记录（2026-07-30）

- 主提交：`753a599bab95ffc7205823f445f2b980d3c3e1fc`；
- Ruff CI 修复及最终验证提交：`b6cd75756b960eeba169c92531dbcfc3cd6b706a`；
- R7 聚焦回归：`106 passed`；补强后的另一轮聚焦回归：`90 passed`；
- 本地全量后端：`1103 passed, 15 skipped, 0 failed`；
- Ruff check/format、diff check 与 Compose config：通过；
- [Backend CI #33](https://github.com/jwj911/project_rich_snowball/actions/runs/30493521137)
  成功，包含依赖锁、R7 placeholder preflight、Alembic、PostgreSQL pytest/API smoke、
  Ruff 和 `pip-audit`；
- CI placeholder preflight 只验证 11 项门禁的 CLI/报告契约，不提供真实生产凭据、部署或
  发布证据；
- 前端无变更且本轮未重跑；R6 前端基线只作为历史证据；
- 当前未完成：真实生产凭据、发布窗口部署、发布前备份恢复验证、发布/回滚负责人，以及
  Pub/Sub/跨实例 SSE 连接管理。完整边界见
  [`releases/20260730_r7_release_gates.md`](releases/20260730_r7_release_gates.md)。

## 16. R8 K 线分区生命周期执行记录（2026-08-02）

- 实现提交：`41c79f1ed70b90cfe46f163f3e5af80b5f93d3d6`；
- R8 聚焦回归：`79 passed, 3 skipped, 0 failed`；3 个 skip 均为真实 PostgreSQL 专项；
- 本地全量后端：`1157 passed, 18 skipped, 0 failed`；
- Ruff check/format 与 diff check：通过；
- Backend CI 已增加 PostgreSQL 16 容量预检、分区别名/DEFAULT 路由、影子复制、事务回滚、
  分区裁剪及资源残留断言，首次运行链接在实现提交推送后回填；
- 前端无变更且本轮未重跑；R6 前端基线只作为历史证据；
- 当前未完成：活动 `kline_data` 切换、真实冷数据导出/删除、对象存储归档、生产备份恢复和
  维护窗口演练。完整边界见
  [`releases/20260802_r8_kline_partition_lifecycle.md`](releases/20260802_r8_kline_partition_lifecycle.md)。
