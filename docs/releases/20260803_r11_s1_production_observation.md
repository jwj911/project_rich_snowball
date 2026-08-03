# R11 S1 目标环境生产观测受阻规划记录（2026-08-03）

> 类型：`blocked planning record`，不是 `engineering baseline` 或 `production release`。
> 当前状态：R11 独立规格已完成并批准，但 operator gate 仍为 `blocked`；未执行任何生产操作。
> 对应规格：
> [`conduct-r11-production-observation`](../../.trae/specs/conduct-r11-production-observation/spec.md)
> 对应任务：
> [`tasks.md`](../../.trae/specs/conduct-r11-production-observation/tasks.md)
> 对应验收清单：
> [`checklist.md`](../../.trae/specs/conduct-r11-production-observation/checklist.md)
> 当前路线图：
> [`../iteration_plan_20260802_post_r9.md`](../iteration_plan_20260802_post_r9.md)
> 通用发布清单：[`../release_checklist_20260719.md`](../release_checklist_20260719.md)

## 状态快照

- R10 `non-production engineering baseline` 保持不变；历史本地与 CI 结果不作为 R11 生产证据。
- 真实 production 环境、四类责任人、deploy/rollback SHA、镜像 digest、UTC 发布与观测
  窗口、仓库外证据根目录均未提供。
- `CSP_REPORT_SAMPLE_RATE`、`SSE_DEPLOYMENT_MODE=single|sticky` 及对应拓扑证据也未批准。
- 未执行真实 preflight、备份、隔离恢复、迁移、部署、canary、完整业务周期窗口、生产指标
  采集或 production R10 report。
- R12/S2 和 R13/S3 均未启动；本记录不批准 CSP 收紧、token 迁移或其他后续实施。

## Operator Gate 输入

以下输入必须全部由人工确认后，R11 才能从 `blocked` 进入只读预检；规格批准本身不解除门禁。

| 门禁输入 | 当前状态 |
|---|---|
| 真实 production PostgreSQL、Redis、HTTPS CORS、非 Mock 数据源和 CSP 报告 endpoint | 未提供 |
| 发布负责人、回滚负责人、证据保管人、安全评审人 | 未提供 |
| 完整 40 位 deploy SHA 与已验证的完整 40 位 rollback SHA | 未提供 |
| 与待部署构建一致的镜像 digest | 未提供 |
| 明确的 UTC 发布窗口与观测窗口 | 未提供 |
| `SSE_DEPLOYMENT_MODE=single|sticky` 与对应拓扑证据 | 未提供 |
| 经批准且窗口内冻结的 `CSP_REPORT_SAMPLE_RATE` | 未提供 |
| 仓库外受限、加密的证据根目录与至少 90 天保留策略 | 未提供 |

仓库不得记录真实 host、origin、连接串、凭据、个人账号、审批 ID、证据绝对路径或下载地址。
任一输入缺失时，不得使用 placeholder、历史 CI、staging、本地或 synthetic 数据替代。

## 生产执行清单

- [ ] operator gate 全部输入已人工确认。
- [ ] 不可变发布计划已固定 deploy/rollback SHA、镜像 digest、CSP hash、sample rate、SSE
  模式、Alembic head 和 artifact 清单。
- [ ] 已使用真实生产输入执行 R7 的 11 项只读 preflight，并保存仓库外脱敏 trace 报告。
- [ ] 已完成 PostgreSQL 逻辑备份、SHA-256 记录和隔离恢复。
- [ ] 已核对恢复库的 Alembic head、核心表、聚合计数、约束、readiness 和 RTO。
- [ ] 已部署冻结镜像并核对运行时 `RELEASE_COMMIT`、deploy SHA 与镜像 digest。
- [ ] 已确认 API scheduler 关闭、独立 worker 唯一启用、Redis/真实数据源共享及 SSE 拓扑。
- [ ] 已确认强制 CSP 与 Report-Only hash、认证、Bearer 写请求和 cookie-only 拒绝边界未漂移。
- [ ] 已在正式窗口前完成目标环境 CSP canary，并将 canary 排除出正式窗口。
- [ ] 已完成 14 项核心流程 smoke，全部结果为 `passed`。
- [ ] 已完成至少 5 个实际交易日和连续至少 7 个自然日的有效观测窗口。
- [ ] 已采集并核对业务 HTTP、六类 CSP outcome、持久化记录、重启/reset 和告警证据。
- [ ] 已在仓库外生成 production context、catalog 和 R10 report。
- [ ] production R10 report 已达到 `ready_for_review`，且无 unknown、pending、failed、
  sensitive 或 truncated 项。
- [ ] 四类责任角色已完成退出签字和回滚步骤确认。

以上项目均未执行，保持未勾选。

## 完整业务周期

有效窗口必须同时满足：

- 覆盖至少 5 个实际交易日；
- 从 `window_start` 到 `window_end` 连续至少 7 个自然日；
- 跨越至少一个周末或完整休市段；
- 覆盖日盘、夜盘、一次行情刷新/宽表调度周期和一个非交易时段；
- 法定休市导致 7 日内不足 5 个交易日时，顺延至第 5 个实际交易日结束；
- 全程以 UTC 记录，并冻结 deploy SHA、镜像 digest、release、sample rate、双 CSP、认证、
  SSE 模式、expected/trusted origins 和指标口径。

代码、镜像、配置、CSP、sample rate、认证或关键拓扑变化，以及无法解释的重启、counter
reset、证据缺口、时钟异常、敏感数据或 R10 截断，都会使窗口失效。旧窗口必须标记为
`invalidated`，修复后重新部署并从新的 `window_start` 完整重跑，不得拼接新旧证据。

## 14 项核心流程

同一 production release 的以下流程必须逐项记录 `passed`、`failed` 或 `not_run`：

1. `login`
2. `refresh_recovery`
3. `concurrent_401_singleflight`
4. `logout`
5. `sse_initial_connect`
6. `sse_reconnect`
7. `products`
8. `product_detail`
9. `workspace`
10. `strategies`
11. `agents`
12. `bearer_write`
13. `cookie_only_write_rejected`
14. `csp_reporting_canary`

每项只记录执行时间、执行角色、release 和低敏 artifact ID。任何 `failed` 或 `not_run` 都会
阻止 `ready_for_review`；不得保存账号、token、payload、完整 URL、用户截图或响应正文。

## 指标与判定

同一有效窗口必须采集并交叉核对：

- 非 CSP 业务 `http_requests_total` 增量，且业务流量必须大于 0；
- `csp_reports_total` 的 `received`、`accepted`、`sampled`、`rejected`、
  `rate_limited`、`persist_failed` 六类增量；
- 同 environment/release/window 的 `FrontendLogDB` 已接受记录数量；
- sample rate、实例/进程重启、Prometheus counter reset 和时钟事件；
- readiness、scheduler、Redis 降级和 CSP 告警及响应结论。

`persist_failed` 必须为 0，`accepted` 必须与完整且未截断的目标记录数一致。所有非零
`rejected` / `rate_limited` 都必须有原因分类、责任角色和复验结论。指标缺失、计数不一致、
无法解释的 reset 或监控缺口都会阻止 production context 进入 R10 报告。

## Artifact 安全

preflight、backup、restore、deploy、smoke、metrics、context、catalog、report 和 rollback
证据必须：

- 存放在仓库外、加密且访问受限的存储中；
- 使用 1 至 64 位低敏 ASCII slug 作为 artifact ID；
- 记录 SHA-256、生成时间、schema version、保留截止时间、保管角色和状态；
- 至少保留 90 天，并按组织策略采用更长期限；
- 到期后由证据保管人和安全评审人共同批准销毁，仅保留低敏销毁记录；
- 不进入 Git、CI artifact、聊天、工单正文或公开日志。

若发现密钥、Token、连接串、完整 URL、query、fragment、脚本、DOM、用户标识或业务数据，
必须隔离 artifact 并停止 R11，不得通过复制或重新包装继续流转。

## 停止与回滚

以下任一情况触发停止和已批准回滚：preflight、备份恢复、迁移、readiness、scheduler、权限
smoke 失败；双 CSP、认证、Bearer/CSRF 或 SSE 边界漂移；`persist_failed` 非零；出现敏感
数据、未知高风险违规或报告完整性失败；关键组件异常使窗口失效；无法在批准时限内恢复服务或
证据连续性。

回滚顺序为：停止 worker/API，保留低敏日志和 trace，恢复已批准应用提交，按需恢复数据库，
再验证 readiness、认证、行情、SSE 和 CSP。R11 不新增 migration，正常应用回滚不执行
Alembic downgrade，也不删除既有脱敏 `frontend_logs`。事件记录仅保留 UTC 时间、稳定事件
码、影响范围、rollback SHA、恢复时间、责任角色和低敏 artifact ID。

## 下一步

下一步仅是由授权人员在仓库外补齐并批准全部 operator gate 输入。输入齐备后先冻结不可变发布
计划，再执行真实只读 preflight；preflight 通过前不得开始备份、恢复、迁移或部署。

只有真实 preflight、备份恢复、部署、canary、完整窗口、14 项流程、指标、production R10
report 和四方签字全部满足后，R11 才能标记完成。R11 完成也只允许发起 R12/S2 人工专项
评审，不自动修改 CSP；R13/S3 继续保持未启动。
