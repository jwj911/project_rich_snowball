# Changelog

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
