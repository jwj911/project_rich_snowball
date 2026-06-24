# 后端 API 参考（面向前端）

> 本文档由 FastAPI OpenAPI schema 自动生成，日期：2026-06-01。
> 所有端点前缀为 `http://127.0.0.1:8401`（或 `NEXT_PUBLIC_API_BASE` 配置值）。

---

## 认证方式

- **登录后请求**：在 Header 中携带 `Authorization: Bearer <access_token>`。
- **Token 获取**：`POST /api/auth/login` 返回 `access_token`。
- **Token 刷新**：`POST /api/auth/refresh` 用 `refresh_token` 换取新的 `access_token`。
- **SSE 端点**：统一走 cookie-only 路径（`withCredentials: true` + `access_token` cookie），不需要手动传 Header。

---

## 认证

### `POST` /api/auth/register

**Register**  

**参数：**
- `body` (application/json) — `UserCreate`

**响应：**
- `201` -> `UserResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `POST` /api/auth/login

**Login**  

**参数：**
- `body` (application/x-www-form-urlencoded) — `Body_login_api_auth_login_post`

**响应：**
- `200` -> `TokenResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `POST` /api/auth/refresh

**Refresh Token**  
用 HttpOnly refresh cookie 换取新的 access token（refresh token 轮转）。

安全行为：
1. 验证当前 refresh token
2. 生成新的 refresh token 并持久化
3. 吊销旧的 refresh token（防止重放攻击）
4. 通过 HttpOnly cookie 返回新的 refresh token  

**参数：**
- `body` (application/json) — `RefreshTokenRequest | null`

**响应：**
- `200` -> `RefreshTokenResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `POST` /api/auth/logout

**Logout**  
吊销当前 refresh token（logout）。  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)
- `body` (application/json) — `RefreshTokenRequest | null`

**响应：**
- `200` -> `MessageResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/auth/me

**Get Me**  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `UserResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 新闻资讯

### `GET` /api/news/sources

**List News Sources**  
列出所有启用的新闻源。  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[NewsSourceResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `POST` /api/news/sources

**Create News Source**  
添加 RSS 新闻源（admin）。  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)
- `body` (application/json) — `NewsSourceCreate`

**响应：**
- `201` -> `NewsSourceResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/news/articles

**List News Articles**  
查询新闻条目，按发布时间倒序。  

**参数：**
- `source_id` (query, optional, `integer | null`) — 按来源筛选
- `q` (query, optional, `string | null`) — 标题搜索关键词
- `skip` (query, optional, `integer`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[NewsArticleResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `DELETE` /api/news/sources/{source_id}

**Delete News Source**  
删除 RSS 新闻源及其关联文章（admin）。  

**参数：**
- `source_id` (path, required, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `204` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `POST` /api/news/fetch

**Trigger News Fetch**  
手动触发所有启用源的 RSS 抓取（admin），返回 {source_id: new_count}。  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `object` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `POST` /api/news/sources/{source_id}/fetch

**Trigger Single Source Fetch**  
手动触发单个源的 RSS 抓取（admin），返回新增文章数。  

**参数：**
- `source_id` (path, required, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `integer` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 交易观点

### `GET` /api/opinions

**List Opinions**  
查询交易观点列表（登录用户可见全部用户的公开观点）。  

**参数：**
- `variety_id` (query, optional, `integer | null`) — 按品种筛选
- `status` (query, optional, `string | null`) — 按状态筛选
- `skip` (query, optional, `integer`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[OpinionResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `POST` /api/opinions

**Create Opinion**  
创建交易观点。  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)
- `body` (application/json) — `OpinionCreate`

**响应：**
- `201` -> `OpinionResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/opinions/me

**List My Opinions**  
查询当前用户的交易观点时间线。  

**参数：**
- `status` (query, optional, `string | null`) — 按状态筛选
- `skip` (query, optional, `integer`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[OpinionResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/opinions/{opinion_id}

**Get Opinion**  
获取单条观点详情。  

**参数：**
- `opinion_id` (path, required, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `OpinionResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `PUT` /api/opinions/{opinion_id}

**Update Opinion**  
更新交易观点（仅 owner）。支持关闭观点和标记复盘结果。  

**参数：**
- `opinion_id` (path, required, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)
- `body` (application/json) — `OpinionUpdate`

**响应：**
- `200` -> `OpinionResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `DELETE` /api/opinions/{opinion_id}

**Delete Opinion**  
删除交易观点（仅 owner）。  

**参数：**
- `opinion_id` (path, required, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `204` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 前端监控

### `POST` /api/log/frontend

**Create Frontend Log**  
接收前端错误、日志和 Web Vitals 数据。

该端点不返回业务数据，仅确认接收（202 Accepted）。
写入失败时降级为结构化日志，不向前端抛错。  

**参数：**
- `body` (application/json) — `FrontendLogCreate`

**响应：**
- `202` -> `object` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/log/frontend

**List Frontend Logs**  
查询前端日志。

权限策略：
- admin 用户可查询全部日志
- 普通用户只能查询与自己 user_id 关联的日志  

**参数：**
- `type` (query, optional, `string | null`) — 日志类型筛选
- `level` (query, optional, `string | null`) — 日志级别筛选
- `start_time` (query, optional, `string | null`) — 起始时间（ISO 8601）
- `end_time` (query, optional, `string | null`) — 结束时间（ISO 8601）
- `skip` (query, optional, `integer`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[FrontendLogResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 实时行情

### `GET` /api/realtime/batch

**Get Realtime Batch**  

**参数：**
- `symbols` (query, optional, `list[string]`) — 品种代码列表，如 ?symbols=AU&symbols=CU
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `RealtimeBatchResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `POST` /api/realtime/stream-token

**Create Realtime Stream Token**  
Issue a short-lived token for EventSource connections.

Deprecated: SSE 鉴权已统一走 cookie-only 路径（access_token cookie），
stream-token 不再推荐使用，后续版本可能移除。  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `object` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/realtime/stream

**Get Realtime Stream**  
SSE 实时行情推送端点。每 5 秒推送一次订阅品种的行情数据。

并发限制：同一用户同时只能维持 1 个活跃 SSE 连接，新连接建立时旧连接会被取消。  

**参数：**
- `symbols` (query, optional, `list[string]`) — 品种代码列表，如 ?symbols=AU&symbols=CU
- `token` (query, optional, `string`) — JWT token（EventSource 不支持自定义 Header，通过 query param 传递）
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `object` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/realtime/{symbol}

**Get Realtime**  

**参数：**
- `symbol` (path, required, `string`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `RealtimeResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## K线

### `GET` /api/klines/{symbol}

**Get Kline**  

**参数：**
- `symbol` (path, required, `string`)
- `period` (query, optional, `string`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[KlineResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/klines/{symbol}/continuous

**Get Continuous Kline Api**  
获取连续 K 线（按主力切换拼接多合约）。  

**参数：**
- `symbol` (path, required, `string`)
- `period` (query, optional, `string`)
- `start` (query, optional, `datetime | null`)
- `end` (query, optional, `datetime | null`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[ContinuousKlineResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/klines/{symbol}/main

**Get Main Contract Kline Api**  
获取当前主力合约的 K 线（不拼接）。  

**参数：**
- `symbol` (path, required, `string`)
- `period` (query, optional, `string`)
- `start` (query, optional, `datetime | null`)
- `end` (query, optional, `datetime | null`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[ContinuousKlineResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 品种

### `GET` /api/varieties

**Get Varieties**  
品种列表（含实时行情），用于替代 /api/products。

联合查询 VarietyDB + RealtimeQuoteDB，支持搜索/分类/涨跌筛选/排序/分页。  

**参数：**
- `skip` (query, optional, `integer`)
- `limit` (query, optional, `integer`)
- `search` (query, optional, `string | null`)
- `category` (query, optional, `string | null`)
- `direction` (query, optional, `string`)
- `sort_by` (query, optional, `string`)
- `sort_order` (query, optional, `string`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[VarietyWithQuoteResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/varieties/{symbol}

**Get Variety**  

**参数：**
- `symbol` (path, required, `string`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `VarietyResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/varieties/{symbol}/detail

**Get Variety Detail**  
品种详情（含实时行情 + 评论列表），用于替代 /api/products/{id}。  

**参数：**
- `symbol` (path, required, `string`)
- `comment_skip` (query, optional, `integer`)
- `comment_limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `VarietyDetailResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/varieties/{variety_id}/contracts

**Get Variety Contracts**  
获取某品种下的所有合约（已废弃，请使用 GET /api/contracts?variety_id=X）。  

**参数：**
- `variety_id` (path, required, `integer`)
- `active_only` (query, optional, `boolean`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[ContractResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/varieties/{variety_id}/rollovers

**Get Variety Rollovers**  
获取某品种的合约切换历史（已废弃，请使用 GET /api/contracts/rollovers?variety_id=X）。  

**参数：**
- `variety_id` (path, required, `integer`)
- `skip` (query, optional, `integer`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[ContractRolloverResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/varieties/{symbol}/fees

**Get Variety Fees**  
获取品种最新的手续费与保证金数据。  

**参数：**
- `symbol` (path, required, `string`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `VarietyFeeResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 评论

### `POST` /api/comments

**Create Comment**  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)
- `body` (application/json) — `CommentCreate`

**响应：**
- `201` -> `CommentResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/comments/me

**Get My Comments**  
获取当前登录用户的评论历史。  

**参数：**
- `skip` (query, optional, `integer`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[CommentResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/comments/user/{username}

**Get User Comments**  
获取指定用户的评论历史（仅允许查看自己的评论）。  

**参数：**
- `username` (path, required, `string`)
- `skip` (query, optional, `integer`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[CommentResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 价位标注

### `GET` /api/price-levels

**List Price Levels**  

**参数：**
- `variety_id` (query, optional, `integer | null`)
- `type` (query, optional, `string | null`)
- `scope` (query, optional, `string | null`)
- `contract_id` (query, optional, `integer | null`)
- `skip` (query, optional, `integer`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[PriceLevelResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `POST` /api/price-levels

**Create Price Level**  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)
- `body` (application/json) — `PriceLevelCreate`

**响应：**
- `201` -> `PriceLevelResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `PUT` /api/price-levels/{price_level_id}

**Update Price Level**  

**参数：**
- `price_level_id` (path, required, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)
- `body` (application/json) — `PriceLevelUpdate`

**响应：**
- `200` -> `PriceLevelResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `DELETE` /api/price-levels/{price_level_id}

**Delete Price Level**  

**参数：**
- `price_level_id` (path, required, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `MessageResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `POST` /api/price-levels/batch

**Create Price Levels Batch**  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)
- `body` (application/json) — `PriceLevelBatchCreate`

**响应：**
- `200` -> `PriceLevelBatchResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 自选

### `GET` /api/watchlists

**List Watchlists**  

**参数：**
- `variety_id` (query, optional, `integer | null`)
- `skip` (query, optional, `integer`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[WatchlistResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `POST` /api/watchlists

**Create Watchlist**  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)
- `body` (application/json) — `WatchlistCreate`

**响应：**
- `201` -> `WatchlistResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `PUT` /api/watchlists/{watchlist_id}

**Update Watchlist**  

**参数：**
- `watchlist_id` (path, required, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)
- `body` (application/json) — `WatchlistUpdate`

**响应：**
- `200` -> `WatchlistResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `DELETE` /api/watchlists/{watchlist_id}

**Delete Watchlist**  

**参数：**
- `watchlist_id` (path, required, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `MessageResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 工作区

### `GET` /api/workspace/me

**Get Workspace**  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `WorkspaceSummary` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 合约

### `GET` /api/contracts

**List Contracts**  
列出期货合约，支持按品种、交易所筛选。  

**参数：**
- `variety_id` (query, optional, `integer | null`)
- `exchange` (query, optional, `string | null`)
- `active_only` (query, optional, `boolean`)
- `skip` (query, optional, `integer`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[ContractResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/contracts/rollovers

**List Contract Rollovers**  
获取某品种的合约切换历史。  

**参数：**
- `variety_id` (query, required, `integer`) — 品种 ID
- `skip` (query, optional, `integer`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[ContractRolloverResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/contracts/{contract_id}

**Get Contract**  
获取单个合约详情。  

**参数：**
- `contract_id` (path, required, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `ContractResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /api/contracts/{contract_id}/kline

**Get Contract Kline**  
获取单个合约的 K 线数据。  

**参数：**
- `contract_id` (path, required, `integer`)
- `period` (query, optional, `string`)
- `start` (query, optional, `datetime | null`)
- `end` (query, optional, `datetime | null`)
- `limit` (query, optional, `integer`)
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `list[KlineResponse]` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 健康检查

### `GET` /health

**Health Check**  

**响应：**
- `200` -> `object` — Successful Response

### `GET` /health/ready

**Readiness Check**  
返回系统就绪状态。DB 可连接即 ready；若配置了 Redis，也检查 Redis 连通性。  

**响应：**
- `200` -> `object` — Successful Response

### `GET` /health/scheduler

**Scheduler Check**  
返回调度器状态与最近任务历史。API 进程本身不运行 scheduler 时也返回信息。

生产环境限制为内网/本机访问，防止敏感内部状态外泄。  

**响应：**
- `200` -> `object` — Successful Response

---

## 市场状态

### `GET` /api/market/status

**Get Market Status**  

**响应：**
- `200` -> `MarketStatusResponse` — Successful Response

---

## 指标面板

### `GET` /metrics/dashboard

**Get Dashboard Overview**  
平台总体统计。  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `object` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /metrics/dashboard/activity

**Get Dashboard Activity**  
最近 7 天活跃度趋势。  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `object` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `GET` /metrics/dashboard/collection

**Get Dashboard Collection**  
数据采集健康度。  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `object` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 设置

### `GET` /api/settings

**Get User Settings**  
获取当前用户的偏好设置。  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)

**响应：**
- `200` -> `UserPreferenceResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

### `PUT` /api/settings

**Update User Settings**  
更新当前用户的偏好设置（Patch 语义：仅更新提供的字段）。  

**参数：**
- `authorization` (header, optional, `string`)
- `access_token` (cookie, optional, `string`)
- `body` (application/json) — `UserPreferenceUpdate`

**响应：**
- `200` -> `UserPreferenceResponse` — Successful Response
- `422` -> `HTTPValidationError` — Validation Error

---

## 未分类

### `GET` /metrics

**Metrics**  
Prometheus 指标抓取端点。仅限本地/内网访问。  

**响应：**
- `200` -> `object` — Successful Response

### `GET` /

**Root**  

**响应：**
- `200` -> `object` — Successful Response

---

## 常用 Schema 速查

### `CommentCreate`

- `variety_id` (`integer`, required)
- `content` (`string`, required)
- `price_level_id` (`integer | null`, optional)

### `CommentResponse`

- `id` (`integer`, required)
- `variety_id` (`integer`, required)
- `product_symbol` (`string | null`, optional)
- `product_name` (`string | null`, optional)
- `variety_symbol` (`string | null`, optional)
- `variety_name` (`string | null`, optional)
- `user_id` (`integer`, required)
- `username` (`string`, required)
- `content` (`string`, required)
- `price_level_id` (`integer | null`, optional)
- `created_at` (`datetime`, required)

### `ContinuousKlineResponse`

- `time` (`string`, required)
- `open` (`number`, required)
- `high` (`number`, required)
- `low` (`number`, required)
- `close` (`number`, required)
- `volume` (`integer`, required)
- `contract_code` (`string | null`, required)
- `contract_id` (`integer | null`, required)

### `ContractResponse`

- `id` (`integer`, required)
- `ts_code` (`string`, required)
- `symbol` (`string | null`, required)
- `name` (`string | null`, required)
- `fut_code` (`string | null`, required)
- `exchange` (`string | null`, required)
- `list_date` (`datetime | null`, required)
- `delist_date` (`datetime | null`, required)
- `contract_type` (`string | null`, required)
- `is_active` (`boolean`, required)

### `ContractRolloverResponse`

- `id` (`integer`, required)
- `variety_id` (`integer`, required)
- `old_contract_id` (`integer | null`, required)
- `new_contract_id` (`integer | null`, required)
- `old_contract_code` (`string | null`, required)
- `new_contract_code` (`string | null`, required)
- `effective_date` (`datetime`, required)
- `source` (`string`, required)
- `created_at` (`datetime`, required)

### `FrontendLogCreate`

- `type` (`string`, required)
- `payload` (`object`, optional)
- `level` (`string | null`, optional)
- `meta` (`object`, optional)
- `user_id` (`integer | null`, optional) — 已登录用户上报时关联用户 ID

### `FrontendLogResponse`

- `id` (`integer`, required)
- `user_id` (`integer | null`, required)
- `type` (`string`, required)
- `level` (`string | null`, required)
- `url` (`string | null`, required)
- `user_agent` (`string | null`, required)
- `release` (`string | null`, required)
- `environment` (`string | null`, required)
- `payload` (`object`, required)
- `created_at` (`datetime`, required)

### `KlineResponse`

- `time` (`string`, required)
- `open` (`number`, required)
- `high` (`number`, required)
- `low` (`number`, required)
- `close` (`number`, required)
- `volume` (`integer`, required)

### `MarketStatusResponse`

- `date` (`string`, required)
- `is_trading_day` (`boolean`, required)
- `current_session` (`string`, required)
- `next_trade_date` (`string | null`, required)
- `remark` (`string | null`, required)

### `MessageResponse`

- `detail` (`string`, required)

### `NewsArticleResponse`

- `id` (`integer`, required)
- `source_id` (`integer`, required)
- `title` (`string`, required)
- `summary` (`string | null`, required)
- `url` (`string`, required)
- `published_at` (`datetime | null`, required)
- `fetched_at` (`datetime`, required)

### `NewsSourceCreate`

- `name` (`string`, required)
- `url` (`string`, required)
- `category` (`string | null`, optional)
- `is_enabled` (`boolean`, optional)

### `NewsSourceResponse`

- `name` (`string`, required)
- `url` (`string`, required)
- `category` (`string | null`, optional)
- `is_enabled` (`boolean`, optional)
- `id` (`integer`, required)
- `last_fetched_at` (`datetime | null`, required)
- `fetch_error_count` (`integer`, required)
- `created_at` (`datetime`, required)

### `OpinionCreate`

- `variety_id` (`integer`, required)
- `type` (`string`, required)
- `reason` (`string`, required)
- `target_price` (`number | string | null`, optional)
- `stop_loss` (`number | string | null`, optional)

### `OpinionResponse`

- `id` (`integer`, required)
- `user_id` (`integer`, required)
- `variety_id` (`integer`, required)
- `variety_symbol` (`string`, required)
- `variety_name` (`string`, required)
- `type` (`string`, required)
- `reason` (`string | null`, required)
- `target_price` (`string | null`, required)
- `stop_loss` (`string | null`, required)
- `status` (`string`, required)
- `actual_outcome` (`string | null`, required)
- `created_at` (`datetime`, required)
- `closed_at` (`datetime | null`, required)

### `OpinionUpdate`

- `reason` (`string | null`, optional)
- `target_price` (`number | string | null`, optional)
- `stop_loss` (`number | string | null`, optional)
- `status` (`string | null`, optional)
- `actual_outcome` (`string | null`, optional)

### `PriceLevelBatchCreate`

- `items` (`list[PriceLevelBatchItem]`, required)

### `PriceLevelBatchItem`

- `variety_id` (`integer`, required)
- `type` (`string`, required)
- `price` (`number | string`, required)
- `scope` (`string`, optional)
- `contract_id` (`integer | null`, optional)
- `note` (`string | null`, optional)

### `PriceLevelBatchResponse`

- `success` (`list[PriceLevelResponse]`, required)
- `failed` (`list[object]`, required)
- `created_count` (`integer`, required)
- `failed_count` (`integer`, required)

### `PriceLevelCreate`

- `variety_id` (`integer`, required)
- `type` (`string`, required)
- `price` (`number | string`, required)
- `scope` (`string`, optional)
- `contract_id` (`integer | null`, optional)
- `note` (`string | null`, optional)

### `PriceLevelResponse`

- `id` (`integer`, required)
- `user_id` (`integer`, required)
- `variety_id` (`integer`, required)
- `contract_id` (`integer | null`, optional)
- `variety_symbol` (`string | null`, optional)
- `variety_name` (`string | null`, optional)
- `type` (`string`, required)
- `price` (`string`, required)
- `scope` (`string`, required)
- `note` (`string | null`, required)
- `source` (`string`, required)
- `created_at` (`datetime`, required)
- `updated_at` (`datetime`, required)

### `PriceLevelUpdate`

- `price` (`number | string | null`, optional)
- `note` (`string | null`, optional)

### `RealtimeBatchResponse`

- `quotes` (`list[RealtimeResponse]`, required)
- `not_found` (`list[string]`, required)

### `RealtimeResponse`

- `symbol` (`string`, required)
- `current_price` (`number`, required)
- `change_percent` (`number`, required)
- `open_price` (`number | null`, required)
- `high` (`number | null`, required)
- `low` (`number | null`, required)
- `volume` (`integer | null`, required)
- `updated_at` (`datetime`, required)
- `delayed` (`boolean`, optional)
- `data_source` (`string | null`, optional)
- `limit_up` (`number | null`, optional)
- `limit_down` (`number | null`, optional)

### `RefreshTokenRequest`

- `refresh_token` (`string | null`, optional)

### `RefreshTokenResponse`

- `access_token` (`string`, required)
- `token_type` (`string`, optional)
- `expires_in` (`integer`, required)

### `TokenResponse`

- `access_token` (`string`, required)
- `token_type` (`string`, optional)
- `refresh_token` (`string | null`, optional)
- `expires_in` (`integer`, optional)

### `UserCreate`

- `username` (`string`, required)
- `email` (`string`, required)
- `password` (`string`, required)

### `UserPreferenceResponse`

- `user_id` (`integer`, required)
- `theme` (`string`, required)
- `polling_interval_seconds` (`integer`, required)
- `notifications_enabled` (`boolean`, required)
- `language` (`string`, required)
- `created_at` (`datetime | null`, optional)
- `updated_at` (`datetime | null`, optional)

### `UserPreferenceUpdate`

- `theme` (`Theme | null`, optional) — 主题: dark | light | system
- `polling_interval_seconds` (`integer | null`, optional) — 行情轮询间隔（秒）
- `notifications_enabled` (`boolean | null`, optional) — 是否启用通知
- `language` (`string | null`, optional) — 语言代码，如 zh-CN

### `UserResponse`

- `id` (`integer`, required)
- `username` (`string`, required)
- `email` (`string`, required)
- `created_at` (`datetime`, required)

### `VarietyDetailResponse`

- `id` (`integer`, required)
- `symbol` (`string`, required)
- `contract_code` (`string`, required)
- `name` (`string`, required)
- `exchange` (`string`, required)
- `category` (`string | null`, required)
- `margin_rate` (`number | null`, required)
- `commission` (`number | null`, required)
- `tick_size` (`number | null`, optional)
- `current_price` (`number | null`, optional)
- `change_percent` (`number | null`, optional)
- `open_price` (`number | null`, optional)
- `high` (`number | null`, optional)
- `low` (`number | null`, optional)
- `volume` (`integer | null`, optional)
- `limit_up` (`number | null`, optional)
- `limit_down` (`number | null`, optional)
- `price_precision` (`integer`, optional)
- `comments` (`list[CommentResponse]`, optional)

### `VarietyFeeResponse`

- `symbol` (`string`, required)
- `name` (`string | null`, required)
- `exchange` (`string | null`, required)
- `margin_rate` (`number | null`, required)
- `margin_amount` (`number | null`, required)
- `commission_open` (`number | null`, required)
- `commission_close` (`number | null`, required)
- `commission_close_today` (`number | null`, required)
- `unit` (`string | null`, required)
- `updated_at` (`datetime | null`, required)

### `VarietyResponse`

- `id` (`integer`, required)
- `symbol` (`string`, required)
- `contract_code` (`string`, required)
- `name` (`string`, required)
- `exchange` (`string`, required)
- `category` (`string | null`, required)
- `margin_rate` (`number | null`, required)
- `commission` (`number | null`, required)
- `tick_size` (`number | null`, optional)
- `price_precision` (`integer`, required) — 根据 tick_size 推导价格精度（小数位数）。

### `VarietyWithQuoteResponse`

- `id` (`integer`, required)
- `symbol` (`string`, required)
- `name` (`string`, required)
- `category` (`string | null`, required)
- `current_price` (`number | null`, optional)
- `change_percent` (`number | null`, optional)
- `open_price` (`number | null`, optional)
- `high` (`number | null`, optional)
- `low` (`number | null`, optional)
- `volume` (`integer | null`, optional)
- `limit_up` (`number | null`, optional)
- `limit_down` (`number | null`, optional)
- `price_precision` (`integer`, optional)
- `margin_rate` (`number | null`, optional)
- `commission` (`number | null`, optional)
- `updated_at` (`string | null`, optional)

### `WatchlistCreate`

- `variety_id` (`integer`, required)
- `notes` (`string | null`, optional)

### `WatchlistResponse`

- `id` (`integer`, required)
- `user_id` (`integer`, required)
- `variety_id` (`integer`, required)
- `variety_symbol` (`string`, required)
- `variety_name` (`string`, required)
- `notes` (`string | null`, required)
- `is_notified` (`boolean`, required)
- `created_at` (`datetime`, required)

### `WatchlistUpdate`

- `notes` (`string | null`, optional)
- `is_notified` (`boolean | null`, optional)

### `WorkspaceSummary`

- `price_levels` (`list[PriceLevelResponse]`, required)
- `watchlists` (`list[WatchlistResponse]`, required)
- `recent_comments` (`list[CommentResponse]`, required)
