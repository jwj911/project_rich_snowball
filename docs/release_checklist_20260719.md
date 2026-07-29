# 发布清单（2026-07-19）

> 当前发布治理清单。项目现状以
> [iteration_plan_20260724_follow_up.md](iteration_plan_20260724_follow_up.md)
> 为唯一迭代事实源；本文件只记录发布前后可执行的检查项。

## 1. 发布元数据

- [ ] 发布提交：`<commit>`
- [ ] 发布窗口：`<UTC time>`
- [ ] 变更范围：`<summary>`
- [ ] 发布负责人：`<owner>`
- [ ] 回滚负责人：`<owner>`
- [ ] 使用真实生产输入执行 `python/scripts/release_preflight.py`，11 项检查全部通过。
- [ ] 保存带独立 `trace_id` 的脱敏 JSON 报告；确认报告、stdout/stderr 和日志无原始凭据。

预检是只读门禁，只允许写指定报告文件，不修改数据库、Redis、部署状态或本清单。CI
placeholder preflight 只验证 CLI/报告契约，不能勾选以上生产项。

## 2. 代码与依赖

- [ ] `git status --short` 仅包含预期变更。
- [ ] 后端使用 `python/requirements.lock` 安装，直接依赖与 lock 无漂移。
- [ ] `python -m ruff check .` 通过。
- [ ] `npx tsc --noEmit`、`npm run lint`、`npm run build` 通过。
- [ ] 后端 pytest 失败数为 `0`，跳过项有明确原因。
- [ ] 前端 Vitest 失败数为 `0`。

当前工程基线（2026-07-30）：

- 后端：R7 本地全量 `1103 passed, 15 skipped, 0 failed`；两轮聚焦回归分别为
  `106 passed` 和补强后的 `90 passed`，Ruff check/format、diff check 与 Compose config
  均通过。
- 前端：R7 无变更且未重跑。Next.js 15.5.22 production build、Vitest `202 passed`、
  Playwright `40 passed`、双路由 Lighthouse 和 `npm audit --omit=dev` 均为 R6 历史基线。
- 详细证据见
  [`releases/20260730_r7_release_gates.md`](releases/20260730_r7_release_gates.md)；
  该记录是发布门禁工程基线，不是生产发布。

## 3. 数据库与数据

- [ ] PostgreSQL 目标实例可连接，执行 `alembic upgrade head`。
- [ ] Alembic head 为 `c0d1e2f3a4b5`，迁移数量为 61。
- [ ] `fut_main_daily_data` 唯一键为
  `(variety_id, ts_code, period, trade_date)`。
- [ ] Mock、主力日线、具体合约日线和实时快照路径均有可解释结果。
- [ ] 发布前完成逻辑备份；恢复流程参考
  [`python/docs/postgres_backup_runbook.md`](../python/docs/postgres_backup_runbook.md)。

## 4. 认证、权限与运行拓扑

- [ ] 生产 `SECRET_KEY` 长度至少 32，且未写入仓库。
- [ ] `CORS_ORIGINS` 仅包含实际前端来源。
- [ ] API 使用 `ENABLE_SCHEDULER=0`。
- [ ] 仅一个独立 worker 使用 `ENABLE_SCHEDULER=1`。
- [ ] backend 与 worker 使用相同 `REDIS_URL`，worker 成功刷新后 Redis
  `futures:realtime:update_time` 仅包含 UTC 时间戳。
- [ ] `SSE_DEPLOYMENT_MODE` 明确设置为 `single` 或 `sticky`；`sticky` 的会话亲和已在
  负载均衡层验证。
- [ ] Redis 中断时 SSE 60 秒有界刷新及恢复路径在目标环境验证。
- [ ] `/health/ready`、`/health/scheduler` 和关键 API smoke 通过。
- [ ] 管理页面和普通用户权限各验证一次。

当前 Redis 标记不包含行情内容，只解决 worker/API 更新感知。Redis Pub/Sub、跨实例连接
注册、全局连接上限和跨实例旧连接取消尚未实现，不得把 `single|sticky` 表述为完整的
多实例 SSE 能力。

## 5. 浏览器与性能

- [ ] Frontend CI 的 PostgreSQL/Alembic/backend/Chromium Playwright smoke 通过。
- [ ] 登录、行情中心、品种详情、价位标注、工作区和 metrics smoke 通过。
- [ ] Lighthouse 路由趋势通过并保留 `lighthouse-trend.json`、`lighthouse-history.json` 与
  `latest.json` artifact；确认 commit、route 和 CI run metadata 可读。

当前远程证据：

- [Backend CI #33](https://github.com/jwj911/project_rich_snowball/actions/runs/30493521137)：
  R7 当前成功门禁。
- [Frontend CI #33](https://github.com/jwj911/project_rich_snowball/actions/runs/30233956592)：
  R6 历史基线，本轮未重跑。

Backend CI #33 覆盖依赖锁、R7 placeholder preflight、Alembic、PostgreSQL pytest/API
smoke、Ruff 和 `pip-audit`。远程 CI 不替代真实生产凭据、部署、备份恢复或负责人确认。

## 6. 回滚

- [ ] 先停止 worker，再停止 API，保留失败日志和 trace id。
- [ ] 保存发布前数据库备份与 Alembic 版本。
- [ ] 应用回滚只使用已验证的提交；数据库 downgrade 必须在演练环境先验证。
- [ ] 恢复数据库后重新执行 readiness、认证、行情列表和关键页面 smoke。
- [ ] 将事故原因、影响范围、恢复时间和后续行动写入发布记录。
