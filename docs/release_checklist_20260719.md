# 发布清单（2026-07-19）

> 当前发布治理清单。项目现状以
> [iteration_plan_20260724_follow_up.md](iteration_plan_20260724_follow_up.md)
> 为唯一迭代事实源；本文件只记录发布前后可执行的检查项。

## 1. 发布元数据

- [ ] 发布提交：`<commit>`
- [ ] 发布窗口：`<UTC time>`
- [ ] 变更范围：`<summary>`
- [ ] 回滚负责人：`<owner>`

## 2. 代码与依赖

- [ ] `git status --short` 仅包含预期变更。
- [ ] 后端使用 `python/requirements.lock` 安装，直接依赖与 lock 无漂移。
- [ ] `python -m ruff check .` 通过。
- [ ] `npx tsc --noEmit`、`npm run lint`、`npm run build` 通过。
- [ ] 后端 pytest 失败数为 `0`，跳过项有明确原因。
- [ ] 前端 Vitest 失败数为 `0`。

当前发布候选基线（2026-07-27）：

- 后端：本轮 SQLite `1031 passed, 15 skipped, 0 failed`，全仓 Ruff 通过。
- 前端：Next.js 15.5.22 production build、Vitest `202 passed`、Playwright `40 passed`，
  双路由 Lighthouse 和 `npm audit --omit=dev` 均通过。
- 详细证据见
  [`releases/20260727_r6_release_candidate.md`](releases/20260727_r6_release_candidate.md)；
  该记录仍是隔离环境工程基线，不是生产发布。

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
- [ ] `/health/ready`、`/health/scheduler` 和关键 API smoke 通过。
- [ ] 管理页面和普通用户权限各验证一次。

## 5. 浏览器与性能

- [ ] Frontend CI 的 PostgreSQL/Alembic/backend/Chromium Playwright smoke 通过。
- [ ] 登录、行情中心、品种详情、价位标注、工作区和 metrics smoke 通过。
- [ ] Lighthouse 路由趋势通过并保留 `lighthouse-trend.json`、`lighthouse-history.json` 与
  `latest.json` artifact；确认 commit、route 和 CI run metadata 可读。

当前远程证据：

- [Backend CI #31](https://github.com/jwj911/project_rich_snowball/actions/runs/30234789780)
- [Frontend CI #33](https://github.com/jwj911/project_rich_snowball/actions/runs/30233956592)

两条远程门禁均已成功，详细步骤与 artifact 证据写入对应发布记录。

## 6. 回滚

- [ ] 先停止 worker，再停止 API，保留失败日志和 trace id。
- [ ] 保存发布前数据库备份与 Alembic 版本。
- [ ] 应用回滚只使用已验证的提交；数据库 downgrade 必须在演练环境先验证。
- [ ] 恢复数据库后重新执行 readiness、认证、行情列表和关键页面 smoke。
- [ ] 将事故原因、影响范围、恢复时间和后续行动写入发布记录。
