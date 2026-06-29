# FRONTEND_QUALITY_AUDIT_V6_20260601

> 面向前端修复 agent 的问题清单。  
> 审计日期：2026-06-01  
> 范围：`frontend/app`、`components`、`hooks`、`lib`、`tests`、`e2e`、前端配置。  
> 结论：整体 **B-**。架构基础可继续迭代，但 K 线初始化、鉴权一致性、设置生效和若干体验/安全边界需要优先修复。

## 执行摘要

- P0：1 个核心功能风险
- P1：4 个严重问题
- P2：4 个警告问题
- P3：2 个改进项
- 未执行验证：审计时 `npx tsc --noEmit`、`npm run lint` 因工具沙箱/审批超时未跑完。修复前后请重新执行。

## P0 核心功能风险

### P0-1 K 线图首批数据可能不会灌入 chart

证据：
- `frontend/components/KlineChart.tsx`：`prevPointsRef` 初始化为当前 `points`，只有 `prevPointsRef.current !== points` 才调用 `setData(candleData, volumeData)`。
- `frontend/hooks/useKlineChart.ts`：chart 实例在 effect 中创建，创建完成后没有主动同步当前已有数据。
- `frontend/e2e/product-detail.spec.ts`：只断言 `canvas` 可见，不能发现空 canvas。

影响：产品详情页可能出现 canvas 可见但 K 线为空，用户会误以为没有历史行情或数据源异常。

建议：
- 将 `setData(candleData, volumeData)` 放入 `useEffect`，在 chart 实例创建后也能消费当前数据。
- 增加“chart 创建后首批数据被写入”的单测。
- E2E 增加 canvas 非空像素检查，或提供测试可观测点验证 series 有数据。

验收：
- 首次进入 `/products/{symbol}` 时 K 线稳定显示。
- 切换周期/数据源后不出现空 canvas。

## P1 严重问题

### P1-1 指标页在鉴权加载期间误判未登录并重定向

证据：
- `frontend/app/metrics/page.tsx` 只读取 `isAuthenticated`，没有读取 `isLoading`。
- 初始 `isAuthenticated === false` 时直接 `router.replace('/')`。

影响：已登录用户刷新或直达 `/metrics` 时，可能在用户态恢复前被跳回首页。

建议：
- 按其它受保护页面模式处理：`authLoading` 显示加载态，未登录显示 `LoginRequired`，已登录后再请求 dashboard。
- 增加已登录直达 `/metrics` 的测试。

验收：
- 已登录刷新 `/metrics` 不跳回首页。
- 未登录访问 `/metrics` 显示登录门禁。

### P1-2 新闻页缺少登录门禁

证据：
- `frontend/app/news/page.tsx` 直接渲染 `AppShell` 并请求 `api.getNewsSources()` / `api.getNewsArticles()`。
- 没有 `useAuth`、`authLoading`、`LoginRequired`。

影响：如果新闻不是明确公开页，会破坏“登录后的私密工作台”边界。

建议：
- 接入 `AuthProvider + LoginRequired`。
- 只在已登录后启用 SWR key。

验收：
- 未登录访问 `/news` 显示登录门禁。
- 已登录访问 `/news` 正常加载新闻。

### P1-3 设置页保存的偏好没有实际生效

证据：
- `frontend/app/settings/page.tsx` 可保存 `theme`、`polling_interval_seconds`、`notifications_enabled`、`language`。
- `frontend/app/layout.tsx` 的 `Toaster` 固定 `theme="dark"`。
- `frontend/lib/swr-hooks.ts` 的 `DEFAULT_OPTIONS.refreshInterval` 固定 `30_000`。
- `frontend/hooks/useMarketPolling.ts` 默认轮询间隔固定来自 `MARKET.POLL_INTERVAL_MS`。
- `frontend/lib/constants.ts` 中 `MARKET.POLL_INTERVAL_MS` 固定为 `30_000`。

影响：用户看到“设置已保存”，但主题、刷新间隔、语言没有驱动实际 UI 或数据刷新策略。

建议：
- 增加 `PreferencesProvider` 或 `usePreferences`。
- 将设置接入页面主题、Toaster、SWR refresh interval、`useMarketPolling` interval。
- 如果语言/通知暂未实现，先隐藏入口或标注为“即将支持”。

验收：
- 修改刷新间隔后，行情页/工作区刷新节奏按新值生效。
- 修改主题后 UI 有可见变化。
- 不支持的设置项不再表现为已生效功能。

### P1-4 K 线视口重置参数传入但未使用

证据：
- `frontend/components/product/KlineSection.tsx` 定义并解构了 `viewportResetKey`。
- 渲染 `KlineChart` 时没有传 `key` 或 reset prop。
- `frontend/app/products/[id]/page.tsx` 已构造 `viewportResetKey`。

影响：切换合约、周期或数据源后，图表可能保留旧视口和缩放范围。

建议：
- 简单方案：`<KlineChart key={viewportResetKey} ... />`。
- 细化方案：传入 reset key，在变化时调用 `timeScale().fitContent()`。

验收：
- 切换连续/主力/具体合约后图表回到合理视口。
- 切换周期后不会沿用旧缩放造成误读。

## P2 警告问题

### P2-1 搜索请求缺少 debounce

证据：
- `frontend/app/products/page.tsx` 搜索输入每次 `onChange` 都更新 query。
- `frontend/app/news/page.tsx` `searchQuery` 直接作为 SWR key。

影响：快速输入会制造请求洪峰，也容易造成 UI 闪烁。

建议：增加通用 `useDebouncedValue`，对搜索关键字做 250-400ms debounce。

### P2-2 Access token 存储在 localStorage

证据：
- `frontend/lib/api/auth.ts` 使用 `ACCESS_TOKEN_KEY = 'futures_access_token'`。
- `setToken` 写入 `localStorage`，`getToken` 从 `localStorage` 恢复。

影响：当前未发现 `dangerouslySetInnerHTML`，但一旦未来引入 XSS，access token 可被 JS 直接读取。

建议：中长期改为 HttpOnly access cookie，或短 access token + refresh cookie + 内存 token。若继续保留 localStorage，需要在安全文档中标为已接受风险。

### P2-3 实时行情 hook 只传 delta，状态和数据快照边界不清楚

证据：
- `frontend/lib/realtimeStore.ts` 的 `notifyAll` 默认只传本次更新 delta。
- `frontend/hooks/useRealtimeQuotes.ts` 在 `delta.size === 0` 时保留旧 quotes。

影响：错误、重连、页面可见性切换时，UI 状态可能变化，但数据仍依赖 hook 本地旧 Map。

建议：store callback 同时提供 `snapshot` 和 `delta`，hook 层明确选择合并或替换。

### P2-4 Lighthouse 最新报告端口与真实端口不一致

证据：
- `.lighthouse/latest.json` 中 `url` 是 `http://127.0.0.1:3000`。
- `frontend/playwright.config.ts` 和 `npm run dev` 使用 `http://127.0.0.1:3200`。

影响：性能报告可能不是当前前端服务结果。

建议：重新以 `http://127.0.0.1:3200` 生成基线，并在 CI/脚本中固定端口。

## P3 改进项

### P3-1 导航布局存在重复实现

证据：
- `frontend/components/Navbar.tsx` 内部实现桌面/移动导航，并重复实现 `isActivePath`。
- 同时存在 `frontend/components/layout/SideNav.tsx`、`MobileNav.tsx`、`navigation.ts`。

建议：让 `Navbar` 组合 `SideNav` 和 `MobileNav`，`isActivePath` 统一从 `navigation.ts` 导出。

### P3-2 测试覆盖缺少真实图表绘制和新增页面鉴权

证据：
- `frontend/e2e/product-detail.spec.ts` 只检查 canvas 可见。
- `/news`、`/settings`、`/metrics` 缺少完整鉴权和设置生效 E2E。

建议补测：
- K 线 canvas 非空像素检查。
- `/metrics` 已登录直达刷新。
- `/news` 未登录门禁。
- 设置刷新间隔实际影响行情刷新。

## 建议修复顺序

1. P0-1：K 线首批数据灌入。
2. P1-1 / P1-2：指标页和新闻页鉴权一致性。
3. P1-4：K 线视口 reset 生效。
4. P1-3：设置项要么真正生效，要么先隐藏未实现项。
5. P2-1：搜索 debounce。
6. P2-4：重新生成 3200 端口 Lighthouse 基线。
7. P2-2 / P2-3：安全策略和实时 store 语义评估。
8. P3：导航清理和补测。

## 修复完成后的验证命令

在 `frontend/` 下执行：

```powershell
npx tsc --noEmit
npm run lint
npm run test
```

涉及路由、K 线或鉴权时执行：

```powershell
npx playwright test
```

涉及性能基线时执行：

```powershell
npm run lighthouse -- http://127.0.0.1:3200
```

## 注意事项

- 当前仓库已有其它未提交/未跟踪文件，修复时不要回滚无关变更。
- 继续遵循中国市场色彩语义：上涨红色，下跌绿色。
- API 调用继续走 `frontend/lib/api.ts` / `frontend/lib/api/*`。
- 受保护页面继续沿用 `AuthProvider` + `LoginRequired` 模式。
