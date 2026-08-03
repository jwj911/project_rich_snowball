# Post-R9 迭代路线图：证据门禁、生产观测与条件轨道

> 计划日期：2026-08-02
> 当前状态：Post-R9 唯一当前迭代事实源；R10 独立规格已批准，本地实现与验证已完成，
> 远端 Backend CI 待验证
> 适用范围：R9 之后的 CSP 与认证迁移、生产观测、K 线生命周期、SSE 扩展和产品候选治理
> 历史事实源：
> [`iteration_plan_20260724_follow_up.md`](iteration_plan_20260724_follow_up.md)，仅保留 R1 至 R9
> 的执行记录，不再决定 Post-R9 排期
> 对应治理规格：
> [`define-post-r9-iteration-roadmap`](../.trae/specs/define-post-r9-iteration-roadmap/spec.md)

## 1. 文档定位

本文件是 R9 之后状态、依赖、准入、退出和停止条件的唯一当前事实源。发布记录、设计文档和
历史计划继续提供原始证据；当其中的“下一步”与本文件冲突时，以本文件为准，但不得据此改写
历史测试计数或把未执行事项描述为已完成。

本路线图按实际可执行门禁组织工作，不用版本号顺序掩盖生产凭据、操作者、观测证据或容量阈值
等外部依赖。没有满足门禁且没有独立规格批准的事项，不得标记为“进行中”或“已排期”。

本文定义后续工作，并记录 R10 本地工程实现与验证事实；本次事实源更新不新增业务代码、数据库
迁移或生产操作，也不生成生产报告。其他项目入口的链接同步和活跃设计文档状态校正属于后续
文档任务；在完成同步前，Post-R9 决策仍由本文件统一管理。

## 2. R9 已验证基线

### 2.1 提交与远端 CI

R9 的可追溯提交为：

- 启动文档提交及应用回滚点：
  `756ca605613ba2a4f76919e913e1264e3f9d2a1b`；
- 本地实现提交：`723ba9b949bccf7c96798d2f45388731350eacd3`；
- 本地验证文档提交：`37fc8008a74c1b74c48f74aac5e3267c8a29e5b6`；
- CI 稳定性修复提交：`c7a721a04f58caa51860be67d870855663186a14`。

远端门禁证据为：

- [Backend CI run 30739553595](https://github.com/jwj911/project_rich_snowball/actions/runs/30739553595)
  成功；`R9 CSP contract gate 39 passed`，包含 PostgreSQL 持久化集成测试，完整后端测试约
  `1195 passed, 1 skipped`，Alembic、API smoke、Ruff 与依赖审计均通过；
- [Frontend CI run 30740784839](https://github.com/jwj911/project_rich_snowball/actions/runs/30740784839)
  成功；Vitest、production build、增强版 R9 E2E `3 passed`、全量 Playwright
  `43 passed` 与 Lighthouse 均通过；
- Frontend CI run 30739553574 曾因既有 metrics 页面测试没有等待异步数据而失败，后由
  `c7a721a04f58caa51860be67d870855663186a14` 修复测试竞态。该失败运行不作为成功门禁。

本地证据及其限定为：

- 独立审查修复前后端全量为
  `1177 passed, 18 skipped, 0 failed, 103 warnings`；
- 审查修复后受影响聚焦回归为 `85 passed, 1 skipped, 0 failed`，Ruff check/format 通过；
  唯一 skip 是本地没有隔离 PostgreSQL 的 CSP 持久化专项，该专项已由 Backend CI 的
  PostgreSQL 16 环境覆盖；
- 审查增强前前端 CSP 配置为 `21 passed`、全量 Vitest 为
  `35 files / 223 passed`、production build 通过且最大 First Load JS 为 `157 kB`、
  基础版 R9 Playwright 为 `3 passed`；
- 增加并发 401 单飞刷新和 SSE 首次断线重连后，本地只完成增强版 Playwright `--list`、
  TypeScript 与 ESLint 检查；增强版实际浏览器执行证据来自成功的 Frontend CI，不能把基础版
  本地 `3 passed` 当作增强版本地结果。

完整原始记录见
[`releases/20260802_r9_csp_report_only_observability.md`](releases/20260802_r9_csp_report_only_observability.md)。
以上计数是 R9 历史证据，本路线图没有重新运行或扩大这些代码测试。

### 2.2 已交付能力

R9 已完成 S1 非阻断观测工程闭环：

- 保留既有强制 `Content-Security-Policy` 原值；
- 新增候选 `script-src 'self'` 的 `Content-Security-Policy-Report-Only`；
- 安全接收 legacy CSP 与 Reporting API 报告，限制 8 KiB 请求体和每批 20 条；
- 持久化前移除 URL userinfo、query 与 fragment，不保存原始请求体、sample、脚本、DOM、
  Cookie、Authorization 或未知字段；
- 每条已持久化 `csp-violation` 记录具有独立 `trace_id`；
- 指标使用固定低基数 `csp_reports_total{outcome}`；
- 登录、刷新、退出、SSE、Bearer 写请求和 cookie-only 写请求拒绝已有 R9 工程回归。

### 2.3 非生产边界

R9 仍是非生产工程基线，不是生产发布：

- 尚未部署到真实目标环境；
- 尚未指定生产窗口、发布负责人和回滚负责人；
- 尚未覆盖并归类真实完整业务周期的 Report-Only 报告；
- 强制 CSP 仍包含 `unsafe-inline` / `unsafe-eval`，S2 尚未准入；
- `localStorage['futures_access_token']` 风险仍未关闭，S3 尚未开始；
- POST/PUT/PATCH/DELETE 继续要求 `Authorization: Bearer`，cookie-only 写请求继续拒绝；
- 本地和 CI synthetic 报告只证明接收与回归契约，不是生产 SLO、真实违规率或 S2 准入证据。

R8 也继续保持非生产边界：活动 `kline_data` 未切换，冷数据未导出或删除，对象存储归档和生产
备份恢复未执行。R7 只支持 `SSE_DEPLOYMENT_MODE=single|sticky`，Redis 共享时间戳不是
Pub/Sub 或分布式连接管理。

### 2.4 文档审计结论

本路线图采用以下现有事实，避免重复建设：

- 多因子组合、过滤 DSL、因子注册表、中性化、增强回测指标和日频 walk-forward 已实现，
  不再作为候选功能排期；
- TraderAgent 已上线，后续候选是交易计划的持久化、结果追踪及与回测/持仓的显式关联；
- Data Catalog 后端已实现，后续候选是用户可见的只读目录和质量上下文；
- 策略进化已有后端 Agent 事件流，后续候选是工作台实时进度和断线恢复体验；
- CSP 阶段继续遵循
  [`r5_frontend_quality_observability.md`](r5_frontend_quality_observability.md) 的
  S1、S2、S3 顺序；
- K 线与 SSE 条件轨道分别遵循
  [`../python/docs/kline_partitioning.md`](../python/docs/kline_partitioning.md) 和
  [`../python/docs/sse_scaling_strategy.md`](../python/docs/sse_scaling_strategy.md) 的
  当前运行边界。

## 3. 五类可执行状态

以下状态描述“现在为什么能做或不能做”，不是完成度：

| 可执行状态 | 判定规则 | 排期规则 |
|---|---|---|
| 可立即实施 | 所需输入已存在，且不依赖生产凭据或新增观测窗口 | 只能先建立并批准独立规格，再实施 |
| 需要生产操作者 | 依赖真实凭据、目标环境、发布窗口、发布/回滚负责人或生产操作 | 任一输入缺失即阻塞，不得用 CI 代替 |
| 需要观测证据 | 依赖完整业务周期、无未知违规、稳定性或专项回归证据 | 证据未完成即未准入，不得先改强制策略 |
| 需要容量/并发阈值 | 只有真实容量、性能、并发或高可用需求达到门槛才有实施价值 | 阈值未触发即不排期，触发后仍须独立规格 |
| 候选产品增强 | 用户价值成立，但数据模型、权限、保留和测试成本尚未评审 | 逐项另立规格，每次只实现一个完整用户闭环 |

`待立项`、`阻塞`、`未准入`、`未触发` 和 `候选` 是门禁结论。R10 的“本地实现/验证完成、
远端 CI 待验证”是工程交付状态，不代表生产部署或 S2 准入；其他事项只有独立规格批准且对应
门禁满足后，才可改为 `进行中`。

## 4. 状态总表

| ID | 事项 | 可执行状态 | 优先级 | 当前结论 | 关键依赖或触发 | 退出证据 |
|---|---|---|---|---|---|---|
| R10 | CSP 脱敏证据归类与 S2 准入报告 | 可立即实施 | P0 | 本地实现/验证完成；远端 CI 待验证 | R9 已脱敏记录和受控发布元数据 | 有界只读能力、脱敏 JSON 和正确三状态判定；远端门禁待闭环 |
| R11 | 目标环境 S1 部署与完整业务周期 | 需要生产操作者 | P0 | 阻塞 | 凭据、窗口、发布/回滚负责人、清单、R10 报告能力 | 完整周期、核心流程、告警基线、回滚和可归类证据 |
| R12 | S2 nonce/hash 与 `script-src` 收紧 | 需要观测证据 | P1 | 未准入 | R11 退出，R10 为 `ready_for_review` 且人工批准 | 强制策略专项回归、无未知违规和可验证回滚 |
| R13 | S3 内存 access token | 需要观测证据 | P1 | 未准入 | R12 稳定退出和认证独立规格 | 恢复、401、跨标签、logout、SSE、Bearer 写请求均通过 |
| R8 轨道 | 生产分区与冷归档 | 需要容量/并发阈值 | P2 | 未触发 | 生产只读预检达到固定阈值，且有维护/恢复门禁 | 独立规格规定的切换、恢复、归档和审计证据 |
| R7 轨道 | Redis Pub/Sub 与跨实例 SSE | 需要容量/并发阈值 | 条件 P1 | 未触发 | 多实例高可用需求或并发进入扩展区间 | 分布式连接、全局上限、故障恢复和降级证据 |
| P-C1 | Trader 交易计划生命周期 | 候选产品增强 | P2 | 候选，未排期 | 用户闭环、模型、权限、保留和测试成本评审 | 一个计划从创建到结果关联的完整闭环 |
| P-C2 | Data Catalog 前端展示 | 候选产品增强 | P2 | 候选，未排期 | 只读权限、质量语义、可见范围和性能评审 | 用户可理解且不泄露私有信息的目录闭环 |
| P-C3 | 策略进化实时进度 | 候选产品增强 | P2 | 候选，未排期 | 事件契约、断线恢复、保留和并发成本评审 | 可恢复、可解释的单任务进度闭环 |

## 5. 依赖图

```text
R9 S1 非生产工程基线
  |
  +--> R10 独立规格已批准
  |      |
  |      +--> R10 有界只读归类能力本地实现/验证完成，远端 CI 待验证
  |                 |
  |                 +--> 仅本地/CI synthetic 时：insufficient_evidence
  |
  +--> R11 生产操作者门禁 + R10 报告能力
         |
         +--> 目标环境 S1 部署和完整业务周期
                  |
                  +--> 用 R11 证据重新生成 R10 报告
                           |
                           +--> ready_for_review + 人工 S2 批准
                                      |
                                      +--> R12 S2
                                               |
                                               +--> 稳定退出 + 认证专项批准
                                                        |
                                                        +--> R13 S3

R9/R8 基线 --> R8 阈值轨道，仅在生产容量或性能门槛触发
R9/R7 基线 --> R7 阈值轨道，仅在高可用需求或并发门槛触发
产品候选   --> 各自独立价值评审和规格，不接入上述安全主链
```

R10 可以在没有生产数据时完成报告契约和能力，但此时正确结论只能是
`insufficient_evidence`。R11 产出的完整周期证据必须再次通过同一 R10 能力归类；只有
`ready_for_review` 经人工批准后，R12 才可能准入。

## 6. R10：CSP 脱敏证据归类与 S2 准入报告

### 6.1 目标与输入边界

R10 是当前已完成本地实现与验证、等待远端 Backend CI 复核的工程迭代。目标是把 R9 已经
脱敏的 `csp-violation` 记录转成可审计、可复现的 S2 评审输入，不收集新型敏感数据，也不修改
任何 CSP。

允许输入：

- R9 已持久化且 `log_type=csp-violation` 的脱敏记录；
- 受控路由类别、环境枚举、可信发布版本和明确时间窗口；
- 与同一窗口关联的低基数业务流量、报告 outcome 和发布元数据。

禁止读取、恢复、拼接或新增：

- 原始请求体、query、fragment、URL userinfo；
- Cookie、Authorization、access token、refresh token；
- sample、脚本、DOM、页面内容或异常原文；
- 原始 User-Agent、用户标识或可反推个人身份的字段；
- 为了归类而重新接收或保存的完整 URL、source file 或 referrer。

如果现有脱敏字段不能支持某项分类，结果必须标记证据不足，不能回退读取原始数据。

### 6.2 低基数归类

只允许按以下受控维度聚合：

- 受控路由类别，不使用完整页面 URL；
- 规范化 directive，不直接使用任意原始字符串；
- blocked source 类别，例如同源、受信任静态源、内联、动态执行、浏览器扩展或未知类别，
  具体枚举由 R10 独立规格固定；
- 环境枚举；
- 可信发布版本集合；
- 有上限的时间窗口。

完整 URL、用户标识、`trace_id`、任意请求 ID、原始 User-Agent 和其他高基数字段不得成为
指标标签或聚合分组。`trace_id` 只作为一次报告的诊断字段，不参与指标基数。

### 6.3 有界离线接口

R10 独立规格已选择离线只读命令，不新增管理员 HTTP API，并满足：

- 不暴露匿名、用户或管理员在线查询面；
- 数据库访问只读，不修改 CSP 报告、业务数据、发布状态或清单；
- 查询时间窗口、最大扫描行数、输出字节数和执行时间均有硬上限；
- 所有上限在独立规格中给出可测试数值，缺少任一上限不得进入实现；
- 达到上限时失败关闭或明确返回截断状态，不静默输出“无违规”；
- 离线报告不得自动提交到仓库，生产报告按访问控制和保留策略存放；
- 日志和错误只保留独立 `trace_id`、稳定错误类型与安全计数。

### 6.4 脱敏 JSON 契约

每次报告生成独立 `trace_id`，输出至少包含以下逻辑结构：

```json
{
  "trace_id": "<independent-report-trace-id>",
  "status": "insufficient_evidence | blocked | ready_for_review",
  "window": {
    "start": "<bounded-start>",
    "end": "<bounded-end>"
  },
  "scope": {
    "environment": "<controlled-enum>",
    "trusted_releases": ["<approved-release>"],
    "route_categories": ["<controlled-category>"]
  },
  "aggregates": [
    {
      "route_category": "<controlled-category>",
      "directive": "<normalized-directive>",
      "blocked_source_category": "<controlled-category>",
      "count": 0
    }
  ],
  "known_violations": [
    {
      "category": "<controlled-category>",
      "owner": "<accountable-role>",
      "decision": "<approved-disposition>",
      "retest_status": "<controlled-status>"
    }
  ],
  "limits": {
    "window_bounded": true,
    "rows_bounded": true,
    "output_bounded": true,
    "runtime_bounded": true
  }
}
```

示例只描述契约，不是实际报告或测试结果。输出不得包含原始报告、完整 URL、用户标识、凭据、
脚本、DOM、原始 User-Agent 或任意高基数标签。

### 6.5 三状态判定

| 状态 | 必要判定 | 允许结论 |
|---|---|---|
| `insufficient_evidence` | 只有本地/CI synthetic 流量，或缺少完整业务周期、核心流程、可信发布元数据、指标基线中的任一项 | 仅说明证据缺口；不得解释为“无违规”或 S2 可执行 |
| `blocked` | 存在未知 directive、路由或 blocked source 类别；或已知违规缺少负责人、处理决策或复验结果 | 输出低敏聚合、责任和待办；不得输出原始报告 |
| `ready_for_review` | 目标环境完整业务周期、核心流程覆盖、发布元数据、指标基线均完整，且全部违规已分类并有负责人、决策和复验结果 | 只建议进入 S2 专项人工评审，不代表已批准或可自动实施 |

判定优先级为：敏感数据边界违规立即停止；未知或未闭环违规为 `blocked`；其余证据不完整为
`insufficient_evidence`；全部条件满足后才可为 `ready_for_review`。

### 6.6 准入、退出、非目标与停止条件

实施准入（已满足）：

- R9 脱敏持久化契约和低基数 outcome 指标保持不变；
- R10 独立规格已经批准；
- 独立规格已固定输入 schema、受控枚举、四类硬上限、权限、保留、失败模式和测试矩阵。

退出：

- 有界管理员或离线只读能力通过独立规格规定的回归；
- 相同受控输入可复现同一状态与聚合；
- JSON 具有独立 `trace_id`，三状态与证据缺口可审计；
- 已知违规均记录分类、负责人、处理决策和复验结果；
- 报告只给出 S2 评审建议，不执行配置变更。

非目标：

- 不新增或恢复原始 CSP 数据；
- 不建立用户级、URL 级或 trace 级指标；
- 不部署 R9 到生产，不替代 R11；
- 不修改 `Content-Security-Policy` 或 Report-Only 候选；
- 不实施 nonce/hash、token 迁移、R8/R7 轨道或产品候选。

停止条件：

- 任一路径可能读取、输出、记录或持久化禁止字段；
- 查询缺少窗口、扫描行数、输出大小或执行时间上限；
- 把 synthetic、缺失数据或零报告解释为无违规；
- 未知违规被忽略、自动归为可信或缺少责任闭环；
- 报告或任务尝试自动修改 CSP、部署状态或发布清单。

### 6.7 当前执行事实（2026-08-03）

R10 本地实现与验证已完成，远端 Backend CI 待验证。当前发布记录是
[`releases/20260803_r10_csp_evidence_qualification.md`](releases/20260803_r10_csp_evidence_qualification.md)
所定义的 `non-production engineering baseline` 且 `CI pending`，不得描述为远端工程门禁
已闭环、生产已部署或 S2 已准入。

- 聚焦测试：`375 passed, 5 skipped, 1 warning`；
- 后端全量：`1421 passed, 22 skipped, 103 warnings`；
- 本地 PostgreSQL 不可用，3 个 PostgreSQL 专项明确 skip，必须等待远端 PostgreSQL CI
  复核，不能用 SQLite 结果替代；
- Ruff、diff 和安全复核均通过；
- synthetic CLI 按契约返回退出码 `1` 和 `insufficient_evidence`，生成的安全报告为
  `1707 B`；该结果不是生产 SLO、真实违规率或 S2 准入证据；
- context/catalog 输入各不超过 64 KiB，窗口不超过 31 天，最多扫描 50,000 行，keyset page、
  聚合组和 catalog 分别不超过 500，origin 列表各不超过 20，运行时间和 PostgreSQL statement
  timeout 均不超过 30 秒，报告不超过 256 KiB；
- CLI 退出码固定为 `0=ready_for_review`、`1=insufficient_evidence`、`2=blocked`、
  `3=failed`、`4=report_write_failed`；
- 本轮没有新增管理员 HTTP API、数据库表或 Alembic 迁移，没有修改强制 CSP、Report-Only
  策略、`localStorage` token、HttpOnly cookie、Bearer 写请求或 cookie-only 写请求拒绝边界；
- 未生成生产 context、catalog 或 report，包含用户数据的 `python/dev.db` 保持保留；
- 暂定应用回滚点为 Post-R9 提交 `b8f92f1d87a8dfe2304ba7dd621ed5d031d77672`；
  R10 最终实现提交待创建后补记，不得虚构提交哈希。

R11 仍受生产操作者、凭据、窗口和发布/回滚负责人门禁约束，尚未启动；R12/S2 与 R13/S3
均未启动。

## 7. R11：生产操作者门禁与完整业务周期

### 7.1 目标

R11 负责把 R9 S1 部署到真实目标环境，并在不收紧强制 CSP 的前提下采集至少一个完整业务
周期的真实观测。完整业务周期的起止、业务日历、计划任务和核心用户活动必须在 R11 独立规格
和发布记录中预先定义，执行后不得为迎合结果缩短窗口。

### 7.2 准入

以下条件全部满足后才能排期：

- 真实目标环境、生产凭据和受信任待发布版本已确定；
- 发布窗口、发布负责人和回滚负责人已明确指定；
- 从
  [`release_checklist_20260719.md`](release_checklist_20260719.md)
  复制本次发布记录，未执行项保持未勾选；
- 备份、恢复点、数据库迁移、HTTPS CORS、readiness、scheduler owner 和目标环境 smoke
  有执行方案；
- SSE 明确保持 `single|sticky`，没有把 Redis 时间戳误当作分布式连接管理；
- R10 有界归类能力可用于窗口内证据；
- 强制 CSP、Bearer 写请求和 cookie-only 写请求拒绝保持 R9 基线。

缺少任一真实输入时，R11 保持阻塞。历史 CI、候选环境或 synthetic 报告不能替代。

### 7.3 完整周期与核心流程矩阵

观测窗口至少覆盖预先定义的一个完整业务周期，并记录：

- 发布版本、环境、窗口、采样率、负责人和回滚点；
- 登录、刷新恢复、并发 401 单飞、退出；
- SSE 首连、首次断线重连、cookie 轮换和降级路径；
- 关键页面、实时行情、详情读取和既有写操作；
- Bearer 写请求成功与 cookie-only 写请求继续拒绝；
- Report-Only 报告接收、采样、拒绝、限流和持久化失败；
- `csp_reports_total{outcome}` 与同窗口业务 HTTP 流量的趋势对比；
- 已知违规分类、负责人、处理决策、复验结果和未覆盖流程；
- 告警基线、值班响应和应用回滚演练。

观测和报告继续遵守 R9 脱敏边界，不保存生产请求样本、凭据、完整 URL、脚本或页面内容。

### 7.4 退出、非目标与停止条件

退出：

- 目标环境发布清单逐项保留真实执行证据；
- 完整业务周期无窗口缺口，核心流程矩阵有明确覆盖结论；
- 发布、回滚、告警和责任人记录完整；
- R10 使用该窗口重新生成报告，所有证据缺口和违规均可审计；
- 目标环境回滚演练证明可恢复到 R9 S1 已验证行为。

非目标：

- 不收紧强制 CSP，不移除 `unsafe-inline` / `unsafe-eval`；
- 不迁移 `localStorage` access token；
- 不启用 cookie-only 写请求；
- 不执行活动 K 线表切换、冷归档或分布式 SSE；
- 不以“完成 R11”自动批准 R12。

停止并回滚：

- 生产凭据、窗口、发布负责人或回滚负责人失效；
- 备份恢复、readiness、目标环境 smoke 或回滚路径不能验证；
- 登录、刷新、SSE、页面、Bearer 写请求或 CSRF 边界回归；
- 发现敏感 CSP 数据落库、日志或报告；
- Report-Only 被误配为 enforce，或现有强制 CSP 值发生未经批准的变化；
- 持久化失败、拒绝或限流异常无法解释且影响证据完整性。

## 8. R12：S2 nonce/hash 收紧

### 8.1 准入

R12 必须另立 S2 独立规格，且同时满足：

- R11 已按真实发布清单退出；
- 同一完整周期的 R10 报告为 `ready_for_review`；
- 全部已知违规有分类、负责人、处理决策和复验结果；
- 没有未知 directive、路由或 blocked source 类别；
- S2 报告和变更方案已经人工安全评审批准；
- nonce/hash 架构、部署兼容、浏览器矩阵、回滚点和分步顺序已在规格中固定。

`ready_for_review` 不是自动批准。任何 synthetic-only 报告、窗口缺口或未知违规均使 R12
保持未准入。

### 8.2 范围与退出

R12 只处理：

- 为可控 inline 脚本迁移 nonce/hash；
- 移除不再需要的第三方或动态执行来源；
- 按独立、可回滚步骤收紧 `script-src`；
- 保留 Report-Only 与低基数观测，用于验证每一步。

退出证据至少覆盖 production build、登录、刷新、退出、并发 401、SSE、关键页面、详情写操作、
Bearer 写请求、cookie-only 写请求拒绝和完整浏览器 smoke。所有步骤必须没有未知违规，并完成
独立规格规定的目标环境观察与回滚验证。

### 8.3 非目标、停止与回滚

非目标：

- 不迁移 access token，不改变 refresh cookie 或写请求鉴权；
- 不设计 S4 cookie-only、CSRF token 或 origin 策略；
- 不混入 R8、R7 或产品候选。

停止条件：

- 任一未知违规、新增动态执行来源或无法归类的浏览器差异；
- production build、登录、刷新、SSE、页面或写操作回归；
- nonce/hash 在目标部署链路中不稳定或不可复现；
- 观测、告警或回滚证据不完整。

停止时恢复到 R11 已验证的 S1 强制 CSP 原值，保留脱敏 Report-Only 证据和独立 `trace_id`，
不得用放宽其他安全边界掩盖回归。

## 9. R13：S3 内存 access token

### 9.1 准入与范围

R13 必须在 R12 稳定退出后另立认证专项规格。范围仅为：

- 登录和刷新后将短期 access token 保存在内存；
- 页面恢复时通过 HttpOnly refresh cookie 重新建立会话；
- refresh 继续同步轮换 SSE 使用的 access cookie；
- POST/PUT/PATCH/DELETE 继续携带 `Authorization: Bearer`；
- 明确并发 401 单飞、refresh 失败、跨标签页、logout 和 token 失效行为。

准入证据包括 R12 稳定基线、认证状态机、跨标签协调方案、失败模式、SSE 契约、回滚开关和专项
测试矩阵。缺少任一项不得开始迁移。

### 9.2 退出、非目标与停止条件

退出：

- 页面刷新和直接访问可通过 refresh cookie 恢复会话；
- 并发 401 只有一个 refresh 流程，等待者得到一致结果；
- refresh 失败会清理状态并进入明确的重新登录流程；
- 跨标签登录、刷新、失效与 logout 行为符合独立规格；
- SSE cookie 轮换、首次断线重连和显式 logout 均正常；
- 所有状态变更请求继续要求 Bearer，cookie-only 写请求继续拒绝；
- 认证、CSRF 和浏览器回归以及目标环境回滚通过。

非目标：

- 不把写请求改为 cookie-only；
- 不纳入 S4 CSRF token、origin、cookie scope 或跨子域可行性设计；
- 不同时修改 CSP、分区、SSE 基础设施或产品功能。

停止条件：

- 页面刷新、并发 401、refresh 失败、跨标签页、logout、SSE 或 Bearer 写请求任一回归；
- access token 意外进入 URL、日志、持久化存储或不受控跨标签通道；
- cookie-only 写请求被接受；
- 无法在发布窗口内恢复认证状态。

停止时回退到已验证的 R12 CSP 与 S0 认证行为，不启用 cookie-only 写请求。

## 10. R8：生产分区与冷归档阈值轨道

### 10.1 触发规则

启动生产切换规格前，必须取得真实生产环境
`kline_storage_preflight` 的只读报告。固定阈值为：

| 指标 | 触发值 |
|---|---:|
| `kline_data` 总行数 | 100,000,000 |
| 表与索引总大小 | 100 GiB |
| 分钟查询 P99 | 500 ms |

生产报告明确达到任一容量或性能阈值时，只触发“建立独立生产规格并评审”，不直接触发 DDL、
活动表切换、归档或删除。当前没有可用于启动生产切换的真实生产预检、维护窗口和恢复批准证据，
因此本轨道未触发、未排期。

### 10.2 准入与退出

触发后仍需具备：

- 真实生产容量报告和可重复 benchmark；
- 发布窗口、发布负责人、回滚负责人和删除审批人；
- 发布前备份、隔离恢复演练和明确恢复点；
- 影子表增量追平、短暂停写或双写策略；
- swap、权限、sequence owner、依赖对象和旧表保留期方案；
- Parquet 导出、对象存储校验、恢复抽检、保留和合规策略。

退出证据由独立规格按“分区切换”和“冷归档/删除”分别定义，至少覆盖数据计数、自然键、外键、
核心查询、分区裁剪、应用 smoke、回滚时限、归档校验和恢复抽检。

### 10.3 非目标与停止条件

阈值未触发时，不实施活动表 rename/swap、旧分区 detach/drop、冷数据导出/删除或对象存储
归档。达到阈值但缺少备份恢复、维护窗口、负责人、审批或可回滚方案时同样停止。任何演练结果
不能以 SQLite 或合成 BENCH 数据替代真实生产容量和 PostgreSQL 恢复证据。

## 11. R7：SSE 分布式能力阈值轨道

### 11.1 当前边界与触发规则

当前生产契约继续是 `SSE_DEPLOYMENT_MODE=single|sticky`：

- Redis 只共享 realtime quotes 的 UTC 更新时间戳；
- 每用户旧连接取消、每实例 100 连接上限和连接任务仍是进程内状态；
- Redis 不可用时至少每 60 秒有界重查，恢复后重新使用共享标记；
- 尚无 Redis Pub/Sub、跨实例注册/注销、全局上限或跨实例旧连接取消。

以下任一条件触发独立扩展规格评审：

- 业务明确要求多实例 SSE 高可用，不能接受单 SSE 实例或 sticky 实例级故障；
- 实测或经批准的容量计划进入 200+ 并发连接区间；
- 500+ 并发的大规模场景成为明确目标。

本路线图采用 200+ 作为提前评审区间，500+ 是必须认真评估分布式路线的大规模场景，不应等到
超过现有容量后才立项。没有高可用需求且并发未进入该区间时，继续使用 `single|sticky`，本轨道
未触发、未排期。

### 11.2 准入与退出

触发后独立规格至少覆盖：

- Redis Pub/Sub 更新广播的消息契约、丢失补偿和断线重连；
- 跨实例连接注册、注销、租约、实例身份和过期清理；
- 同一用户旧连接跨实例取消；
- 集群全局连接上限、每用户上限和原子并发控制；
- Redis 故障、实例扩缩容、滚动发布和 sticky 失效时的降级；
- 与认证、refresh cookie、SSE 重连和限流的兼容回归。

退出证据必须证明多实例下同一用户连接约束、全局上限、事件传播、实例故障恢复、Redis
断连恢复和 batch polling fallback。容量与故障演练必须使用受控测试数据，不记录 token 或行情
明细。

### 11.3 非目标与停止条件

未触发时不引入 Pub/Sub 消费协程或 Redis 连接注册表。触发后若缺少多实例拓扑、容量模型、
故障预算、Redis 运维责任或可验证降级路径，则停止立项。不得把共享更新时间戳描述为完整的
分布式 SSE，也不得在该轨道中迁移 token 或修改 CSP。

## 12. 三个产品候选

### 12.1 P-C1：Trader 交易计划生命周期

现有基础：TraderAgent 已上线。

候选闭环：创建并持久化交易计划，记录计划状态和执行结果，并与来源回测、目标持仓或实际持仓
建立显式可审计关联。

准入：

- 明确目标用户和从创建到复盘的单一主流程；
- 设计计划、状态转换、结果和回测/持仓关联的数据模型；
- 定义 owner 权限、共享边界、审计、保留和删除策略；
- 评估状态并发、失败恢复、迁移和端到端测试成本。

退出：一个用户可完成计划创建、状态更新、结果记录和关联复盘，权限与审计回归通过。

非目标与停止：不重做 TraderAgent，不混入交易执行自动化、CSP、token、分区或 SSE。用户价值、
持久化责任或权限边界不清时不立项。

### 12.2 P-C2：Data Catalog 前端展示

现有基础：Data Catalog 后端与质量上下文已实现。

候选闭环：为授权用户提供只读数据目录，展示数据视图、时间覆盖、质量状态、血缘摘要和可执行
下一步，不暴露私有 owner 数据、原始行情样本或内部诊断。

准入：

- 明确目录可见范围、用户角色和只读 API 契约；
- 固定质量状态、时间覆盖、血缘和错误提示的用户语义；
- 定义缓存、分页、空态、过期状态和性能预算；
- 评估私有数据隔离、可访问性和页面级测试成本。

退出：用户能从目录发现数据、理解质量与覆盖并进入一个合法只读后续动作，权限和降级行为通过。

非目标与停止：不重做 Data Catalog 后端，不在前端展示内部 SQL、凭据、原始 trace 或私有数据。
可见范围或质量语义不能稳定解释时不立项。

### 12.3 P-C3：策略进化实时进度

现有基础：策略进化已有后端 Agent 事件流和日频 walk-forward。

候选闭环：工作台展示单个进化任务的实时阶段、受控进度、可解释结果和失败状态，并在刷新或
断线后恢复。

准入：

- 固定事件类型、顺序、幂等键、终态和版本兼容；
- 定义断线重连、游标或补拉、刷新恢复与重复事件处理；
- 明确任务 owner、可见范围、事件保留和清理策略；
- 评估并发连接、前端状态机、可访问性和端到端测试成本。

退出：一个任务从开始到终态可实时观察，刷新和断线后可恢复，重复或乱序事件不破坏最终状态。

非目标与停止：不重复实现 walk-forward 或后端进化 Agent，不借此启动分布式 SSE。事件契约、
保留或 owner 隔离不明确时不立项。

### 12.4 候选共同规则

每个候选必须单独建立规格，只实现一个完整用户闭环。规格必须引用本路线图，并在实施前核对
用户价值、数据模型、权限、保留策略和测试成本。任何候选不得混入 CSP、认证、生产切换、K 线
分区或 SSE 基础设施变更。

## 13. 全局准入、退出和停止规则

### 13.1 全局准入

所有 Post-R9 事项必须：

- 有独立、已批准且范围单一的规格；
- 引用本路线图中的当前状态、依赖和非生产边界；
- 使用可追溯输入，不把历史 CI 当作生产证据；
- 在规格中固定负责人、回滚、数据边界、测试矩阵和证据保存方式；
- 保持生产报告、Lighthouse 历史、数据库、日志、浏览器产物和敏感数据不进入源码提交。

### 13.2 全局退出

完成状态必须由独立规格的验收证据支持。文档应分别记录本地、CI、目标环境和生产证据，不能
用近似计数、未执行命令或 synthetic 结果替代。生产事项还必须完成发布清单、负责人、回滚和
目标环境 smoke。

### 13.3 全局停止条件

出现以下任一情况立即停止当前事项并保留可审计诊断：

- 可能泄露凭据、用户标识、完整 URL、query、fragment、脚本、DOM 或原始业务数据；
- 门禁输入缺失却准备通过手工标记、合成数据或历史 CI 绕过；
- 未知违规、认证回归、恢复失败或容量证据不可复现；
- 一个规格混入安全主线、生产切换、基础设施轨道和产品功能中的多个所有权边界；
- 自动修改 CSP、自动启用 cookie-only 写请求、自动切换活动表或自动删除冷数据；
- 无明确负责人、回滚点或停止后的恢复路径。

## 14. 当前非目标

在对应门禁和独立规格完成前，当前明确不做：

- 不直接实施 S2 nonce/hash 或修改强制 CSP；
- 不直接实施 S3 内存 token，更不实施 S4 cookie-only 写请求；
- 不把 R9 描述为生产已部署、XSS 风险已关闭或已具备 S2 证据；
- 不执行活动 K 线表切换、冷数据删除或对象存储归档；
- 不实施 Redis Pub/Sub 或跨实例 SSE 连接管理；
- 不重复建设多因子、过滤 DSL、注册表、中性化、增强指标或 walk-forward；
- 不在同一迭代中混合三个产品候选。

## 15. 唯一下一步

当前唯一下一步是为已完成本地实现与验证的 R10 创建最终实现提交并完成远端 Backend CI
复核；最终提交哈希和 CI 链接在真实产生前保持待填。远端门禁通过后，R10 才能声明非生产工程
门禁闭环。

R11 继续受生产操作者、凭据、窗口和发布/回滚负责人门禁约束；在 R11 完整周期证据经 R10
生成 `ready_for_review` 并通过人工评审前不实施 R12，在 R12 稳定退出前不实施 R13。R8、R7
和三个产品候选继续保持未触发或未排期状态。
