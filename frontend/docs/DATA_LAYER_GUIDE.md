# 数据层使用规范

## 概述

前端数据层采用 **SWR + SSE** 双轨策略：

- **SWR** 管理静态/半静态数据（产品列表、详情、用户数据），提供缓存、重验证、去重
- **SSE（RealtimeStore）** 管理实时推送数据（行情价格），提供低延迟更新
- **手写 mutation** 管理写操作（评论、价位标注、自选）

## 读取操作

### 1. 列表/详情类数据 → SWR

适合使用 SWR 的场景：
- 产品列表（`/api/products`）— 读多写少、可缓存、可重验证
- 品种详情（`/api/products/:id`）— 读多写少、可缓存
- 用户工作区（`/api/workspace`）— 用户专属数据
- 合约列表（`/api/contracts`）— 相对稳定

已封装的 SWR Hooks（见 `lib/swr-hooks.ts`）：

```typescript
import { useProductsPage, useProductDetail, useContracts, useVariety } from '@/lib/swr-hooks'

// 产品列表（带分页/筛选）
const { data, error, isLoading, mutate } = useProductsPage({ limit: 20, skip: 0 })

// 品种详情
const { data: product } = useProductDetail(productId, enabled)

// 合约列表
const { data: contracts } = useContracts(varietyId, enabled)

// 品种元数据
const { data: variety } = useVariety(symbol)
```

**SWR 默认配置**：
- `refreshInterval: 30_000` — 30 秒自动刷新
- `revalidateOnFocus: false` — 窗口聚焦时不自动刷新（行情数据由 SSE 覆盖）
- `errorRetryCount: 3` — 错误时重试 3 次

### 2. 实时推送数据 → SSE / RealtimeStore

不适合 SWR 的场景：
- 实时行情价格 — 属于服务端推送，SWR 的拉取模式不适用
- 高频更新数据 — SWR 默认缓存策略会造成数据延迟

使用方式：

```typescript
import { useRealtimeQuotes } from '@/hooks/useRealtimeQuotes'

const { quotes, loading, source, error } = useRealtimeQuotes(['RB', 'HC'])
// quotes: Map<string, RealtimeQuote>
// source: 'sse' | 'polling' | null
```

RealtimeStore 内部管理 SSE 连接复用和消息批处理（100ms），多个组件订阅相同 symbols 时只建 1 条连接。

### 3. 大数据量序列 → 手写 fetching

- K 线数据 — 数据量大、更新频率高，避免 SWR 默认缓存膨胀
- 使用 `useProductKline` hook 管理 K 线数据获取

## 写入操作

### 表单提交 → react-hook-form + 手写 mutation

```typescript
const { register, handleSubmit } = useForm()

const onSubmit = handleSubmit(async (data) => {
  const comment = await api.createComment(productId, data.content)
  // 成功后刷新 SWR 缓存
  await mutate('workspace')
})
```

### 写操作后刷新缓存

```typescript
import { mutate } from 'swr'

// 添加自选后刷新工作区数据
await api.createWatchlist(varietyId)
await mutate('workspace')
```

## 错误处理

| 数据类型 | 错误处理策略 |
|---------|------------|
| SWR 错误 | 组件内通过 `error` state 展示，统一 ErrorBoundary 兜底 |
| SSE 错误 | RealtimeProvider 内部降级（SSE → 轮询），外部通过 `source`/`error` 感知 |
| Mutation 错误 | 组件级 toast + `captureMessage` 上报 |

## 混合模式示例

产品列表页同时使用 SWR（元数据）+ SSE（实时价格）：

```typescript
function ProductsPage() {
  // SWR 获取产品列表元数据
  const { data: pageData } = useProductsPage({ limit: 20 })
  
  // SSE 获取实时价格
  const symbols = pageData?.items.map(p => p.symbol) ?? []
  const { quotes } = useRealtimeQuotes(symbols)
  
  // 合并实时价格到产品列表
  const products = useMemo(() => {
    return pageData?.items.map(product => ({
      ...product,
      current_price: quotes.get(product.symbol)?.current_price ?? product.current_price,
    })) ?? []
  }, [pageData, quotes])
}
```

## 何时不迁移到 SWR

以下场景保持手写状态管理：

1. **实时行情推送** — SSE 更适合推送模式
2. **写操作** — mutation 语义更清晰，不需要 SWR 的缓存层
3. **K 线数据** — 数据量大，SWR 缓存会占用大量内存
4. **串行依赖请求** — 如果请求 A 的结果决定请求 B 的参数，且需要统一 loading/error 状态，手写 hook 更直观
