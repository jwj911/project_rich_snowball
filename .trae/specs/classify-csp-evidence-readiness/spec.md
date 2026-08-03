# R10 CSP 证据归类与 S2 准入报告 Spec

## Why

R9 已安全接收并脱敏持久化 CSP Report-Only 违规，但现有记录仍缺少服务端可信的环境/发布归属，
也没有有界、可复现的归类与准入报告。直接人工翻阅 `frontend_logs` 容易泄露 URL、忽略截断或把
零报告误判为无违规，因此 R10 需要先把 S1 数据转成审计友好的 S2 评审输入。

## What Changes

- 为后续 CSP 报告写入服务端受信任的 `environment` 和完整 Git `release` 元数据；旧的无归属
  记录保持不变，只能形成证据不足结论。
- 增加纯后端 `csp_evidence` 领域服务，读取 `FrontendLogDB` 中已脱敏的
  `log_type=csp-violation` 记录。
- 按固定路由类别、directive 类别和 blocked source 类别聚合，不输出完整 URL、记录
  `trace_id`、用户信息或原始 User-Agent。
- 使用受校验的上下文清单和已知违规目录，判定 `insufficient_evidence`、`blocked` 或
  `ready_for_review`。
- 增加离线只读 CLI，使用明确的数据库、上下文、目录和报告路径生成带独立 `trace_id` 的 JSON。
- 固定查询窗口、输入文件、扫描行数、聚合组、输出字节和执行时间上限；截断或超限不能静默
  解释为“无违规”。
- 为 PostgreSQL 使用只读事务与 statement timeout，为 SQLite 使用 query-only 连接；除显式
  报告文件外不修改数据库、CSP、部署状态或发布清单。
- 增加 SQLite/PostgreSQL、CLI、脱敏、三状态、限额和 CI 契约测试。
- 更新 Post-R9 路线图、发布清单、运维/安全文档和 R10 非生产工程基线。
- 本轮不新增管理员 HTTP API，不新增数据库表或 Alembic 迁移，不修改强制 CSP 或
  Report-Only 策略，不部署 R9，不实施 S2/S3。
- 本轮无 **BREAKING** API 变更。

## Impact

- Affected specs: CSP 证据治理、S2 准入、前端安全观测、发布治理、只读运维工具。
- Affected code:
  - `python/config.py`
  - `python/routers/frontend_logs.py`
  - `python/services/csp_evidence.py`
  - `python/scripts/csp_evidence_report.py`
  - `python/tests/test_csp_reports.py`
  - `python/tests/test_csp_evidence.py`
  - `python/tests/test_csp_evidence_cli.py`
  - `python/tests/test_csp_evidence_postgres.py`
  - `.github/workflows/backend-ci.yml`
  - `.env.example`
  - `docker-compose.yml`
  - `README.md`、`AGENTS.md`、`.agents/`、Post-R9 计划、发布清单与 R10 发布记录

## ADDED Requirements

### Requirement: 服务端可信观测归属

系统 SHALL 使用服务端配置而不是浏览器报告字段，为新持久化的 CSP 记录写入环境与发布归属：

- 环境来自现有 `ENV`，报告准入只接受 `production`；
- 发布来自 `RELEASE_COMMIT`，非空时必须是 40 位十六进制 Git SHA，并规范化为小写；
- `RELEASE_COMMIT` 缺失时应用仍可启动并继续接收报告，但 CSP 记录的 release 为空；
- 非受控环境或缺少 release 的记录不得进入 `ready_for_review` 证据；
- 客户端无法覆盖 `environment`、`release` 或证据来源。

blocked URL 若使用 `chrome-extension` 或 `moz-extension` scheme，接收端 SHALL 只保存固定
`browser-extension` 类别，不保存 extension ID、path、query 或 fragment。

#### Scenario: 生产报告具有可信归属

- **WHEN** API 进程以 `ENV=production` 和合法 40 位 `RELEASE_COMMIT` 接收合法 CSP 报告
- **THEN** `FrontendLogDB.environment` 与 `release` 由服务端写入，payload 仍只包含 R9
  allowlist 字段

#### Scenario: 发布提交缺失

- **WHEN** API 未配置 `RELEASE_COMMIT`
- **THEN** 报告继续按 R9 边界接收，但 release 为空，后续 R10 报告只能判定证据不足

#### Scenario: 浏览器扩展违规

- **WHEN** blocked URL 使用浏览器扩展 scheme
- **THEN** 持久化值仅为 `browser-extension`，不包含扩展标识或资源路径

### Requirement: 受控证据上下文

R10 CLI SHALL 要求显式提供 UTF-8 JSON 上下文文件，大小不得超过 64 KiB。上下文使用
`schema_version=1` 并至少包含：

- `evidence_source`：`synthetic` 或 `target_environment`；
- `environment`：`development`、`ci`、`staging` 或 `production`；
- 40 位小写 Git `release`；
- UTC `window_start` 和 end-exclusive `window_end`；
- `[0, 1]` 内有限 `sample_rate`；
- `complete_business_cycle` 布尔值；
- 固定核心流程矩阵；
- 非负的业务 HTTP 与 CSP outcome 窗口计数；
- 最多 20 个 expected document origins 和最多 20 个 trusted source origins。

核心流程矩阵固定为：

`login`、`refresh_recovery`、`concurrent_401_singleflight`、`logout`、
`sse_initial_connect`、`sse_reconnect`、`products`、`product_detail`、
`workspace`、`strategies`、`agents`、`bearer_write`、`cookie_only_write_rejected` 和
`csp_reporting_canary`。每项状态只能是 `passed`、`failed` 或 `not_run`。

origin 只允许无 userinfo、query、fragment 且无非根 path 的绝对 HTTP(S) origin。生产上下文只
接受 HTTPS。origin 仅参与分类，不得写入输出报告。

#### Scenario: 只有 synthetic 上下文

- **WHEN** `evidence_source=synthetic`
- **THEN** 即使所有结构和测试数据合法，最终状态也不能高于 `insufficient_evidence`

#### Scenario: 上下文结构非法

- **WHEN** 文件超大、时间非 UTC、end 不晚于 start、release 非完整 SHA、枚举非法或 origin
  含凭据/query/fragment
- **THEN** CLI 使用稳定失败码退出，不查询数据库，不回显非法值

### Requirement: 已知违规目录

R10 CLI SHALL 要求显式提供 UTF-8 JSON 已知违规目录，大小不得超过 64 KiB，最多 500 条。
目录使用 `schema_version=1`，每条只包含受控字段：

- `catalog_id`：1 至 64 位 ASCII slug；
- `route_category`、`directive_category`、`blocked_source_category`；
- `owner_role`：1 至 64 位 ASCII slug，不使用个人姓名或用户 ID；
- `decision`：`remediate_before_s2`、`migrate_nonce_in_s2`、`migrate_hash_in_s2`、
  `remove_source_in_s2` 或 `not_applicable`；
- `retest_status`：`passed`、`failed`、`pending` 或 `not_applicable`。

同一分类三元组不得重复。目录不得包含 URL、脚本、DOM、User-Agent、凭据、记录 trace、自由文本
证据或文件路径。`pending` / `failed` 项及未命中目录的聚合均阻止 `ready_for_review`；
`not_applicable` 只允许与 `migrate_nonce_in_s2`、`migrate_hash_in_s2` 或
`remove_source_in_s2` 决策组合。

#### Scenario: 已知违规闭环

- **WHEN** 一个观测聚合精确命中目录，具有 owner、允许的决策和合格复验状态
- **THEN** 报告将其计入低敏 `known_violations`

#### Scenario: 目录未覆盖或待处理

- **WHEN** 聚合未命中目录，或目录项复验为 `pending` / `failed`
- **THEN** 报告状态为 `blocked`，只输出受控分类与计数

### Requirement: 固定低基数归类

系统 SHALL 使用代码内固定枚举归类，不从数据库值动态生成指标标签或类别。

路由类别至少包含：

`home`、`products`、`product_detail`、`workspace`、`my_comments`、`agents`、
`agent_detail`、`chat`、`strategies`、`strategy_evolution`、`alerts`、`news`、
`opinions`、`portfolio`、`metrics`、`settings` 和 `unknown`。

directive 类别至少包含：

`script_src`、`script_src_elem`、`script_src_attr`、`style_src`、`style_src_elem`、
`style_src_attr`、`connect_src`、`img_src`、`font_src`、`frame_src`、`worker_src`、
`default_src`、`base_uri`、`form_action`、`object_src`、`frame_ancestors`、
`manifest_src`、`media_src`、`child_src` 和 `unknown`。

blocked source 类别固定为：

`inline`、`eval`、`data`、`blob`、`browser_extension`、`same_origin`、
`trusted_source`、`external_untrusted` 和 `unknown`。

document URL 只用于验证 expected origin 和匹配 path。`/products/{id}`、
`/agents/detail` 与 `/strategies/evolution` 必须按更具体规则优先匹配。完整 URL、host、path
参数和 source file 不得进入报告。

#### Scenario: 已知页面与来源

- **WHEN** 记录来自 expected origin 的 `/products/AU`，directive 为 `script-src-elem`，
  blocked URL 为 `inline`
- **THEN** 聚合键为 `product_detail / script_src_elem / inline`

#### Scenario: 未知路由或 directive

- **WHEN** path 或 directive 不在固定映射
- **THEN** 映射为 `unknown` 并阻止 `ready_for_review`，不把原始值写入报告

#### Scenario: 非预期 document origin

- **WHEN** 记录的 document origin 不属于 expected origins
- **THEN** 记录只计入安全问题码与数量，状态为 `blocked`，不输出该 origin

### Requirement: 有界只读查询

R10 服务 SHALL 只选择 `frontend_logs` 中归类所需的
`id/payload_json/environment/release/created_at`，不选择 `url`、`user_agent` 或 `user_id`。
查询必须满足：

- `type = 'csp-violation'`；
- `window_start <= created_at < window_end`；
- 单次窗口最长 31 天；
- 最多读取 50,000 条目标记录，使用 500 条 keyset page；
- 最多输出 500 个聚合组；
- 运行时间最多 30 秒；
- PostgreSQL 事务设置为 read only 且 statement timeout 不超过 30 秒；
- SQLite 连接启用 `PRAGMA query_only=ON`；
- 不调用 ORM `add`、`delete`、`flush` 或 `commit`，不修改报告记录。

服务 SHALL 同时以安全计数识别目标窗口中 environment/release 缺失的 CSP 记录。超过行数、
聚合组或运行时上限时，报告必须明确 `truncated=true` 并判定
`insufficient_evidence`，不得只根据已读取前缀作出无违规结论。

#### Scenario: 查询在限额内

- **WHEN** 时间窗口、记录数、聚合数和运行时间均未超限
- **THEN** 服务读取全部目标记录并输出确定性排序的聚合

#### Scenario: 行数超过上限

- **WHEN** 第 50,001 条目标记录存在
- **THEN** 服务停止继续扫描，标记截断和稳定问题码，状态不能为 `ready_for_review`

#### Scenario: 写入尝试

- **WHEN** R10 查询路径或测试夹具尝试执行 DML
- **THEN** 数据库只读事务拒绝该操作，原表保持不变

### Requirement: 记录完整性与敏感字段停止条件

每条候选记录 SHALL 再次验证 R9 payload allowlist、JSON 类型、32 位十六进制记录 trace、
document URL、directive、disposition 和数值边界。服务不得把记录 trace 放入输出。

以下情况只记录稳定问题码和计数，并使状态为 `blocked`：

- payload JSON 无法解析或不是对象；
- 出现 R9 allowlist 以外的 key；
- 出现 `sample`、脚本、DOM、Cookie、Authorization、token、原始 User-Agent 等禁止字段；
- payload 与列上的 environment/release 不一致或不符合上下文；
- `disposition` 不是 Report-Only 所需的 `report`；
- accepted 窗口计数与完整、未截断的目标记录数不一致；
- `persist_failed > 0`。

任何日志、异常、stdout/stderr 和报告都不得包含 payload、URL、数据库连接串、输入文件内容或异常
原文。

#### Scenario: 遇到非法历史记录

- **WHEN** 一条历史 CSP 记录含未知或敏感 key
- **THEN** 报告只增加对应问题码计数并返回 `blocked`，不回显 key 的值或记录内容

### Requirement: 可审计报告与状态机

R10 SHALL 生成 `schema_version=1` 的 JSON，大小不超过 256 KiB，至少包含：

- 新生成的独立 32 位十六进制 `trace_id` 和 UTC `generated_at`；
- `status`：`insufficient_evidence`、`blocked`、`ready_for_review` 或操作性 `failed`；
- 受控 scope：evidence source、environment、release、UTC 窗口和 sample rate；
- 扫描/分类/已知/未知/非法/无归属/聚合数量和 `truncated`；
- 固定 limits；
- 稳定 check/problem codes；
- 按分类三元组排序的 aggregates；
- 只含 catalog ID、分类、owner role、decision、retest status 和 count 的 known violations；
- 只含分类三元组与 count 的 unknown violations。

报告不得包含完整 URL、origin、host、path 参数、source file、referrer、记录 `trace_id`、用户信息、
原始 User-Agent、凭据、脚本、DOM、原始 payload、数据库 URL 或输入/输出文件路径。

状态优先级固定为：

1. 查询、解析基础设施或报告构建失败：`failed`；
2. 敏感/非法记录、未知分类、未闭环目录、unexpected origin、计数不一致或持久化失败：
   `blocked`；
3. synthetic/非生产、缺少 release、非完整周期、核心流程未全 passed、sample rate 为 0、
   缺少流量/指标、存在无归属记录或发生任何截断：`insufficient_evidence`；
4. 其余条件全部满足：`ready_for_review`。

`ready_for_review` 只表示可以发起人工 S2 专项评审，不表示 S2 已批准或可以自动收紧 CSP。

#### Scenario: 完整 synthetic 数据

- **WHEN** synthetic 数据结构、目录与流程全部满足
- **THEN** 状态仍为 `insufficient_evidence`

#### Scenario: 完整目标环境数据

- **WHEN** production 完整周期、流程、指标、记录、目录和限额均满足且无阻塞问题
- **THEN** 状态为 `ready_for_review`，但系统不修改 CSP

### Requirement: 安全离线 CLI

系统 SHALL 提供 `python/scripts/csp_evidence_report.py`，要求显式参数：

```text
--database-url
--context-path
--catalog-path
--report-path
```

`DATABASE_URL` 可作为 `--database-url` 的受控回退；其余路径不得有默认值。context/catalog 在
查询数据库前完成大小和结构验证。report path 必须位于仓库目录之外，CLI 使用同目录临时文件加
原子 replace 写入，并在支持的平台设置仅当前用户可读写权限。

CLI stdout 只输出 `trace_id`、状态和安全计数摘要；stderr 只输出稳定 error type/code。不得输出
报告正文、文件路径、数据库 URL 或异常文本。

退出码固定为：

- `0`：`ready_for_review`；
- `1`：`insufficient_evidence`；
- `2`：`blocked`；
- `3`：`failed`；
- `4`：报告写入失败。

本地/CI 使用 synthetic 上下文时，退出码 `1` 是预期契约结果，不能被包装为生产准入成功。

#### Scenario: 报告路径在仓库内

- **WHEN** 操作者把 report path 指向仓库根目录或任一子目录
- **THEN** CLI 在查询前拒绝并返回稳定失败，不创建文件

#### Scenario: 报告写入失败

- **WHEN** 临时文件创建、权限设置或原子 replace 失败
- **THEN** CLI 返回 `4`，stderr 只含独立 trace、固定状态和异常类型

### Requirement: 自动化回归与 CI

R10 SHALL 覆盖：

- 服务端 environment/release 归属和浏览器扩展安全类别；
- context/catalog 的大小、枚举、时间、origin、重复和组合校验；
- 路由、directive、source 的全部固定映射和 unknown 行为；
- 三状态优先级、操作失败态、零报告、synthetic、完整目标环境和目录闭环；
- 50,001 行、501 组、31 天、30 秒与 256 KiB 边界；
- malformed/额外/敏感 payload、计数不一致、无归属记录和 `persist_failed`；
- stdout/stderr/JSON/日志不含敏感输入；
- SQLite query-only 与 PostgreSQL read-only/statement timeout；
- CLI 报告路径、原子写入、退出码和写入失败；
- R9 接收、采样、限流、脱敏、批量提交和 PostgreSQL 持久化无回归。

Backend CI SHALL 增加 R10 定向门禁，并使用 synthetic 上下文断言状态只能是
`insufficient_evidence`。CI 产物不得作为生产报告或 S2 准入证据。

#### Scenario: CI 契约

- **WHEN** Backend CI 执行 R10 门禁
- **THEN** SQLite/PostgreSQL、CLI、安全输出、限额和 R9 回归通过，synthetic 报告不能返回
  `ready_for_review`

### Requirement: R10 文档与远程交付

R10 完成后 SHALL 更新 README、AGENTS、`.agents/`、`.env.example`、Compose、Post-R9 计划、
发布清单和新的非生产工程基线记录，明确：

- R10 只提供 evidence-only 分类与人工评审输入；
- 本地/CI 只能形成 synthetic `insufficient_evidence`；
- R11 生产操作者、完整业务周期和真实指标仍未完成；
- R12/S2、R13/S3、R8/R7 条件轨道均未启动；
- 强制 CSP、Report-Only 策略、`localStorage` token、Bearer 写请求和 cookie-only 拒绝边界
  均未改变。

实现、测试、CI 与文档 SHALL 原子提交并推送；远端 CI 失败必须独立修复并记录。生产生成的
context/catalog/report 文件不得进入版本控制。

#### Scenario: R10 工程闭环

- **WHEN** 本地门禁、远端 Backend CI、文档和清理均完成
- **THEN** 项目只声明 R10 非生产工程基线，Post-R9 下一阶段仍是受生产操作者门禁的 R11

## MODIFIED Requirements

### Requirement: R9 CSP 持久化

R9 的 payload allowlist、8 KiB、批量、采样、限流、脱敏、独立记录 trace 和低基数指标保持
不变。R10 只为新记录补充服务端 environment/release 列，并把浏览器扩展 URL 降维为固定类别。
不得回填、重写或删除既有 `frontend_logs`。

### Requirement: Post-R9 当前状态

R10 规格批准后，Post-R9 计划 SHALL 将 R10 标为“规格已批准/实施中”；工程门禁闭环后标为
“非生产工程基线已完成”。只有 R11 真实目标环境证据生成 `ready_for_review` 且经人工评审，
R12 才能进入实施。

### Requirement: 生产发布元数据

`RELEASE_COMMIT` SHALL 从仅用于发布预检扩展为 API 运行时 CSP 证据归属。生产部署若缺失该值，
应用可保持 S1 接收能力，但 R10 必须报告证据不足，不能形成 S2 准入。

## REMOVED Requirements

### Requirement: 通过通用日志 API 或新增管理员 HTTP API 人工浏览 CSP 明细

**Reason**: 通用日志响应会返回逐条 URL/payload，新增在线查询面也会扩大高敏观测数据的权限、
限流和导出风险。

**Migration**: R10 只提供有界离线只读 CLI 和低基数聚合报告；需要在线展示时另立规格。

### Requirement: 零报告等于无违规

**Reason**: 零记录可能来自采样率为 0、接收失败、持久化失败、发布归属缺失、窗口不完整或流程
未覆盖。

**Migration**: 只有 context、流程、指标、记录完整性、目录和限额全部通过时，R10 才可输出
`ready_for_review`；零记录本身不提供准入结论。
