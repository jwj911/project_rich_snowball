# Changelog

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
