# 发布记录

本目录保存按版本逐次填写的发布记录。每次真实发布或工程基线发布都应从
[`../release_checklist_20260719.md`](../release_checklist_20260719.md) 复制检查项，
并保留提交、验证结果、备份、回滚和遗留风险。

当前处于
[`Post-R9` 规划](../iteration_plan_20260802_post_r9.md)：R9 工程门禁已闭环但尚未生产部署，
R10 `non-production engineering baseline` 与远端 Backend CI 已完成，不是生产发布。
R11 operator gate 仍阻塞，R12/S2 与 R13/S3 均未启动。R1 至 R9 历史执行证据见
[`../iteration_plan_20260724_follow_up.md`](../iteration_plan_20260724_follow_up.md)。
R8 生产分区/冷归档与 R7 分布式 SSE 仍是阈值触发、未排期的条件轨道。

## 记录规则

- 文件名使用 `YYYYMMDD_<short-slug>.md`，日期按发布窗口的 UTC 日期。
- 明确标注 `engineering baseline` 或 `production release`，工程基线不得表述为生产已发布。
- 已完成发布的提交必须是已推送且可回滚的 Git 提交；CI pending 记录必须将尚未产生的提交
  哈希和 CI 链接明确标为待填，不得推断或虚构。
- 未执行的生产检查保持未勾选，并在“阻塞项”中说明原因，不用历史 CI 结果代替本次发布验证。

当前记录：

- [20260721_engineering_baseline.md](20260721_engineering_baseline.md)：Phase 3 文档治理基线，非生产发布。
- [20260721_phase4_sql_ast.md](20260721_phase4_sql_ast.md)：Phase 4 SQL AST 安全迭代基线，非生产发布。
- [20260722_phase4_user_scope.md](20260722_phase4_user_scope.md)：Phase 4 私有数据 owner 谓词改写基线，非生产发布。
- [20260727_r6_release_candidate.md](20260727_r6_release_candidate.md)：R6 隔离环境发布候选基线，非生产发布。
- [20260730_r7_release_gates.md](20260730_r7_release_gates.md)：R7 生产发布门禁与 SSE 更新信号工程基线，非生产发布。
- [20260802_r8_kline_partition_lifecycle.md](20260802_r8_kline_partition_lifecycle.md)：R8 K 线分区生命周期准备工程基线，活动表未切换。
- [20260802_r9_csp_report_only_observability.md](20260802_r9_csp_report_only_observability.md)：
  已完成远端工程门禁闭环的 R9 CSP Report-Only S1 非生产工程基线；本地实现提交为
  `723ba9b949bccf7c96798d2f45388731350eacd3`，本地验证文档提交为
  `37fc8008a74c1b74c48f74aac5e3267c8a29e5b6`，CI 稳定性修复提交为
  `c7a721a04f58caa51860be67d870855663186a14`。
  [Backend CI run 30739553595](https://github.com/jwj911/project_rich_snowball/actions/runs/30739553595)
  与
  [Frontend CI run 30740784839](https://github.com/jwj911/project_rich_snowball/actions/runs/30740784839)
  均成功。该记录不是生产发布：完整业务周期观测、生产责任人及 S2/S3 专项仍未完成，强制
  CSP 未收紧，`localStorage` access token 风险未关闭。
- [20260803_r10_csp_evidence_qualification.md](20260803_r10_csp_evidence_qualification.md)：
  R10 CSP 证据归类与 S2 准入报告非生产工程基线；本地聚焦
  `375 passed, 5 skipped, 1 warning`，全量 `1421 passed, 22 skipped, 103 warnings`，
  synthetic CLI 正确返回退出码 `1` / `insufficient_evidence`，安全报告为 `1707 B`。
  本地 PostgreSQL 不可用，3 个 PostgreSQL 专项明确 skip。实现提交为
  `e5dc94ccb6f18a44e15ba4b09ee2e2c97ff62de4`；
  [Backend CI run 30791923945（attempt 1）](https://github.com/jwj911/project_rich_snowball/actions/runs/30791923945)
  成功，R9/R10 gate `268 passed, 1 warning`，远端全量
  `1442 passed, 1 skipped, 103 warnings`，coverage `77.38%`；Alembic、PostgreSQL API
  smoke、Ruff check/format（122 files）和 `pip-audit` 均成功，没有修复提交。未生成生产
  context、catalog 或 report，R11 仍阻塞，R12/S2 与 R13/S3 均未启动。
