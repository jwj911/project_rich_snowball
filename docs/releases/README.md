# 发布记录

本目录保存按版本逐次填写的发布记录。每次真实发布或工程基线发布都应从
[`../release_checklist_20260719.md`](../release_checklist_20260719.md) 复制检查项，
并保留提交、验证结果、备份、回滚和遗留风险。

## 记录规则

- 文件名使用 `YYYYMMDD_<short-slug>.md`，日期按发布窗口的 UTC 日期。
- 明确标注 `engineering baseline` 或 `production release`，工程基线不得表述为生产已发布。
- 发布提交必须是已推送且可回滚的 Git 提交；测试和 CI 证据使用可追溯链接。
- 未执行的生产检查保持未勾选，并在“阻塞项”中说明原因，不用历史 CI 结果代替本次发布验证。

当前记录：

- [20260721_engineering_baseline.md](20260721_engineering_baseline.md)：Phase 3 文档治理基线，非生产发布。
- [20260721_phase4_sql_ast.md](20260721_phase4_sql_ast.md)：Phase 4 SQL AST 安全迭代基线，非生产发布。
