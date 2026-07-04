<!-- .agents/frontend.md — 前端开发规则 -->

## 基本约定

- 页面和组件目前全部按 Client Component 写法组织，保持 `'use client'` 与 Hooks 风格一致。
- API 调用统一通过 `frontend/lib/api/client.ts` 的 `api` 实例，不要在页面里散落裸 `fetch`。
- 行情轮询优先使用 `useMarketPolling`，默认 30 秒。
- 色彩语义遵循中国市场惯例：上涨红色，下跌绿色。
- `KlineChart.tsx` 已使用 `lightweight-charts` v5.2.0，不要再按旧文档理解为自研 SVG 蜡烛图。

## lightweight-charts v5 注意事项

- v5 中 `ISeriesApi.setMarkers` 已移除，必须通过 `createSeriesMarkers(series)` 创建插件实例，再调用 `markersPlugin.setMarkers(...)`。
- 参考 `frontend/hooks/useKlineChart.ts` 的实现，不要对 `candleSeries` 做 `as unknown` 强转后调用 `setMarkers`。

## 价格格式化

- 显示使用 `formatPrice(value, precision)`。
- 构造 API payload 必须使用 `formatPricePayload(price, precision)`，不要直接用 `toFixed(2)`。

## 价位标注（支撑/阻力）

- 支撑/阻力位已同步后端：`price_levels` 表存储（含 `scope` 和 `contract_id`，支持 continuous/main/contract 三种口径隔离），通过 `/api/price-levels` CRUD。
- `frontend/hooks/usePriceLevels.ts` 封装了后端同步逻辑，按 K 线 source 隔离，本地存储作为降级/缓存方案保留（key 格式 `price-levels:v2:{userId}:{symbol}:{scope}:{contractId}`）。

## 登录门禁

- 主页面登录门禁来自 `AuthProvider` 和 `LoginRequired`。
- 新增需要保护的页面时沿用该模式。

## 实时行情 Store

- `realtimeStore.ts` 的 `notifyAll` 同时提供 `snapshot`（全量）和 `delta`（增量）。
- `useRealtimeQuotes.ts` 明确区分增量合并与全量替换场景。
- 订阅 symbol 数组请用 `useMemo` 避免无意义重连。
- SSE URL 截断：当 symbol 数量 >30 时省略 `symbols` 参数，后端为空时自动订阅全部活跃品种。

## 搜索防抖

- 搜索输入统一使用 `useDebouncedValue.ts`，默认 250ms，消除请求洪峰和 UI 闪烁。

## 修改后验证

- 修改前端后至少运行 `npx tsc --noEmit`。
- 如涉及样式或路由，也运行 `npm run lint`。
- 必要时用浏览器查看 `127.0.0.1:3200`。

## 关键配置

- `next.config.js`：`output: 'standalone'`；全局安全响应头（CSP、`X-Frame-Options: DENY`、`Referrer-Policy`、`Permissions-Policy`）；CSP 当前允许 `'unsafe-eval'` 和 `'unsafe-inline'` 以兼容 lightweight-charts 和 Next.js；Bundle 预算红线为任意路由 First Load JS 不得超过 180 kB。
- `tailwind.config.js`：暗色主题，自定义 `up`（红色系）、`down`（绿色系）。
- `tsconfig.json`：`"strict": true`，`"@/*": ["./*"]` 路径别名，`moduleResolution: "bundler"`。
- `playwright.config.ts`：`baseURL: http://127.0.0.1:3200`，`auth.setup.ts` 为前置依赖，`webServer` 自动运行 `npm run dev`。
