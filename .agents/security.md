<!-- .agents/security.md — 安全注意事项 -->

## 生产环境强制要求

- `SECRET_KEY` 长度 >= 32
- 必须使用 PostgreSQL（禁止 SQLite）
- `CORS_ORIGINS` 必填，禁止 `*`、禁止 `http://`、禁止 localhost/127.0.0.1
- `/docs`、`/redoc`、`/openapi.json` 在生产环境应关闭

## 认证与鉴权

- 密码：必须使用 `utils.hash_password()`（bcrypt），禁止明文、MD5、SHA256。
- JWT：解码必须捕获 PyJWT 异常，禁止裸 `except:`。
- CORS：`allow_credentials=True`，因此生产环境不允许通配符 origin。
- CSRF 防护（2026-05-29）：`dependencies.py` 方法感知鉴权，POST/PUT/PATCH/DELETE 必须携带 `Authorization: Bearer` header，不接受 `access_token` cookie 回退；GET/HEAD 保持兼容。
- refresh token 仅通过 HttpOnly cookie 轮换；每次 refresh 必须同步轮换 SSE/read-only 兼容所需的
  HttpOnly access cookie，logout 必须清理两者。
- access token 当前仍保存于 localStorage 以支持写请求的 Bearer header。cookie-only 写请求需要
  独立验证 CSRF token/origin、防重放、SSE 和跨域边界，未完成前不得改变 Bearer 要求。
- R9 不迁移 token：S1 已增加 CSP Report-Only 观测，但 `localStorage`、HttpOnly
  access/refresh cookie、Bearer 写请求和 CSRF 拒绝 cookie-only 写请求的边界不变。内存
  access token 属于后续 S3。

## XSS 与输入安全

- 评论内容通过 Pydantic validator + `html.escape()` 过滤，长度限制在 schema 中维护。
- 交易观点 `reason` 字段应与评论一致，使用 `html.escape()` 或等价 sanitize，防止 XSS。
- 前端日志：`POST /api/log/frontend` 必须鉴权并忽略客户端传入的 `user_id`；需限制 payload 大小、深度与 key 数量，防止日志注入与存储滥用。

## 内容安全与 SSRF

- CSP：强制 `Content-Security-Policy` 继续允许 `unsafe-eval` 和 `unsafe-inline`，R9
  保持其原值不变；新增的 Report-Only 候选策略仅将 `script-src` 收紧到 `'self'`，并通过
  `report-uri`、`report-to` 和 `Reporting-Endpoints` 上报，不阻断页面执行。
- `POST /api/log/csp-report` 是浏览器匿名上报端点，只接受 `application/csp-report` 和
  `application/reports+json`。请求体最大 8 KiB，Reporting API 每批最多 20 条；使用
  `report:csp` 独立 action 按客户端 IP 限流，每 60 秒最多 60 次，Redis 优先、内存降级。
- `CSP_REPORT_SAMPLE_RATE` 必须是 `[0, 1]` 内有限数，默认 `1`；采样发生在结构校验和 URL
  规范化之后、持久化之前。`CSP_REPORT_URL` 只能是无凭据、query、fragment 的绝对
  HTTP(S) URL，未设置时从受控 API origin 生成。
- document URL、blocked URL、source file 和 referrer 在持久化前移除 userinfo、query 与
  fragment；sample、脚本片段、DOM 内容、Cookie、Authorization、原始请求体和未知字段
  一律丢弃。
- 每条持久化 CSP 报告使用独立 `trace_id`；失败日志只包含 `trace_id`、异常类型和安全计数。
  指标只使用 `csp_reports_total{outcome}` 固定低基数标签，不得加入完整 URL、用户标识、
  原始 directive 或 `trace_id`。
- 完整业务周期的真实报告未归类前，禁止移除强制策略中的 `unsafe-inline` 或
  `unsafe-eval`。本地和 CI 合成报告不构成生产 SLO、XSS 风险关闭或 S2 准入证据。
- R9 本地实现提交为 `723ba9b949bccf7c96798d2f45388731350eacd3`；最终验证提交及
  Backend/Frontend CI 证据仍待补，不得将本地实现状态表述为远端或生产验收完成。
- RSS/新闻源：添加外部 RSS URL 时必须校验协议与主机（拒绝 private/local/link-local/file 等危险目标），抓取时设置显式超时，防止 SSRF 与 worker 阻塞。
- admin 手动触发抓取接口（`/api/news/fetch`、`/api/news/sources/{id}/fetch`）已通过 `BackgroundTasks` 后台化，不再阻塞 HTTP 请求。

## 资源与限流

- Metrics：`/metrics` 端点限制为可信内网 IP，外网返回 403。
- 实时行情批量：`/api/realtime/batch` 应对 symbol 数量做上限控制（建议 ≤50/100），避免超大数据库查询。
- 登录/注册限流：当前使用 Redis 优先 + 内存降级的 `check_rate_limit`，action key 独立为 `auth:register` / `auth:login`。
- CSP 报告限流 action 固定为 `report:csp`，不得与登录、注册或全局写入限流共用计数。

## 部署安全

- SSE 不原生水平扩展：`_sse_connections` 为进程内内存，多实例部署需 sticky session 或 Redis pub/sub，详见 `python/docs/sse_scaling_strategy.md`。
- 生产环境 scheduler：`ENABLE_SCHEDULER=1` 仅作本地便利；生产应运行独立 `python/worker.py`，避免 API 进程混入定时任务。
- API 版本路径：新接口优先在 `/api/v1/*` 下实现；`ApiVersionMiddleware` 会自动把 `/api/v1/*` 映射到 `/api/*`，未版本化路径仍兼容但将逐步废弃。

完整的 token/CSP 阶段、验收与停止条件见
[`docs/r5_frontend_quality_observability.md`](../docs/r5_frontend_quality_observability.md)。
