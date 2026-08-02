# Changelog

## 2026-08-02

- R9 完成 CSP Report-Only S1 工程实现：前端保留原值不变的强制
  `Content-Security-Policy`，同时新增 `Content-Security-Policy-Report-Only` 与
  `Reporting-Endpoints`；候选 `script-src` 仅允许 `'self'`，违规只上报、不阻断业务。
- 新增匿名 CSP 报告接收端点，兼容 legacy `application/csp-report` 与 Reporting API
  `application/reports+json`，限制 8 KiB 请求体、20 条批量、受校验采样和独立 IP 限流；
  URL 在持久化前移除 userinfo、query 与 fragment，未知字段和敏感内容不落库。
- 每条持久化报告生成独立 `trace_id`，新增低基数
  `csp_reports_total{outcome}` 指标；`CSP_REPORT_SAMPLE_RATE` 默认 `1`，可在 `[0, 1]`
  范围配置。现有 `localStorage` access token、HttpOnly cookie、Bearer 写请求和 CSRF
  拒绝 cookie-only 写请求的边界保持不变。
- R9 独立审查修复前的后端全量为
  `1177 passed, 18 skipped, 0 failed, 103 warnings`；审查修复后受影响聚焦回归为
  `85 passed, 1 skipped, 0 failed`，Ruff check/format 通过。唯一 skip 是新增 PostgreSQL
  持久化专项，本地无隔离 PostgreSQL，待 Backend CI 的 PostgreSQL 16 环境执行；修复后的
  完整后端全量由 CI 复核。
- 审查增强前的基础版 R9 Playwright 为 `3 passed`。增加并发 401 单飞刷新和 SSE 首次断线
  重连后，增强版已通过 Playwright `--list`、TypeScript 与 ESLint，实际浏览器执行待
  Frontend CI；不得将基础版结果解释为增强版已在本地通过。
- 新增
  [`docs/releases/20260802_r9_csp_report_only_observability.md`](docs/releases/20260802_r9_csp_report_only_observability.md)。
  R9 本地实现提交为 `723ba9b949bccf7c96798d2f45388731350eacd3`；最终验证提交及
  Backend/Frontend CI 链接待补/待验证。本地和 CI 合成报告不是生产 SLO，也不能作为进入
  S2 强制 CSP 收紧的证据。
- R8 新增 K 线存储容量预检，固定使用 1 亿行、100 GiB 和分钟查询 P99 500 ms 阈值；
  PostgreSQL 报告覆盖容量、周期分布、时间边界、分区状态和查询计划，SQLite 明确返回
  `unsupported_for_partitioning`，每次生成脱敏 `trace_id` JSON。
- `benchmark_kline.py` 改为默认只读；只有显式 `--seed` 且非生产环境才允许生成 BENCH
  数据，并支持包含样本数、p50、p95、p99 和阈值结论的稳定 JSON。
- 新增当前模型兼容的 PostgreSQL LIST + RANGE 影子分区 DDL、未来 3 个月维护命令和隔离
  复制演练。命令默认 dry-run，拒绝活动表、非法标识符、非 PostgreSQL 和缺少确认参数；
  演练验证聚合一致性、自然键、序列、外键、冲突写入及分区裁剪，失败由事务回滚。
- 管理员新增 `/metrics/dashboard/kline-storage` 低成本概况，使用 60 秒 TTL；Prometheus
  常规抓取不执行 K 线容量统计。
- R8 实现提交为 `41c79f1ed70b90cfe46f163f3e5af80b5f93d3d6`，最终验证提交为
  `68386c51358a1e6f9a590f5e4e9b3edfea887624`。
- Backend CI 增加 PostgreSQL 16 的 R8 只读预检、全部周期别名/DEFAULT 路由、幂等 DDL、
  成功清理、失败回滚和影子资源残留门禁。本地全量后端为
  `1157 passed, 18 skipped, 0 failed`，Ruff check/format 和 diff check 通过；新增的 3 个
  PostgreSQL 用例因本机无隔离 PostgreSQL 而明确跳过。
- [Backend CI #38](https://github.com/jwj911/project_rich_snowball/actions/runs/30732688519)
  成功：R8 专项 `45 passed`，全量 PostgreSQL `1174 passed, 1 skipped`，覆盖率
  `75.98%`，API smoke、Ruff、`pip-audit` 和影子资源残留断言均通过。
- 新增
  [`docs/releases/20260802_r8_kline_partition_lifecycle.md`](docs/releases/20260802_r8_kline_partition_lifecycle.md)。
  R8 未替换活动 `kline_data`，未导出或删除冷数据，也未执行生产备份恢复，因此是非生产
  工程基线。

## 2026-07-30

- R7 新增 11 项只读生产发布预检，覆盖生产环境、PostgreSQL、强密钥、安全 CORS、真实数据源、
  Redis、发布提交/UTC 窗口/负责人及 `SSE_DEPLOYMENT_MODE`；每次输出独立 `trace_id`
  和脱敏结构化 JSON，不修改数据库、Redis、部署状态或发布清单。
- realtime quotes 成功刷新后由 worker 更新本地状态并向 Redis 写入仅含 UTC 时间戳的共享标记；
  API 使用本地/共享标记中的较新值驱动 SSE，Redis 不可用时按 60 秒有界周期刷新并记录脱敏
  降级/恢复事件。
- 生产 SSE 部署模式仅接受 `single` 或 `sticky`；本轮未实现 Redis Pub/Sub、跨实例连接注册、
  全局连接上限或跨实例旧连接取消。
- R7 主提交为 `753a599bab95ffc7205823f445f2b980d3c3e1fc`，Ruff CI 修复后的最终提交为
  `b6cd75756b960eeba169c92531dbcfc3cd6b706a`。本地全量后端为
  `1103 passed, 15 skipped, 0 failed`；两轮聚焦回归分别为 `106 passed` 和 `90 passed`，
  Ruff check/format、diff check 与 Compose config 均通过。
- [Backend CI #33](https://github.com/jwj911/project_rich_snowball/actions/runs/30493521137)
  成功，覆盖依赖锁、R7 placeholder preflight、Alembic、PostgreSQL pytest/API smoke、Ruff
  和 `pip-audit`；placeholder preflight 只验证契约，不是生产凭据或生产发布证据。
- 前端本轮无变更且未重跑；R6 前端结果仅保留为历史基线。新增
  [`docs/releases/20260730_r7_release_gates.md`](docs/releases/20260730_r7_release_gates.md)，
  明确真实生产凭据、部署、备份恢复、发布/回滚负责人仍未完成，当前不是生产已发布。

## 2026-07-27

- 完成 R6 隔离环境发布候选验证：空 PostgreSQL 迁移至 `c0d1e2f3a4b5`，逻辑备份与恢复
  演练、readiness、权限和 scheduler owner smoke 均通过。
- 修复 scheduler 关闭时向 APScheduler 传入不支持参数的问题；Compose 强制部署方提供
  `SECRET_KEY`、`CORS_ORIGINS` 与真实 `DATA_SOURCE`。
- 前端升级至 Next.js 15.5.22，并固定安全版本的 PostCSS/sharp；production build、
  Vitest 202 项、Playwright 40 项、双路由 Lighthouse 和生产依赖审计通过。
- Mock 用户与评论改为按用户名解析真实外键，消除 PostgreSQL 序列前移后的启动失败；
  Lighthouse CI 改用 3 个样本的 LCP 中位样本，并保留全部样本指标。
- Backend CI #31 与 Frontend CI #33 全部通过，后者生成 5.42 KB 趋势 artifact。
- 新增
  [`docs/releases/20260727_r6_release_candidate.md`](docs/releases/20260727_r6_release_candidate.md)，
  明确真实生产凭据、部署、CORS 和回滚负责人仍未验证，当前不是生产发布。

## 2026-07-26

- R5 完成：Lighthouse 改为 `home` / `products` 命名路由趋势，记录 commit 和 CI 元数据、
  跨提交 delta，并在 Frontend CI 恢复与上传 90 天趋势 artifact。
- 详情页补充实时行情降级、详情/评论/价位标注失败态及页面级回归；行情中心保留每页 20 条
  服务端分页，并记录超过 100 行时重新评估虚拟滚动的条件。
- refresh 轮换同步更新 SSE 使用的 access cookie，logout 同时清理 access/refresh cookie；
  CSP 和 localStorage access token 迁移策略、停止条件见
  [`docs/r5_frontend_quality_observability.md`](docs/r5_frontend_quality_observability.md)。
- R4 完成：建立共享 DSL transform 执行契约，compiler 默认生成
  `multiply_indicator2`，未知或参数非法的 transform 在回测数据读取前显式拒绝。
- 新增日频 expanding / rolling walk-forward 稳定性诊断、窗口指标汇总、质量提示和
  `not_run` / `inconclusive` 状态；冻结 DSL 结果不再被描述为独立 OOS 验收。
- `StrategyLifecycleDB.walk_forward_metrics` 已接入策略进化、策略回测、生命周期摘要和
  evolution 查询 API；日 K 时间窗口改为优先按 `trading_date` 进行包含式筛选。

## 2026-07-25

- 宽表构建接入 `data_ingestion_runs` 批次记录、连接类异常指数退避重试和不含原始行情样本的质量快照；失败通过 `trace_id` 和异常类型诊断。
- PostgreSQL 模式全量后端回归：`1017 passed, 1 skipped, 0 failed`。

## 2026-07-24

- 新增 [`docs/iteration_plan_20260724_follow_up.md`](docs/iteration_plan_20260724_follow_up.md)，统一编排 Phase 4 后续安全回归、数据基础、策略验证、前端质量和发布治理。
- 新增 PostgreSQL 私有查询语义回归测试，覆盖 LEFT JOIN、CTE/UNION 和 `agent_task_steps` owner 关联。
- 校正路线图中已完成的日志 payload 限制、实时行情 symbol 上限、评论级联和交易观点清洗状态。
- 在独立 PostgreSQL 测试库完成 Alembic head 迁移与 owner-scope 回归，并保留开发库迁移 marker 漂移的非破坏性处理。
- 私有数据 owner policy 收敛到单一映射，补齐 `frontend_logs`、`user_preferences` 隔离；用户自建新闻源与文章移出 Agent 通用 SQL 白名单。
- 新增 `agent_market_panel_daily` raw_contract 日频研究宽表、幂等重建服务和 dry-run 运维脚本，并接入 Data Catalog 与数据质量检查。
