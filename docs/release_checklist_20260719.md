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

- 后端：独立审查修复前的 R9 全量为
  `1177 passed, 18 skipped, 0 failed, 103 warnings`；修复后受影响聚焦回归为
  `85 passed, 1 skipped, 0 failed`，Ruff check/format 通过。唯一 skip 是新增 PostgreSQL
  持久化专项，待 Backend CI 的 PostgreSQL 16 环境执行；修复后的完整全量由 CI 复核。
- 前端：审查增强前的基础版 R9 Playwright 为 `3 passed`。增加并发 401 单飞刷新和 SSE
  首次断线重连后，增强版已通过 Playwright `--list`、TypeScript 与 ESLint，实际浏览器
  执行待 Frontend CI；不得将基础版结果表述为增强版已在本地通过。
- `git diff --check` 通过。R9 本地实现提交为
  `723ba9b949bccf7c96798d2f45388731350eacd3`；最终验证提交及 Backend/Frontend CI
  链接待补/待验证。
- 详细证据见
  [`releases/20260802_r9_csp_report_only_observability.md`](releases/20260802_r9_csp_report_only_observability.md)；
  该记录是 CSP Report-Only 非生产工程基线，不是强制 CSP 收紧或生产发布。

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
- [ ] `CSP_REPORT_SAMPLE_RATE` 已按目标流量配置为 `[0, 1]` 内有限数，并记录变更原因。
- [ ] `CSP_REPORT_URL` 未设置或为受控的绝对 HTTP(S) URL，不含凭据、query、fragment。
- [ ] 页面同时返回强制 CSP 和 Report-Only CSP，且强制 CSP 原值未变化。
- [ ] CSP 报告端点的 8 KiB、20 条批量、采样、`report:csp` IP 限流和脱敏边界在目标环境
  验证。
- [ ] `csp_reports_total{outcome="persist_failed"}` 在 5 分钟窗口内大于 0 时立即告警；
  `rejected` / `rate_limited` 异常比例和 `accepted` / 业务 HTTP 流量对比已接入看板。

当前 Redis 标记不包含行情内容，只解决 worker/API 更新感知。Redis Pub/Sub、跨实例连接
注册、全局连接上限和跨实例旧连接取消尚未实现，不得把 `single|sticky` 表述为完整的
多实例 SSE 能力。

## 5. 浏览器与性能

- [ ] Frontend CI 的 PostgreSQL/Alembic/backend/Chromium Playwright smoke 通过。
- [ ] R9 双 CSP 头、legacy/Reporting API 接收、登录刷新、SSE、Bearer 写请求与
  cookie-only 写请求拒绝通过本次 Frontend CI 验证。
- [ ] 登录、行情中心、品种详情、价位标注、工作区和 metrics smoke 通过。
- [ ] Lighthouse 路由趋势通过并保留 `lighthouse-trend.json`、`lighthouse-history.json` 与
  `latest.json` artifact；确认 commit、route 和 CI run metadata 可读。

当前远程证据：

- R9 Backend CI：待本轮推送后补记/待验证，链接待补；需执行新增 PostgreSQL 专项并复核
  审查修复后的完整后端全量。
- R9 Frontend CI：待本轮推送后补记/待验证，链接待补；增强版及完整 Playwright 结果以该
  workflow 的实际浏览器步骤为准。
- [Backend CI #38](https://github.com/jwj911/project_rich_snowball/actions/runs/30732688519)：
  R8 历史成功门禁，专项 `45 passed`，全量 `1174 passed, 1 skipped`，覆盖率 `75.98%`。
- [Backend CI #33](https://github.com/jwj911/project_rich_snowball/actions/runs/30493521137)：
  R7 历史成功门禁。
- [Frontend CI #33](https://github.com/jwj911/project_rich_snowball/actions/runs/30233956592)：
  R6 历史基线，本轮未重跑。

Backend CI #38 覆盖只读容量预检、真实 PostgreSQL 分区路由/迁移演练、影子资源残留断言、
Alembic、全量 pytest/API smoke、Ruff 和 `pip-audit`。远程 CI 不替代真实生产容量、活动表
切换、冷归档、备份恢复或负责人确认。

本地和 CI synthetic CSP 报告只验证契约，不构成生产 SLO。只有取得并归类真实完整业务周期
报告后，才允许启动 S2 专项评审；在此之前不得移除强制 CSP 的 `unsafe-inline` /
`unsafe-eval`。

## 6. 回滚

- [ ] 先停止 worker，再停止 API，保留失败日志和 trace id。
- [ ] 保存发布前数据库备份与 Alembic 版本。
- [ ] 应用回滚只使用已验证的提交；数据库 downgrade 必须在演练环境先验证。
- [ ] R9 应用回滚点为启动文档提交
  `756ca605613ba2a4f76919e913e1264e3f9d2a1b`；回滚后重新检查强制 CSP、登录、SSE 与
  Bearer 写请求。
- [ ] 恢复数据库后重新执行 readiness、认证、行情列表和关键页面 smoke。
- [ ] 将事故原因、影响范围、恢复时间和后续行动写入发布记录。
