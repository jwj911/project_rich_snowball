# R11 目标环境 S1 部署与完整业务周期观测 Spec

## Why

R10 已完成非生产 evidence-only 工程闭环，但 synthetic 结果只能证明工具契约，不能证明真实
业务没有未知 CSP 违规。R11 需要在生产操作者、备份恢复、回滚和安全证据全部就绪后，将现有
S1 Report-Only 基线部署到真实目标环境并完成一个不可缩短的业务周期观测。

## What Changes

- 建立生产操作者门禁，要求真实目标环境、批准的部署提交、UTC 窗口、发布/回滚负责人和证据
  保管责任人齐备后才能执行。
- 从当前发布清单复制 R11 专属生产记录，所有生产项按实际执行逐项勾选，不复用历史 CI 结果。
- 使用真实生产输入执行 R7 只读发布预检，保存仓库外脱敏报告。
- 在部署前完成 PostgreSQL 逻辑备份、隔离恢复演练、核心计数和 readiness 验证。
- 部署当前 R9/R10 S1 基线，设置与实际镜像一致的完整 `RELEASE_COMMIT`，保持强制 CSP、
  Report-Only、认证和 SSE 边界不变。
- 在正式观测窗口前执行目标环境 CSP canary 和 14 项核心流程 smoke，避免 synthetic canary
  污染真实窗口。
- 观测至少 5 个实际交易日并跨越一个周末/休市段；窗口内冻结 release、采样率、CSP、认证和
  关键部署拓扑。
- 采集 R10 context 所需的业务 HTTP 与六类 CSP outcome 窗口计数，记录重启、指标 reset 和
  告警响应。
- 在仓库外维护受控 known-violation catalog，运行 R10 离线 CLI，逐轮归类所有 unknown /
  pending / failed 项。
- 只有生产报告达到 `ready_for_review`、全部核心流程通过且人工签字后，R11 才可退出；该状态
  只允许发起 R12/S2 专项评审。
- 任一代码、CSP、认证、采样率、release 或关键拓扑变更都终止当前观测窗口；修复后必须重新
  部署并从新窗口起点开始。
- 本轮不修改业务代码、不收紧强制 CSP、不实施 nonce/hash、不迁移 token、不启用 cookie-only
  写请求、不执行 R8 分区或 R7 分布式 SSE。
- 本轮无 **BREAKING** API 或数据库 schema 变更。

## Impact

- Affected specs: 生产发布治理、CSP S1 观测、R10 准入证据、备份恢复、认证/SSE 回归、S2
  人工评审门禁。
- Affected systems:
  - 生产部署配置与发布平台
  - PostgreSQL 备份/隔离恢复环境
  - Redis 与 `single|sticky` SSE 拓扑
  - Prometheus/日志/告警平台
  - 仓库外 R11 context、catalog、report 和发布证据存储
  - `docs/releases/YYYYMMDD_r11_s1_production_observation.md`
  - `docs/release_checklist_20260719.md`
  - `docs/iteration_plan_20260802_post_r9.md`
  - README、AGENTS 与 `.agents/`

## ADDED Requirements

### Requirement: R11 生产操作者门禁

R11 SHALL 在任何部署、迁移、备份或目标环境查询前取得并人工确认以下输入：

- `DEPLOY_COMMIT`：实际构建并部署的完整 40 位 Git SHA；
- `ROLLBACK_COMMIT`：已验证的完整 40 位回滚 SHA；
- `RELEASE_WINDOW_UTC`：明确的 UTC start/end；
- `RELEASE_OWNER`、`ROLLBACK_OWNER`、`EVIDENCE_CUSTODIAN` 和 `SECURITY_REVIEWER`；
- 真实生产 PostgreSQL、Redis、HTTPS CORS、非 Mock 数据源和 CSP 报告 endpoint；
- `SSE_DEPLOYMENT_MODE=single|sticky` 及对应拓扑证据；
- 仓库外受限证据根目录和至少 90 天保留策略；
- 经批准的 `CSP_REPORT_SAMPLE_RATE`，整个观测窗口内保持不变。

姓名、账号、连接串、密钥、Token、生产 host、证据绝对路径和审批系统 ID 不得写入 Git 文档。
仓库只记录角色已确认、脱敏时间、状态、报告 trace 和校验摘要。

规格获批本身 SHALL NOT 解除 operator gate。任一输入缺失时，R11 状态保持 `blocked`，不得使用
placeholder、CI、staging 或本地数据代替。

#### Scenario: 操作者输入完整

- **WHEN** 四类责任角色、真实生产输入、部署/回滚提交、UTC 窗口和证据存储均经人工确认
- **THEN** R11 可进入只读预检阶段，但尚不能直接部署

#### Scenario: 缺少生产输入

- **WHEN** 任一责任人、凭据、窗口、回滚点、证据目录或真实目标环境缺失
- **THEN** 所有执行任务保持未勾选，项目只保留 R10 非生产基线

### Requirement: 不可变发布计划与证据清单

系统 SHALL 在执行前创建 R11 专属发布记录，固定：

- deploy/rollback SHA 和镜像 digest；
- 计划窗口、观测窗口、目标环境与 `single|sticky` 模式；
- Alembic 当前 head、迁移数量和预期无新增 R11 migration；
- CSP 强制头与 Report-Only 头的规范化 hash；
- R9/R10 配置边界、sample rate、expected origins 和 trusted origins 数量；
- preflight、backup、restore、deploy、smoke、metrics、context、catalog、report 和 rollback
  证据的受控 artifact ID；
- 每个 artifact 的 SHA-256、生成时间、schema version、保留截止时间、保管角色和状态。

artifact ID 只能是 1 至 64 位低敏 ASCII slug。仓库记录不得包含 artifact 的绝对路径、下载 URL、
对象存储 bucket/key、生产 host、用户名或凭据。

#### Scenario: 发布输入在执行前发生变化

- **WHEN** deploy SHA、镜像 digest、窗口、sample rate、CSP hash 或拓扑在执行前变化
- **THEN** 重新审批并生成新的发布记录版本，旧版本保留为取消状态

### Requirement: 真实发布预检

R11 SHALL 使用真实生产输入执行 `python/scripts/release_preflight.py` 的 11 项只读门禁，并将
报告写入仓库外受限目录。预检必须验证：

- `ENV=production`；
- PostgreSQL、强密钥、安全 HTTPS CORS、非 Mock 数据源和 Redis；
- deploy SHA、UTC 发布窗口、发布/回滚负责人；
- `SSE_DEPLOYMENT_MODE=single|sticky`。

预检报告必须有独立 `trace_id`，stdout/stderr 和仓库记录不得包含连接串、密钥、Token 或路径。
预检失败时不得继续备份、迁移或部署。

#### Scenario: 真实预检通过

- **WHEN** 11 项真实生产检查全部通过且报告脱敏检查通过
- **THEN** R11 可进入备份恢复阶段

#### Scenario: placeholder 或失败报告

- **WHEN** 输入来自 CI placeholder，或任一检查失败
- **THEN** 报告只能作为工程契约或失败证据，不能勾选 R11 生产预检

### Requirement: 部署前备份与恢复验证

R11 SHALL 在目标环境变更前完成：

- PostgreSQL 逻辑备份，记录工具版本、开始/结束时间、字节数和 SHA-256；
- 在隔离 PostgreSQL 中恢复该备份，不覆盖生产或用户开发数据库；
- 核对 schema/Alembic head、核心表集合、受控聚合行数和关键约束；
- 使用恢复库执行 `/health/ready` 或等价只读应用连接检查；
- 记录 RTO 实测值并与已批准目标比较；
- 验证回滚负责人能够访问恢复步骤和备份保留策略。

备份、恢复目录、数据库 URL、表中样本、用户数据和原始行不得进入仓库。恢复失败、校验不一致或
RTO 超限时不得部署。

#### Scenario: 隔离恢复成功

- **WHEN** 备份可恢复，schema/聚合计数/约束/readiness 均符合预期
- **THEN** R11 可进入迁移和部署阶段

#### Scenario: 恢复验证失败

- **WHEN** 备份不可读、计数/约束不一致、readiness 失败或恢复目标不是隔离环境
- **THEN** 停止 R11，不修改生产应用或数据库

### Requirement: S1 生产部署

部署 SHALL 使用冻结的 deploy SHA 和镜像 digest，并满足：

- 生产数据库执行 `alembic upgrade head`，确认 head 与计划一致；
- API 使用 `ENABLE_SCHEDULER=0`，只有独立 worker 使用 `ENABLE_SCHEDULER=1`；
- API/worker 使用相同 Redis 与真实数据源；
- API 设置 `ENV=production` 和与镜像一致的 `RELEASE_COMMIT`；
- `CSP_REPORT_SAMPLE_RATE` 与批准值一致；
- 页面强制 CSP 与 R9 hash 完全一致，Report-Only 与 R9/R10 hash 完全一致；
- 没有新增或修改管理员 API、认证方式、cookie scope、Bearer 写请求或数据库 schema；
- `single` 仅一个 SSE 实例；`sticky` 已验证负载均衡会话亲和。

部署完成后 SHALL 先验证 liveness/readiness/scheduler，再执行 canary；未通过不得开始观测窗口。

#### Scenario: 部署提交与运行元数据一致

- **WHEN** 镜像 digest、deploy SHA 和运行时 `RELEASE_COMMIT` 可相互核对
- **THEN** 新 CSP 记录具有可信 production/release 归属

#### Scenario: CSP 或认证边界漂移

- **WHEN** 任一强制/Report-Only hash、token 存储、cookie、Bearer 或 cookie-only 拒绝行为变化
- **THEN** 立即停止并回滚，不以 R11 名义接受该变更

### Requirement: 窗口前 canary 与核心 smoke

正式窗口开始前 SHALL 执行：

- 目标环境 CSP reporting canary，确认 legacy/Reporting API 接收、可信 release/environment、
  指标递增和脱敏落库；
- canary 记录位于正式 `window_start` 之前，或通过独立受控 release/window 明确排除；
- 登录、refresh 恢复、并发 401 singleflight、logout；
- SSE 首连、cookie 轮换、首次断线重连和 Redis 降级恢复；
- products、product detail、workspace、strategies、agents；
- 至少一个 Bearer 写请求成功，cookie-only 写请求继续拒绝；
- 页面双 CSP 头、关键 API、管理员/普通用户权限和 Lighthouse 快速基线。

canary/smoke 失败时不得开始完整业务周期。测试账号、请求体、URL 和响应内容不得写入仓库证据。

#### Scenario: canary 全部通过

- **WHEN** 14 项核心流程与运行健康检查均通过，且 canary 已排除出正式窗口
- **THEN** 由发布负责人和安全评审人共同确认 `window_start`

### Requirement: 完整业务周期与配置冻结

R11 正式观测窗口 SHALL：

- 覆盖至少 5 个实际交易日；
- 从 `window_start` 到 `window_end` 至少连续 7 个自然日；
- 跨越至少一个周末或完整休市段；
- 覆盖至少一个日盘、一个夜盘、一个行情刷新/宽表调度周期和一个非交易时段；
- 遇法定休市导致 7 日内不足 5 个交易日时顺延到第 5 个实际交易日结束；
- 所有时间使用 UTC 存储，同时记录所覆盖的交易日数量。

窗口内 deploy SHA、镜像 digest、release、sample rate、强制 CSP、Report-Only、认证边界、
SSE 模式、expected/trusted origins 和关键指标采集必须冻结。以下事件使窗口失效并要求从新的
`window_start` 重新开始：

- 代码、镜像、配置、CSP、sample rate、认证或关键拓扑变更；
- API/worker/Redis/数据库重启导致指标窗口无法连续解释；
- Prometheus counter reset、证据采集缺口或时钟异常；
- 敏感信息落入 CSP 记录、日志、报告或 artifact；
- R10 查询达到任一截断/上限。

#### Scenario: 无变更完整窗口

- **WHEN** 窗口满足交易日/自然日/业务周期条件且没有失效事件
- **THEN** 该窗口可用于生成 production R10 context

#### Scenario: 观测中修复问题

- **WHEN** 发现问题并需要代码、配置或部署修复
- **THEN** 关闭当前窗口并记录 `invalidated`，修复另立变更，重新部署后开始全新窗口

### Requirement: 14 项生产流程矩阵

R11 SHALL 对 R10 固定的 14 项流程逐项记录 `passed`、`failed` 或 `not_run`：

`login`、`refresh_recovery`、`concurrent_401_singleflight`、`logout`、
`sse_initial_connect`、`sse_reconnect`、`products`、`product_detail`、`workspace`、
`strategies`、`agents`、`bearer_write`、`cookie_only_write_rejected` 和
`csp_reporting_canary`。

每项至少有执行时间、执行角色、部署 release 和低敏 artifact ID。任何 `failed` / `not_run`
使 context 不能达到 `ready_for_review`。流程证据不得包含用户名、token、业务 payload、完整
URL、截图中的用户数据或请求/响应正文。

#### Scenario: 流程矩阵完整

- **WHEN** 同一 production release 的 14 项流程全部为 `passed`
- **THEN** context 可将流程矩阵标记为完整

### Requirement: 指标窗口与告警响应

R11 SHALL 为同一窗口采集并交叉核对：

- 非 CSP 业务 `http_requests_total` 增量；
- `csp_reports_total` 的 `received`、`accepted`、`sampled`、`rejected`、
  `rate_limited`、`persist_failed` 增量；
- `FrontendLogDB` 中同 environment/release/window 的已接受记录数量；
- sample rate、实例/进程重启和 Prometheus reset 事件；
- readiness、scheduler、Redis 降级和 CSP 告警事件。

`persist_failed` 必须为 0。`accepted` 与完整、未截断的目标记录数必须一致。`rejected` /
`rate_limited` 非零时必须有原因分类、责任角色和复验结论，不能仅按比例忽略。业务 HTTP 为 0、
指标缺失或 counter 无法解释时，context 必须标记证据不足。

#### Scenario: 指标完整一致

- **WHEN** 业务流量非零、CSP counters 连续、accepted 与记录一致且 persist_failed 为 0
- **THEN** 指标可进入 R10 production context

#### Scenario: 指标或持久化异常

- **WHEN** persist_failed 非零、accepted 不一致、counter reset 无法校正或监控缺口存在
- **THEN** 停止准入，调查后重新开始有效窗口

### Requirement: 仓库外 context、catalog 与报告

R11 SHALL 在仓库外受限目录生成 R10 `schema_version=1` context：

- `evidence_source=target_environment`；
- `environment=production`；
- release 与 deploy SHA 完全一致；
- 使用有效窗口 start/end、冻结 sample rate、完整业务周期、14 项流程和窗口指标；
- expected/trusted origins 使用批准值，均不超过 20 个。

known-violation catalog SHALL 只使用 R10 受控分类、owner role、decision 和 retest status。
unknown、pending 或 failed 项必须由责任角色处理并重新生成报告，不得读取或导出逐条 CSP 明细。

CLI SHALL 使用仓库外 database/context/catalog/report 输入运行。`0=ready_for_review` 是 R11
退出的必要条件；`1=insufficient_evidence`、`2=blocked`、`3=failed`、
`4=report_write_failed` 均阻止退出。

#### Scenario: R10 报告未就绪

- **WHEN** 报告为 `insufficient_evidence`、`blocked`、`failed` 或 `report_write_failed`
- **THEN** R11 保持进行中或阻塞，不能开启 R12

#### Scenario: R10 报告就绪

- **WHEN** production report 为 `ready_for_review` 且无敏感/截断问题
- **THEN** 只进入人工签字阶段，不自动修改 CSP

### Requirement: 证据安全、保留与销毁

R11 的 preflight、backup、restore、deploy、smoke、metrics、context、catalog、report 和
rollback artifact SHALL：

- 存放于仓库外、访问受限且加密的存储；
- 文件权限在支持的平台限制为当前操作者/服务账号；
- 记录 SHA-256、生成时间、schema version、artifact ID 和保管角色；
- 至少保留 90 天；组织策略要求更长时使用更长期限；
- 到期后由证据保管人和安全评审人共同批准删除并保留低敏销毁记录；
- 不进入 Git、CI artifact、聊天、工单正文或公开日志。

若 artifact 检测到密钥、Token、连接串、完整 URL、query、fragment、脚本、DOM、用户标识或
业务数据，必须隔离并停止 R11，不得通过二次复制继续流转。

#### Scenario: 证据保管合规

- **WHEN** 所有 artifact 均有 hash、保留期、访问控制和保管角色
- **THEN** 发布记录只引用低敏 artifact ID 与检查状态

### Requirement: 停止、回滚与事件记录

R11 SHALL 在以下任一事件发生时停止并由回滚负责人执行已批准回滚：

- preflight、备份恢复、迁移、readiness、scheduler 或权限 smoke 失败；
- 强制 CSP/Report-Only hash、认证、Bearer/CSRF 或 SSE 行为漂移；
- persist_failed、敏感数据、未知高风险违规或报告完整性失败；
- API/worker/Redis/数据库异常导致窗口失效；
- 无法在批准时限内恢复服务或证据连续性。

回滚顺序 SHALL 明确停止 worker/API、保留低敏日志和 trace、恢复应用提交、按需恢复数据库、
重新验证 readiness/认证/行情/SSE/CSP。R11 不新增 migration，因此正常应用回滚不执行 Alembic
downgrade，也不删除既有脱敏 `frontend_logs`。

事件记录只保存时间、稳定事件码、影响范围、回滚 SHA、恢复时间、责任角色和 artifact ID，不
保存异常原文或敏感输入。

#### Scenario: 回滚成功

- **WHEN** 停止条件触发且回滚后关键健康、认证、行情、SSE 和 CSP 边界恢复
- **THEN** 本次窗口标记 `invalidated/rolled_back`，R11 不声明完成

### Requirement: R11 退出与人工签字

R11 只有同时满足以下条件才能标记完成：

- 真实 preflight、备份恢复、部署、canary 和发布清单全部通过；
- 有效完整业务周期覆盖至少 5 个交易日和 7 个自然日；
- 14 项核心流程全部 passed；
- 指标完整、persist_failed 为 0、accepted 与记录一致；
- 所有 unknown / pending / failed 分类已闭环；
- production R10 report 为 `ready_for_review`，无截断或敏感问题；
- 发布负责人、回滚负责人、证据保管人和安全评审人完成签字；
- 回滚步骤已验证且生产发布记录完成。

R11 完成只表示 S1 真实观测和 R10 人工评审输入就绪。R12 仍需新规格、人工安全评审和独立
批准，系统不得自动收紧强制 CSP。

#### Scenario: 全部退出条件满足

- **WHEN** 四类责任角色共同确认所有退出证据
- **THEN** Post-R9 状态可更新为“R11 完成，R12 待人工专项评审”

### Requirement: R11 文档交付

项目 SHALL 新增 R11 生产观测发布记录，并更新 Post-R9 计划、发布清单、README、AGENTS 和
`.agents/`。仓库文档只记录：

- deploy/rollback SHA、镜像 digest 的低敏摘要；
- UTC 窗口、交易日/自然日覆盖；
- 检查状态、R10 report trace/status、artifact ID/hash 摘要；
- 停止/回滚事件的稳定码；
- 四类角色签字状态；
- 未开始的 R12/S2、R13/S3、R8/R7 条件轨道。

文档不得包含生产凭据、host、连接串、origin、绝对路径、个人账号、报告正文或业务数据。

#### Scenario: R11 文档闭环

- **WHEN** R11 完成或停止
- **THEN** 发布记录准确区分 `production observation completed`、`blocked`、
  `invalidated` 或 `rolled_back`，不伪造生产成功

## MODIFIED Requirements

### Requirement: Post-R9 当前状态

R11 规格批准后，Post-R9 状态 SHALL 为“R11 规格已完成，operator gate 仍阻塞”。只有真实输入
齐备并完成预检后，状态才能变为“R11 执行中”；只有全部退出条件满足后才能变为“R11 完成”。

### Requirement: 生产发布清单

R11 SHALL 复制而不是直接预先勾选通用发布清单。历史 R9/R10 CI 与本地结果继续作为工程基线，
但数据库、配置、备份、目标环境 smoke、CSP 观测和负责人项必须在本次窗口重新执行。

### Requirement: R10 production readiness

R10 `ready_for_review` SHALL 以 R11 同一 production release、同一有效窗口和同一指标口径为
输入。synthetic、staging、历史 release、混合窗口或截断报告均不得进入 R11 退出证据。

## REMOVED Requirements

### Requirement: 使用历史 CI 或 synthetic 结果替代生产观测

**Reason**: 工程门禁不能证明生产流量、真实浏览器、运维拓扑、指标连续性或完整业务周期。

**Migration**: R11 重新执行真实 preflight、部署、流程、指标和 R10 production report；历史
结果只作为回归基线。

### Requirement: 修复后继续沿用原观测窗口

**Reason**: 代码、配置、采样、CSP、认证或拓扑变更会改变证据总体，拼接窗口无法证明单一 release
的稳定行为。

**Migration**: 旧窗口标记 invalidated，修复另立变更并重新部署，从新的 UTC `window_start`
开始完整业务周期。

### Requirement: 在仓库或在线日志接口中保存/浏览生产 CSP 明细

**Reason**: 逐条 URL/payload 会扩大敏感数据、权限、导出和误提交风险。

**Migration**: 只使用 R10 仓库外低基数 context/catalog/report；在线可视化需另立规格。
