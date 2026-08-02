# R9 CSP Report-Only 观测工程基线（2026-08-02）

> 类型：待远端闭环的 `engineering baseline`，不是生产发布或强制 CSP 收紧。
> 当前状态：本地实现、审查修复后聚焦回归与前端静态检查完成；增强版浏览器执行、远端 CI、
> 生产部署和完整业务周期观测待完成。
> 对应规格：
> [`add-csp-reporting-observability`](../../.trae/specs/add-csp-reporting-observability/spec.md)
> 对应清单：[`../release_checklist_20260719.md`](../release_checklist_20260719.md)
> 安全阶段：[`../r5_frontend_quality_observability.md`](../r5_frontend_quality_observability.md)

## 发布元数据

- R9 启动文档提交：`756ca605613ba2a4f76919e913e1264e3f9d2a1b`
- R9 本地实现提交：`723ba9b949bccf7c96798d2f45388731350eacd3`
- R9 最终验证提交：待本轮推送后补记/待验证
- 应用回滚点：`756ca605613ba2a4f76919e913e1264e3f9d2a1b`
- Backend CI：待本轮推送后补记/待验证，链接待补
- Frontend CI：待本轮推送后补记/待验证，链接待补
- 变更范围：双 CSP 响应头、安全报告接收、采样、限流、脱敏、`trace_id`、低基数指标、
  后端/前端/浏览器回归和 CI 门禁
- 生产发布窗口：未指定
- 发布负责人：未指定
- 回滚负责人：未指定
- 生产状态：未部署

## 已交付能力

### 双 CSP 响应头

- 保留既有 `Content-Security-Policy` 原值，包括兼容 Next.js 与图表运行时的
  `script-src 'self' 'unsafe-eval' 'unsafe-inline'`；
- 新增 `Content-Security-Policy-Report-Only`，候选 `script-src` 仅允许 `'self'`；
- 新增 `report-uri`、`report-to` 与 `Reporting-Endpoints`，报告地址来自受控配置；
- Report-Only 违规只上报，不阻断登录、刷新、退出、SSE、详情页面或写请求。

R9 没有移除强制策略中的 `unsafe-inline` / `unsafe-eval`，不得描述为 nonce/hash 强制 CSP
已经启用。

### 安全报告接收

- `POST /api/log/csp-report` 兼容 `application/csp-report` 与
  `application/reports+json`；
- 请求体最大 8 KiB，Reporting API 每批最多 20 条；
- 只接收 CSP violation 和允许字段，未知字段不原样持久化；
- 使用 `report:csp` 独立 action 按客户端 IP 限流，每 60 秒最多 60 次，Redis 优先、内存
  降级；
- `CSP_REPORT_SAMPLE_RATE` 必须为 `[0, 1]` 内有限数，默认 `1`；
- 每条持久化报告生成独立 `trace_id`，复用现有 `FrontendLogDB`，`log_type` 为
  `csp-violation`；
- 响应只返回 `accepted`、`sampled`、`persist_failed` 安全计数，不回显报告内容。

### 脱敏与认证边界

- document URL、blocked URL、source file 和 referrer 移除 userinfo、query 与 fragment，
  并执行 scheme、host、path 和长度限制；
- sample、脚本片段、DOM 内容、Cookie、Authorization、原始请求体和未知字段不落库、不写
  日志；
- 持久化失败回滚事务，日志只记录 `trace_id`、异常类型和安全计数，不记录异常原文；
- `localStorage['futures_access_token']` 继续为写请求提供 Bearer token；
- HttpOnly access cookie 继续服务 SSE 和兼容只读请求，refresh cookie 继续负责轮换；
- POST/PUT/PATCH/DELETE 仍拒绝 cookie-only 写请求。

## 配置

| 变量 | 默认值 | 约束 |
|---|---|---|
| `CSP_REPORT_SAMPLE_RATE` | `1` | `[0, 1]` 内有限数；`0` 全部采样丢弃，`1` 全部进入持久化尝试 |
| `CSP_REPORT_URL` | API origin + `/api/log/csp-report` | 可选；无凭据、query、fragment 的绝对 HTTP(S) URL |
| `NEXT_PUBLIC_API_BASE` | `http://127.0.0.1:8401` | 用于默认报告地址和前端 API 来源 |

生产调整采样率前必须记录流量依据和回退值。采样率只控制通过校验的报告，不替代 8 KiB、批量、
限流或脱敏边界。

## 指标与告警输入

实际指标为 `csp_reports_total{outcome}`，固定 outcome：

- `received`
- `accepted`
- `sampled`
- `rejected`
- `rate_limited`
- `persist_failed`

持久化失败应立即告警：

```promql
increase(csp_reports_total{outcome="persist_failed"}[5m]) > 0
```

拒绝或限流异常上升可先使用以下 15 分钟规则，取得真实业务基线后再调整初始阈值：

```promql
(
  sum(increase(csp_reports_total{outcome=~"rejected|rate_limited"}[15m]))
  /
  clamp_min(sum(increase(csp_reports_total{outcome="received"}[15m])), 1)
  > 0.10
)
and
sum(increase(csp_reports_total{outcome="received"}[15m])) > 20
```

接受量必须与实际业务 HTTP 流量同窗对比：

```promql
sum(increase(csp_reports_total{outcome="accepted"}[30m]))
/
clamp_min(
  sum(increase(http_requests_total{endpoint!="/api/log/csp-report"}[30m])),
  1
)
```

`accepted` 突增需要结合部署、页面流量和 directive 归类排查。CI 和本地 synthetic 报告只验证
接收契约，不是生产 SLO、真实违规率或 S2 准入证据。`accepted` 按报告条目计数，
`http_requests_total` 按 HTTP 请求计数，Reporting API 批量会使二者不具备一一对应关系，
因此该比值只用于同部署、同窗口的趋势对比。完整运维说明见
[`.agents/operations.md`](../../.agents/operations.md)。

## 本地验证

独立审查前的验证：

- 后端 CSP 定向测试：`20 passed`；
- 后端全量：`1177 passed, 18 skipped, 0 failed, 103 warnings`；
- 前端 CSP 配置测试：`21 passed`；
- 前端全量 Vitest：`35 files / 223 passed`；
- production build：通过，最大 First Load JS `157 kB`；
- 基础版 R9 Playwright：`3 passed`，覆盖双头、两种 synthetic 报告、登录、刷新恢复、退出、
  SSE、Bearer 写请求和 cookie-only 写请求拒绝。

独立审查修复后的验证：

- 受影响后端聚焦回归：`85 passed, 1 skipped, 0 failed`；
- 唯一 skip 是新增 PostgreSQL CSP 持久化专项，本地无隔离 PostgreSQL，待 Backend CI 的
  PostgreSQL 16 环境执行；
- Ruff check 与 format check：通过；
- 增强版增加并发 401 单飞刷新和 SSE 首次断线重连，Playwright `--list`、TypeScript 与
  ESLint：通过；
- 增强版 Playwright 实际浏览器执行：未在本地运行，待 Frontend CI；
- `git diff --check`：通过。

审查修复后的完整后端全量未在本地重跑，由 Backend CI 复核。基础版 `3 passed` 不代表增强版
已在本地通过。本次文档维护没有重新运行代码测试、构建或 CI。

## 远程门禁

- Backend CI 已加入 R9 CSP 接收契约定向步骤；
- Frontend CI 已加入双 CSP 响应头门禁和 R9 认证/刷新/SSE/Bearer 浏览器定向步骤；
- Backend CI 需执行新增 PostgreSQL CSP 持久化专项，并复核审查修复后的完整后端全量；
- Frontend CI 需实际执行并发 401 单飞刷新、SSE 首次断线重连增强版与完整 Chromium
  Playwright smoke，不以基础版 R9 `3 passed` 替代增强版或全量浏览器验证；
- 当前代码尚未在本轮推送，因此 Backend CI 与 Frontend CI 均未执行；
- CI 链接、运行编号和最终结果必须在推送后补记，失败时不得把本记录改写为已通过。

## 回滚

R9 没有新增 Alembic 迁移。应用回滚时停止前端和 API，保留脱敏指标、日志及 `trace_id`，
回滚到 `756ca605613ba2a4f76919e913e1264e3f9d2a1b`，然后重新验证：

1. 页面只保留回滚点已有的强制 CSP；
2. 登录、刷新、退出和 SSE 可用；
3. Bearer 写请求成功，cookie-only 写请求继续被拒绝；
4. readiness 和关键页面 smoke 通过。

既有 `frontend_logs` 中的脱敏 `csp-violation` 记录使用现有表结构，回滚不应自动删除。需要清理
时必须按数据保留策略和 `trace_id` 审计执行。

## 待完成项

- [ ] R9 本地实现提交 `723ba9b949bccf7c96798d2f45388731350eacd3` 已推送。
- [ ] R9 最终验证提交已推送并补记完整哈希。
- [ ] Backend CI 成功并补记可追溯链接。
- [ ] Frontend CI 成功并补记可追溯链接，完整 Playwright 全量步骤通过。
- [ ] 在真实业务环境覆盖完整业务周期采集 Report-Only 报告。
- [ ] 已按 directive、页面、浏览器和版本归类全部已知违规。
- [ ] 已建立生产流量基线并调整 `rejected` / `rate_limited` 告警阈值。
- [ ] 已指定生产窗口、发布负责人和回滚负责人。
- [ ] S2 nonce/hash 强制 CSP 已另立规格并通过专项评审。
- [ ] S3 内存 access token 已另立规格并通过认证、CSRF、刷新与 SSE 专项评审。

## 非生产边界

R9 是本地实现且审查后聚焦/静态检查已通过、增强版浏览器与远端待验证的非生产工程基线，
不是生产发布。真实完整业务周期报告未归类前不得进入 S2。R8 也继续保持非生产边界：活动
`kline_data` 未切换，冷数据未导出或删除，生产备份恢复未执行。R9 不改变这些事实。
