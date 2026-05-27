# 前端可执行迭代文档 v4

> 迭代目标：基于 FRONTEND_QUALITY_AUDIT_V4_20260526 的审计结论，逐项修复并亮绿灯
> 迭代周期：建议 1 周（P0 半天 + P1 2-3 天 + P2 2-3 天）
> 验收原则：**所有修改必须通过 lint、tsc、test、build、e2e 五重门禁**

---

## 迭代概览

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 0: 依赖可复现性  (0.5 天)                            │
│  ├─ T0.1 声明 react-hook-form 依赖                          │
│  └─ T0.2 干净环境验证                                        │
├─────────────────────────────────────────────────────────────┤
│  Phase 1: 运行时架构债  (2-3 天)                            │
│  ├─ T1.1 构建 RealtimeProvider（SSE 连接复用 + 批处理）     │
│  ├─ T1.2 监控闭环：sentry-lite / web-vitals 真实上报        │
│  ├─ T1.3 消除静默 catch，统一错误语义                       │
│  └─ T1.4 补充 SSE fallback 测试                             │
├─────────────────────────────────────────────────────────────┤
│  Phase 2: 降低迭代摩擦  (2-3 天)                            │
│  ├─ T2.1 拆分 KlineChart.tsx                                │
│  ├─ T2.2 A11y 测试增强                                      │
│  ├─ T2.3 性能基线（Lighthouse / Playwright trace）          │
│  ├─ T2.4 数据层策略统一（SWR 评估与迁移）                   │
│  └─ T2.5 设计 token 彻底化                                  │
└─────────────────────────────────────────────────────────────┘
```

**前置条件**：在干净环境执行 `cd frontend && npm ci`，确认所有门禁通过后再开始 Phase 1。

---

## Phase 0：依赖可复现性（P0）

### T0.1 声明 react-hook-form 依赖

**问题描述**：`LoginModal.tsx` / `RegisterModal.tsx` 直接 import `react-hook-form`，但 `frontend/package.json` 未声明。当前构建成功是因为根目录 `node_modules/react-hook-form` 存在，干净安装会失败。

**涉及文件**：
- `frontend/package.json`
- `frontend/package-lock.json`

**执行步骤**：
1. 确认当前使用的 `react-hook-form` 版本：`npm ls react-hook-form`（从根目录 node_modules 读取）
2. 在 `frontend/package.json` 的 `dependencies` 中添加：
   ```json
   "react-hook-form": "^7.54.0"
   ```
   （版本号以实际 `npm ls` 输出为准，保持与当前行为一致）
3. 删除根目录 `node_modules/react-hook-form`（模拟干净环境）
4. 在 `frontend/` 下执行 `npm install` 生成 lock 文件

**验收标准**：
- [ ] `cd frontend && npm ls react-hook-form` 输出包含版本号，无 `extraneous` / `missing` 标记
- [ ] `npx tsc --noEmit` 通过
- [ ] `npm run lint` 通过
- [ ] `npm run test` 通过
- [ ] `npm run build` 通过

---

### T0.2 干净环境验证

**问题描述**：当前门禁通过可能依赖根目录 node_modules 的隐式依赖传递，需验证干净环境下的可复现性。

**执行步骤**：
1. 备份并删除 `frontend/node_modules` 和 `frontend/package-lock.json`
2. 删除根目录 `node_modules/react-hook-form`（确保没有隐式兜底）
3. 执行 `cd frontend && npm install`
4. 顺序执行以下命令并记录输出：
   ```bash
   cd frontend
   npm.cmd ls next
   npm.cmd ls react-hook-form
   npx.cmd tsc --noEmit
   npm.cmd run lint
   npm.cmd run test
   npm.cmd run build
   ```
5. 确认 `npm.cmd ls react-hook-form` 不再出现 `extraneous`

**验收标准**：
- [ ] 上述 6 条命令全部成功退出（exit code 0）
- [ ] `npm.cmd ls next` 输出 `next@14.2.35`
- [ ] `npm.cmd ls react-hook-form` 输出对应版本且无 warning

---

## Phase 1：运行时架构债（P1）

### T1.1 构建 RealtimeProvider（SSE 连接复用 + 批处理）

**问题描述**：当前 `useRealtimeQuotes` 每个调用者独立创建 `EventSource`。行情列表页和详情页同时存在时，会建立多条 SSE 连接。高频消息逐条 `setQuotes(new Map(...))` 可能造成 render 抖动。

**目标**：
1. 同页相同 symbols 集合复用同一条 SSE 连接
2. 多订阅者通过 store/observer 模式分发数据
3. 高频消息批处理（100ms 节流）后再触发 React setState
4. 暴露连接状态、降级次数、最近错误

**涉及文件**：
- **新建** `frontend/lib/realtime/RealtimeStore.ts` — 全局 SSE 连接管理器
- **新建** `frontend/lib/realtime/RealtimeProvider.tsx` — React Context 封装
- **新建** `frontend/lib/realtime/useRealtimeSubscription.ts` — 订阅 hook
- **修改** `frontend/hooks/useRealtimeQuotes.ts` — 迁移到 RealtimeProvider
- **修改** `frontend/hooks/useProductListRealtime.ts` — 适配新接口
- **修改** `frontend/hooks/useProductPolling.ts` — 详情页实时价格也走 RealtimeProvider
- **修改** `frontend/app/layout.tsx` — 在根布局注入 RealtimeProvider

**技术方案**：

```typescript
// RealtimeStore.ts 核心思路（非最终代码，仅方案示意）

class RealtimeStore {
  private es: EventSource | null = null
  private symbols: Set<string> = new Set()
  private subscribers = new Map<string, Set<(quote: RealtimeQuote) => void>>()
  private batchQueue: RealtimeQuote[] = []
  private batchTimer: number | null = null
  private source: 'sse' | 'polling' | null = null
  private error: string | null = null
  private reconnectAttempts = 0

  subscribe(symbols: string[], callback: (quotes: Map<string, RealtimeQuote>) => void): () => void {
    // 1. 注册订阅者
    // 2. 如果 symbols 有变化，重建 SSE 连接（合并所有订阅者的 symbols）
    // 3. 返回 unsubscribe 函数
  }

  private connect() {
    // 1. 关闭旧连接
    // 2. 按合并后的 symbols 建立 EventSource
    // 3. onmessage 时将消息推入 batchQueue，启动 batchTimer
  }

  private flushBatch() {
    // 1. 将 batchQueue 中的 quotes 合并为 Map
    // 2. 通知所有 subscriber
    // 3. 清空 batchQueue
  }

  // 暴露 readonly 状态：source、error、reconnectAttempts
}

export const realtimeStore = new RealtimeStore()
```

**关键约束**：
- 批处理延迟固定 100ms，用 `requestAnimationFrame` 或 `setTimeout` 实现
- 组件 unmount 后必须取消订阅，但连接本身仅在最后一个订阅者离开时才关闭
- 保留现有 fallback 逻辑：SSE 出错 → 轮询降级 → 指数退避重连 SSE
- 保留 visibility 处理：页面 hidden 时关闭连接，visible 时重连
- **不引入新依赖**（不用 zustand/redux，用原生 Map/Set + React Context）

**验收标准**：
- [ ] `npm run test` 通过（包括新增测试）
- [ ] `npm run build` 通过
- [ ] 新增单元测试覆盖：
  - [ ] 多个 hook 订阅相同 symbols 时只建 1 个 EventSource
  - [ ] 新增 symbols 时复用连接并更新订阅参数
  - [ ] 所有订阅者 unmount 后关闭 EventSource
  - [ ] SSE error 后降级到轮询，且只启动 1 个轮询定时器
  - [ ] 高频消息（>10条/100ms）被批处理为 1 次通知
  - [ ] visibility hidden 时关闭连接，visible 时恢复
- [ ] e2e `market.spec.ts` 和 `product-detail.spec.ts` 通过

---

### T1.2 监控闭环：sentry-lite / web-vitals 真实上报

**问题描述**：当前 `sentry-lite.ts` 和 `vitals.ts` 仅输出 console，线上白屏率、加载失败率、SSE 降级率无法定位。

**目标**：
1. `captureException` / `captureMessage` 支持 POST 到 `/api/log/frontend`
2. Web Vitals 支持环境开关和采样率（生产 10%，开发 100%）
3. 上报内容包含：route、user agent、release/head、metric name/value、错误上下文

**涉及文件**：
- **修改** `frontend/lib/sentry-lite.ts`
- **修改** `frontend/lib/vitals.ts`
- **修改** `frontend/components/WebVitalsReporter.tsx`
- **新建** `frontend/tests/lib/sentry-lite.test.ts`
- **新建** `frontend/tests/lib/vitals.test.ts`

**技术方案**：

```typescript
// sentry-lite.ts 改造思路

interface SentryConfig {
  dsn?: string
  enabled?: boolean
  reportUri?: string
  sampleRate?: number
  release?: string
  environment?: string
}

function shouldReport(config: SentryConfig): boolean {
  if (!config.enabled) return false
  if (typeof window === 'undefined') return false
  return Math.random() < (config.sampleRate ?? 1)
}

async function sendToEndpoint(
  type: 'exception' | 'message',
  payload: unknown,
  config: SentryConfig,
) {
  if (!config.reportUri) return
  try {
    await fetch(config.reportUri, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type,
        payload,
        meta: {
          url: window.location.href,
          ua: navigator.userAgent,
          release: config.release,
          environment: config.environment,
          timestamp: new Date().toISOString(),
        },
      }),
      // 使用 keepalive 确保页面卸载时也能发送
      keepalive: true,
    })
  } catch {
    // 上报失败不抛错，避免死循环
  }
}
```

**环境配置**：
- 新增环境变量：
  - `NEXT_PUBLIC_SENTRY_ENABLED` — 是否启用上报（默认 `false`）
  - `NEXT_PUBLIC_SENTRY_SAMPLE_RATE` — 采样率（默认 `0.1`）
  - `NEXT_PUBLIC_SENTRY_REPORT_URI` — 上报端点（默认空）
  - `NEXT_PUBLIC_RELEASE` — 版本号（可用 git HEAD）
- `.env.example` 中补充上述变量

**vitals.ts 改造**：
- 在 `sendToAnalytics` 中增加：当 `reportUri` 存在时 POST 上报
- 增加采样逻辑
- 上报字段：`name`（LCP/CLS/INP/FCP/TTFB）、`value`、`id`、`route`

**验收标准**：
- [ ] `npm run test` 通过（包括新增测试）
- [ ] `npm run build` 通过
- [ ] `captureException` 在 `enabled=true` 时发起 POST 请求
- [ ] `captureException` 在 `enabled=false` 时仅 console，不发请求
- [ ] `captureMessage` 采样率工作正常（mock Math.random）
- [ ] Web Vitals 在 `reportUri` 配置后发起 POST 请求
- [ ] 上报 payload 包含规定的 meta 字段（url, ua, release, environment, timestamp）
- [ ] 上报失败时不抛异常（避免死循环）

---

### T1.3 消除静默 catch，统一错误语义

**问题描述**：多处 `catch(() => null)` 或 `catch((err) => console.error(...))` 静默吞错，用户无感知，开发者线上也看不到。

**涉及文件**：
- **修改** `frontend/hooks/useProductKline.ts`（第 65-68 行，合约加载 catch）
- **修改** `frontend/app/products/[id]/page.tsx`（第 106-110 行，watchlist catch）
- **修改** `frontend/hooks/usePriceLevels.ts`（第 104-111 行、121 行、152 行、190 行、228 行、251 行）

**执行步骤**：

**1. useProductKline.ts 合约加载 catch**
```typescript
// 当前（第 65-68 行）：
}).catch(() => {
  if (cancelled || abortController.signal.aborted) return
  setContracts([])
  setSelectedContractId(null)
})

// 改为：
}).catch((err) => {
  if (cancelled || abortController.signal.aborted) return
  const message = err instanceof Error ? err.message : '合约列表加载失败'
  captureMessage(`合约列表加载失败: ${symbol}, ${message}`, 'error')
  setContracts([])
  setSelectedContractId(null)
})
```

**2. page.tsx watchlist catch**
```typescript
// 当前（第 106-110 行）：
.catch(() => {
  if (!cancelled) {
    setIsInWatchlist(false)
    setWatchlistId(null)
  }
})

// 改为：
.catch((err) => {
  if (!cancelled) {
    captureMessage(`自选状态查询失败: 品种#${varietyId}, ${err instanceof Error ? err.message : '未知错误'}`, 'warning')
    setIsInWatchlist(false)
    setWatchlistId(null)
  }
})
```

**3. usePriceLevels.ts 多处 console.error**
- 第 104-111 行：价位导入失败（`console.error('导入支撑位失败:', err)`）→ 改为 `captureMessage` + toast（通过 `levelError` 已在 UI 展示，但上报缺失）
- 第 121 行：`console.error('加载价位标注失败:', err)` → 已有 `setLevelError`，补 `captureMessage`
- 第 152 行：`console.error('添加支撑位失败:', err)` → 已有 `setLevelError`，补 `captureMessage`
- 第 190 行：`console.error('添加阻力位失败:', err)` → 同上
- 第 228 行：`console.error('删除支撑位失败:', err)` → 已有 `setLevelError`，补 `captureMessage`
- 第 251 行：`console.error('删除阻力位失败:', err)` → 同上

**统一原则**：
- 用户可见的错误：通过已有的 `toast.error` 或组件内 `error` state 展示
- 开发者可见的错误：通过 `captureMessage` 或 `captureException` 上报
- 不再单独 `console.error`（避免生产环境泄露信息）

**验收标准**：
- [ ] `npm run lint` 通过
- [ ] `npm run test` 通过
- [ ] `grep -r "catch(()" frontend/src frontend/hooks frontend/components frontend/lib` 无结果（除测试文件外）
- [ ] `grep -rn "console.error" frontend/src frontend/hooks frontend/components frontend/lib` 仅保留合理的调试输出（数量比当前减少 ≥ 80%）

---

### T1.4 补充 SSE fallback 测试

**问题描述**：`useRealtimeQuotes` 的 fallback 逻辑（SSE error → 轮询降级 → 指数退避重连）缺乏测试覆盖。

**涉及文件**：
- **修改** `frontend/tests/hooks/useRealtimeQuotes.test.tsx`

**测试用例清单**：
1. **SSE 连接失败后启动轮询**：mock EventSource 触发 onerror，验证 `source` 变为 `'polling'`
2. **轮询期间 SSE 重连成功**：mock 定时器推进退避延迟，验证新的 EventSource 被创建且 `source` 恢复 `'sse'`
3. **unmount 后关闭所有资源**：验证 EventSource.close()、clearInterval、clearTimeout 都被调用
4. **visibility hidden 时关闭 SSE**：mock `document.hidden = true`，验证连接关闭
5. **visibility visible 时重连 SSE**：mock `document.hidden = false`，验证重新创建连接
6. **多 symbol 切换时正确处理**：symbols 从 ['A'] 变为 ['A', 'B']，验证旧连接关闭、新连接建立

**验收标准**：
- [ ] `npm run test` 通过
- [ ] `useRealtimeQuotes.test.tsx` 覆盖率 ≥ 85%（语句覆盖）
- [ ] 新增测试用例 ≥ 6 个，覆盖上述清单

---

## Phase 2：降低迭代摩擦（P2）

### T2.1 拆分 KlineChart.tsx

**问题描述**：`components/KlineChart.tsx` 当前约 382 行，集中了 chart 初始化、series 数据更新、price lines/annotations、crosshair tooltip、viewport 管理、右键菜单。后续加更多绘图能力会变脆。

**目标**：按职责拆分为 hooks，保持组件文件 < 200 行

**涉及文件**：
- **新建** `frontend/hooks/useKlineChart.ts` — chart 实例生命周期（createChart / remove / resize）
- **新建** `frontend/hooks/useKlineSeries.ts` — candle + volume series 数据更新
- **新建** `frontend/hooks/useKlinePriceLines.ts` — 支撑/阻力位 price lines
- **新建** `frontend/hooks/useKlineCrosshair.ts` — crosshair move 事件和 tooltip 数据
- **修改** `frontend/components/KlineChart.tsx` — 只保留 JSX 组合和事件转发

**拆分原则**：
- 每个 hook 只负责一个 chart 子系统
- hook 接收 `chartRef`、`seriesRef` 等 ref，不自行创建 chart
- chart 实例仍由 `KlineChart.tsx` 创建，通过 ref 传递给各 hook
- 保持现有 props 接口不变（对外透明）

**验收标准**：
- [ ] `KlineChart.tsx` 行数 < 200 行
- [ ] `npm run test` 通过（现有测试不应因拆分而失败）
- [ ] `npm run build` 通过
- [ ] e2e `product-detail.spec.ts` 通过（K 线交互不受影响）
- [ ] 新增 hook 测试覆盖：
  - [ ] `useKlineChart` — chart 创建、resize、cleanup
  - [ ] `useKlineSeries` — setData 调用
  - [ ] `useKlinePriceLines` — price lines 增删
  - [ ] `useKlineCrosshair` — crosshair move 数据更新

---

### T2.2 A11y 测试增强

**问题描述**：当前弹窗 A11y 实现已接入，但测试覆盖不足。缺少 Tab trap、焦点恢复、键盘导航的自动化验证。

**涉及文件**：
- **修改** `frontend/tests/components/LoginModal.test.tsx`（新建或扩展）
- **修改** `frontend/tests/components/RegisterModal.test.tsx`（新建或扩展）
- **修改** `frontend/e2e/auth.spec.ts`

**测试用例清单**：

**单元测试**（Testing Library）：
1. 弹窗打开后焦点落到 `data-autofocus` 元素（用户名 input）
2. Tab 键在弹窗内循环，不逃出弹窗（最后一个 focusable → 第一个）
3. Shift+Tab 反向循环（第一个 focusable → 最后一个）
4. Escape 键关闭弹窗
5. 点击弹窗 backdrop 关闭弹窗
6. 关闭后焦点回到触发按钮

**e2e 测试**（Playwright）：
1. 键盘全程操作登录：Tab 到用户名 → 输入 → Tab 到密码 → 输入 → Enter 提交
2. 登录成功后焦点回到页面主体（无焦点丢失）

**验收标准**：
- [ ] `npm run test` 通过
- [ ] `npx playwright test e2e/auth.spec.ts` 通过
- [ ] A11y 相关测试 ≥ 8 个

---

### T2.3 性能基线

**问题描述**：build 体积达标，但 Lighthouse / LCP / CLS / INP / 内存均无数据。缺少可量化的性能回归防护。

**目标**：建立本地可运行的性能基线，记录关键指标

**涉及文件**：
- **新建** `frontend/e2e/performance.spec.ts` — Playwright trace + 自定义指标采集
- **修改** `frontend/playwright.config.ts` — 增加 trace 配置
- **新建** `frontend/scripts/perf-baseline.js` — 性能基线记录脚本

**执行步骤**：
1. **Playwright trace**：
   - 在 `playwright.config.ts` 中启用 `trace: 'on-first-retry'` 或 `trace: 'retain-on-failure'`
   - 在 `performance.spec.ts` 中：
     - 登录后访问 `/products`，等待 table 渲染完成
     - 使用 `page.evaluate` 采集 `performance.timing` 数据
     - 访问 `/products/1`，等待 K 线渲染完成，采集相同指标
   - 记录指标：DOMContentLoaded、Load Event、First Paint（如有）、自定义 "table-render-time"、"kline-render-time"

2. **Lighthouse 集成（可选但推荐）**：
   - 安装 `lighthouse` 作为 devDependency
   - 创建 `scripts/lighthouse-baseline.js`，对 `/products` 和 `/products/1` 跑 Lighthouse
   - 记录 Performance 评分、LCP、CLS、TBT
   - 将结果写入 `frontend/perf-baseline.json`

3. **SSE 高频内存测试**：
   - 在 `performance.spec.ts` 中模拟 SSE 高频消息（1000 条 / 10 秒）
   - 使用 Chrome DevTools Protocol 采集 heap snapshot 前后对比
   - 验证无内存泄漏（heap growth < 10%）

**验收标准**：
- [ ] `npx playwright test e2e/performance.spec.ts` 通过
- [ ] 性能基线数据可被记录到 `perf-baseline.json`
- [ ] 脚本在 CI 中可运行（无 GUI 依赖）

---

### T2.4 数据层策略统一（SWR 评估与迁移）

**问题描述**：SWR 已引入（`frontend/lib/swr-hooks.ts`），但主行情列表和详情页仍走手写状态管理。数据层策略不统一导致缓存、重验证、去重语义不一致。

**目标**：评估并迁移核心数据获取到 SWR，制定统一规范

**涉及文件**：
- **修改** `frontend/lib/swr-hooks.ts`
- **修改** `frontend/hooks/useProductListRealtime.ts` — 评估是否迁移列表获取到 SWR
- **修改** `frontend/hooks/useProductPolling.ts` — 评估详情页是否部分走 SWR
- **新建** `frontend/docs/DATA_LAYER_GUIDE.md` — 数据层使用规范

**评估原则**：
1. **适合 SWR 迁移**：
   - 产品列表（`/api/products`）：读多写少、可缓存、可重验证
   - 品种详情（`/api/products/:id`）：读多写少、可缓存
   - 合约列表（`/api/contracts`）：相对稳定，可缓存

2. **不适合 SWR 迁移**：
   - 实时行情推送（SSE）：属于推送而非拉取，SWR 不适合
   - 写操作（评论、价位标注、自选）：用 mutation hook 更合适
   - K 线数据：数据量大、更新频率高，SWR 默认缓存策略可能不适用

**执行步骤**：
1. 扩展 `lib/swr-hooks.ts`，新增：
   - `useProducts(query)` — 封装 `api.getProductsPage`
   - `useProduct(productId)` — 封装 `api.getProduct`
   - `useContracts(varietyId)` — 封装 `api.getContracts`
2. 在 `useProductListRealtime.ts` 中，用 `useProducts` 替代手写的 `loadProducts` + `useState`
3. 在 `useProductPolling.ts` 中，用 `useProduct` 替代手写的 `api.getProduct` 调用
4. 保留 SSE 实时价格合并逻辑不变（SWR 管元数据，SSE 管实时价格）

**数据层规范（DATA_LAYER_GUIDE.md）**：
```markdown
# 数据层使用规范

## 读取操作
- 列表/详情类数据 → SWR（缓存 + 重验证 + 去重）
- 实时推送数据 → SSE / RealtimeProvider（不缓存，只分发）
- 大数据量序列（K线）→ 手写 fetching（避免 SWR 默认缓存膨胀）

## 写入操作
- 表单提交 → react-hook-form + 手写 mutation
- 成功后在 onSuccess 中调用 `mutate()` 刷新 SWR 缓存

## 错误处理
- SWR 错误 → 统一 ErrorBoundary + toast fallback
- SSE 错误 → RealtimeProvider 内部降级，外部通过 `source`/`error` 感知
- Mutation 错误 → 组件级 toast + captureMessage
```

**验收标准**：
- [ ] `npm run test` 通过
- [ ] `npm run build` 通过
- [ ] `lib/swr-hooks.ts` 新增 ≥ 3 个 hook
- [ ] `useProductListRealtime.ts` 使用 SWR 获取产品列表
- [ ] `useProductPolling.ts` 使用 SWR 获取产品详情
- [ ] 数据层规范文档 `DATA_LAYER_GUIDE.md` 存在且通过团队 review
- [ ] e2e `market.spec.ts` 和 `product-detail.spec.ts` 通过

---

### T2.5 设计 token 彻底化

**问题描述**：`lib/constants.ts` 已有部分 chart token，但 UI 中仍有大量硬编码颜色如 `border-[#2a2e39]`、`bg-[#131722]`、`text-slate-400`。Tailwind 的 slate 色阶和自定义 hex 混用，无主题切换能力。

**目标**：将高频使用的自定义颜色提取到 Tailwind theme，减少 JSX 硬编码

**涉及文件**：
- **修改** `frontend/tailwind.config.js`
- **修改** `frontend/lib/constants.ts` — 统一 UI token 命名
- **修改** `frontend/components/KlineChart.tsx`
- **修改** `frontend/components/product/KlineSection.tsx`
- **修改** `frontend/app/products/page.tsx`
- **修改** `frontend/app/products/[id]/page.tsx`

**执行步骤**：

1. **扩展 tailwind.config.js**：
```javascript
module.exports = {
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#10161d',
          elevated: '#1e222d',
          inset: '#131722',
        },
        border: {
          DEFAULT: '#2a2e39',
        },
      },
    },
  },
}
```

2. **统一替换高频硬编码**（按出现频率排序）：
   - `bg-[#10161d]` → `bg-surface`
   - `bg-[#131722]` → `bg-surface-inset`
   - `bg-[#1e222d]` → `bg-surface-elevated`
   - `border-[#2a2e39]` → `border-border`

3. **chart token 统一**：`lib/constants.ts` 中的 `CHART` 常量已在多处使用，确认 KlineChart 和其他 chart 相关组件全部从常量导入。

**不做的范围**（避免迭代膨胀）：
- 不实现主题切换（light/dark 切换）
- 不替换所有 `text-slate-xxx`（Tailwind 色阶可接受）
- 不替换一次性使用的颜色

**验收标准**：
- [ ] `npm run lint` 通过
- [ ] `npm run test` 通过
- [ ] `npm run build` 通过
- [ ] `grep -rn "#2a2e39" frontend/components frontend/app` 无结果
- [ ] `grep -rn "#131722" frontend/components frontend/app` 无结果（chart 初始化代码除外，因为它从常量导入）
- [ ] `grep -rn "#10161d" frontend/components frontend/app` 无结果

---

## 执行顺序与依赖关系

```
T0.1 ──→ T0.2 ──→ T1.3 ──→ T1.4 ──→ T2.1 ──→ T2.2
  │        │        │                    │        │
  │        │        └────→ T1.2 ──→ T2.5         │
  │        │                                      │
  └────────┴────────────────────────────────────→ T2.3
                     │
                     └────→ T2.4（可与 T2.1 并行）
```

**依赖说明**：
- T0.1 → T0.2：必须先声明依赖，再验证干净环境
- T0.2 → 所有其他任务：干净环境验证是后续所有修改的前提
- T1.3（消除静默 catch）依赖 T1.2（监控闭环）中的 `captureMessage` 可用，但当前 `captureMessage` 已存在（只是 console 占位），所以 T1.3 可独立执行
- T1.1（RealtimeProvider）与 T2.4（SWR 迁移）可并行，但建议先做 T1.1 再评估 T2.4，因为 RealtimeProvider 改造会影响数据流
- T2.1（拆分 KlineChart）与 T2.5（设计 token）可并行

**推荐执行顺序**：
1. Day 1 上午：T0.1 + T0.2
2. Day 1 下午：T1.3 + T1.4（同步进行，改动量小）
3. Day 2-3：T1.1（RealtimeProvider，核心任务，需充分测试）
4. Day 3-4：T1.2（监控闭环）+ T2.5（设计 token）
5. Day 4-5：T2.1（拆分 KlineChart）+ T2.4（SWR 迁移评估）
6. Day 5：T2.2（A11y 测试）+ T2.3（性能基线）
7. Day 5 下午：全量回归测试

---

## 最终验收门禁（所有任务完成后必须执行）

在**干净环境**（删除 `frontend/node_modules` 和 `frontend/package-lock.json` 后重新 `npm install`）下顺序执行：

```bash
cd frontend

# 1. 依赖健康检查
npm.cmd ls next
npm.cmd ls react-hook-form
npm.cmd ls swr

# 2. 静态检查
npx.cmd tsc --noEmit
npm.cmd run lint

# 3. 单元测试
npm.cmd run test

# 4. 生产构建
npm.cmd run build

# 5. 端到端测试（需要后端服务运行）
npx.cmd playwright test e2e/

# 6. 性能基线（如后端可用）
npx.cmd playwright test e2e/performance.spec.ts
```

**全部通过标准**：
- [ ] 上述 6 组命令全部 exit code 0
- [ ] `npm.cmd ls` 无 `extraneous` / `missing` / `invalid`
- [ ] `npm run test` 覆盖率：语句覆盖 ≥ 75%，分支覆盖 ≥ 65%
- [ ] `npm run build` 无 warning，FLJS 未超 180 kB 红线
- [ ] e2e 测试全部通过
- [ ] 无新增 `console.error` / `console.warn`（除框架/库自身输出外）

---

## 附录：代码审查 Checklist

提交 PR 前，逐条确认：

- [ ] 所有新增文件有对应的测试文件
- [ ] 所有修改的 hook/component 测试仍通过
- [ ] 无 `any` 类型新增
- [ ] 无 `eslint-disable` 新增（已有注释需说明理由）
- [ ] 所有 `useEffect` 有 cleanup 函数
- [ ] 所有定时器/事件监听在 cleanup 中移除
- [ ] 无硬编码魔法数字（≥3 处使用必须提取到常量）
- [ ] 异步操作有 AbortController 或等效取消机制
- [ ] 错误处理覆盖网络错误、超时、服务端错误、解析错误
- [ ] A11y：表单有 label、弹窗有 dialog 语义、按钮有 type
