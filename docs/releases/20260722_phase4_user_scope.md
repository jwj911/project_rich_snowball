# 工程基线记录：Phase 4 私有数据 owner 谓词改写

> 类型：`engineering baseline`，不是生产发布。
> 对应清单：[`../release_checklist_20260719.md`](../release_checklist_20260719.md)
> 实施记录：[`../phase4_sql_ast_readonly.md`](../phase4_sql_ast_readonly.md)

## 发布元数据

- 实施提交：待提交
- 基线窗口：2026-07-22
- 变更范围：将 Agent 私有数据 `user_id` 自动注入从字符串拼接升级为 AST 谓词改写。
- 生产发布状态：未发布
- 回滚负责人：不适用（安全迭代基线）

## 已完成验证

- 定向数据库工具测试：`40 passed, 0 failed`。
- 后端全量测试：`978 passed, 8 skipped, 0 failed`。
- 全仓库 Ruff：通过。
- 覆盖多个私有表、别名、CTE、子查询、LEFT JOIN、UNION、task steps owner 关联和越权 user_id 条件。
- 本轮未新增依赖；既有 `sqlglot==26.20.0` 锁定保持不变。

## 生产发布阻塞项

- [ ] 提交已推送，且 Backend CI 对本次提交完成并结论为 success。
- [ ] 生产 PostgreSQL 迁移、备份恢复和 readiness 已重新执行。
- [ ] 生产权限、CORS、scheduler owner、前端 smoke 和 Lighthouse 已重新执行。
- [ ] 事故日志、trace id 和回滚结果已写入正式生产记录。
