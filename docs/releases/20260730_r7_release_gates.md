# R7 生产发布门禁工程基线（2026-07-30）

> 类型：`engineering baseline / release candidate`，不是生产发布。
> 对应清单：[`../release_checklist_20260719.md`](../release_checklist_20260719.md)
> SSE 边界：[`../../python/docs/sse_scaling_strategy.md`](../../python/docs/sse_scaling_strategy.md)

## 发布元数据

- R7 主提交：`753a599bab95ffc7205823f445f2b980d3c3e1fc`
- Ruff CI 修复及最终提交：`b6cd75756b960eeba169c92531dbcfc3cd6b706a`
- 应用回滚点：`b04a61ed57e706a80cb417f6a0d967dd43135b9d`
- 变更范围：只读生产发布预检、脱敏诊断报告、worker/API Redis 更新时间戳共享标记、
  Redis 降级有界刷新、生产 SSE 模式门禁和 Backend CI 契约门禁
- 生产发布窗口：未指定
- 发布负责人：未指定
- 回滚负责人：未指定
- 生产发布状态：未部署

## 11 项只读生产预检

`python/scripts/release_preflight.py` 固定执行以下检查：

1. `ENV` 必须为 `production`；
2. `DATABASE_URL` 必须使用 PostgreSQL；
3. `SECRET_KEY` 长度必须不少于 32；
4. CORS 来源必须为显式 HTTPS，且不得包含通配符、localhost 或 loopback；
5. `DATA_SOURCE` 必须显式配置且不得为 `mock`；
6. `REDIS_URL` 必须显式配置；
7. `RELEASE_COMMIT` 必须存在；
8. `RELEASE_WINDOW_UTC` 必须为 UTC 时间点或有效的 UTC 起止区间；
9. `RELEASE_OWNER` 必须存在；
10. `ROLLBACK_OWNER` 必须存在；
11. `SSE_DEPLOYMENT_MODE` 必须为 `single` 或 `sticky`。

每次运行生成独立 `trace_id` 和结构化 JSON，报告只保留检查代码、状态、安全摘要、提交及
时间元数据。原始 `SECRET_KEY`、数据库/Redis 密码、Provider Token 和行情内容不得进入
stdout、stderr、日志或报告。退出码 `0`、`1`、`2` 分别表示通过、门禁失败和报告写入失败。

除写入指定 JSON 报告外，预检不连接或修改数据库、Redis、部署状态及发布清单。本轮没有使用
真实生产凭据执行预检，因此没有可作为生产发布证据的通过报告。

## Worker/API 更新信号

- worker 只在 realtime quotes 成功刷新后调用 `mark_realtime_updated()`；失败刷新不发布标记。
- 本地状态更新后，worker 尽力向 Redis `futures:realtime:update_time` 写入同一个 UTC
  时间戳，标记不包含 symbol、价格或其他行情内容。
- API 读取本地时间与 Redis 共享时间中的较新值，既有 SSE 连接在下一个检查周期据此重新
  查询并推送。
- Redis 未配置、连接失败、运行中断开或标记非法时，SSE 保持服务并使用本地状态；距上次
  查询达到 60 秒时强制刷新，避免无限期停留在初始行情。
- 降级与恢复只记录状态和原因代码，不记录 Redis 连接信息；Redis 恢复后自动重新使用共享
  标记，无需重启 API。

## SSE 部署边界

- 生产环境只接受 `SSE_DEPLOYMENT_MODE=single|sticky`。
- `single` 表示 realtime SSE 只由一个 API 实例承载。
- `sticky` 表示负载均衡必须保证同一用户持续命中同一实例。
- Redis 时间戳标记只解决 worker/API 及多个 API 实例之间的行情更新感知。
- 每用户单连接、实例连接上限和旧连接取消仍由 `_sse_connections` 在实例内管理。
- 本轮未实现 Redis Pub/Sub、跨实例连接注册/注销、集群全局连接上限或跨实例旧连接取消，
  不得将 R7 描述为完整的多实例 SSE 支持。

## 本地验证

- R7 聚焦回归：`106 passed, 0 failed`。
- 补强后的另一轮聚焦回归：`90 passed, 0 failed`。
- 全量后端：`1103 passed, 15 skipped, 0 failed`。
- Ruff check：通过。
- Ruff format check：通过。
- `git diff --check`：通过。
- Compose config：通过。

两轮聚焦回归是不同阶段的验证结果，不相加为单一测试总数。

## 远程门禁

- [Backend CI #33](https://github.com/jwj911/project_rich_snowball/actions/runs/30493521137)
  成功。
- 覆盖步骤：直接依赖锁检查、R7 placeholder preflight、Alembic、PostgreSQL pytest、
  PostgreSQL API smoke、Ruff check/format 和 `pip-audit`。
- CI preflight 使用占位数据库、Redis、CORS、负责人和未来 UTC 窗口，只验证只读 CLI、
  11 项检查及报告契约；它不是生产凭据验证、生产部署验证或生产发布证据。

## 前端证据边界

R7 未修改前端，本轮未重跑 TypeScript、ESLint、build、Vitest、Playwright 或 Lighthouse。
R6 的 Next.js 15.5.22 build、Vitest `202 passed`、Playwright `40 passed`、双路由
Lighthouse 和 Frontend CI 只作为历史证据，详见
[`20260727_r6_release_candidate.md`](20260727_r6_release_candidate.md)。真实生产发布窗口仍需
按发布清单重新验证前端和浏览器路径。

## 回滚

若后续部署 R7 后需要应用回滚，先停止 worker，再停止 API，保留脱敏日志与 `trace_id`，然后
回滚到 `b04a61ed57e706a80cb417f6a0d967dd43135b9d`。R7 未新增数据库迁移；不得为回滚直接
执行未演练的 Alembic downgrade。Redis 更新时间戳标记不包含业务数据，不替代数据库备份。

本轮未部署到真实生产，也未执行真实生产备份/恢复，因此没有生产恢复点可声明。生产发布前必须
创建目标实例备份，在隔离环境验证恢复，并在恢复后重跑 readiness、认证、行情和关键页面
smoke。

## 未完成生产项

以下条件未满足，因此本记录不能表述为生产已发布：

- [ ] 已取得并核验真实生产数据库、Redis、密钥、HTTPS CORS 和真实数据源配置。
- [ ] 已指定生产发布窗口、发布负责人和回滚负责人。
- [ ] 已使用真实生产输入执行 11 项只读预检并归档脱敏 JSON。
- [ ] 已完成真实生产发布前备份及隔离恢复验证。
- [ ] 已在真实生产环境完成迁移、部署、readiness、权限、行情和浏览器 smoke。
- [ ] 若选择 `sticky`，已在负载均衡层验证会话亲和与故障重连。

Redis Pub/Sub 和跨实例连接管理不属于本轮范围；如生产拓扑需要完整多实例 SSE 高可用，应在
后续迭代单独设计、实现和验收。
