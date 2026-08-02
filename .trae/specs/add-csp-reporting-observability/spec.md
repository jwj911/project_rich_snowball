# R9 CSP Report-Only 观测闭环 Spec

## Why

R8 已完成并推送远端，当前仍可在不依赖生产凭据的情况下推进的明确风险项，是 R5 已记录但尚未
实施的 CSP 分阶段迁移。现有强制 CSP 仍允许 `unsafe-inline` 与 `unsafe-eval`，在缺少真实违规
证据时直接收紧会破坏 Next.js、图表、登录、SSE 或写请求流程，因此 R9 先完成 S1 报告模式与
可审计观测闭环。

## What Changes

- 在新迭代开始前确认 R8 已完整推送至 GitHub，且本地 `master`、`origin/master` 与工作区一致。
- 先更新项目事实源、路线图、安全说明和状态文档，声明 R9 范围、停止条件及非目标，并在代码
  实施前形成独立文档提交推送至 GitHub。
- 新增匿名但受大小、结构、采样和限流约束的 CSP 报告接收端点。
- 兼容 legacy `application/csp-report` 与 Reporting API `application/reports+json` 格式，
  将报告规范化、脱敏后复用现有前端日志存储。
- 为每个持久化报告生成独立 `trace_id`，增加低基数指标和可执行告警说明，不记录原始请求体、
  URL 查询参数、URL fragment、Cookie、Authorization 或页面内容。
- 前端同时发送现有强制 CSP 和更严格的 Report-Only 策略；强制策略在 R9 保持不变。
- 增加配置、后端、前端和浏览器回归，并把 R9 门禁接入 CI。
- 更新变更日志、发布清单、Agent 文档和 R9 非生产工程基线记录，完成原子提交与 GitHub 推送。
- 本轮无 **BREAKING** API 变更，不移除 `localStorage` access token，不启用 cookie-only 写请求，
  不执行 nonce/hash 强制 CSP 切换。

## Impact

- Affected specs: 前端安全、CSP、认证边界、前端可观测性、发布治理。
- Affected code:
  - `frontend/next.config.js`
  - `frontend/tests/` 与 `frontend/e2e/`
  - `python/routers/frontend_logs.py`
  - `python/schemas.py`
  - `python/services/metrics.py`
  - `python/config.py`
  - `python/tests/test_frontend_logs.py`
  - `.github/workflows/backend-ci.yml`
  - `.github/workflows/frontend-ci.yml`
  - 项目状态、安全、迭代和发布文档

## ADDED Requirements

### Requirement: 已完成迭代交接

系统 SHALL 在 R9 代码实施前确认 R8 最终提交已存在于 GitHub `origin/master`，本地与远端没有
领先或落后提交，工作区没有未说明改动。若 R8 尚未推送，必须先完成 R8 的原子提交、推送和远端
门禁记录，才能开始 R9。

#### Scenario: R8 已同步

- **WHEN** 操作者 fetch 远端并比较本地与 `origin/master`
- **THEN** 领先/落后计数均为 0，R8 最终文档提交可从远端解析，工作区保持干净

#### Scenario: R8 尚未同步

- **WHEN** 本地包含 R8 已完成但未推送的提交或文档
- **THEN** 操作者只提交并推送 R8 相关变更，确认远端门禁后再创建 R9 代码变更

### Requirement: 文档先行的 R9 启动

系统 SHALL 在 R9 代码实施前更新当前迭代事实源、README、Agent 状态、安全边界和路线图，
明确 R9 仅实施 CSP S1 报告模式，并以独立文档提交推送 GitHub。文档不得把 Report-Only 描述为
强制 CSP 已收紧，也不得把 R8 描述为生产已经分区或发布。

#### Scenario: R9 启动文档完成

- **WHEN** R9 范围、非目标、验收门槛和回退边界已写入项目文档
- **THEN** 文档提交先于 R9 实现提交出现在 `origin/master`

### Requirement: CSP 报告安全接收

系统 SHALL 提供专用 CSP 报告端点，接受 `application/csp-report` 和
`application/reports+json`，并执行以下边界：

- 请求体最大 8 KiB，Reporting API 单批报告数量有固定上限；
- 只接受 CSP violation 类型和允许字段，未知字段不得原样持久化；
- 每个客户端 IP 使用 Redis 优先、内存降级的独立限流 action；
- 采样率由受校验配置控制，默认值可在 CI 中确定性覆盖；
- 无论报告被接受、采样丢弃或受限流，均不得回显报告内容。

#### Scenario: legacy CSP 报告

- **WHEN** 浏览器发送合法 `application/csp-report`
- **THEN** 端点返回 202，并将规范化报告按采样策略持久化

#### Scenario: Reporting API 批量报告

- **WHEN** 浏览器发送不超过上限的合法 CSP report 数组
- **THEN** 每条报告独立规范化并生成结果计数，端点只返回安全摘要

#### Scenario: 非法或过大报告

- **WHEN** Content-Type、结构、类型、批量数量或字节数不符合约束
- **THEN** 端点返回稳定的 4xx，数据库与日志中不出现原始请求体

### Requirement: CSP 报告脱敏与关联

系统 SHALL 为每条持久化报告生成独立 `trace_id`，只保留排障需要的低敏字段。文档 URL、
blocked URL、source file 和 referrer 必须移除 userinfo、查询参数和 fragment，并执行长度上限；
sample、脚本片段、DOM 内容、Cookie、Authorization 及原始请求体不得持久化或写日志。

#### Scenario: URL 含敏感参数

- **WHEN** 报告 URL 包含 token、查询参数、fragment 或 userinfo
- **THEN** 存储结果只保留允许的 scheme、host、port 和受限 path，且可通过 `trace_id` 关联

#### Scenario: 持久化失败

- **WHEN** 数据库写入 CSP 报告失败
- **THEN** 事务回滚并记录 `trace_id`、异常类型和安全计数，不记录报告字段值或异常原文

### Requirement: CSP 报告观测与告警输入

系统 SHALL 为收到、接受、采样丢弃、拒绝、限流和持久化失败增加低基数计数指标。指标标签不得
使用完整 URL、用户标识、浏览器原始 directive 或 `trace_id`。运维文档 SHALL 给出按时间窗口
观察违规率、未知违规和持久化失败的告警条件，并说明本地/CI 流量不是生产 SLO。

#### Scenario: 报告被接受

- **WHEN** 合法报告通过限流和采样
- **THEN** 接受计数递增，存储记录包含规范化 directive、disposition、文档来源和 `trace_id`

#### Scenario: 报告被丢弃

- **WHEN** 报告因采样、限流或校验失败未持久化
- **THEN** 对应 outcome 指标递增，且不会产生高基数标签

### Requirement: Report-Only 响应头

前端 SHALL 保留当前 `Content-Security-Policy` 强制策略，并额外发送
`Content-Security-Policy-Report-Only`。Report-Only 策略 SHALL 指向 R9 报告端点，使用比强制
策略更严格的候选 `script-src` 收集 inline/eval 违规，同时保留应用正常运行所需的连接、图片、
字体、frame、base 和 form 边界。

#### Scenario: 页面响应

- **WHEN** 浏览器请求任意前端页面
- **THEN** 响应同时包含强制 CSP 与 Report-Only CSP，且报告地址来自受控配置

#### Scenario: 候选策略产生违规

- **WHEN** Next.js runtime、图表或业务代码触发候选策略违规
- **THEN** 浏览器只上报违规而不阻断执行，登录、刷新、退出、SSE、详情和写请求仍可使用

### Requirement: 自动化安全回归

系统 SHALL 覆盖报告格式、内容类型、大小、批量上限、采样、限流、脱敏、`trace_id`、指标和
持久化失败。前端测试 SHALL 验证双 CSP 头及报告地址；浏览器回归 SHALL 覆盖登录、刷新恢复、
退出、SSE 与至少一个需要 Bearer 的写请求，并确认 R9 没有改变强制 CSP。

#### Scenario: CI 门禁

- **WHEN** Backend CI 与 Frontend CI 执行 R9 门禁
- **THEN** CSP 接收契约、双响应头、认证/CSRF/SSE 回归、全量测试、构建、Ruff 和前端静态检查
  均通过

## MODIFIED Requirements

### Requirement: 现有 CSP 迁移状态

R5 的 CSP 迁移状态 SHALL 从 S0 更新为“R9 完成 S1 工程实现”。只有取得覆盖完整业务周期的
真实 Report-Only 数据、归类全部已知违规并通过 S2 专项评审后，后续迭代才能移除强制策略中的
`unsafe-inline` 或 `unsafe-eval`。

#### Scenario: R9 工程验收完成

- **WHEN** R9 代码、测试、CI 和文档均通过
- **THEN** 项目只声明具备 Report-Only 观测能力，不声明强制 CSP 已收紧或 XSS 风险已关闭

### Requirement: 认证与 CSRF 边界

R9 SHALL 保持 access token 的既有双通道：前端 `localStorage` token 用于 Bearer 写请求，
HttpOnly access cookie 用于 SSE 和兼容只读请求，HttpOnly refresh cookie 用于轮换。所有
POST/PUT/PATCH/DELETE 仍必须使用 Authorization Bearer，不接受 access cookie 回退。

#### Scenario: CSP 报告能力上线

- **WHEN** Report-Only 头和报告端点启用
- **THEN** 登录、并发 401 单飞刷新、access cookie 轮换、退出清理、SSE 和 CSRF 拒绝行为不变

### Requirement: 迭代文档与远程交付

R9 完成后 SHALL 更新 `CHANGELOG.md`、`AGENTS.md`、`.agents/`、README、当前迭代计划、
发布清单和新的非生产发布记录。实现、验证和文档提交 SHALL 范围清晰，并推送至 GitHub；
远端 CI 失败必须以独立修复提交处理。

#### Scenario: R9 远程闭环

- **WHEN** 本地门禁和远端 CI 均通过
- **THEN** 本地与 `origin/master` 一致、工作区干净、规格任务与验收清单全部勾选

## REMOVED Requirements

### Requirement: R9 收紧强制 CSP 或移除 localStorage token

**Reason**: S1 需要先取得真实违规证据；同时移除 `localStorage` token 会把 CSP 观测和认证迁移
耦合，扩大 CSRF、刷新恢复、SSE 与回滚风险。

**Migration**: nonce/hash 强制策略进入后续 S2 规格；内存 access token 进入后续 S3 规格。
两者都必须复用 R9 观测证据并独立验收。
