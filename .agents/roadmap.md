<!-- .agents/roadmap.md — 模块演进状态与待处理事项 -->

> 当前状态：R1 至 R9 工程项已闭环；R10 已完成本地实施与验证，远端 Backend CI 待验证，
> 当前仍为非生产状态。R10 仅提供 evidence-only 服务与离线 CLI；R11、R12/S2、R13/S3 均未
> 开始。治理顺序见
> [`Post-R9` 计划](../docs/iteration_plan_20260802_post_r9.md)，实现边界见
> [R10 spec](../.trae/specs/classify-csp-evidence-readiness/spec.md)。R8 生产分区/冷归档与
> R7 分布式 SSE 均为未触发、未排期的条件轨道。
>
> R1 至 R9 历史执行证据见
> [`docs/iteration_plan_20260724_follow_up.md`](../docs/iteration_plan_20260724_follow_up.md)。

## 主要模块演进状态

### Phase 0：可运行性收口 — 已完成（2026-07-18）

- Mock 初始化补齐 `FutMainDailyDataDB` 主力日线，恢复 `/api/varieties` 列表数据
- 同步前端 `useProductKline` 测试契约，修复后端 schema 测试的执行顺序依赖
- `requirements.txt` / `requirements.lock` 补齐 `scikit-learn`、`feedparser` 及其依赖
- Python `ruff check .`、后端全量 pytest、前端 Vitest、TypeScript、ESLint、production build 全部通过
- 当前基线：后端 `965 passed, 8 skipped, 0 failed`；前端 `195 passed, 0 failed`
- 详细记录：[docs/iteration_plan_20260718_project_audit.md](../docs/iteration_plan_20260718_project_audit.md)

### Phase 1：行情读模型收敛 — 已完成（2026-07-18）

- `/api/varieties` 查询收敛到 `MarketDataService`
- 主力日线优先、实时快照 fallback、无数据状态和来源字段统一
- 新增 `upsert_fut_main_daily_bulk`、主力日线 pipeline 和 scheduler job
- 增加 SQLite/PG 读写回归与 `data_source` / `data_freshness` 测试

### Phase 2：执行可靠性与生产拓扑 — 已完成（2026-07-19）

- Agent 步骤持久化改为任务级事务，避免步骤级 `commit()` 带来的 SQLite 锁竞争
- `docker-compose.yml` 中 backend 关闭 scheduler，新增独立 worker 作为唯一 scheduler owner
- backend CI 增加 direct dependency/lock 漂移检查、PostgreSQL API smoke，coverage 门槛提升到 `40%`
- frontend CI 增加 PostgreSQL + Alembic + backend 启动和 Playwright Chromium smoke
- 新增 `fut_main_daily_data` Alembic 迁移 `f7a8b9c0d1e2`，并验证 `(variety_id, ts_code, period, trade_date)` 唯一键
- 升级 `python-multipart`、`scikit-learn`、`starlette` 到无已知漏洞版本，lock 漂移检查保持通过
- 本地后端全量：`965 passed, 8 skipped, 0 failed`；覆盖率 `71.97%`
- Backend CI #22：Alembic、PostgreSQL pytest、API smoke、Ruff、`pip-audit` 全部通过
- 前端 Vitest：`195 passed, 0 failed`；TypeScript、ESLint、production build 通过
- Frontend CI #28（run `29670891119`）：PostgreSQL migration、backend、frontend build/start、Chromium Playwright、Vitest、Lighthouse 全部通过
- 详情页价位标注 E2E 使用精确 heading 定位，`usePriceLevels` 增加主力范围隔离和 optimistic mutation 保护
- 详细记录：[docs/iteration_plan_20260718_project_audit.md](../docs/iteration_plan_20260718_project_audit.md)

下一阶段：进入 Phase 3「文档与发布治理」，建立唯一现状基线、发布清单和历史计划归档规则。

### Phase 3：文档与发布治理 — 首批完成（2026-07-19）

- `docs/iteration_plan_20260718_project_audit.md` 记录已完成审计基线；
  [`docs/iteration_plan_20260724_follow_up.md`](../docs/iteration_plan_20260724_follow_up.md)
  现保留为 R1 至 R9 已完成历史事实源，当前执行入口已切换到
  [`docs/iteration_plan_20260802_post_r9.md`](../docs/iteration_plan_20260802_post_r9.md)
- 新增 [`docs/release_checklist_20260719.md`](../docs/release_checklist_20260719.md)，统一代码、迁移、数据、权限、浏览器、备份和回滚检查
- ProductDB 退场计划、旧前端质量清单和旧前端路线图移动到 `docs/archive/`，并标记为历史记录
- 已完成的 Agent/项目审计、P0-P2、Phase 5 及 2026-07-05 修复记录移动到 `docs/archive/`，保留历史上下文但不再作为当前执行入口
- `.agents/data.md` 移除已退场的兼容层调度任务，更新归档链接

### Phase 3：文档与发布治理 — 第三批完成（2026-07-21）

- 新增 [`docs/releases/README.md`](../docs/releases/README.md)，固定工程基线和生产发布记录格式；
- 新增 [`docs/releases/20260721_engineering_baseline.md`](../docs/releases/20260721_engineering_baseline.md)，记录 Phase 3 文档治理基线，并明确其不是生产发布；
- `AGENTS.md`、`README.md`、`.agents/operations.md` 已接入发布记录入口；
- 未执行的生产检查保持未勾选，避免用历史 CI 结果冒充本次生产验收。

Phase 3 后续只在真实发布窗口填写生产记录；工程风险治理进入 Phase 4。

### Phase 4：远期风险与安全 — 第一项完成（2026-07-21）

- Agent `query_database` 已切换到 `sqlglot` AST 只读校验；
- 覆盖单语句、SELECT/集合查询根节点、DML/DDL/事务节点、危险函数、CTE/子查询和 schema/table 白名单；
- 新增 `sqlglot` 直接依赖与锁定版本，补充 31 个数据库工具回归用例；
- Backend CI run `29846448474` 已成功，覆盖 Alembic、PostgreSQL pytest、API smoke、Ruff 和 pip-audit；
- 详细记录：[`docs/phase4_sql_ast_readonly.md`](../docs/phase4_sql_ast_readonly.md)

### Phase 4：远期风险与安全 — 第二项完成（2026-07-22）

- 私有数据 `user_id` 自动注入改为 AST 作用域改写；
- 每个私有表按别名注入 owner 谓词，JOIN 表写入 `ON`，保留 LEFT JOIN 语义；
- CTE、子查询、UNION 和多个私有表分别隔离；
- `agent_task_steps` 使用 `EXISTS` 关联父任务的 `user_id`；
- 不信任查询中的其他 `user_id` 值，只有等于当前上下文用户时才跳过重复注入；
- 定向测试 `40 passed`，全量后端 `978 passed, 8 skipped, 0 failed`；
- Backend CI run `29881570031` 已成功，覆盖 Alembic、PostgreSQL pytest、API smoke、Ruff 和 pip-audit；
- 详细记录：[`docs/releases/20260722_phase4_user_scope.md`](../docs/releases/20260722_phase4_user_scope.md)

### Phase 4：远期风险与安全 — 第三项完成（2026-07-24）

- 新增后续迭代事实源：[`docs/iteration_plan_20260724_follow_up.md`](../docs/iteration_plan_20260724_follow_up.md)；
- 独立 PostgreSQL 测试库从空库迁移到 `f7a8b9c0d1e2`，owner-scope 回归覆盖 LEFT JOIN、
  CTE/UNION、`agent_task_steps` 父任务关联、前端日志和用户偏好；
- 数据库工具、PostgreSQL owner-scope 与既有 PostgreSQL upsert 回归合计 `50 passed`；
- 私有表 owner policy 已收敛到单一映射，用户自建新闻源和新闻文章不再由通用 SQL 查询；
- 决策记录：[`docs/phase4_private_data_access_boundary.md`](../docs/phase4_private_data_access_boundary.md)。

当前下一项：进入 R3「数据基础与可复现性」，先完成 `raw_contract` 日级宽表的最小
schema、血缘和重建设计。

### R3：数据基础与可复现性 — 第一项完成（2026-07-24）

- 新增 `agent_market_panel_daily`，首版只物化 `raw_contract`、`1d` 合约级视图；
- `kline_data` 提供 OHLCV，`fut_daily_data` 补充成交额、持仓和结算价；估算值与缺失值通过
  `source_flags` 和 `quality_status` 显式标记；
- 通过 `rebuild_raw_contract_daily_panel()` 与
  `scripts/rebuild_raw_contract_panel.py` 支持幂等重建和 dry-run；
- Data Catalog 与 DataQualityService 已提供宽表覆盖和质量摘要；
- 干净 PostgreSQL 库迁移至 `a1c2d3e4f5a6`，专项回归通过；
- 本地全量后端：`1012 passed, 1 skipped, 0 failed`；全仓库 Ruff 通过；
- 详细记录：[`docs/r3_raw_contract_market_panel.md`](../docs/r3_raw_contract_market_panel.md)。

R3 后续：构建批次/失败重试/质量快照、主力连续与复权视图、FactorMiningAgent 与
BacktestAgent 的显式 `data_view` 消费。

### R3：数据基础与可复现性 — 第二项完成（2026-07-25）

- `run_raw_contract_daily_panel_build()` 为每次宽表构建尝试写入
  `data_ingestion_runs`，成功批次含统计与无原始行情样本的质量快照；
- 可恢复数据库连接错误以指数退避重试，失败批次使用共享 `trace_id` 和异常类型诊断；
- CLI 支持 `--max-attempts`、`--retry-delay-seconds`，dry-run 不写入数据或批次记录；
- 独立 PostgreSQL 空库迁移至 `a1c2d3e4f5a6` 并通过宽表批次专项回归；
- PostgreSQL 模式全量后端：`1017 passed, 1 skipped, 0 failed`；全仓库 Ruff 通过；
- 详细记录：[`docs/r3_raw_contract_market_panel.md`](../docs/r3_raw_contract_market_panel.md)。

### R3：数据基础与可复现性 — R3.3 至 R3.6 完成（2026-07-26）

- 新增 `main_continuous`、`main_back_adjusted`、`main_forward_adjusted`，并以实际合约、
  换月 ID、调整值、算法、血缘 JSON 与 build trace 支持重放；
- Data Catalog、DataQualityService 与 DataQualityAgent 均按 `data_view + period` 工作，
  连续/复权视图检查日期、OHLC、换月和血缘；
- 因子与回测只有显式 `data_view` 时才消费宽表，默认保持原 K 线语义；`raw_contract`
  必须指定具体合约，报告和缓存键保留数据口径；
- worker 独占宽表调度，16:18 在依赖日线完成后运行，至少回建 20 个交易日，迟到换月从
  最早影响日回推。

R3 已收口，并作为 R4 的数据口径基础。

### R4：策略验证闭环 — 已完成（2026-07-26）

- 策略 compiler、DSL 校验、回测服务、条件引擎与可读解释共享 transform 契约；
  `multiply_indicator2` 为 canonical 右侧 `indicator2 * value` 变换，历史
  `multiply_value` 仅保持兼容，未知或参数非法 transform 显式拒绝；
- 新增基于已观测日线的 expanding / rolling walk-forward 服务，报告每个 IS/OOS 窗口、
  聚合指标、覆盖和质量提示，并对数据不足、失败窗口和冻结 DSL 的非独立 OOS 边界明确标记；
- `StrategyLifecycleDB.walk_forward_metrics` 已接入策略进化、策略回测、摘要和 evolution
  API 查询；`BacktestAgent` 与 `StrategyEvolutionAgent` 统一展示诊断状态；
- `KlineDataDB` 窗口查询优先使用 `trading_date` 包含边界，旧数据才回退 SQL 日期；
- 详细记录：[`docs/r4_dsl_walk_forward_validation.md`](../docs/r4_dsl_walk_forward_validation.md)。

下一项：R5 前端质量与观测趋势。

### R5：前端质量与观测趋势 — 已完成（2026-07-26）

- Lighthouse 采集固定为 `home` / `products` 命名路由，记录 commit、ref、CI run/attempt 和
  同 ref 上一提交的指标 delta；Frontend CI 恢复并上传 90 天趋势 artifact；
- 行情中心保持服务端每页 20 条，因双响应式 DOM 仍有成本；超过 100 行、无限滚动或可复现
  性能回归时必须以生产样本重新评估虚拟滚动；
- 详情页恢复单品种实时行情读取，实时故障保留收盘数据并明确降级；详情、评论和价位标注
  写入失败均有页面级状态与 Playwright 回归；
- refresh 轮换同步 access cookie，logout 同时清理 access/refresh cookie；CSP Report-Only、
  nonce/hash、内存 token 和 cookie-only 写请求的前置/停止条件已记录。

详细记录：[`docs/r5_frontend_quality_observability.md`](../docs/r5_frontend_quality_observability.md)。
后续已进入 R6 发布候选验证；真实发布仍需按发布日重新执行，不能复用工程或历史 CI 结果。

### R6：发布候选基线 — 已完成（2026-07-27）

- 隔离 PostgreSQL 候选库从空库迁移到 `c0d1e2f3a4b5`，完成逻辑备份、恢复演练和核心计数核对；
- readiness、scheduler owner、行情/实时、管理员与普通用户权限 smoke 已通过；
- scheduler 使用 APScheduler 支持的优雅停止契约，Compose 强制生产密钥、CORS 和数据源；
- Next.js 升级到 15.5.22，PostCSS/sharp 固定安全版本；production build、Vitest 202 项、
  Playwright 40 项、双路由 Lighthouse 和生产依赖审计通过；
- 候选提交 `c5e1a545` 已推送；Backend CI #31 与 Frontend CI #33 已通过，发布记录见
  [`docs/releases/20260727_r6_release_candidate.md`](../docs/releases/20260727_r6_release_candidate.md)。

R6 后续已进入 R7 发布门禁加固；R6 前端结果继续作为历史基线，不替代 R7 或真实生产窗口验证。

### R7：生产发布门禁与 SSE 更新信号 — 工程基线已完成（2026-07-30）

- 新增 11 项只读生产预检，覆盖 `ENV`、PostgreSQL、强密钥、安全 HTTPS CORS、真实数据源、
  Redis、发布提交、UTC 窗口、发布/回滚负责人及 `SSE_DEPLOYMENT_MODE`；
- 每次预检生成独立 `trace_id` 和脱敏结构化 JSON；CLI 不修改数据库、Redis、部署状态或
  发布清单；
- worker 成功刷新 realtime quotes 后更新本地状态，并向 Redis 写入只含 UTC 时间戳的共享
  标记；API 使用本地/共享标记中的较新值驱动 SSE；
- Redis 不可用时保留本地状态，并按 60 秒有界周期强制刷新；恢复后自动重新读取共享标记；
- 生产 SSE 模式仅允许 `single|sticky`。连接注册、每用户旧连接取消和全局连接上限仍为
  实例内状态，本轮未实现 Redis Pub/Sub 或跨实例连接管理；
- R7 主提交为 `753a599bab95ffc7205823f445f2b980d3c3e1fc`，Ruff CI 修复后的最终提交为
  `b6cd75756b960eeba169c92531dbcfc3cd6b706a`；
- 本地全量后端 `1103 passed, 15 skipped, 0 failed`；两轮聚焦回归分别为
  `106 passed` 和补强后的 `90 passed`，Ruff check/format、diff check 与 Compose config
  均通过；
- [Backend CI #33](https://github.com/jwj911/project_rich_snowball/actions/runs/30493521137)
  成功。CI placeholder preflight 只验证契约，不是生产证据；
- 前端无变更且本轮未重跑；R6 前端验证只作为历史证据。

发布记录见
[`docs/releases/20260730_r7_release_gates.md`](../docs/releases/20260730_r7_release_gates.md)。
生产侧仍需取得真实生产凭据，指定发布/回滚负责人，并在真实生产窗口完成备份恢复、部署和
smoke；完成前不得标记为生产已发布。

### R8：K 线分区生命周期准备 — 工程实现已完成（2026-08-02）

- 新增只读容量预检，固定使用 1 亿行、100 GiB 和分钟查询 P99 500 ms 阈值，输出脱敏
  `trace_id` JSON；SQLite 返回 `unsupported_for_partitioning`；
- benchmark 默认只读，显式 `--seed` 仅允许非生产隔离环境；
- 影子表按 `LIST (period)` 和分钟 `RANGE (trading_time)` 分区，覆盖全部现有周期别名及
  DEFAULT；DDL 与当前 `KlineDataDB` 字段、精度、外键、主键和自然唯一键一致；
- 生命周期与迁移命令默认 dry-run，硬拒绝活动表、非法标识符、非 PostgreSQL 和缺失确认；
- 隔离演练使用 `REPEATABLE READ` 和 advisory lock，验证复制计数、周期计数、时间边界、
  自然键、序列、外键、冲突写入、级联和 `EXPLAIN` 分区裁剪；
- 管理员存储概况使用 60 秒 TTL 和 PostgreSQL 系统目录估算，Prometheus scrape 不执行
  容量统计；
- R8 实现提交为 `41c79f1ed70b90cfe46f163f3e5af80b5f93d3d6`；
- 本地全量后端 `1157 passed, 18 skipped, 0 failed`，Ruff check/format 与 diff check
  通过；新增的 3 个真实 PostgreSQL 用例由 Backend CI PostgreSQL 16 门禁执行。
- 最终验证提交为 `68386c51358a1e6f9a590f5e4e9b3edfea887624`；
  [Backend CI #38](https://github.com/jwj911/project_rich_snowball/actions/runs/30732688519)
  成功，R8 专项 `45 passed`，远程全量 `1174 passed, 1 skipped`。

完整记录见
[`docs/releases/20260802_r8_kline_partition_lifecycle.md`](../docs/releases/20260802_r8_kline_partition_lifecycle.md)。
R8 未切换活动表，未导出或删除冷数据，也未执行生产备份恢复；达到容量阈值后必须另立生产
切换和归档规格。

### R9：CSP Report-Only 观测闭环 — 工程门禁已闭环（2026-08-02）

- 前端同时返回原值不变的强制 CSP、`Content-Security-Policy-Report-Only` 和
  `Reporting-Endpoints`；候选 `script-src` 仅允许 `'self'`，只上报而不阻断；
- 匿名接收端点兼容 legacy CSP 与 Reporting API，限制 8 KiB 请求体、20 条批量、受校验
  `CSP_REPORT_SAMPLE_RATE` 和 `report:csp` 独立 IP 限流；
- document URL、blocked URL、source file 与 referrer 在持久化前移除 userinfo、query 和
  fragment；sample、脚本、DOM、Cookie、Authorization、原始请求体和未知字段不落库；
- 每条持久化报告使用独立 `trace_id`，实际指标为 `csp_reports_total{outcome}`，outcome
  固定为 `received`、`accepted`、`sampled`、`rejected`、`rate_limited`、
  `persist_failed`；
- 独立审查修复前的 R9 后端全量为
  `1177 passed, 18 skipped, 0 failed, 103 warnings`；修复后受影响聚焦回归为
  `85 passed, 1 skipped, 0 failed`，Ruff check/format 通过；唯一 skip 是新增 PostgreSQL
  持久化专项，本地无隔离 PostgreSQL；Backend CI 的 PostgreSQL 16
  `R9 CSP contract gate 39 passed` 包含该持久化集成测试，远端全量约
  `1195 passed, 1 skipped`；
- 审查增强前的基础版 R9 Playwright 为 `3 passed`；增加并发 401 单飞刷新和 SSE 首次断线
  重连后，本地 Playwright `--list`、TypeScript 与 ESLint 通过；Frontend CI 的增强版 R9
  E2E `3 passed`、全量 Playwright `43 passed`，Vitest、build 与 Lighthouse 均成功；
- 完整记录见
  [`docs/releases/20260802_r9_csp_report_only_observability.md`](../docs/releases/20260802_r9_csp_report_only_observability.md)。

R9 本地实现提交为 `723ba9b949bccf7c96798d2f45388731350eacd3`，本地验证文档提交为
`37fc8008a74c1b74c48f74aac5e3267c8a29e5b6`，CI 稳定性修复提交为
`c7a721a04f58caa51860be67d870855663186a14`。
[Backend CI run 30739553595](https://github.com/jwj911/project_rich_snowball/actions/runs/30739553595)
与
[Frontend CI run 30740784839](https://github.com/jwj911/project_rich_snowball/actions/runs/30740784839)
均成功。R9 尚未生产部署，也未完成真实完整业务周期观测；强制 CSP 未收紧，不移除
`localStorage` access token，不启用 cookie-only 写请求。真实报告未归类前不进入 S2，S3
内存 access token 仍需独立立项；本地和 CI 合成报告不是生产 SLO。

### R10：CSP 证据归类与 S2 准入报告 — 本地实施验证完成（2026-08-03）

- 新增后端 `csp_evidence` 有界只读服务和 `scripts/csp_evidence_report.py` 离线 CLI；没有
  新增管理员 HTTP API、数据库表或 Alembic 迁移；
- 新 CSP 记录使用服务端 `ENV` 和可选 `RELEASE_COMMIT` 归属。后者非空时必须是完整 40 位
  Git SHA；缺失不阻止 S1 接收，但对应记录不能形成 `ready_for_review`；
- Compose 对 backend 和 worker 均安全传递可选 `RELEASE_COMMIT`，空值不会变成生产启动
  必填；
- context、catalog 和 report 按运维约束存放在仓库外且不得提交；CLI 强制 report path
  位于仓库外；
- 单次执行限制为最长 31 天、最多 50,000 条记录、500 个聚合组、30 秒和 256 KiB 报告；
  退出码 `0/1/2/3/4` 分别对应 ready/insufficient/blocked/failed/write-failed，synthetic
  的预期结果是 `insufficient_evidence` 和退出码 `1`；
- 本地聚焦测试 `375 passed, 5 skipped, 1 warning`，后端全量
  `1421 passed, 22 skipped, 103 warnings`；本地 PostgreSQL 不可用，相关集成用例保持明确
  skip；
- 远端 Backend CI 待验证，因此尚未形成 R10 远程工程闭环，更不是生产发布或 S2 准入。

R10 不修改强制 CSP、Report-Only 策略、`localStorage` token、Bearer 写请求或 cookie-only
写请求拒绝边界。R11 生产操作者与完整业务周期、R12/S2、R13/S3 均未开始。

### Phase 1~3：用户工作区、合约 K 线、生产边界 — 已完成

- `price_levels` / `watchlists` / `workspace` 云端同步闭环
- `contract_rollovers` + 连续 K 线拼接 + 合约切换
- 独立 worker、`ENABLE_SCHEDULER=0` 默认、数据源熔断、数据质量检查

### Phase 4：ProductDB 全面退场 — 已完成（2026-05-28）

- 删除 `products` 物理表及所有废弃代码，品种数据统一走 `VarietyDB`
- pytest 全部通过

### 前端监控闭环 — 已完成（2026-06-01）

- 后端：`POST /api/log/frontend` + `FrontendLogDB` + Alembic 迁移
- `sentry-lite.ts` + `lib/vitals.ts`：无论 Sentry 是否启用，总是同时发送到后端日志端点
- 后端 `GET /api/log/frontend` 支持 admin 查询全部 / 普通用户查询自己的日志

### CSRF 防护 — 已完成（2026-05-29）

- 后端 `dependencies.py` 方法感知鉴权
- `test_csrf_protection.py` 覆盖写接口拒绝/读接口兼容

### SSE 鉴权统一 — 已完成（2026-05-29）

- 方案 B：废弃 stream-token，SSE 鉴权统一走 cookie-only 路径
- `/api/realtime/stream-token` endpoint 标记 `deprecated=True`
- SSE 连接管理仍为进程内状态，生产只允许 `single|sticky`；R7 已增加 worker/API Redis
  时间戳共享标记，但未实现 Pub/Sub 或跨实例连接注册/取消

### 交易时段 badge 后端权威化 — 已完成（2026-05-29）

- `useMarketStatus()` SWR hook 统一消费 `/api/market/status`
- `MarketSessionBadge` 和 `MarketClosedBanner` 共用同一份后端状态

### 价位标注 batch scope/contract 补齐 — 已完成（2026-05-29）

- `PriceLevelBatchItem` schema 与单条在 scope/contract_id 语义上完全一致
- 重复检测 key 扩展为 `(variety_id, type, price, scope, contract_id)`

### Lighthouse 性能基线 — 已完成（2026-05-29）

- `scripts/lighthouse-baseline.js`：headless Chrome 测量首页未登录态性能
- 报告保存到 `.lighthouse/latest.json`
- `frontend-ci.yml` 集成 Lighthouse，build 后自动跑基线

### 标注价格精度统一 — 已完成（2026-05-29）

- `formatPricePayload(price, precision)` 专用于 API payload 格式化
- `usePriceLevels` 创建/迁移标注时使用 `formatPricePayload()` 替代 `toFixed(2)`

### SSE URL 截断 — 已完成（2026-05-29）

- `frontend/lib/realtimeStore.ts`：`buildSseUrl` 当 symbol 数量 >30 时省略 `symbols` 参数
- 后端 `symbols` 为空时自动订阅全部活跃品种

### 精度中立化 — 已完成（2026-05-29）

- K 线价格显示统一使用 `formatPrice`，支持品种级别 `price_precision` 配置
- `CrosshairTooltip`、`KlineChartHeader`、`PriceChange` 等组件接入精度配置

### AI Chat（期货助手）— 已完成（2026-06-01）

**后端**

- `ChatMessageDB` 模型 + Alembic 迁移
- Router `/api/chat`：历史记录查询 + 发送消息 + 清空对话
- AI 服务 `services/ai_chat.py`：OpenAI 兼容 API，自动检索 `RealtimeQuoteDB` + `OpinionDB` 作为上下文
- 未配置时返回友好提示（不阻断应用启动）

**前端**

- `/chat` 页面：ChatGPT 风格对话界面
- 导航：`secondaryNavGroups` 新增「AI 助手」

### Portfolio（模拟持仓）— 已完成（2026-06-01）

**后端**

- `TradeRecordDB` 模型 + Alembic 迁移
- Router `/api/portfolio`：列表（含实时浮动盈亏）+ 创建 + 平仓 + 删除
- 盈亏公式：`long: (exit - entry) * qty * multiplier`，`short: (entry - exit) * qty * multiplier`

**前端**

- `/portfolio` 页面：盈亏统计面板 + 交易卡片列表
- 导航：`secondaryNavGroups` 新增「模拟持仓」

### Price Alert（价格预警）— 已完成（2026-06-01）

**后端**

- `PriceAlertDB` 模型 + Alembic 迁移
- Router `/api/price-alerts`：CRUD + 触发查询
- Scheduler 集成：`refresh_realtime_quotes` 成功后调用 `_check_price_alerts()`

**前端**

- API 层：`lib/api/price_alerts.ts`
- 品种详情页 `PriceAlertPanel`：表单 + 列表 + 删除

### Opinions（交易观点/日记）— 已完成（2026-05-30）

**后端**

- `opinions` 表 + 生命周期字段（`status/closed_at/actual_outcome`）
- Router `/api/opinions`：公开列表 + 个人时间线 + CRUD
- `OpinionService` 作为 service 层试点，router 仅负责 HTTP 契约转换

**前端**

- `/opinions` 页面：双标签页「全部观点」+「我的观点」
- 筛选：品种、方向、状态

### News（新闻资讯）— 已完成（2026-05-30）

**后端**

- `NewsSourceDB` / `NewsArticleDB` 模型
- RSS 抓取 + AI 摘要（`services/news_fetcher.py`）
- Router `/api/news`：源管理 + 文章列表 + 单篇摘要
- **手动抓取后台化**（2026-06-24）：`/api/news/fetch` 与 `/api/news/sources/{id}/fetch` 改为通过 `BackgroundTasks` 提交后台任务，立即返回 `NewsFetchTaskResponse`，不再同步阻塞 HTTP 请求；新增 `fetch_source_background` / `fetch_all_enabled_sources_background` 函数，内部独立创建 `SessionLocal` 会话

**前端**

- `/news` 页面：来源筛选 + 标题搜索 + AI 解读
- 搜索输入已接入 `useDebouncedValue`

### 前端 Sprint 2：体验优化 — 已完成（2026-06-04）

- **搜索防抖**（P2-1）：新建 `useDebouncedValue.ts`，products 和 news 页面搜索输入防抖 250ms，消除请求洪峰和 UI 闪烁
- **Token 安全评估**（P2-2）：选择方案 C（保守），新建 `frontend/docs/SECURITY_RISKS.md` 记录 RISK-001（access token 存 localStorage）及后续行动项
- **实时行情 Store 语义清晰化**（P2-3）：`realtimeStore.ts` 的 `notifyAll` 同时提供 `snapshot`（全量）和 `delta`（增量），`useRealtimeQuotes.ts` 明确区分增量合并与全量替换场景
- **Lighthouse 端口基线修复**（P2-4）：`.lighthouse/latest.json` url 修正为 `http://127.0.0.1:3200`，与 `npm run dev` 实际端口一致
- **验证**：`npx tsc --noEmit` 通过，`npm run lint` 通过，`useDebouncedValue.test.ts` 通过

### 前端 Sprint 3：架构清理 — 已完成（2026-06-05）

- **导航组件去重**（P3-1）：删除死代码 `SideNav.tsx` 和 `MobileNav.tsx`（无任何页面引用）；`Navbar.tsx` 从 `navigation.ts` 导入 `isActivePath`，消除内联重复定义。遵循“如无必要勿增实体”，不强行拆分 Navbar
- **测试覆盖补齐**（P3-2）：新建 `e2e/metrics.spec.ts`（未登录门禁 + 已登录直达不跳转 + 指标卡片显示）、`e2e/news.spec.ts`（未登录门禁 + 已登录加载 + 搜索框防抖）
- **验证**：`npx tsc --noEmit` 通过，`npm run lint` 通过，单元测试通过

### 后端 Roadmap V3 阶段四：扩展性与限流 — 已完成（2026-06-05）

- **高成本 GET 限流**：`/api/realtime/batch`（60s/100req）、`/api/realtime/stream`（60s/30req）增加独立限流窗口
- **SSE 独立限流**：按 IP 限流，超限时返回 429 而非静默断开
- **登录/注册限流 Redis 化**：与全局限流 middleware 统一，使用 `check_rate_limit`（Redis 优先+内存降级）；action key 独立（`auth:register`/`auth:login`）
- **Redis 空值标记修复**：用常量字符串 `__CACHE_EMPTY__` 替代 dict 对象，穿透防护在 Redis 路径稳定
- **SSE query token 移除**：标记 `deprecated=True`；鉴权改为 cookie 优先，token 仅降级兼容

### 后端 Roadmap V3 阶段五：CI/运维与架构优化 — 已完成（2026-06-05）

- **CI 增强**：backend-ci.yml 增加 Alembic 迁移一致性检查（CI 内嵌 PostgreSQL service）+ pytest-cov（当前阈值 40%）
- **运维文档补齐**：`python/docs/sse_scaling_strategy.md`（SSE 部署约束）、`python/docs/kline_partitioning.md`（K 线表分区策略）
- **交易日历预测告警**：`services/trading_calendar.py` 使用预测年份时输出 warning 日志
- **Service 层试点**：`routers/opinions.py` 提取 `OpinionService`，router 仅负责 HTTP 契约转换
- **compose backend service**：取消 backend 注释，配置健康检查、环境变量、端口映射

### Agent 系统 Phase 0~2 — 已完成（2026-07-04）

**Phase 0：基座修复与边界收敛**

- Alembic revision 冲突修复；`agent_tasks` / `agent_task_steps` 表模型与迁移完成
- 统一 `AgentEvent` schema（start/thought/action/observation/result/error/done）前后端一致
- Tool 注册与执行入口收敛：`@register_tool` 装饰器 + `_execute_tool` 服务层调用
- 复用 `services/ai_chat.py` 作为 LLM client

**Phase 1：DataAgent**

- 品种别名解析（黄金→AU，螺纹钢→RB，原油→SC）
- 5 个数据工具：get_variety_info、get_realtime_quote、get_kline_data、list_active_varieties、get_market_status
- 规则优先解析 + LLM fallback 的意图理解

**Phase 2：TechAnalysisAgent + RiskManagementAgent**

- 后端纯 numpy/pandas 指标库 `python/lib/technical_indicators.py`（12 个指标）
- 技术分析子模块：trend、pattern、divergence、composite（5 维度 0-100 综合评分）
- 风控子模块：position（仓位管理）、stop_loss（5 种止损）、take_profit（5 种止盈）、drawdown（回撤控制）
- 前端 Chat 页升级为 8 种模式切换
- 流式 SSE 展示 Agent 执行过程（步骤展开/收起）

**前端**

- `/chat` 页面重构：模式切换标签 + Agent 执行步骤可视化
- API 层新增 `lib/api/agents.ts`

**体验修复计划 P0/P1（2026-07-04）**

- **流式真实化**：`core.py` 新增 `PROGRESS` 事件与 `map_role_to_event_type`；全部本地 Agent 的 `run_stream` 先 `start`，过程中实时 `thought/action/observation/progress`，最后 `result/error + done`，避免「执行完再回放」。
- **执行器批量提交**：`executor.py` 步骤持久化由 per-step `commit()` 改为批量提交，解决 SQLite `database is locked`。
- **LLM 客户端加固**：`llm_client.py` 共享 `httpx.AsyncClient`、指数退避重试（最多 3 次）、记录上游状态码与响应摘要。
- **风控参数真实化**：`risk_management_agent.py` 浮动盈亏与止损计算使用品种真实 `multiplier` / `tick_size`；移除账户余额 50% 错误兜底；持仓加载失败改 `warning`。
- **策略 DSL 语义修正**：`strategy_compiler_agent.py` 中 MACD+成交量条件改为 `volume > volume_sma * mult`（通过 `transform: multiply_indicator2` 表达）；删除重复 `_is_valid_indicator`。
- **数据 bad 降级**：`analysis_pipeline_agent.py` preflight `bad` 时返回「数据现状报告」+ `completed` 状态，不再直接失败。
- **移除悬空能力**：`routers/agents.py` 与 `schemas.py` 移除未实现的 `orchestrator` 类型。
- **前端 SSE 治理**：`agents.ts` 支持 `AbortSignal`、`event:` 标签解析、malformed 行提示；`chat/page.tsx` 增加 `AbortController` 与停止按钮。
- **测试补强（历史记录）**：新增 `tests/test_agent_streaming.py`、`tests/test_agent_data_preflight.py`；该阶段后端曾达到 `669 passed, 7 skipped, 0 failed`，当前统一基线见本文顶部 Phase 0。

### TraderAgent 新增上线（2026-07-05）

**目标**：新增交易员 Agent，模拟经验丰富的期货交易员，基于多周期图表研判输出具体交易计划。

**后端**

- 新增 `services/agent/trader_agent.py`：交易员 Agent 主类，支持四种交易风格（scalping / intraday_swing / short_term_trend / medium_term_trend）
- 新增 `services/agent/trader/` 子模块：
  - `market_structure.py`：趋势识别、支撑阻力、突破/假突破判断
  - `multi_timeframe.py`：多周期共振分析与入场周期推荐
  - `candlestick.py`：K线形态识别与多空力量评分
  - `trade_plan.py`：交易计划生成（方向/入场/止损/止盈/仓位/盈亏比/置信度）
  - `risk_check.py`：风控校验（单笔风险、盈亏比、仓位、回撤提示）
- 接入 `routers/agents.py`：`_AGENT_CAPABILITIES` 与 `_build_agent()` 增加 `trader`
- 更新 `schemas.py`：`AgentType.TRADER` + task/chat 请求 pattern
- 更新 `services/agent/intent_router.py`：交易相关关键词路由到 `trader`
- 更新 `services/agent/__init__.py`：导出 `TraderAgent`

**前端**

- `frontend/app/chat/page.tsx`：Chat 页增加 `trader` 模式、快捷提示、图标与描述
- `frontend/app/agents/page.tsx`：`agentTypeLabels` 增加 `trader: '交易员'`

**测试**

- `tests/test_trader_modules.py`：12 个单元测试
- `tests/test_trader_agent.py`：6 个集成测试
- trader 专项测试 18 个全部通过；前端 `tsc --noEmit` + `lint` 通过

**设计文档**

- `docs/trader_agent_design.md`：完整设计文档 + 迭代进展记录

### 策略/回测/预警新模块 — 持续迭代中

- `strategies` / `backtest_runs` / `alert_events` / `alert_event_user_states` 等表已加入模型
- 后端 routers：`strategies.py`、`alerts.py`
- 前端页面：`/strategies`、`/alerts`、`/agents`、`/agents/detail`
- 相关 pytest 已覆盖核心链路：`test_strategies.py`、`test_backtest_agent.py`、`test_alert_events.py`、`test_strategy_compiler.py`

## 已完成安全边界校正（2026-07-24）

以下历史 P1 项已在代码和测试中完成，保留在此用于追溯：

1. ~~前端日志鉴权与 payload 限制~~：已覆盖 8KB 大小、嵌套深度和 key 数量限制。
2. ~~RSS URL 校验与抓取超时~~：已拒绝非 HTTP(S)、内网/本地地址并限制超时和重定向。
3. ~~价位标注并发重复~~：已建立 partial unique index。
4. ~~评论外键冲突~~：品种/用户删除使用级联策略。
5. ~~实时行情批量 symbol 上限~~：batch 与 SSE 共用 50 个 symbol 上限。
6. ~~交易观点 reason 字段清洗~~：请求 schema 层执行 HTML 清洗。

后续未完成项统一以
[`docs/iteration_plan_20260802_post_r9.md`](../docs/iteration_plan_20260802_post_r9.md)
为执行入口，不再从本节拆分平行待办。

## 待处理 P2 风险接受项

以下问题已被识别，但在当前阶段作为**风险接受项**处理，不影响当前产品形态上线；后续可按业务增长逐步推进：

1. ~~**API 版本治理**：当前所有接口统一在 `/api/` 前缀下，无 `/api/v1` 版本隔离。~~ **已修复（2026-06-24）**：新增 `ApiVersionMiddleware`，`/api/v1/*` 透明映射到 `/api/*`，`/api/` 继续兼容；前端可逐步迁移，详见 `BACKEND_API_VERSIONING_GUIDE.md`。
2. **`kline_data` 生产切换/归档**：R8 已完成容量门禁、影子 LIST+RANGE DDL、隔离演练和
   存储观测；活动表仍是单表。真实切换、冷数据导出/删除和生产恢复演练待达到阈值后另立规格，
   详见 `python/docs/kline_partitioning.md`。
3. ~~**RSS fetch 后台化**：`/api/news/sources/{id}/fetch` 在 API 请求内同步执行，慢源可能导致请求超时。~~ **已修复（2026-06-24）**：手动触发接口改为 `BackgroundTasks` 异步执行。
4. ~~**自动备份/恢复演练**：`python/docs/postgres_backup_runbook.md` 已提供手动 runbook，但尚未自动化。~~ **已修复（2026-06-24）**：新增 `python/scripts/backup_postgres.py`（逻辑/物理备份 + 过期清理）与 `python/scripts/restore_postgres.py`（恢复演练 + 核心表行数校验），支持 `DATABASE_URL` / `PG*` 环境变量与 `--dry-run`。
5. ~~**`database_tools.py` SQL 安全加固**：当前使用正则白名单 + 字符串匹配做 SQL 校验，存在被绕过的理论风险。~~ **已完成 AST 只读校验和 owner 谓词改写（2026-07-22）；PostgreSQL 专项语义回归见后续迭代 R1。**

> 注：上述列表随修复迭代更新；已修复项保留 ~~删除线~~ 以便追溯。
