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

当前工程基线（2026-08-02）：

- 后端：R8 本地全量 `1157 passed, 18 skipped, 0 failed`，Ruff check/format 与 diff
  check 均通过。新增的 3 个 PostgreSQL 分区专项用例因本机没有隔离 PostgreSQL 而明确
  skip，并已在远程 PostgreSQL 16 门禁中通过。
- 前端：R8 无变更且未重跑。Next.js 15.5.22 production build、Vitest `202 passed`、
  Playwright `40 passed`、双路由 Lighthouse 和 `npm audit --omit=dev` 均为 R6 历史基线。
- 详细证据见
  [`releases/20260802_r8_kline_partition_lifecycle.md`](releases/20260802_r8_kline_partition_lifecycle.md)；
  该记录是 K 线分区生命周期工程基线，不是生产分区或生产发布。

## 3. 数据库与数据

- [ ] PostgreSQL 目标实例可连接，执行 `alembic upgrade head`。
- [ ] Alembic head 为 `c0d1e2f3a4b5`，迁移数量为 61。
- [ ] `fut_main_daily_data` 唯一键为
  `(variety_id, ts_code, period, trade_date)`。
- [ ] Mock、主力日线、具体合约日线和实时快照路径均有可解释结果。
- [ ] 发布前完成逻辑备份；恢复流程参考
  [`python/docs/postgres_backup_runbook.md`](../python/docs/postgres_backup_runbook.md)。
- [ ] 在目标实例执行只读 `kline_storage_preflight.py`，保存脱敏 `trace_id` 报告并确认是否
  达到 1 亿行、100 GiB 或分钟查询 P99 500 ms 阈值。
- [ ] 若需生产分区，先在隔离库使用显式 shadow 表完成迁移演练、资源清理和恢复验证。
- [ ] 活动表切换方案已单独评审，包含停写/追平、权限、sequence、依赖对象、回滚时限和旧表
  保留期；不得直接使用 R8 命令替换 `kline_data`。
- [ ] 冷数据导出、对象存储校验、恢复抽检和删除审批已完成；R8 尚未执行这些生产动作。

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

- [Backend CI #38](https://github.com/jwj911/project_rich_snowball/actions/runs/30732688519)：
  R8 当前成功门禁，专项 `45 passed`，全量 `1174 passed, 1 skipped`，覆盖率 `75.98%`。
- [Backend CI #33](https://github.com/jwj911/project_rich_snowball/actions/runs/30493521137)：
  R7 历史成功门禁。
- [Frontend CI #33](https://github.com/jwj911/project_rich_snowball/actions/runs/30233956592)：
  R6 历史基线，本轮未重跑。

Backend CI #38 覆盖只读容量预检、真实 PostgreSQL 分区路由/迁移演练、影子资源残留断言、
Alembic、全量 pytest/API smoke、Ruff 和 `pip-audit`。远程 CI 不替代真实生产容量、活动表
切换、冷归档、备份恢复或负责人确认。

## 6. 回滚

- [ ] 先停止 worker，再停止 API，保留失败日志和 trace id。
- [ ] 保存发布前数据库备份与 Alembic 版本。
- [ ] 应用回滚只使用已验证的提交；数据库 downgrade 必须在演练环境先验证。
- [ ] 恢复数据库后重新执行 readiness、认证、行情列表和关键页面 smoke。
- [ ] 将事故原因、影响范围、恢复时间和后续行动写入发布记录。
