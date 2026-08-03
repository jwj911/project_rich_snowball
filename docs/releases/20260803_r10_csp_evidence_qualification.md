# R10 CSP 证据归类与 S2 准入报告工程基线（2026-08-03）

> 类型：`non-production engineering baseline`，不是生产发布或 S2 批准。
> 当前状态：本地实现与验证完成；远端 Backend CI 待验证（`CI pending`）。
> 对应规格：
> [`classify-csp-evidence-readiness`](../../.trae/specs/classify-csp-evidence-readiness/spec.md)
> 对应清单：[`../release_checklist_20260719.md`](../release_checklist_20260719.md)
> 当前路线图：
> [`../iteration_plan_20260802_post_r9.md`](../iteration_plan_20260802_post_r9.md)

## 发布元数据

- Post-R9 基线及暂定应用回滚点：
  `b8f92f1d87a8dfe2304ba7dd621ed5d031d77672`
- R10 最终实现提交：待填；当前尚未创建提交，不得推断或虚构哈希
- Backend CI：待验证；当前没有可记录的 R10 CI 运行链接
- 变更范围：可信 CSP environment/release 归属、有界只读证据归类、脱敏准入 JSON、安全离线
  CLI、定向测试和 Backend CI 契约门禁
- 生产发布窗口：未指定
- 发布负责人：未指定
- 回滚负责人：未指定
- 生产状态：未部署

## 已交付能力

- 新 CSP 记录可由服务端受控配置写入 environment 和完整 40 位 Git `RELEASE_COMMIT`；
  客户端字段不能覆盖，旧记录不回填、不重写；
- `chrome-extension` / `moz-extension` blocked URL 只持久化为固定
  `browser-extension` 类别；
- 后端证据服务只读取 `frontend_logs` 的
  `id/payload_json/environment/release/created_at`，按固定路由、directive 和 blocked source
  类别聚合；
- PostgreSQL 使用 read-only transaction 和 statement timeout，SQLite 使用
  `PRAGMA query_only=ON`；
- 离线 CLI 显式要求 database/context/catalog/report 输入，在查询前校验输入和仓库外报告
  路径，并以同目录临时文件和原子 replace 写入报告；
- 报告只保留独立报告 `trace_id`、受控 scope、低基数分类、计数、限额和稳定问题码，不输出
  完整 URL、origin、记录 trace、用户信息、原始 User-Agent、payload、数据库 URL 或路径。

## 固定限额

| 项目 | 限额 |
|---|---:|
| context 文件 | 64 KiB |
| catalog 文件 | 64 KiB |
| 单次 UTC 窗口 | 31 天 |
| 扫描记录 | 50,000 行 |
| keyset page | 500 行 |
| 聚合组 | 500 组 |
| catalog 条目 | 500 条 |
| expected origins | 20 个 |
| trusted origins | 20 个 |
| 运行时间 | 30 秒 |
| PostgreSQL statement timeout | 30,000 ms |
| JSON 报告 | 256 KiB |
| 单条 R9 payload 二次校验 | 8 KiB |

达到行数、聚合组或运行时上限时必须标记截断并返回 `insufficient_evidence`，不能将已读取前缀或
零记录解释为无违规。

## 状态与退出码

| 退出码 | 状态 | 含义 |
|---:|---|---|
| `0` | `ready_for_review` | 仅可发起人工 S2 专项评审 |
| `1` | `insufficient_evidence` | synthetic、非生产、周期/流程/指标/归属不足或截断 |
| `2` | `blocked` | 非法/敏感记录、未知分类、目录未闭环、计数不一致或持久化失败 |
| `3` | `failed` | 查询、解析基础设施或报告构建失败 |
| `4` | `report_write_failed` | 报告原子写入失败 |

状态优先级为 `failed`、`blocked`、`insufficient_evidence`、`ready_for_review`。
`ready_for_review` 也不表示 S2 已批准，更不会自动修改 CSP。

## 本地验证

- 聚焦 pytest：`375 passed, 5 skipped, 1 warning`；
- 后端全量 pytest：`1421 passed, 22 skipped, 103 warnings`；
- 本地 PostgreSQL 不可用，3 个 PostgreSQL 专项明确 skip；这些专项仍需远端 PostgreSQL CI
  验证，SQLite 结果不替代 PostgreSQL 证据；
- Ruff：通过；
- `git diff --check`：通过；
- 安全检查：通过；
- synthetic CLI：按契约返回退出码 `1`，状态为 `insufficient_evidence`，安全报告大小为
  `1707 B`；
- synthetic 报告只验证 CLI、状态机和脱敏契约，不是生产 SLO、真实违规率、生产部署证据或
  S2 准入证据。

本地验证没有生成生产 context、catalog 或 report。包含用户数据的 `python/dev.db` 已保留，
未作为测试数据库清理或纳入本次发布记录。

## 远端与生产状态

- R10 Backend CI 尚未运行或尚未形成可记录的成功证据，状态保持 `pending`；
- 不记录虚构的 CI URL、运行号或实现提交；
- R11 生产操作者门禁尚未启动，生产凭据、窗口、发布负责人和回滚负责人均未确认；
- 未覆盖真实目标环境完整业务周期，未生成生产 context、catalog 或 report；
- R12/S2 nonce/hash 与 `script-src` 收紧未启动；
- R13/S3 内存 access token 迁移未启动；
- R8 生产分区/冷归档与 R7 分布式 SSE 条件轨道继续保持未触发。

## 未改变边界

R10 没有新增管理员 HTTP API、数据库表或 Alembic 迁移，也没有回填既有 CSP 记录。强制
`Content-Security-Policy` 和 `Content-Security-Policy-Report-Only` 策略未改变。
`localStorage['futures_access_token']`、HttpOnly access/refresh cookie、Bearer 写请求和
cookie-only 写请求拒绝边界均保持 R9 基线。

## 回滚

在 R10 最终实现提交产生前，暂定应用回滚点为 Post-R9 提交
`b8f92f1d87a8dfe2304ba7dd621ed5d031d77672`。最终实现提交创建后应补记真实哈希，并继续保留
该提交作为回退到 Post-R9 状态的基点。

R10 无数据库迁移，回滚不需要 Alembic downgrade，也不得删除既有 `frontend_logs`、
脱敏 CSP 记录或 `python/dev.db`。回滚后应重新确认：

1. R9 强制 CSP 与 Report-Only 响应头保持原值；
2. CSP 报告接收、8 KiB、20 条批量、采样、限流和脱敏契约正常；
3. 登录、刷新、退出和 SSE 正常；
4. Bearer 写请求成功，cookie-only 写请求继续拒绝。

## 执行清单

- [x] R10 本地实现完成。
- [x] R10 聚焦与全量本地验证完成。
- [x] synthetic CLI 安全报告为 `1707 B` 且正确返回退出码 `1`。
- [x] Ruff、diff 和安全检查通过。
- [x] 生产 context、catalog 和 report 未生成。
- [x] `python/dev.db` 已保留。
- [ ] R10 最终实现提交已创建并补记。
- [ ] Backend CI 在 PostgreSQL 环境通过并补记真实链接。
- [ ] R11 operator gate、生产窗口和责任人已满足。
- [ ] 真实完整业务周期已覆盖并生成生产 R10 报告。
- [ ] 生产报告达到 `ready_for_review` 并通过人工 S2 专项评审。
- [ ] R12/S2 已启动。
- [ ] R13/S3 已启动。

## 非生产边界

R10 当前只是一项本地实现与验证完成、远端 CI 待验证的 evidence-only 非生产工程基线。它没有
部署 R9/R10，没有生成生产事实文件，没有关闭强制 CSP 中的 `unsafe-inline` /
`unsafe-eval`，也没有关闭 `localStorage` access token 风险。下一工程门禁是完成真实 R10
提交和远端 Backend CI；下一生产门禁仍是 R11 operator gate。
