# 前端全面体检 —— 问题清单与修复方案

> 文档生成日期：2026/05/21
> 技术栈：Next.js 14 + React 18 + TypeScript + Tailwind CSS + lightweight-charts
> 目标：逐条修复后打勾确认，按优先级顺序推进

---

## 总体评分：62 / 100

---

## 修复优先级总览

| 优先级 | 编号 | 问题 | 分级 |
|---|---|---|---|
| P0 | SEC-02 | Token 明文存在 localStorage + SSE URL 传 Token | 严重 |
| P0 | SEC-01 | fetch 无超时控制，网络异常长期挂起 | 严重 |
| P0 | QUAL-01 | 超大组件未拆分（详情页 745 行、Navbar 400 行） | 严重 |
| P0 | QUAL-09 | 多处空 catch 静默吞错 | 严重 |
| P1 | PERF-05 | 无请求缓存，路由切换重复请求 | 建议 |
| P1 | PERF-01 | 未使用路由级懒加载/动态导入 | 建议 |
| P1 | API-06 | 页面不可见时未暂停轮询 | 建议 |
| P1 | API-03 | fetch 无 AbortController，组件卸载可能内存泄漏 | 建议 |
| P1 | FUT-06 | 无交易时段指示器（交易中/休市/夜盘） | 建议 |
| P1 | QUAL-10 | 无 Error Boundary，组件抛错整页白屏 | 建议 |
| P2 | QUAL-11 | 魔法数字未提取为命名常量 | 建议 |
| P2 | PERF-06 | 无 bundle 体积分析工具 | 建议 |
| P2 | BUILD-02 | next.config.js 过于简单，未开启 standalone | 建议 |
| P2 | TEST-02 | 无任何组件渲染测试 | 建议 |
| P2 | TEST-03 | 核心 Hook 无单元测试 | 建议 |
| P2 | A11Y-08 | 操作成功无 toast/成功提示 | 建议 |
| P2 | FUT-07 | 涨跌停无视觉标识 | 建议 |
| P2 | FUT-08 | 价格精度未按品种区分 | 建议 |
| P2 | FUT-10 | 节假日/休市无提示 | 建议 |
| P3 | BUILD-06 | 无前端错误监控（Sentry） | 建议 |
| P3 | BUILD-07 | 无性能埋点（Web Vitals） | 建议 |
| P3 | TEST-04 | 无端到端测试 | 建议 |
| P3 | ARCH-05 | 无自定义 404 页面 | 建议 |
| P3 | ARCH-04 | 表单状态手写，建议引入 React Hook Form | 建议 |

---

## P0 — 致命/严重（必须修复）

---

### SEC-02: Token 明文存储在 localStorage + SSE URL 明文传输 Token

**问题描述**：
1. JWT Token 以明文存储在 `localStorage`，XSS 攻击可直接窃取。
2. SSE 连接将 Token 作为 URL query param 发送，会被记录在：服务器访问日志、浏览器历史、HTTP Referer、代理日志中。

**代码位置**：
- `frontend/lib/api.ts:125-128` — `localStorage.setItem('token', token)`
- `frontend/hooks/useRealtimeQuotes.ts:17-22` — `buildSseUrl` 拼接 `token=${token}`

**修复方案**：

方案 A（推荐，需后端配合）：改为 httpOnly Cookie

1. **后端修改**：登录接口返回 `Set-Cookie: access_token=xxx; HttpOnly; Secure; SameSite=Lax`。
2. **前端修改**：移除所有 `localStorage` Token 读写，改为依赖浏览器自动携带 Cookie。
3. **SSE 修改**：`EventSource` 不支持自定义 header，改用 Cookie 鉴权时无需传 Token。

方案 B（最小改动，无需后端配合）：内存存储 Token + SSE 单独鉴权

1. **Token 改为内存存储**：

```typescript
// frontend/lib/api.ts
class ApiService {
  private token: string | null = null

  setToken(token: string | null) {
    this.token = token
    // 不再写入 localStorage
  }

  getToken(): string | null {
    return this.token
  }

  // 新增：页面刷新后从 Cookie 或 sessionStorage（短期）恢复
  // 但生产环境应走方案 A
}
```

2. **SSE URL 移除 Token**：

```typescript
// frontend/hooks/useRealtimeQuotes.ts
function buildSseUrl(symbols: string[]): string {
  const params = new URLSearchParams()
  for (const s of symbols) params.append('symbols', s)
  return `${API_BASE}/api/realtime/stream?${params.toString()}`
  // Token 由浏览器 Cookie 自动携带，或通过独立 /auth/sse-token 接口获取短期 token
}
```

3. **后端 SSE 接口改为读取 Cookie 鉴权**。

**过渡方案（当前不做后端改动时）**：
- 至少将 SSE Token 改为通过 POST 获取短期 token（如 5 分钟有效期），再用该短期 token 连接 SSE，降低泄露窗口。

---

### SEC-01: fetch 无超时控制

**问题描述**：`fetch` 默认无超时，网络异常时请求会挂起 300s 以上，用户长时间看到 loading 态。

**代码位置**：`frontend/lib/api.ts:139-169`

**修复方案**：在 `request` 方法中增加 `AbortController` 和超时逻辑。

```typescript
// frontend/lib/api.ts
private async request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }

  const token = this.getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), 15000) // 15s 超时

  let response: Response
  try {
    response = await fetch(`${API_BASE}${url}`, {
      ...options,
      headers,
      signal: controller.signal,
    })
  } catch (err) {
    window.clearTimeout(timeoutId)
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ApiError('请求超时，请检查网络连接', 0, 'TIMEOUT')
    }
    throw new ApiError(err instanceof Error ? err.message : 'Network request failed', 0, 'NETWORK_ERROR')
  } finally {
    window.clearTimeout(timeoutId)
  }
  // ... 后续逻辑不变
}
```

同理修改 `login` 方法中的 `fetch` 调用。

---

### QUAL-01: 超大组件未拆分

**问题描述**：
- `app/products/[id]/page.tsx` 745 行，包含：品种信息展示、K线图表区、周期切换、技术分析、评论面板、支撑位/阻力位编辑器、交易信息、自选按钮。
- `components/Navbar.tsx` 400 行，包含：导航栏布局、登录弹窗、注册弹窗、ModalShell。

**代码位置**：
- `frontend/app/products/[id]/page.tsx`
- `frontend/components/Navbar.tsx`

**修复方案**：

**1. 拆分 `app/products/[id]/page.tsx`**

新建以下组件文件：

```
frontend/components/product/
├── ProductHeader.tsx        # 品种标题 + 自选按钮 + 返回
├── KlineSection.tsx         # K线图表 + 周期/数据源切换
├── TradingInfoPanel.tsx     # 交易信息（保证金、手续费等）
├── LevelEditor.tsx          # 支撑位/阻力位编辑器（已存在，提取为独立文件）
├── CommentSection.tsx       # 评论区
└── WatchlistButton.tsx      # 自选按钮（已存在，提取为独立文件）
```

**2. 拆分 `components/Navbar.tsx`**

新建以下组件文件：

```
frontend/components/auth/
├── ModalShell.tsx           # 弹窗外壳（已存在 LoginModal/RegisterModal 内，提取）
├── LoginModal.tsx           # 登录弹窗
└── RegisterModal.tsx        # 注册弹窗
```

注意：LoginModal 和 RegisterModal 已在 Navbar.tsx 内定义为局部组件，直接提取到独立文件即可。

**重构后的 page.tsx 目标长度**：< 150 行。

---

### QUAL-09: 多处空 catch 静默吞错

**问题描述**：多个异步操作的错误被空 catch 块吞掉，用户无感知，也无法排查问题。

**代码位置**：
- `frontend/app/products/[id]/page.tsx:203-206` — 详情页轮询失败
- `frontend/app/products/[id]/page.tsx:566-568` — WatchlistButton 操作失败
- `frontend/hooks/usePriceLevels.ts:96-99, 131-134, 146-149, 166-169, 185-188` — 价位操作失败
- `frontend/app/workspace/page.tsx:86-91` — 删除自选失败

**修复方案**：

1. **统一错误日志**：至少使用 `console.error` 记录。
2. **用户反馈**：使用 toast 或内联错误提示告知用户。

```typescript
// 示例：WatchlistButton
const handleClick = async () => {
  try {
    if (isInWatchlist && watchlistId != null) {
      await api.deleteWatchlist(watchlistId)
      onToggle(false, null)
    } else {
      const item = await api.createWatchlist(varietyId)
      onToggle(true, item.id)
    }
  } catch (err) {
    console.error('自选操作失败:', err)
    // 方案 A：通过回调通知父组件显示错误
    onError?.(err instanceof Error ? err.message : '操作失败，请重试')
    // 方案 B：全局 toast（需先实现 toast 组件）
    // showToast('error', '自选操作失败，请重试')
  }
}
```

```typescript
// 示例：usePriceLevels
for (const price of support) {
  await api.createPriceLevel(varietyId, 'support', price.toFixed(2)).catch((err) => {
    console.error('导入支撑位失败:', err)
  })
}
```

**推荐补充**：在 `lib/api.ts` 中增加全局错误拦截器，统一上报或日志记录。

---

## P1 — 重要（建议尽快修复）

---

### PERF-05: 无请求缓存，路由切换重复请求

**问题描述**：每次进入页面都重新请求数据，无缓存机制。例如从工作台切换到品种详情再返回，所有数据重新加载。

**代码位置**：全局

**修复方案**：引入 SWR 或 TanStack Query。

**方案 A：SWR（轻量，改动小）**

```bash
cd frontend && npm install swr
```

```typescript
// 封装 useSWR hook
import useSWR from 'swr'
import { api } from '@/lib/api'

export function useProducts() {
  return useSWR('products', api.getProducts.bind(api), {
    refreshInterval: 30000,
    revalidateOnFocus: false,
  })
}

export function useProduct(id: number) {
  return useSWR(`product-${id}`, () => api.getProduct(id), {
    refreshInterval: 30000,
  })
}
```

**方案 B：TanStack Query（功能更全）**

```bash
cd frontend && npm install @tanstack/react-query
```

在 `layout.tsx` 中包裹 `QueryClientProvider`。

**建议**：如果当前项目规模不大，SWR 足够；如果后续需要乐观更新、离线缓存，用 TanStack Query。

---

### PERF-01: 未使用路由级懒加载/动态导入

**问题描述**：所有组件同步加载，KlineChart（依赖 lightweight-charts）在首屏就加载，增加首屏 bundle。

**代码位置**：`frontend/app/products/[id]/page.tsx` 直接 import KlineChart

**修复方案**：使用 `next/dynamic` 懒加载重型组件。

```typescript
// frontend/app/products/[id]/page.tsx
import dynamic from 'next/dynamic'

const KlineChart = dynamic(() => import('@/components/KlineChart'), {
  ssr: false, // lightweight-charts 依赖 DOM，禁用 SSR
  loading: () => <div className="h-[520px] animate-pulse rounded-lg bg-slate-800" />,
})
```

**其他可懒加载的组件**：
- `TechnicalAnalysisPanel` — 纯计算组件，可懒加载
- `CommentSection` — 页面下方，非首屏关键

---

### API-06: 页面不可见时未暂停轮询

**问题描述**：用户切换到其他标签页，轮询仍在后台运行，浪费资源。

**代码位置**：`frontend/hooks/useMarketPolling.ts:128`

**修复方案**：监听 `document.visibilitychange`，页面隐藏时暂停轮询，恢复时立即刷新。

```typescript
// frontend/hooks/useMarketPolling.ts
useEffect(() => {
  if (!enabled) {
    setLoading(false)
    setHeartbeat((current) => ({ ...current, status: 'stale', nextRefreshAt: undefined }))
    return
  }

  setLoading(runOnMount)
  // ...

  const interval = window.setInterval(refresh, intervalMs)

  const handleVisibilityChange = () => {
    if (document.hidden) {
      // 页面隐藏：不清除 interval，但跳过执行
      // 或者清除 interval，恢复时重新启动
      window.clearInterval(interval)
    } else {
      // 页面恢复：立即刷新一次
      refresh()
      // 重新启动 interval（需要重新赋值）
    }
  }

  document.addEventListener('visibilitychange', handleVisibilityChange)

  return () => {
    window.clearInterval(interval)
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  }
}, [enabled, intervalMs, refresh, runOnMount])
```

**更完善的实现**：使用 ref 保存 interval id，在 visibility change 时动态启停。

---

### API-03: fetch 无 AbortController，组件卸载可能内存泄漏

**问题描述**：组件卸载时正在进行的 `fetch` 请求不会被取消，`setState` 可能在已卸载的组件上执行。

**代码位置**：`frontend/lib/api.ts:139-169`

**修复方案**：`request` 方法返回 `AbortController`，调用方在 cleanup 时 abort。

```typescript
// frontend/lib/api.ts
private async request<T>(
  url: string,
  options: RequestInit = {},
  signal?: AbortSignal
): Promise<T> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), 15000)

  const finalSignal = signal
    ? AbortSignal.any([signal, controller.signal]) // 合并外部 signal 和内部超时 signal
    : controller.signal

  try {
    const response = await fetch(`${API_BASE}${url}`, {
      ...options,
      headers,
      signal: finalSignal,
    })
    // ...
  } finally {
    window.clearTimeout(timeoutId)
  }
}
```

调用方在 `useEffect` cleanup 中 abort：

```typescript
useEffect(() => {
  const controller = new AbortController()
  api.getProducts({ signal: controller.signal })
    .then(setProducts)
    .catch((err) => {
      if (err.name !== 'AbortError') setError(err.message)
    })
  return () => controller.abort()
}, [])
```

**注意**：`AbortSignal.any` 是较新的 API，需确认目标浏览器支持，或手动实现合并逻辑。

---

### FUT-06: 无交易时段指示器

**问题描述**：用户无法判断当前是否在交易时段内，不知道看到的行情数据是否是实时有效数据。

**代码位置**：全局

**修复方案**：

1. **新增交易时段判断工具**：

```typescript
// frontend/lib/trading-hours.ts
export type MarketSession = 'pre-market' | 'day' | 'night' | 'closed'

interface TradingHours {
  day: { start: string; end: string }    // 如 09:00-15:00
  night?: { start: string; end: string }  // 如 21:00-02:30
}

const DEFAULT_HOURS: TradingHours = {
  day: { start: '09:00', end: '15:00' },
  night: { start: '21:00', end: '02:30' },
}

export function getCurrentSession(hours: TradingHours = DEFAULT_HOURS): MarketSession {
  const now = new Date()
  const timeStr = now.toLocaleTimeString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

  const timeToMinutes = (t: string) => {
    const [h, m] = t.split(':').map(Number)
    return h * 60 + m
  }

  const currentMinutes = timeToMinutes(timeStr)
  const dayStart = timeToMinutes(hours.day.start)
  const dayEnd = timeToMinutes(hours.day.end)

  // 夜盘跨天判断
  if (hours.night) {
    const nightStart = timeToMinutes(hours.night.start)
    const nightEnd = timeToMinutes(hours.night.end)
    if (nightStart < nightEnd) {
      // 不跨天（如 21:00-23:00）
      if (currentMinutes >= nightStart && currentMinutes <= nightEnd) return 'night'
    } else {
      // 跨天（如 21:00-02:30）
      if (currentMinutes >= nightStart || currentMinutes <= nightEnd) return 'night'
    }
  }

  if (currentMinutes >= dayStart && currentMinutes <= dayEnd) return 'day'
  if (currentMinutes >= dayEnd && hours.night && currentMinutes < timeToMinutes(hours.night.start)) return 'closed'

  return 'closed'
}
```

2. **在页面头部显示交易状态**：

```tsx
// 新增组件 components/market/MarketSessionBadge.tsx
export default function MarketSessionBadge() {
  const session = getCurrentSession()
  const config = {
    'day': { label: '日盘交易中', color: 'text-emerald-400 bg-emerald-400/10' },
    'night': { label: '夜盘交易中', color: 'text-amber-400 bg-amber-400/10' },
    'closed': { label: '休市中', color: 'text-slate-400 bg-slate-400/10' },
  }
  const { label, color } = config[session]
  return <span className={`rounded px-2 py-1 text-xs ${color}`}>{label}</span>
}
```

---

### QUAL-10: 无 Error Boundary

**问题描述**：React 组件抛错时整页白屏，无优雅降级。

**代码位置**：全局

**修复方案**：添加 Error Boundary。

```tsx
// frontend/components/ErrorBoundary.tsx
'use client'

import { Component, ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo)
    // 可接入 Sentry: Sentry.captureException(error, { extra: errorInfo })
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="flex min-h-[400px] flex-col items-center justify-center rounded-lg border border-red-900/50 bg-red-950/20 p-8 text-center">
          <h2 className="text-lg font-semibold text-red-300">页面出现错误</h2>
          <p className="mt-2 text-sm text-slate-400">
            {this.state.error?.message ?? '未知错误'}
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 rounded-lg bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
          >
            刷新页面
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
```

在 `layout.tsx` 中包裹：

```tsx
<ErrorBoundary>
  <AuthProvider>{children}</AuthProvider>
</ErrorBoundary>
```

---

## P2 — 改进项（建议修复）

---

### QUAL-11: 魔法数字未提取为命名常量

**问题描述**：多处硬编码数字，含义不清晰。

**代码位置**：
- `frontend/hooks/useMarketPolling.ts:32` — `30000`（轮询间隔）
- `frontend/hooks/useRealtimeQuotes.ts:7-8` — `3000`, `10000`（SSE 重试延迟、轮询间隔）
- `frontend/components/KlineChart.tsx:65` — `520`（图表高度）
- `frontend/app/products/[id]/page.tsx:47-55` — `120`, `100`, `90`（K线 limit）
- `frontend/components/activity/RefreshStatus.tsx:22-23` — `60000`, `300000`（陈旧阈值）

**修复方案**：新建常量配置文件。

```typescript
// frontend/lib/constants.ts
export const MARKET = {
  POLL_INTERVAL_MS: 30_000,
  SSE_RETRY_DELAY_MS: 3_000,
  SSE_FALLBACK_INTERVAL_MS: 10_000,
  STALE_THRESHOLD_MS: 60_000,
  DANGER_THRESHOLD_MS: 300_000,
} as const

export const CHART = {
  HEIGHT: 520,
  PRICE_DIGITS: 2,
} as const

export const KLINE = {
  SHORT_PERIOD_LIMIT: 120,   // 1m/5m/15m/30m
  MEDIUM_PERIOD_LIMIT: 100,  // 1h
  LONG_PERIOD_LIMIT: 90,     // 1d/1w
} as const
```

---

### PERF-06: 无 Bundle 体积分析工具

**问题描述**：无法评估打包体积，无法发现体积膨胀问题。

**修复方案**：安装分析工具。

```bash
cd frontend && npm install --save-dev @next/bundle-analyzer
```

```javascript
// frontend/next.config.js
const withBundleAnalyzer = require('@next/bundle-analyzer')({
  enabled: process.env.ANALYZE === 'true',
})

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
}

module.exports = withBundleAnalyzer(nextConfig)
```

使用：
```bash
cd frontend && ANALYZE=true npm run build
```

---

### BUILD-02: next.config.js 过于简单

**问题描述**：未开启 standalone 输出，Docker 部署时需要完整 node_modules。

**代码位置**：`frontend/next.config.js`

**修复方案**：

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',          // 生成独立部署包
  poweredByHeader: false,        // 隐藏 X-Powered-By
  compress: true,                // 启用 gzip
  images: {
    unoptimized: true,           // 若不用 Next.js Image 优化，设为 true
  },
  // productionBrowserSourceMaps: false, // 明确关闭生产 source map
}

module.exports = nextConfig
```

---

### TEST-02 / TEST-03: 测试覆盖率低

**问题描述**：仅 2 个 format 测试文件，无任何组件测试和 Hook 测试。

**修复方案**：

1. **组件测试示例（QuoteCard）**：

```tsx
// frontend/tests/components/QuoteCard.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import QuoteCard from '@/components/market/QuoteCard'
import { Product } from '@/lib/api'

const mockProduct: Product = {
  id: 1,
  name: '螺纹钢主力',
  symbol: 'RB2501',
  current_price: 3500.5,
  change_percent: 1.25,
  open_price: 3450,
  high: 3520,
  low: 3440,
  volume: 1234567,
  category: '黑色金属',
  margin: 10,
  commission: 5,
  updated_at: '2026-05-21T08:00:00.000Z',
}

describe('QuoteCard', () => {
  it('renders product name and symbol', () => {
    render(<QuoteCard product={mockProduct} />)
    expect(screen.getByText('螺纹钢主力')).toBeInTheDocument()
    expect(screen.getByText('RB2501')).toBeInTheDocument()
  })

  it('renders formatted price', () => {
    render(<QuoteCard product={mockProduct} />)
    expect(screen.getByText('3,500.50')).toBeInTheDocument()
  })

  it('renders placeholder for null price', () => {
    const noPrice = { ...mockProduct, current_price: null }
    render(<QuoteCard product={noPrice} />)
    expect(screen.getByText('--')).toBeInTheDocument()
  })
})
```

2. **Hook 测试示例（useMarketPolling）**：

```tsx
// frontend/tests/hooks/useMarketPolling.test.ts
import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { useMarketPolling } from '@/hooks/useMarketPolling'

describe('useMarketPolling', () => {
  it('should fetch data on mount when enabled', async () => {
    const fetcher = vi.fn().mockResolvedValue(['item1', 'item2'])

    const { result } = renderHook(() =>
      useMarketPolling({
        enabled: true,
        fetcher,
        intervalMs: 1000,
      })
    )

    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(['item1', 'item2'])
  })

  it('should not fetch when disabled', async () => {
    const fetcher = vi.fn().mockResolvedValue([])

    const { result } = renderHook(() =>
      useMarketPolling({
        enabled: false,
        fetcher,
      })
    )

    expect(result.current.loading).toBe(false)
    expect(fetcher).not.toHaveBeenCalled()
  })
})
```

---

### A11Y-08: 操作成功无反馈

**问题描述**：用户添加自选、发表评论、添加支撑位等操作成功后，没有任何视觉反馈。

**修复方案**：实现轻量级 Toast 系统。

```tsx
// frontend/components/ui/Toast.tsx + ToastProvider.tsx
// 或使用 sonner 库
```

```bash
cd frontend && npm install sonner
```

```tsx
// frontend/app/layout.tsx
import { Toaster } from 'sonner'

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>
        <AuthProvider>
          {children}
          <Toaster position="top-right" theme="dark" />
        </AuthProvider>
      </body>
    </html>
  )
}
```

使用示例：
```tsx
import { toast } from 'sonner'

// 发表评论成功后
toast.success('评论已发表')

// 添加自选成功后
toast.success('已加入自选')

// 操作失败时
toast.error('操作失败，请重试')
```

---

### FUT-07: 涨跌停无视觉标识

**问题描述**：价格达到涨跌停时，用户无法从视觉上区分。

**修复方案**：

1. 后端接口返回涨跌停价格字段（`limit_up`, `limit_down`）。
2. 前端比较当前价格与涨跌停价：

```tsx
// 在 QuoteCard / QuoteTable 中增加判断
function isLimitUp(price: number, limitUp?: number | null) {
  return limitUp != null && Math.abs(price - limitUp) < 0.01
}

function isLimitDown(price: number, limitDown?: number | null) {
  return limitDown != null && Math.abs(price - limitDown) < 0.01
}

// 渲染时增加标签
{isLimitUp(product.current_price, product.limit_up) && (
  <span className="rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white">涨停</span>
)}
{isLimitDown(product.current_price, product.limit_down) && (
  <span className="rounded bg-green-600 px-1.5 py-0.5 text-[10px] font-bold text-white">跌停</span>
)}
```

---

### FUT-08: 价格精度未按品种区分

**问题描述**：所有品种统一 2 位小数，但不同期货品种精度要求不同。

**修复方案**：

1. 后端 `Product` / `Variety` 类型增加 `price_tick` 或 `price_precision` 字段。
2. 前端 `formatNumber` 支持按品种精度格式化。

```typescript
// frontend/lib/format.ts
export function formatPrice(value: number | null | undefined, precision?: number) {
  return formatNumber(value, precision ?? 2)
}

// 使用示例
formatPrice(product.current_price, product.price_precision)
```

常见品种精度参考：
- 股指期货：1 位小数
- 黄金：2 位小数
- 螺纹钢：1 位小数
- 原油：1 位小数

---

### FUT-10: 节假日/休市无提示

**问题描述**：节假日期间无明确提示，可能显示过期数据。

**修复方案**：

1. 后端接口返回 `market_status` 字段（`trading` / `closed` / `holiday`）。
2. 前端根据状态显示提示：

```tsx
// 在页面顶部显示
{marketStatus === 'holiday' && (
  <div className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
    今日为节假日休市，显示数据为上一交易日收盘数据
  </div>
)}
```

---

## P3 — 锦上添花（有余力时修复）

---

### BUILD-06: 无前端错误监控

**修复方案**：接入 Sentry。

```bash
cd frontend && npm install @sentry/nextjs
```

配置 `sentry.client.config.ts` 和 `sentry.server.config.ts`。

---

### BUILD-07: 无性能埋点

**修复方案**：使用 `web-vitals` 库上报 Core Web Vitals。

```bash
cd frontend && npm install web-vitals
```

```typescript
// frontend/lib/vitals.ts
import { onCLS, onFID, onFCP, onLCP, onTTFB } from 'web-vitals'

export function reportWebVitals(onReport: (metric: any) => void) {
  onCLS(onReport)
  onFID(onReport)
  onFCP(onReport)
  onLCP(onReport)
  onTTFB(onReport)
}
```

---

### ARCH-05: 无自定义 404 页面

**修复方案**：

```tsx
// frontend/app/not-found.tsx
export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-950 text-white">
      <h1 className="text-4xl font-bold">404</h1>
      <p className="mt-2 text-slate-400">页面不存在</p>
      <a href="/" className="mt-4 text-red-400 hover:underline">返回工作台</a>
    </div>
  )
}
```

---

### ARCH-04: 表单状态手写

**修复方案**：复杂表单（如登录注册）引入 React Hook Form。

```bash
cd frontend && npm install react-hook-form zod @hookform/resolvers
```

---

## 附录 A：修复检查清单

按优先级顺序推进，修复后打勾：

### P0
- [ ] SEC-02: Token 存储方式改为 httpOnly Cookie 或内存存储
- [ ] SEC-02: SSE URL 不再明文传输 Token
- [ ] SEC-01: fetch 增加 15s 超时（AbortController）
- [ ] QUAL-01: 拆分 `app/products/[id]/page.tsx`（目标 < 150 行）
- [ ] QUAL-01: 拆分 `components/Navbar.tsx`（提取 LoginModal/RegisterModal）
- [ ] QUAL-09: 所有空 catch 块增加 console.error + 用户反馈

### P1
- [ ] PERF-05: 引入 SWR 或 TanStack Query 做请求缓存
- [ ] PERF-01: KlineChart 使用 `next/dynamic` 懒加载
- [ ] API-06: useMarketPolling 监听 visibilitychange 暂停/恢复
- [ ] API-03: fetch 支持外部 AbortSignal
- [ ] FUT-06: 新增交易时段指示器组件
- [ ] QUAL-10: 添加 ErrorBoundary

### P2
- [ ] QUAL-11: 提取魔法数字到 `lib/constants.ts`
- [ ] PERF-06: 安装 @next/bundle-analyzer
- [ ] BUILD-02: next.config.js 开启 standalone
- [ ] TEST-02: QuoteCard 组件测试
- [ ] TEST-03: useMarketPolling Hook 测试
- [ ] A11Y-08: 接入 sonner Toast
- [ ] FUT-07: 涨跌停视觉标识
- [ ] FUT-08: 价格精度按品种区分
- [ ] FUT-10: 节假日休市提示

### P3
- [ ] BUILD-06: 接入 Sentry
- [ ] BUILD-07: Web Vitals 性能埋点
- [ ] TEST-04: 核心用户路径 E2E 测试
- [ ] ARCH-05: 自定义 404 页面
- [ ] ARCH-04: 登录注册表单使用 React Hook Form

---

## 附录 B：代码风格约定

修复过程中遵循以下约定：

1. **组件长度**：单个文件 < 150 行，超过则拆分。
2. **命名**：组件 PascalCase、hooks useXxx、工具函数动词开头。
3. **错误处理**：禁止空 catch，必须 `console.error` + 用户反馈至少二选一。
4. **类型安全**：禁止裸 `any`，接口返回类型与前端类型分离。
5. **常量**：禁止魔法数字，提取到 `lib/constants.ts`。
6. **测试**：每新增/修改一个工具函数或 hook，同步补充测试。
