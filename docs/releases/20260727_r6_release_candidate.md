# R6 发布候选基线（2026-07-27）

> 类型：`engineering baseline / release candidate`，不是生产发布。
> 对应清单：[`../release_checklist_20260719.md`](../release_checklist_20260719.md)

## 发布元数据

- 候选提交：`c5e1a545544e602c24f2e31ca256c37a7511b8ef`
- 验证窗口：2026-07-26 15:40 UTC 至 2026-07-27 03:40 UTC
- 变更范围：R3-R5 发布候选验证、scheduler/Compose 加固、Next.js 安全升级、CI 稳定性修复
- 回滚负责人：未指定
- 生产发布状态：未部署

## 代码与依赖

- [x] 候选代码已推送至 `origin/master`。
- [x] `requirements.lock` 的 26 个直接依赖无缺失。
- [x] `python -m ruff check .` 通过。
- [x] 后端全量回归：`1031 passed, 15 skipped, 0 failed`。
- [x] `npm ci`、TypeScript、ESLint 和 production build 通过。
- [x] Vitest：34 个文件、`202 passed, 0 failed`。
- [x] `npm audit --omit=dev`：`0 vulnerabilities`。
- [ ] 本地 `pip-audit` 通过。当前 Windows 进程异常申请 5 GiB 内存后失败。
- [x] Backend CI #31 使用同一 `requirements.lock` 完成 `pip-audit`。

前端依赖从 Next.js 14.2.35 升级至维护中的 15.5.22，并将
`@next/bundle-analyzer`、`eslint-config-next` 对齐至相同版本。Next 内嵌依赖通过 lock
override 固定为 PostCSS 8.5.23 和 sharp 0.35.3；生产依赖审计为 0。动态路由改用
`useParams()`，根布局直接使用已有的客户端 Toaster 边界。

## 数据库与恢复演练

- [x] 隔离候选库 `r6_candidate_20260726_2345` 从空库迁移到
  Alembic head `c0d1e2f3a4b5`。
- [x] `fut_main_daily_data` 目标唯一索引与 `agent_market_panel_daily` 表存在。
- [x] `pg_dump -Fc` 逻辑备份完成，大小 290,995 bytes，SHA-256 为
  `4f392f66dc8e83cd62a9c1eabc649125d1012a7c648f7de3cff24f706f7dc348`。
- [x] 隔离恢复库 `r6_restore_20260726_2345` 恢复成功，Alembic head 与核心表计数一致。
- [x] 证据记录完成后已删除候选库、恢复库和容器内临时 dump。
- [ ] 真实生产实例迁移、发布前备份与恢复验证完成。

源库与恢复库在恢复时的核心计数均为：users=3、varieties=10、comments=5；
news、opinions、price levels、trade records 和 watchlists 均为 0。

## 认证、权限与运行拓扑

- [x] `/health/ready` 返回 200，`ready=true`。
- [x] `/health/scheduler` 确认 API 的 scheduler 已禁用且未运行。
- [x] 行情列表返回 10 个品种，`/api/realtime/AU` 返回 200。
- [x] 普通用户访问运营指标返回 403，管理员访问返回 200。
- [x] CI 使用的 PostgreSQL TestClient smoke 在候选库原样通过。
- [x] PostgreSQL 用户序列前移后，Mock 用户 ID 为 3/4/5 时启动、登录和评论外键仍通过。
- [x] Compose 回归确认 API 使用 `ENABLE_SCHEDULER=0`，仅 worker 使用
  `ENABLE_SCHEDULER=1`。
- [x] scheduler 使用 APScheduler 支持的 `shutdown(wait=True)` 契约，并可重复停止。
- [x] Compose 强制部署方提供 `SECRET_KEY`、`CORS_ORIGINS` 和 `DATA_SOURCE`。
- [ ] 真实生产 `SECRET_KEY` 长度、生产 CORS 来源和真实数据源已核验。

## 浏览器与性能

- [x] Next.js 15.5.22 production build 完成；最大 First Load JS 为 157 kB，低于 180 kB。
- [x] Playwright：`40 passed, 0 failed`，覆盖认证、行情、详情失败态、写操作和 metrics。
- [x] Lighthouse `home` 中位样本：97 分，LCP 2682 ms，TBT 49 ms，CLS 0。
- [x] Lighthouse `products` 中位样本：96 分，LCP 2689 ms，TBT 57 ms，CLS 0。
- [x] 每条路由保留 3 个原始样本，以 LCP 中位样本执行阈值和趋势判断。
- [x] 本地运行的提交和 CI run 字段按设计为空；CI provenance 单测与 Frontend CI
  artifact 生成均通过。

## 远程门禁

- [x] [Backend CI #31](https://github.com/jwj911/project_rich_snowball/actions/runs/30234789780)
  成功，覆盖迁移、全量 pytest、PostgreSQL API smoke、Ruff 和 `pip-audit`。
- [x] [Frontend CI #33](https://github.com/jwj911/project_rich_snowball/actions/runs/30233956592)
  成功，覆盖 build、Playwright、Vitest 和 Lighthouse。
- [x] Lighthouse 趋势 artifact 已生成，大小 5.42 KB，SHA-256 为
  `310b05b84673bf795c36e8a66942773a8033d321e09f38f0644dc89fbb96852b`。

## 回滚与阻塞项

应用回滚点为 R3-R5 基线提交 `20f2dc277606cd4d97aaf5189071e2150775dea6`。数据库
回滚优先恢复本次逻辑备份，不在生产实例直接执行未演练的 Alembic downgrade。

以下条件未满足，因此本记录不能表述为生产已发布：

- [ ] 已指定发布窗口和回滚负责人。
- [ ] 已取得并核验真实生产凭据、HTTPS CORS 来源和真实 `DATA_SOURCE`。
- [ ] 已在真实生产环境执行迁移、备份、部署和恢复后 smoke。
- [ ] 已确认生产 SSE 多实例采用 sticky session 或 Redis pub/sub。
