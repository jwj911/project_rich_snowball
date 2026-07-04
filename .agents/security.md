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

## XSS 与输入安全

- 评论内容通过 Pydantic validator + `html.escape()` 过滤，长度限制在 schema 中维护。
- 交易观点 `reason` 字段应与评论一致，使用 `html.escape()` 或等价 sanitize，防止 XSS。
- 前端日志：`POST /api/log/frontend` 必须鉴权并忽略客户端传入的 `user_id`；需限制 payload 大小、深度与 key 数量，防止日志注入与存储滥用。

## 内容安全与 SSRF

- CSP：前端有 Content-Security-Policy 响应头，但当前允许 `unsafe-eval` 和 `unsafe-inline`（为兼容 lightweight-charts 和 Next.js）。
- RSS/新闻源：添加外部 RSS URL 时必须校验协议与主机（拒绝 private/local/link-local/file 等危险目标），抓取时设置显式超时，防止 SSRF 与 worker 阻塞。
- admin 手动触发抓取接口（`/api/news/fetch`、`/api/news/sources/{id}/fetch`）已通过 `BackgroundTasks` 后台化，不再阻塞 HTTP 请求。

## 资源与限流

- Metrics：`/metrics` 端点限制为可信内网 IP，外网返回 403。
- 实时行情批量：`/api/realtime/batch` 应对 symbol 数量做上限控制（建议 ≤50/100），避免超大数据库查询。
- 登录/注册限流：当前使用 Redis 优先 + 内存降级的 `check_rate_limit`，action key 独立为 `auth:register` / `auth:login`。

## 部署安全

- SSE 不原生水平扩展：`_sse_connections` 为进程内内存，多实例部署需 sticky session 或 Redis pub/sub，详见 `python/docs/sse_scaling_strategy.md`。
- 生产环境 scheduler：`ENABLE_SCHEDULER=1` 仅作本地便利；生产应运行独立 `python/worker.py`，避免 API 进程混入定时任务。
- API 版本路径：新接口优先在 `/api/v1/*` 下实现；`ApiVersionMiddleware` 会自动把 `/api/v1/*` 映射到 `/api/*`，未版本化路径仍兼容但将逐步废弃。
