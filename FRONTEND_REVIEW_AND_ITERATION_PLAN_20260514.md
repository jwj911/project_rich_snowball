# 前端全方位审查与迭代计划（2026-05-14）

## 1. 审查结论摘要

本次审查范围覆盖 `frontend/app`、`frontend/components`、`frontend/hooks`、`frontend/lib` 及前端工程配置。当前前端整体工程状态可运行，类型和构建闸门通过，但在实时行情架构、K 线组件生命周期、组件拆分、交易域能力缺失、可访问性和测试体系方面仍有明显迭代空间。

前端架构健康度评分：**6.5 / 10**

主要判断：

- 工程基础良好：`npm.cmd run lint`、`npx.cmd tsc --noEmit`、`npm.cmd run build` 均通过。
- 当前并非 Vite/ECharts 技术栈，而是 Next.js App Router + React + Tailwind + lightweight-charts。
- 当前产品形态是行情展示、K 线分析、评论、个人工作区；下单面板、持仓列表、资金账户等交易操作模块尚未实现。
- 最近一次前端迭代主要引入或重构了 `lightweight-charts` K 线图、详情页、首页/列表/工作区，本次审查将这些标记为“本次迭代引入/改动”。

## 2. 技术栈确认

实际技术栈如下：

| 分类 | 实际技术 |
| --- | --- |
| 框架 | Next.js 14.1.0 App Router |
| UI Runtime | React 18.2 |
| 语言 | TypeScript 5.3，`strict: true` |
| 样式 | Tailwind CSS 3.4 |
| 图标 | lucide-react |
| 图表 | lightweight-charts 5.2.0 |
| 状态管理 | React Context + local component state |
| 数据请求 | 自定义 `ApiService` + `fetch` |
| 测试 | 暂无自动化前端测试，仅有人工测试清单 |

生产构建结果：

| Route | First Load JS |
| --- | ---: |
| `/` | 103 kB |
| `/products` | 104 kB |
| `/products/[id]` | 161 kB |
| `/workspace` | 103 kB |
| `/my-comments` | 101 kB |

当前包体积处于健康范围，暂未发现首屏 JS 超过 500 kB 的问题。

## 3. 区分本次迭代与历史遗留

根据 `git show --stat HEAD -- frontend`，最近一次提交 `d718100 feat: optimize frontend chart workspace` 改动如下：

| 文件 | 归类 |
| --- | --- |
| `frontend/components/KlineChart.tsx` | 本次迭代重点改动 |
| `frontend/app/products/[id]/page.tsx` | 本次迭代重点改动 |
| `frontend/app/page.tsx` | 本次迭代小幅改动 |
| `frontend/app/products/page.tsx` | 本次迭代小幅改动 |
| `frontend/app/workspace/page.tsx` | 本次迭代小幅改动 |
| `frontend/package.json` / `package-lock.json` | 本次迭代引入 `lightweight-charts` |

更偏历史遗留的问题：

- API 默认地址与文档不一致。
- 前端无自动化测试体系。
- `Navbar.tsx` 同时承载导航、登录弹窗、注册弹窗。
- token 存储在 `localStorage`。
- 交易操作域尚未实现。
- `.next`、`node_modules`、日志、`tsconfig.tsbuildinfo` 等运行产物出现在未跟踪工作区中。

## 4. P0 致命级问题

### P0-1 默认 API 地址错误，前端开箱即可能不可用

文件：`frontend/lib/api.ts:1`

当前：

```ts
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8200'
```

项目文档、后端默认端口、人工测试清单均指向 `8000`，当前默认值 `8200` 容易导致新环境启动后全部 API 请求失败。

影响：

- 新开发者按 README 启动后，前端默认无法连接后端。
- 环境变量缺失时，登录、行情、评论全部失败。

建议修复：

```ts
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000'
```

同时建议新增环境配置文档：

```env
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
```

优先级：立即修复。

### P0-2 交易操作界面缺失，交易安全无法闭环

审查范围要求覆盖下单面板、持仓列表、资金账户、防重复提交、下单确认等，但当前前端没有相关模块。

影响：

- 如果产品目标包含真实交易，则当前版本不能上线交易功能。
- 无法审查资金展示、重复提交、下单预览、平仓确认、持仓实时同步等交易安全项。

建议先定义交易域最小闭环：

```tsx
type OrderSide = 'buy' | 'sell'
type Offset = 'open' | 'close'

interface OrderPreview {
  symbol: string
  side: OrderSide
  offset: Offset
  price: number
  quantity: number
  estimatedMargin: number
  estimatedFee: number
}
```

交互流程建议：

1. 用户在品种详情页点击“模拟下单”。
2. 打开下单面板，填写方向、开平、价格、手数。
3. 面板实时展示合约、方向、数量、预估保证金、手续费、风险提示。
4. 第一次点击按钮进入确认态，按钮文案变为“确认提交”。
5. 提交中禁用按钮并展示 loading。
6. 成功后展示回执，失败后保留输入并展示可读错误。

优先级：如果近期要做交易功能，则立即补齐；如果当前只做社区行情，则在产品边界中明确“当前不支持交易”。

## 5. P1 严重级问题

### P1-1 KlineChart 每次数据变化都会销毁并重建图表

文件：`frontend/components/KlineChart.tsx:95`

当前 `createChart` 所在 effect 依赖 `[points]`。每当 K 线数据刷新、周期切换、fallback 数据更新时，图表实例会被销毁并重建。

影响：

- 大数据量下性能浪费明显。
- 用户缩放、拖动位置会被重置。
- 十字光标订阅、ResizeObserver 会频繁创建销毁。

建议拆成“一次初始化”和“数据更新”两个 effect：

```tsx
useEffect(() => {
  const container = chartContainerRef.current
  if (!container || chartRef.current) return

  const chart = createChart(container, chartOptions)
  const candleSeries = chart.addSeries(CandlestickSeries, candleOptions)
  const volumeSeries = chart.addSeries(HistogramSeries, volumeOptions)

  chartRef.current = chart
  candleSeriesRef.current = candleSeries
  volumeSeriesRef.current = volumeSeries

  return () => {
    chart.remove()
    chartRef.current = null
    candleSeriesRef.current = null
    volumeSeriesRef.current = null
  }
}, [])

useEffect(() => {
  candleSeriesRef.current?.setData(candleData)
  volumeSeriesRef.current?.setData(volumeData)
}, [candleData, volumeData])
```

优先级：本周修复。

### P1-2 十字光标移动时 O(n) 查找 K 线点

文件：`frontend/components/KlineChart.tsx:176`

当前：

```ts
const matchedPoint = points.find((point) => point.time === seriesData.time)
```

鼠标移动事件触发频繁，数据量上来后会造成不必要的 CPU 消耗。

建议：

```ts
const pointByTime = useMemo(
  () => new Map(points.map((point) => [point.time, point])),
  [points],
)

const matchedPoint = pointByTime.get(seriesData.time)
```

优先级：本周修复。

### P1-3 每次数据刷新都会 `fitContent`，破坏用户缩放位置

文件：`frontend/components/KlineChart.tsx:220`

当前每次 `points` 变化都执行：

```ts
chart.timeScale().fitContent()
```

影响：

- 用户正在看历史区间时，刷新会把视图拉回全量。
- 周期切换可以 fit，增量行情刷新不应 fit。

建议：

```tsx
const hasFitInitialContentRef = useRef(false)

useEffect(() => {
  if (!chartRef.current || points.length === 0) return
  candleSeriesRef.current?.setData(candleData)
  volumeSeriesRef.current?.setData(volumeData)

  if (!hasFitInitialContentRef.current) {
    chartRef.current.timeScale().fitContent()
    hasFitInitialContentRef.current = true
  }
}, [candleData, volumeData, points.length])
```

周期切换时可显式重置 `hasFitInitialContentRef.current = false`。

### P1-4 详情页轮询缺少并发保护和 AbortController

文件：`frontend/app/products/[id]/page.tsx:129`

当前详情页手写 `setInterval`，请求慢时可能出现并发请求和旧响应覆盖新响应。

建议复用 `useMarketPolling`，或增加请求锁：

```tsx
const pollingInFlightRef = useRef(false)

useEffect(() => {
  if (!isAuthenticated || !Number.isFinite(productId)) return

  const tick = async () => {
    if (pollingInFlightRef.current) return
    pollingInFlightRef.current = true
    try {
      const data = await api.getProduct(productId)
      setProduct(data.product)
      if (data.product?.symbol) {
        setRealtime(await api.getRealtime(data.product.symbol))
      }
    } finally {
      pollingInFlightRef.current = false
    }
  }

  const interval = window.setInterval(tick, 30000)
  return () => window.clearInterval(interval)
}, [isAuthenticated, productId])
```

### P1-5 行情列表没有虚拟滚动，移动端和桌面端重复渲染

文件：`frontend/components/market/QuoteTable.tsx:34`

当前移动卡片列表和桌面表格都在 DOM 中，只靠 Tailwind `hidden/md:block` 控制展示。

影响：

- 合约数量少时没问题，数量扩大后会重复创建 DOM。
- 行情刷新时全部行重新渲染，缺少细粒度更新。

建议：

- 引入 `@tanstack/react-virtual`。
- 将 `QuoteTableDesktop` 与 `QuoteListMobile` 拆开。
- 根据 media query 只挂载当前视图。
- 行级组件用 `React.memo`。

示例：

```tsx
const QuoteRow = memo(function QuoteRow({ product }: { product: Product }) {
  return <tr>{/* row cells */}</tr>
})
```

### P1-6 详情页、KlineChart、Navbar 组件过大

文件行数：

| 文件 | 行数 | 问题 |
| --- | ---: | --- |
| `frontend/app/products/[id]/page.tsx` | 567 | 数据请求、K线、评论、价位编辑、交易信息全部混在页面 |
| `frontend/components/KlineChart.tsx` | 408 | 图表初始化、数据清洗、交互菜单、价位标注混在一起 |
| `frontend/components/Navbar.tsx` | 374 | 导航、登录、注册、弹窗 shell 全部混在一起 |

建议拆分：

```text
components/product/ProductHeader.tsx
components/product/KlineSection.tsx
components/product/TradingInfo.tsx
components/product/LevelEditor.tsx
components/product/CommentPanel.tsx
components/auth/AuthModalShell.tsx
components/auth/LoginModal.tsx
components/auth/RegisterModal.tsx
components/chart/useKlineChart.ts
components/chart/KlineAnnotationMenu.tsx
```

目标：页面组件低于 250 行，复杂展示组件低于 300 行。

### P1-7 全局鉴权 Context 更新粒度较粗

文件：`frontend/components/auth/AuthProvider.tsx`

当前所有消费 `useAuth()` 的组件都会随 `user/isLoading/error` 任意字段变化重渲染。

短期可接受，但后续交易、行情连接、用户偏好增加后建议拆分：

- `AuthStateContext`
- `AuthActionsContext`
- 或引入 Zustand selector。

## 6. P2 重要级问题

### P2-1 时间显示没有固定东八区，也没有相对时间

文件：`frontend/lib/format.ts:23`

当前使用运行环境本地时区：

```ts
return date.toLocaleString('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})
```

建议明确中国期货场景：

```ts
export function formatDateTime(value: string | null | undefined) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'

  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date)
}
```

补充相对时间：

```ts
export function formatRelativeTime(value: string | null | undefined) {
  if (!value) return '--'
  const seconds = Math.floor((Date.now() - new Date(value).getTime()) / 1000)
  if (seconds < 60) return `${Math.max(seconds, 0)} 秒前`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}
```

### P2-2 K 线图可访问性不足

文件：`frontend/components/KlineChart.tsx`

问题：

- 图表容器缺少 `aria-label`。
- 右键添加支撑/阻力不适合键盘用户。
- 图表顶部指标对屏幕阅读器不够友好。

建议：

```tsx
<div
  ref={rootRef}
  role="img"
  aria-label={`${symbol} K线图，最新价 ${latestPoint.close.toFixed(2)}，最高 ${maxOf(points, 'high').toFixed(2)}，最低 ${minOf(points, 'low').toFixed(2)}`}
>
  ...
</div>
```

同时保留侧栏 `LevelEditor` 作为完整键盘替代路径。

### P2-3 表单 label 关联不完整

文件：`frontend/components/Navbar.tsx`、`frontend/app/products/page.tsx`、`frontend/app/products/[id]/page.tsx`

当前很多 label 只包裹控件或只视觉展示，没有 `htmlFor/id`，可读性和自动化测试定位较弱。

建议：

```tsx
<label htmlFor="login-username" className="mb-1 block text-sm text-slate-400">
  用户名
</label>
<Input id="login-username" ... />
```

### P2-4 行情变动缺少平滑反馈

文件：`frontend/components/market/QuoteCard.tsx`、`frontend/components/market/QuoteTable.tsx`

目前涨跌颜色符合国内习惯（红涨绿跌），但没有价格跳动高亮。可增加 `PriceFlash`：

```tsx
function PriceFlash({ value }: { value: number | null | undefined }) {
  const previous = useRef(value)
  const [direction, setDirection] = useState<'up' | 'down' | null>(null)

  useEffect(() => {
    if (value == null || previous.current == null || value === previous.current) return
    setDirection(value > previous.current ? 'up' : 'down')
    previous.current = value
    const timer = window.setTimeout(() => setDirection(null), 700)
    return () => window.clearTimeout(timer)
  }, [value])

  return (
    <span className={direction === 'up' ? 'animate-price-up' : direction === 'down' ? 'animate-price-down' : ''}>
      {formatNumber(value)}
    </span>
  )
}
```

### P2-5 Google Fonts 远程 CSS 导入影响性能和稳定性

文件：`frontend/app/globals.css:1`

当前：

```css
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');
```

建议改为 `next/font/google` 或本地字体，避免 CSS 阻塞和外网不可达。

### P2-6 错误处理缺少错误归一化和自动重试策略

文件：`frontend/lib/api.ts`、`frontend/hooks/useMarketPolling.ts`

建议在 API 层提供错误类型：

```ts
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message)
  }
}
```

轮询层根据状态码决定是否重试：

- `401`：登出或要求重新登录。
- `429/5xx/network`：指数退避重试。
- `400/404`：不自动重试。

## 7. P3 优化级问题

### P3-1 前端无自动化测试

当前仅有 `frontend/tests/p0-fixes.test.md` 人工清单。

建议新增：

```json
{
  "scripts": {
    "test": "vitest",
    "test:e2e": "playwright test",
    "type-check": "tsc --noEmit"
  }
}
```

优先测试：

- `format.ts` 格式化函数。
- `useMarketPolling` 轮询清理和错误状态。
- 登录弹窗提交和 loading 锁。
- 品种列表筛选排序。
- K 线周期切换和空数据状态。
- 评论提交防重复。

### P3-2 CI/CD 缺失

建议 GitHub Actions：

```yaml
name: frontend
on:
  pull_request:
    paths:
      - 'frontend/**'
jobs:
  verify:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npx tsc --noEmit
      - run: npm run build
```

### P3-3 监控埋点缺失

建议后续接入：

- Sentry：捕获前端运行时错误、API 错误、chunk 加载失败。
- Web Vitals：首屏、交互延迟。
- 业务埋点：登录、评论、行情刷新失败、K线周期切换、标注新增/删除。

### P3-4 运行产物未跟踪但出现在工作区

当前工作区存在：

- `frontend/.next/`
- `frontend/node_modules/`
- `frontend/frontend*.log`
- `frontend/tsconfig.tsbuildinfo`

建议确认 `.gitignore` 覆盖这些产物，避免后续误提交。

## 8. 逐文件审查摘要

| 文件 | 发现 |
| --- | --- |
| `frontend/app/layout.tsx` | 根布局简单清晰，`AuthProvider` 全局包裹合理。 |
| `frontend/app/page.tsx` | 首页结构清晰，轮询复用 `useMarketPolling`；可增加价格变化动画。 |
| `frontend/app/products/page.tsx` | 筛选排序逻辑清楚；大量合约时需要虚拟滚动和避免移动/桌面重复渲染。 |
| `frontend/app/products/[id]/page.tsx` | 组件过大；轮询缺少并发保护；K线、评论、价位标注、交易信息需要拆分。 |
| `frontend/app/my-comments/page.tsx` | 逻辑可读；`401` 判断依赖错误 message，不够稳。 |
| `frontend/app/workspace/page.tsx` | 本地标注读取逻辑实用；自选仍是占位，需接入真实模型。 |
| `frontend/components/KlineChart.tsx` | 本次迭代核心；应修复图表重建、十字光标查找和缩放重置问题。 |
| `frontend/components/Navbar.tsx` | 功能完整但过大；登录/注册弹窗应拆分；表单 label/id 可加强。 |
| `frontend/components/market/QuoteTable.tsx` | 桌面和移动重复渲染；缺少虚拟滚动。 |
| `frontend/components/market/QuoteCard.tsx` | 展示清晰；可增加价格闪烁/跳动反馈。 |
| `frontend/components/market/PriceChange.tsx` | 红涨绿跌符合国内习惯；建议增加非颜色辅助文本或符号以照顾色盲用户。 |
| `frontend/components/market/TechnicalAnalysisPanel.tsx` | 计算逻辑集中在组件内，后续可抽到 `lib/indicators.ts` 并补单测。 |
| `frontend/hooks/useMarketPolling.ts` | 抽象方向正确；可增强 AbortController、退避重试、页面可见性控制。 |
| `frontend/lib/api.ts` | API 集中管理是好方向；默认端口错误，错误模型和 query 编码需加强。 |
| `frontend/lib/format.ts` | 简洁；需固定 `Asia/Shanghai` 并增加相对时间。 |
| `frontend/app/globals.css` | 主题轻量；Google Fonts `@import` 建议替换。 |

## 9. 本周必须修复 TOP 10

1. 修正 `frontend/lib/api.ts:1` 默认 API 端口为 `8000`。
2. 重构 `frontend/components/KlineChart.tsx`，图表实例只初始化一次。
3. 优化 `KlineChart` 十字光标 `points.find` 为 `Map` 查找。
4. 避免 K 线数据刷新时无条件 `fitContent`。
5. 给 `frontend/app/products/[id]/page.tsx` 轮询加并发保护或复用 `useMarketPolling`。
6. 拆分 `frontend/app/products/[id]/page.tsx` 为 header、K线区、评论区、价位编辑、交易信息组件。
7. 拆分 `frontend/components/Navbar.tsx` 中的登录/注册弹窗。
8. 为 `frontend/components/market/QuoteTable.tsx` 制定虚拟滚动方案。
9. 修正 `frontend/lib/format.ts` 时区为 `Asia/Shanghai` 并补相对时间。
10. 建立前端自动化测试最小集：Vitest + Testing Library，先覆盖 format、polling、筛选排序、评论提交。

## 10. 迭代路线图

### 第 1 阶段：稳定性和开箱可用（1-2 天）

- 修正 API 默认端口。
- 确认 `.gitignore` 覆盖运行产物。
- 增加 `type-check` script。
- 固定时区展示。
- 对 `api.ts` 引入 `ApiError`。

验收标准：

- 不设置 `NEXT_PUBLIC_API_BASE` 时能正常连接默认后端。
- lint/type-check/build 全部通过。
- 页面时间在不同时区机器上显示一致。

### 第 2 阶段：K 线与行情性能（2-4 天）

- 重构 KlineChart 生命周期。
- 优化 crosshair 查找。
- 保留用户缩放位置。
- 行情列表行组件 memo 化。
- 评估并引入虚拟滚动。

验收标准：

- K 线周期切换正常。
- 轮询刷新不重建 chart。
- 用户缩放后刷新不强制回到全量视图。
- 500 条合约列表滚动不卡顿。

### 第 3 阶段：架构拆分与状态管理（3-5 天）

- 拆分详情页大组件。
- 拆分 Navbar/AuthModal。
- 将技术指标计算抽到纯函数模块。
- 评估 Zustand 或 React Query。

验收标准：

- 单文件核心组件不超过 300 行。
- 数据请求和展示组件职责分离。
- 指标计算有单元测试。

### 第 4 阶段：UX、a11y、交易域准备（1 周）

- 增加价格变化反馈。
- K 线图增加 aria 摘要和键盘替代路径。
- 统一表单 label/id。
- 明确交易域产品边界。
- 若要做交易，先实现模拟下单安全闭环。

验收标准：

- 关键交互可键盘完成。
- 涨跌不只依赖颜色表达。
- 下单模块具备预览、确认、loading 锁、回执。

### 第 5 阶段：测试与工程化（长期）

- 引入 Vitest + Testing Library。
- 引入 Playwright E2E。
- 建立 GitHub Actions。
- 接入 Sentry 和 Web Vitals。

验收标准：

- 每个 PR 自动跑 lint/type-check/build/test。
- 关键页面有 E2E smoke test。
- 生产错误可观测。

## 11. 推荐引入的库和工具

| 工具 | 用途 | 引入优先级 |
| --- | --- | --- |
| `@tanstack/react-query` | API 缓存、重试、失焦刷新、请求状态统一 | P1 |
| `@tanstack/react-virtual` | 大量合约行情虚拟滚动 | P1 |
| `zustand` | 用户偏好、自选、行情连接状态等轻量全局状态 | P2 |
| `vitest` | 单元测试和 hooks 测试 | P1 |
| `@testing-library/react` | 组件交互测试 | P1 |
| `playwright` | 登录、行情、K线、评论端到端测试 | P2 |
| `next/font` | 替代远程 CSS 字体导入 | P2 |
| `sentry` | 前端错误监控 | P3 |

## 12. 当前验证记录

在 Windows PowerShell 环境中，直接执行 `npm` / `npx` 会被执行策略拦截，因此使用 `.cmd` 后缀执行。

已通过命令：

```powershell
npm.cmd run lint
npx.cmd tsc --noEmit
npm.cmd run build
```

构建产物显示：

- 编译成功。
- lint 和类型检查成功。
- 静态页面生成成功。
- 最大首屏 JS 为 `/products/[id]` 的 161 kB。

