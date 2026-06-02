# 前端质量迭代 Roadmap

> 基于架构师审查报告 `FRONTEND_FIX_LIST_20260601.md` 的细化迭代计划。
> 梳理日期：2026-06-02
> 范围：`frontend/app`、`components`、`hooks`、`lib`、`tests`、`e2e`、前端配置。
> 当前评级：**B-**

---

## 执行摘要

- **Sprint 1（功能修复）**：4 个任务 — 解决 P0 核心风险和 P1 严重问题
- **Sprint 2（体验优化）**：3 个任务 — 解决 P2 警告问题
- **Sprint 3（架构清理）**：2 个任务 — 解决 P3 改进项
- **每个 Sprint 结束后执行验证命令**

---

## 前置约定

- 继续遵循中国市场色彩语义：上涨红色，下跌绿色
- API 调用继续走 `frontend/lib/api.ts` / `frontend/lib/api/*`
- 受保护页面继续沿用 `AuthProvider` + `LoginRequired` 模式
- 修复时不要回滚无关变更
- 所有修改先通过 `npx tsc --noEmit` 和 `npm run lint`

---

## Sprint 1：功能修复（P0 + P1）

### Sprint 1-1：P0-1 K 线首批数据灌入修复

**问题描述**：
- `components/KlineChart.tsx:104-109`：`prevPointsRef` 初始化为当前 `points`，chart 实例尚未创建时调用 `setData` 会被忽略
- `hooks/useKlineChart.ts:43-147`：chart 实例在 effect 中创建，创建后没有主动同步当前已有数据
- 首次进入 `/products/{symbol}` 可能出现 canvas 可见但 K 线为空

**修改文件**：
- `frontend/hooks/useKlineChart.ts` — chart 创建完成后主动调用 `setData` 灌入当前数据
- `frontend/components/KlineChart.tsx` — 确保 chart 创建与数据同步的时序正确

**验收标准**：
- [ ] 首次进入 `/products/{symbol}` 时 K 线稳定显示，不再出现空 canvas
- [ ] 切换周期/数据源后不出现空 canvas
- [ ] `tests/hooks/useKlineChart.test.ts` 增加"chart 创建后首批数据被写入"测试（如文件不存在则新建）

---

### Sprint 1-2：P1-1 指标页鉴权加载态修复

**问题描述**：
- `app/metrics/page.tsx:24-36`：只读取 `isAuthenticated`，没有读取 `isLoading`
- 初始 `isAuthenticated === false` 时直接 `router.replace('/')`
- 已登录用户刷新或直达 `/metrics` 时，可能在用户态恢复前被跳回首页

**参考模式**：`app/workspace/page.tsx:33,98-104` — 正确使用 `authLoading` 和 `LoginRequired`

**修改文件**：
- `frontend/app/metrics/page.tsx` — 增加 `isLoading` 读取，鉴权加载期间显示加载态，未登录显示 `LoginRequired`

**验收标准**：
- [ ] 已登录用户刷新 `/metrics` 不跳回首页
- [ ] 未登录访问 `/metrics` 显示 `LoginRequired` 登录门禁
- [ ] `e2e/metrics.spec.ts` 增加已登录直达刷新测试（如文件不存在则新建）

---

### Sprint 1-3：P1-2 新闻页鉴权门禁接入

**问题描述**：
- `app/news/page.tsx`：直接渲染 `AppShell` 并请求 `api.getNewsSources()` / `api.getNewsArticles()`
- 没有 `useAuth`、`authLoading`、`LoginRequired`
- 破坏"登录后的私密工作台"边界

**修改文件**：
- `frontend/app/news/page.tsx` — 接入 `useAuth`、`authLoading`、`LoginRequired`，只在已登录后启用 SWR key

**验收标准**：
- [ ] 未登录访问 `/news` 显示 `LoginRequired` 登录门禁
- [ ] 已登录访问 `/news` 正常加载新闻
- [ ] `e2e/news.spec.ts` 增加未登录门禁测试（如文件不存在则新建）

---

### Sprint 1-4：P1-3 设置偏好实际生效

**问题描述**：
- `app/settings/page.tsx`：可保存 `theme`、`polling_interval_seconds`、`notifications_enabled`、`language`
- `app/layout.tsx:24`：`Toaster` 固定 `theme="dark"`
- `lib/swr-hooks.ts:6`：`DEFAULT_OPTIONS.refreshInterval` 固定 `30_000`
- `hooks/useMarketPolling.ts:33`：默认轮询间隔固定来自 `MARKET.POLL_INTERVAL_MS`
- `lib/constants.ts:2`：`MARKET.POLL_INTERVAL_MS` 固定为 `30_000`
- 用户看到"设置已保存"，但主题、刷新间隔没有驱动实际 UI 或数据刷新策略

**修改文件**：
- 新建 `frontend/hooks/usePreferences.ts` — 提供用户偏好读取和订阅机制
- 新建 `frontend/components/PreferencesProvider.tsx` — 将偏好注入全局上下文
- `frontend/app/layout.tsx` — `Toaster` 主题从偏好读取
- `frontend/lib/swr-hooks.ts` — `refreshInterval` 从偏好读取，支持动态更新
- `frontend/hooks/useMarketPolling.ts` — 轮询间隔从偏好读取
- `frontend/app/settings/page.tsx` — 保存后触发偏好上下文更新

**处理未实现项**：
- `language`（多语言）：当前无 i18n 框架，建议先隐藏入口或标注"即将支持"
- `notifications_enabled`（推送通知）：当前无通知服务，建议先隐藏入口或标注"即将支持"

**验收标准**：
- [ ] 修改刷新间隔后，行情页/工作区刷新节奏按新值生效
- [ ] 修改主题后 `Toaster` 主题同步变化
- [ ] 不支持的设置项（language、notifications）不再表现为已生效功能

---

### Sprint 1-5：P1-4 K 线视口重置生效

**问题描述**：
- `components/product/KlineSection.tsx:19`：定义并解构了 `viewportResetKey`
- `components/product/KlineSection.tsx:161-171`：渲染 `KlineChart` 时没有传 `key` 或 reset prop
- `app/products/[id]/page.tsx:339`：已构造 `viewportResetKey`
- 切换合约、周期或数据源后，图表可能保留旧视口和缩放范围

**修改文件**：
- `frontend/components/product/KlineSection.tsx` — 将 `viewportResetKey` 传入 `KlineChart`
- `frontend/components/KlineChart.tsx` — 接收 `resetKey` prop，在变化时调用 `timeScale().fitContent()`
- `frontend/hooks/useKlineChart.ts` — 暴露 `fitContent()` 方法或自动响应 reset

**验收标准**：
- [ ] 切换连续/主力/具体合约后图表回到合理视口
- [ ] 切换周期后不会沿用旧缩放造成误读
- [ ] E2E `product-detail.spec.ts` 增加视口切换断言

---

## Sprint 2：体验优化（P2）

### Sprint 2-1：P2-1 搜索请求 Debounce

**问题描述**：
- `app/products/page.tsx:67-70,118-127`：搜索输入每次 `onChange` 都更新 query
- `app/news/page.tsx:13-36`：`searchQuery` 直接作为 SWR key，每次输入都触发请求
- 快速输入制造请求洪峰，造成 UI 闪烁

**修改文件**：
- 新建 `frontend/hooks/useDebouncedValue.ts` — 通用 debounce hook
- `frontend/app/products/page.tsx` — 搜索输入使用 debounce
- `frontend/app/news/page.tsx` — 搜索输入使用 debounce

**验收标准**：
- [ ] 快速输入搜索词时，请求间隔不小于 250ms
- [ ] UI 不再因频繁请求而闪烁
- [ ] `tests/hooks/useDebouncedValue.test.ts` 增加单元测试（如文件不存在则新建）

---

### Sprint 2-2：P2-2 Access Token 安全存储评估

**问题描述**：
- `lib/api/auth.ts:5-47`：access token 存储在 `localStorage`（`futures_access_token`）
- 一旦未来引入 XSS，access token 可被 JS 直接读取

**决策**：这是一个**中长期安全架构决策**，非紧急修复。

**可选方案**：
1. **方案 A（推荐）**：改为 HttpOnly cookie 存储 access token，API 请求自动带 cookie
2. **方案 B**：短 access token（内存）+ refresh token（HttpOnly cookie），登录后先换 token
3. **方案 C（保守）**：继续保留 localStorage，在 `SECURITY.md` 或项目文档中明确标注为已接受风险

**修改文件**：
- 待定（取决于方案选择）
- 如选方案 C：`frontend/docs/SECURITY_RISKS.md` — 记录已知风险

**验收标准**：
- [ ] 选定方案并文档化
- [ ] 如实施改造，确保登录/登出/刷新流程全部正常
- [ ] 如保留 localStorage，文档中明确标注风险

---

### Sprint 2-3：P2-3 实时行情 Store 语义清晰化

**问题描述**：
- `lib/realtimeStore.ts:280-297`：`notifyAll` 默认只传本次更新 delta
- `hooks/useRealtimeQuotes.ts:32-44`：在 `delta.size === 0` 时保留旧 quotes
- 错误、重连、页面可见性切换时，UI 状态可能变化但数据仍依赖 hook 本地旧 Map

**修改文件**：
- `frontend/lib/realtimeStore.ts` — `notifyAll` 同时提供 `snapshot`（全量）和 `delta`（增量）
- `frontend/hooks/useRealtimeQuotes.ts` — 明确选择：正常更新时合并 delta，重连/错误时替换为 snapshot

**验收标准**：
- [ ] 重连后 hook 中 quotes 与 store 内部 _quotes 一致
- [ ] `tests/hooks/useRealtimeQuotes.test.tsx` 通过（如需要则更新）

---

### Sprint 2-4：P2-4 Lighthouse 端口基线修复

**问题描述**：
- `.lighthouse/latest.json`：url 是 `http://127.0.0.1:3000`
- `frontend/playwright.config.ts` 和 `npm run dev` 使用 `http://127.0.0.1:3200`
- 性能报告可能不是当前前端服务结果

**修改文件**：
- `frontend/.lighthouse/latest.json` — 重新以 `http://127.0.0.1:3200` 生成
- `frontend/package.json` — 检查 lighthouse 脚本是否固定端口

**验收标准**：
- [ ] `.lighthouse/latest.json` 中 url 为 `http://127.0.0.1:3200`
- [ ] CI/脚本中端口固定为 3200

---

## Sprint 3：架构清理（P3）

### Sprint 3-1：P3-1 导航组件去重

**问题描述**：
- `components/Navbar.tsx`：内部完整实现桌面/移动导航，并内联定义 `isActivePath`
- `components/layout/SideNav.tsx`：与 Navbar 桌面部分高度重复
- `components/layout/MobileNav.tsx`：与 Navbar 移动部分高度重复
- `components/layout/navigation.ts`：已导出 `isActivePath`，但 Navbar 未使用

**现状分析**：
- `SideNav.tsx` 和 `MobileNav.tsx` 当前**未被任何页面使用**
- `Navbar.tsx` 内部自行实现了两套导航逻辑

**修改文件**：
- `frontend/components/Navbar.tsx` — 重构为组合 `SideNav` + `MobileNav`，删除内联 `isActivePath`，统一从 `navigation.ts` 导入
- `frontend/components/layout/SideNav.tsx` — 微调以适配 Navbar 组合接口（如需）
- `frontend/components/layout/MobileNav.tsx` — 微调以适配 Navbar 组合接口（如需）

**验收标准**：
- [ ] 导航功能无回归（桌面侧边栏、移动顶部栏、路由高亮、登录/登出）
- [ ] `tests/components/Navbar.test.tsx` 通过
- [ ] 无重复代码（Navbar 不再内联实现完整导航）

---

### Sprint 3-2：P3-2 测试覆盖补齐

**补充测试清单**：

| 测试项 | 类型 | 目标文件 |
|--------|------|----------|
| K 线 canvas 非空像素检查 | E2E | `e2e/product-detail.spec.ts` |
| `/metrics` 已登录直达刷新 | E2E | `e2e/metrics.spec.ts`（新建） |
| `/news` 未登录门禁 | E2E | `e2e/news.spec.ts`（新建） |
| 设置刷新间隔实际影响行情刷新 | E2E | `e2e/settings.spec.ts`（新建） |
| `useDebouncedValue` hook | 单元 | `tests/hooks/useDebouncedValue.test.ts`（新建） |
| `useKlineChart` 首批数据灌入 | 单元 | `tests/hooks/useKlineChart.test.ts`（新建） |

---

## 验证矩阵

每个 Sprint 结束后执行：

```powershell
# 基础验证（每次修改后必做）
cd frontend
npx tsc --noEmit
npm run lint
npm run test

# 路由、K 线或鉴权相关（Sprint 1 必做）
npx playwright test

# 性能基线相关（Sprint 2-4 涉及 P2-4 时做）
npm run lighthouse -- http://127.0.0.1:3200
```

---

## 迭代顺序建议

```
Week 1 (Sprint 1-1 ~ 1-3): P0-1 → P1-1 → P1-2
Week 2 (Sprint 1-4 ~ 1-5): P1-4 → P1-3
Week 3 (Sprint 2-1 ~ 2-2): P2-1 → P2-4
Week 4 (Sprint 2-3 ~ 3-2): P2-3 → P2-2(评估) → P3-1 → P3-2
```

> P2-2（Token 安全存储）是架构决策类任务，可以独立评估不阻塞其他迭代。

---

## 附录：受影响的完整文件清单

### Sprint 1
| 文件 | 操作 | 关联问题 |
|------|------|----------|
| `frontend/hooks/useKlineChart.ts` | 修改 | P0-1 |
| `frontend/components/KlineChart.tsx` | 修改 | P0-1 |
| `frontend/app/metrics/page.tsx` | 修改 | P1-1 |
| `frontend/app/news/page.tsx` | 修改 | P1-2 |
| `frontend/app/settings/page.tsx` | 修改 | P1-3 |
| `frontend/app/layout.tsx` | 修改 | P1-3 |
| `frontend/lib/swr-hooks.ts` | 修改 | P1-3 |
| `frontend/hooks/useMarketPolling.ts` | 修改 | P1-3 |
| `frontend/components/product/KlineSection.tsx` | 修改 | P1-4 |
| `frontend/hooks/usePreferences.ts` | 新建 | P1-3 |
| `frontend/components/PreferencesProvider.tsx` | 新建 | P1-3 |

### Sprint 2
| 文件 | 操作 | 关联问题 |
|------|------|----------|
| `frontend/hooks/useDebouncedValue.ts` | 新建 | P2-1 |
| `frontend/app/products/page.tsx` | 修改 | P2-1 |
| `frontend/app/news/page.tsx` | 修改 | P2-1 |
| `frontend/lib/realtimeStore.ts` | 修改 | P2-3 |
| `frontend/hooks/useRealtimeQuotes.ts` | 修改 | P2-3 |
| `frontend/.lighthouse/latest.json` | 重新生成 | P2-4 |
| `frontend/package.json` | 可能修改 | P2-4 |

### Sprint 3
| 文件 | 操作 | 关联问题 |
|------|------|----------|
| `frontend/components/Navbar.tsx` | 重构 | P3-1 |
| `frontend/components/layout/SideNav.tsx` | 可能微调 | P3-1 |
| `frontend/components/layout/MobileNav.tsx` | 可能微调 | P3-1 |
| `frontend/e2e/product-detail.spec.ts` | 补充 | P3-2 |
| `frontend/e2e/metrics.spec.ts` | 新建 | P3-2 |
| `frontend/e2e/news.spec.ts` | 新建 | P3-2 |
| `frontend/e2e/settings.spec.ts` | 新建 | P3-2 |
| `frontend/tests/hooks/useDebouncedValue.test.ts` | 新建 | P3-2 |
| `frontend/tests/hooks/useKlineChart.test.ts` | 新建 | P3-2 |
