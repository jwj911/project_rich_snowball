# 工程基线记录：Phase 4 SQL AST 只读校验

> 类型：`engineering baseline`，不是生产发布。
> 对应清单：[`../release_checklist_20260719.md`](../release_checklist_20260719.md)
> 实施记录：[`../phase4_sql_ast_readonly.md`](../phase4_sql_ast_readonly.md)

## 发布元数据

- 实施提交：`0d225664`
- 基线窗口：2026-07-21
- 变更范围：为 Agent `query_database` 引入 `sqlglot` AST 只读校验和锁定依赖。
- 生产发布状态：未发布
- 回滚负责人：不适用（安全迭代基线）

## 已完成验证

- 定向数据库工具测试：`31 passed, 0 failed`。
- 后端全量测试：`969 passed, 8 skipped, 0 failed`。
- 全仓库 Ruff：通过。
- 依赖锁漂移检查：通过。
- `pip check`：No broken requirements found。
- `pip-audit`（OSV）：No known vulnerabilities found。
- [Backend CI run 29846448474](https://github.com/jwj911/project_rich_snowball/actions/runs/29846448474)：记录创建时仍为 `in_progress`，待 GitHub 完成后补记最终结论。

## 生产发布阻塞项

- [ ] Backend CI 对本次提交完成并结论为 success。
- [ ] 生产 PostgreSQL 迁移、备份恢复和 readiness 已重新执行。
- [ ] 生产权限、CORS、scheduler owner、前端 smoke 和 Lighthouse 已重新执行。
- [ ] 事故日志、trace id 和回滚结果已写入正式生产记录。
