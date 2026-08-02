# Post-R9 后续迭代路线图治理 Spec

## Why

R1 至 R9 的工程项已经闭环，但当前唯一迭代事实源仍停留在 R9，且部分活跃设计文档保留了
已经完成的 walk-forward、因子抽象、依赖安装和测试待办。生产发布、CSP S2/S3、K 线切换、
SSE 横向扩展和产品增强又具有不同准入条件，需要新的 Post-R9 事实源避免重复排期或越过门禁。

## What Changes

- 新增 `docs/iteration_plan_20260802_post_r9.md`，作为 R9 之后唯一的当前迭代事实源。
- 将后续工作分为“可立即实施”“需要生产操作者”“需要观测证据”“需要容量/并发阈值”和
  “候选产品增强”五类，不用时间顺序掩盖外部依赖。
- 推荐下一工程迭代为 R10“CSP 证据归类与 S2 准入报告”，只把 R9 已脱敏数据转为可审计证据，
  不收紧强制 CSP。
- 规划 R11“R9 S1 目标环境部署与完整业务周期观测”、R12“CSP S2 nonce/hash 收紧”和
  R13“内存 access token 迁移”，为每一阶段定义前置条件、停止条件、验证和回滚边界。
- 将 R8 生产分区/冷归档和 R7 SSE 分布式能力保留为阈值触发的独立轨道，不强行纳入安全主线。
- 记录 Trader 交易计划生命周期、Data Catalog 前端展示和策略进化实时进度三个产品候选项，
  但要求各自另立规格，不与认证、CSP 或生产切换混合实施。
- 同步 README、AGENTS、`.agents/`、发布入口和安全风险文档中的当前迭代入口及状态。
- 为 `strategy_abstraction_plan.md`、`strategy_evolution_agent_design.md`、
  `trader_agent_design.md` 和 `data_agent_data_iteration_plan.md` 增加当前状态说明，消除已完成
  能力仍被描述为待实现的问题。
- 保留 `docs/iteration_plan_20260724_follow_up.md` 作为 R1 至 R9 历史事实，不删除历史证据。
- 本变更只修改项目文档与规格文档，没有 **BREAKING** API、数据库、认证或运行时变更。

## Impact

- Affected specs: 迭代治理、CSP 分阶段迁移、认证安全、生产发布、数据生命周期、SSE 扩展、
  Agent/策略产品路线。
- Affected code: 无业务代码；预计更新以下文档系统：
  - `docs/iteration_plan_20260802_post_r9.md`
  - `docs/iteration_plan_20260724_follow_up.md`
  - `README.md`
  - `AGENTS.md`
  - `.agents/project.md`
  - `.agents/roadmap.md`
  - `.agents/security.md`
  - `.agents/operations.md`
  - `docs/release_checklist_20260719.md`
  - `docs/releases/README.md`
  - `frontend/docs/SECURITY_RISKS.md`
  - `docs/strategy_abstraction_plan.md`
  - `docs/strategy_evolution_agent_design.md`
  - `docs/trader_agent_design.md`
  - `docs/data_agent_data_iteration_plan.md`

## ADDED Requirements

### Requirement: Post-R9 唯一事实源

项目 SHALL 新增 Post-R9 迭代计划作为当前执行入口。该文档必须记录 R9 的已验证基线、仍未完成
的生产条件、后续迭代顺序、每项准入/退出条件和独立规格要求。R1 至 R9 的旧计划继续保留为
历史执行记录，但不得与新计划同时宣称为当前唯一事实源。

#### Scenario: 查找当前迭代

- **WHEN** 开发者从 README、AGENTS、`.agents/roadmap.md` 或发布入口查找后续工作
- **THEN** 所有入口指向同一份 Post-R9 计划，且 R1 至 R9 文件明确标记为已完成历史事实源

#### Scenario: 核对 R9 边界

- **WHEN** 开发者查看 Post-R9 基线
- **THEN** 文档明确 R9 已完成本地与远端工程门禁，但尚未生产部署、未完成真实完整业务周期
  观测，强制 CSP 与 `localStorage` token 风险均未关闭

### Requirement: 带门禁的后续路线

Post-R9 计划 SHALL 按实际可执行性而非愿望清单组织后续工作：

1. **可立即实施**：R10 CSP 证据归类与 S2 准入报告；
2. **生产操作者门禁**：R11 R9 S1 目标环境部署和完整业务周期观测；
3. **观测证据门禁**：R12 CSP S2 nonce/hash 收紧；
4. **认证专项门禁**：R13 内存 access token 迁移，继续使用 Bearer 写请求；
5. **容量/并发阈值门禁**：R8 后续生产分区/冷归档、R7 后续 Redis Pub/Sub 与跨实例连接管理；
6. **候选产品增强**：Trader 交易计划生命周期、Data Catalog 前端展示、策略进化实时进度。

每项必须声明优先级、依赖、触发条件、非目标、验收证据和停止条件。没有满足门禁的事项不得标为
“进行中”或“已排期”。

#### Scenario: 缺少生产输入

- **WHEN** 没有真实生产凭据、发布/回滚负责人或目标环境窗口
- **THEN** R11 保持阻塞，团队可实施 R10 或为候选产品项另立规格，但不得伪造生产证据

#### Scenario: 容量阈值未达到

- **WHEN** `kline_storage_preflight` 未达到 1 亿行、100 GiB 或分钟查询 P99 500 ms 阈值
- **THEN** 活动表切换、冷数据删除和对象存储归档不进入当前迭代

#### Scenario: SSE 扩展条件未达到

- **WHEN** 没有多实例高可用需求，且 SSE 并发未达到既定扩展阈值
- **THEN** 继续使用 `single|sticky` 边界，不实施 Redis Pub/Sub 或分布式连接注册

### Requirement: R10 CSP 证据归类与准入设计

路线图 SHALL 将 R10 定义为下一推荐工程迭代，并要求后续 R10 独立规格至少覆盖：

- 只读取 R9 已脱敏的 `csp-violation` 记录，不恢复或新增原始请求体、query、fragment、
  Cookie、Authorization、脚本、DOM 内容或原始 User-Agent；
- 按受控路由类别、规范化 directive、blocked source 类别、环境、受信任发布版本和时间窗口
  聚合，禁止使用完整 URL、用户标识、`trace_id` 或任意高基数字段作为指标标签；
- 提供管理员鉴权或离线只读命令，查询窗口、扫描行数、输出大小和执行时间均有上限；
- 输出带独立 `trace_id` 的脱敏 JSON 准入报告，状态至少包含 `insufficient_evidence`、
  `blocked` 和 `ready_for_review`；
- “证据不足”不能等同于“无违规”，“已知违规”必须有分类、负责人、处理决策和复验结果；
- 报告只允许建议进入 S2 专项评审，不得自动修改 `Content-Security-Policy`。

#### Scenario: 只有本地或 CI 合成报告

- **WHEN** 输入只来自本地或 CI synthetic 流量
- **THEN** R10 报告状态为 `insufficient_evidence`，不得输出 S2 可执行结论

#### Scenario: 存在未知违规

- **WHEN** 观测窗口内仍有未分类 directive、路由或 blocked source 类别
- **THEN** R10 报告状态为 `blocked`，并只输出低敏聚合和处理责任，不输出原始报告

#### Scenario: 证据满足评审条件

- **WHEN** 目标环境完整业务周期、核心流程覆盖、发布元数据、指标基线和全部违规归类均完整
- **THEN** R10 只能输出 `ready_for_review`，R12 仍需另立规格并由人工批准

### Requirement: R11 至 R13 安全迁移顺序

路线图 SHALL 保持 CSP 与 token 迁移解耦：

- R11 负责目标环境 S1 部署、发布清单、至少一个完整业务周期的真实观测、核心流程矩阵、
  告警基线和回滚演练；
- R12 只在 R10/R11 证据通过后逐项迁移 nonce/hash 并收紧 `script-src`，任何未知违规或业务
  回归均停止；
- R13 在 R12 稳定后把短期 access token 从持久化存储迁移到内存，通过 refresh cookie 恢复
  会话，但 POST/PUT/PATCH/DELETE 继续要求 Authorization Bearer；
- cookie-only 写请求、S4 CSRF/origin 设计不属于 R13。

#### Scenario: R12 准入不满足

- **WHEN** 真实报告未覆盖完整业务周期、存在未知违规或强制策略回归测试不完整
- **THEN** 不移除 `unsafe-inline` / `unsafe-eval`，继续运行 S1 Report-Only

#### Scenario: R13 出现认证回归

- **WHEN** 页面刷新、并发 401 单飞、refresh 失败、跨标签页行为、logout、SSE 或 Bearer 写请求
  任一回归
- **THEN** 停止迁移并回退到已验证的 R12/S0 认证行为，不启用 cookie-only 写请求

### Requirement: 产品候选项不重复建设

路线图 SHALL 基于当前代码事实校正产品候选：

- 多因子组合、过滤 DSL、因子注册表、中性化、增强回测指标和日频 walk-forward 已实现，
  不得作为新功能重复排期；
- TraderAgent 已上线，后续候选是交易计划持久化、结果追踪和与回测/持仓的显式关联；
- Data Catalog 后端已实现，候选是用户可见的只读数据目录与质量上下文；
- 策略进化已具备后端 Agent 事件流，候选是工作台实时进度与断线恢复体验。

每个候选必须先核对用户价值、数据模型、权限、保留策略和测试成本，再创建独立规格。

#### Scenario: 选择产品增强

- **WHEN** 团队在生产输入不可用期间选择产品候选项
- **THEN** 新规格引用 Post-R9 计划，只实现一个完整用户闭环，不混入 CSP、token、分区或 SSE
  基础设施变更

### Requirement: 活跃设计文档状态校正

项目 SHALL 为仍位于活跃 `docs/` 目录的设计文档增加清晰状态说明。状态校正必须引用当前实现
或新的事实源，不删除历史设计过程，也不把历史测试计数改写成当前全量基线。

#### Scenario: 已完成能力仍被列为待办

- **WHEN** 文档仍把 walk-forward、因子抽象、`scikit-learn` lock 或 Trader 全量验证描述为
  未完成
- **THEN** 文档顶部或相关待办处明确该项已由后续迭代完成，并链接当前证据

### Requirement: 文档交付质量

本变更 SHALL 只提交规划相关 Markdown，保持原子范围，并验证：

- 文档链接可从仓库根目录解析；
- 当前状态、提交哈希、CI run、测试计数和非生产边界与 R9 事实一致；
- 全仓活跃文档不存在两个“唯一当前事实源”；
- 不生成或提交生产报告、Lighthouse 历史、数据库、日志、浏览器产物或敏感数据；
- `git diff --check` 与适用于 Markdown 的 pre-commit 检查通过。

#### Scenario: 文档提交完成

- **WHEN** Post-R9 路线图和入口同步通过检查
- **THEN** 仅规划文档被原子提交并推送，工作区与 `origin/master` 一致

## MODIFIED Requirements

### Requirement: 当前迭代入口

项目当前执行入口 SHALL 从 `docs/iteration_plan_20260724_follow_up.md` 切换为
`docs/iteration_plan_20260802_post_r9.md`。旧文件继续负责 R1 至 R9 的历史证据；新文件负责
R10 以后决策、依赖和状态。

### Requirement: 当前阶段表述

README、AGENTS、`.agents/` 和发布入口 SHALL 将“当前迭代 R9”更新为“R9 工程门禁已闭环，
当前处于 Post-R9 规划/R10 待立项”。该表述不得暗示 R9 已生产部署、S2 已准入或 S3 已启动。

### Requirement: 发布与安全边界

生产发布清单 SHALL 继续保留真实凭据、负责人、备份恢复、目标环境 smoke、CSP 完整周期观测
等未勾选项。Post-R9 规划不得用历史 CI 替代这些生产证据，也不得把 R8/R7 条件项改成无条件
实施任务。

## REMOVED Requirements

### Requirement: R1 至 R9 计划继续充当当前唯一执行源

**Reason**: 该文件已经超过原始范围并包含大量历史执行记录，继续追加会让当前待办与历史证据
混杂。

**Migration**: 保留原文件并增加“已完成历史事实源”说明；所有当前入口迁移到 Post-R9 计划。

### Requirement: 过期设计待办继续进入当前队列

**Reason**: walk-forward、因子抽象、依赖锁和 Trader 基础验证已有实现或新基线证据，继续作为
待办会重复建设。

**Migration**: 在原设计文档中保留历史文字并增加状态校正；真正未完成的用户能力作为独立候选
重新评审。
