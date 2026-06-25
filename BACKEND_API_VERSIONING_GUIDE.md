# 后端 API 版本治理迁移指南

> 本文档面向前端开发/前端 Agent，说明后端 API 版本治理方案及前端迁移方式。
> 更新日期：2026-06-24

---

## 1. 背景

后端已完成 API 版本治理的第一步：在保持现有 `/api/*` 路径完全兼容的同时，新增 `/api/v1/*` 作为正式版本化路径。

- **当前状态**：`/api/*` 与 `/api/v1/*` 完全等价，指向同一套接口。
- **未来计划**：当所有前端代码完成迁移并经过验证后，后端将逐步废弃无版本前缀的 `/api/*`，最终仅保留 `/api/v1/*`。

---

## 2. 后端实现方式

后端通过 `python/middleware/api_version.py` 中的 `ApiVersionMiddleware` 实现路径映射：

```text
/api/v1/news/sources  ->  /api/news/sources
/api/v1/varieties     ->  /api/varieties
/api/v1/realtime      ->  /api/realtime
...
```

该中间件对所有 `/api/v1/` 开头的请求做透明重写，不改变请求方法、query string、header 和 body。

### 不受影响的端点

- `/health`、`/metrics`、`/docs`、`/redoc`、`/openapi.json` 等根路径端点
- `/api/v1`（无尾部斜杠）不会被重写，会返回 404

---

## 3. 前端迁移建议

### 3.1 新代码使用 `/api/v1/`

所有新页面、新组件、新 hook 中调用后端 API 时，统一使用带版本前缀的路径：

```typescript
// 推荐
const res = await api.get('/api/v1/news/sources');

// 不推荐（旧路径，仍可运行，但未来会被废弃）
const res = await api.get('/api/news/sources');
```

### 3.2 逐步迁移现有代码

不需要一次性全量替换。建议按模块/页面逐步迁移，每次改动一个领域：

| 模块 | 涉及文件示例 |
|------|-------------|
| 新闻资讯 | `frontend/lib/api/news.ts`、`frontend/app/news/page.tsx` |
| 行情相关 | `frontend/lib/api/market.ts`、`frontend/hooks/useRealtimeQuotes.ts` |
| 品种详情 | `frontend/lib/api/products.ts`、`frontend/app/products/[id]/page.tsx` |
| 工作区 | `frontend/lib/api/workspace.ts`、`frontend/app/workspace/page.tsx` |
| 用户/设置 | `frontend/lib/api/settings.ts`、`frontend/lib/api/auth.ts` |

### 3.3 全局搜索替换策略

迁移单个模块时，可将 `frontend/lib/api/` 下对应客户端的前缀从 `'/api/` 替换为 `'/api/v1/`，然后运行：

```powershell
cd frontend
npx tsc --noEmit
npm run lint
npx playwright test
```

### 3.4 不建议修改 `frontend/lib/api/request.ts`

`request.ts` 中的 `baseURL` 或默认前缀建议保持为 `http://127.0.0.1:8401`（即服务根地址），由各 API 客户端模块自行决定路径前缀。这样可以在细粒度上控制迁移节奏。

---

## 4. 路径映射速查表

| 旧路径 | 新路径 |
|--------|--------|
| `/api/auth/*` | `/api/v1/auth/*` |
| `/api/comments/*` | `/api/v1/comments/*` |
| `/api/varieties/*` | `/api/v1/varieties/*` |
| `/api/contracts/*` | `/api/v1/contracts/*` |
| `/api/klines/*` | `/api/v1/klines/*` |
| `/api/realtime/*` | `/api/v1/realtime/*` |
| `/api/market/*` | `/api/v1/market/*` |
| `/api/news/*` | `/api/v1/news/*` |
| `/api/opinions/*` | `/api/v1/opinions/*` |
| `/api/portfolio/*` | `/api/v1/portfolio/*` |
| `/api/price-alerts/*` | `/api/v1/price-alerts/*` |
| `/api/price-levels/*` | `/api/v1/price-levels/*` |
| `/api/settings/*` | `/api/v1/settings/*` |
| `/api/watchlists/*` | `/api/v1/watchlists/*` |
| `/api/workspace/*` | `/api/v1/workspace/*` |
| `/api/chat/*` | `/api/v1/chat/*` |
| `/api/log/*` | `/api/v1/log/*` |
| `/health` | 不变 |
| `/metrics` | 不变 |

---

## 5. 验收标准

前端模块迁移完成后，应满足：

1. 该模块所有 API 调用路径使用 `/api/v1/` 前缀。
2. `npx tsc --noEmit` 通过。
3. `npm run lint` 通过。
4. 相关 Vitest 单元测试通过。
5. 相关 Playwright E2E 测试通过（或至少验证核心流程）。

---

## 6. 注意事项

- `/api/v1`（无斜杠）不会自动重定向到 `/api/v1/`，请确保代码中使用带斜杠的完整路径。
- 当前 `/api/*` 仍完全兼容，迁移过程中可以混合使用新旧前缀。
- 后端 OpenAPI 文档（`/docs`）当前仍按 `/api/*` 展示，这不影响实际调用。

---

*本文档随迁移进度更新；当 `/api/*` 正式废弃时，将发布新的迁移通知。*
