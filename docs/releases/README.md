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
- [20260722_phase4_user_scope.md](20260722_phase4_user_scope.md)：Phase 4 私有数据 owner 谓词改写基线，非生产发布。
- [20260727_r6_release_candidate.md](20260727_r6_release_candidate.md)：R6 隔离环境发布候选基线，非生产发布。
- [20260730_r7_release_gates.md](20260730_r7_release_gates.md)：R7 生产发布门禁与 SSE 更新信号工程基线，非生产发布。
- [20260802_r8_kline_partition_lifecycle.md](20260802_r8_kline_partition_lifecycle.md)：R8 K 线分区生命周期准备工程基线，活动表未切换。
- [20260802_r9_csp_report_only_observability.md](20260802_r9_csp_report_only_observability.md)：
  待远端闭环的 R9 CSP Report-Only S1 本地工程基线；本地实现提交为
  `723ba9b949bccf7c96798d2f45388731350eacd3`，强制 CSP 与认证边界未改变。最终验证提交、
  Backend/Frontend CI 和完整业务周期观测待补；上述字段补齐前，该记录不满足最终可追溯
  发布记录条件。
