# 前端迭代计划 v6

> 制定日期：2026-05-28
> 依据来源：[FRONTEND_QUALITY_AUDIT_V5_20260527.md](FRONTEND_QUALITY_AUDIT_V5_20260527.md)
> 当前 HEAD：`e0cc4949 T2.2 A11y 测试增强 + T2.3 性能基线`
> 目标：修复 v5 审计遗留的 P0/P1 问题，补全测试缺口，使质量门禁完整可信

---

## 本轮目标

将前端质量评级从 **B+** 推进到 **A-**，核心是把 v5 审计中标记为 P0/P1 的问题收干净：

1. 消除 SSE 订阅稳定性风险（P0）
2. 恢复 build/lint 门禁可证明性（P0）
3. 补齐 RealtimeStore 多订阅复用测试（P1）
4. 处理监控上报闭环（P1）
5. 补 /metrics 页面测试覆盖（P2）
6. 执行一次性能基线采集（P2）

---

## 任务清单

### T1 — SSE 订阅稳定性修复（P0）

**问题描述：**
`useProductPolling` 第 27 行传入 `useRealtimeQuotes(symbol ? [symbol] : [])`，每次 render 都创建新数组。`useRealtimeQuotes` effect 依赖 `[symbols]`，数组引用变化触发退订+重订，详情页在状态更新时会反复关闭并重建 SSE 连接。

**修复方案：**

**方案 A（推荐，改动最小）：** 在 `useProductPolling` 中 memoize symbols 数组。

```ts
// frontend/hooks/useProductPolling.ts
const realtimeSymbols = useMemo(() => (symbol ? [symbol] : []), [symbol])
const { quotes: realtimeQuotes } = useRealtimeQuotes(realtimeSymbols)
```

**方案 B（防御性增强）：** 在 `useRealtimeQuotes` 内部将数组转为稳定 key，减少调用方犯错概率。

```ts
// frontend/hooks/useRealtimeQuotes.ts
const symbolsKey = useMemo(() => symbols.join(','), [symbols])
// effect 依赖改为 [symbolsKey]
```

**验收标准：**
- [ ] `useProductPolling` 使用 `useMemo` 稳定 `symbols` 数组
- [ ] 新增测试：rerender 相同 symbol 不重建 EventSource
- [ ] 新增测试：两个 hook 订阅同 symbol 只创建 1 个 EventSource
- [ ] 新增测试：两个 hook 订阅不同 symbol，连接 URL 包含 union
- [ ] 新增测试：最后一个订阅卸载后关闭 SSE、timer、visibility listener
- [ ] `npm.cmd run test` 全绿

**涉及文件：**
- `frontend/hooks/useProductPolling.ts`
- `frontend/hooks/useRealtimeQuotes.ts`（如选方案 B）
- `frontend/tests/hooks/useRealtimeQuotes.test.tsx`

---

### T2 — 质量门禁修复（P0）

**问题描述：**
`npm.cmd run lint` 和 `npm.cmd run build` 失败于 `frontend/.next/cache` 写入权限 `EPERM`。不是代码错误，但质量门禁无法证明通过。

**修复步骤：**

```powershell
cd frontend
# 1. 清理缓存
Remove-Item -Recurse -Force .next\cache
# 或
npx.cmd next lint --no-cache
npx.cmd next build --no-lint

# 2. 如果仍失败，检查是否有杀毒/IDE 锁定
# 3. 确认不是沙箱权限问题后复跑完整命令
npm.cmd run lint
npm.cmd run build
```

**验收标准：**
- [ ] `npm.cmd run lint` 通过（0 error, 0 warning 或可接受的 warning 清单）
- [ ] `npm.cmd run build` 通过，生成 `frontend/.next/`
- [ ] 记录各路由 First Load JS 体积到本文件「性能基线」章节
- [ ] 如使用 `--no-cache` 绕过，需记录原因并评估是否需要在 CI 中同样处理

**涉及文件：**
- `frontend/.next/cache/`（临时文件，不提交）
- `frontend/next.config.js`（如需要调整 bundle analyzer）

---

### T3 — RealtimeStore 测试补全（P1）

**问题描述：**
当前 `useRealtimeQuotes.test.tsx` 覆盖 open/error/reconnect/visibility/symbol change，但缺少多订阅复用和数组 identity 回归测试。v5 审计发现的 SSE 数组依赖问题正是这类测试缺失的直接后果。

**需补充的测试用例：**

```ts
// 1. 同 symbol 多订阅复用
describe('multi-subscriber reuse', () => {
  it('两个 hook 订阅同 symbol，只创建 1 个 EventSource', async () => {
    // renderHook x2，都传 ['RB']
    // 断言 MockEventSource.instances.length === 1
  })

  it('两个 hook 订阅不同 symbol，URL 包含 symbols union', async () => {
    // 一个 ['RB']，一个 ['HC']
    // 断言 URL 同时包含 RB 和 HC
  })

  it('rerender 相同 symbols 不重建连接', async () => {
    // renderHook({ symbols: ['RB'] })
    // rerender({ symbols: ['RB'] }) — 同一个数组引用或不同引用但内容相同
    // 断言 MockEventSource.instances.length 不变
  })

  it('最后一个订阅卸载后关闭所有资源', async () => {
    // unmount 第二个 hook
    // 断言 EventSource closed、interval cleared、visibility listener removed
  })
})
```

**验收标准：**
- [ ] 新增 4 个测试用例全部通过
- [ ] 总测试数 ≥ 171（当前 167 + 4）

**涉及文件：**
- `frontend/tests/hooks/useRealtimeQuotes.test.tsx`

---

### T4 — 监控上报闭环（P1）

**问题描述：**
`sentry-lite` 默认 `reportUri = ${API_BASE}/api/log/frontend`，但后端路由中没有 `/api/log/frontend`。生产开启 `NEXT_PUBLIC_SENTRY_ENABLED=true` 且未配置 `NEXT_PUBLIC_SENTRY_REPORT_URI` 时，上报会打到 404。

**方案二选一：**

**方案 A（后端补 endpoint，推荐）：**
- 后端新增 `POST /api/log/frontend` 路由
- Payload 格式与 `sentry-lite.ts:52-62` 对齐：
  ```json
  {
    "type": "exception | message | web-vitals",
    "payload": { ... },
    "level": "error | warning | info",
    "meta": {
      "url": "...",
      "ua": "...",
      "release": "...",
      "environment": "...",
      "timestamp": "..."
    }
  }
  ```
- 后端行为：记录日志（不抛错），可异步落库

**方案 B（前端默认值收敛）：**
- `sentry-lite.ts` 默认 `reportUri` 改为 `undefined`（空值）
- 只有显式配置 `NEXT_PUBLIC_SENTRY_REPORT_URI` 时才开启 POST 上报
- `vitals.ts` 同样处理

**验收标准：**
- [ ] 选定方案并实现
- [ ] 如选方案 A：后端有对应路由，POST 测试通过，返回 204/200
- [ ] 如选方案 B：未配置时 `shouldReport()` 返回 false，不触发 fetch
- [ ] `npm.cmd run test` 全绿

**涉及文件：**
- 方案 A：`python/routers/*.py`（新增或扩展）
- 方案 B：`frontend/lib/sentry-lite.ts`、`frontend/lib/vitals.ts`

---

### T5 — /metrics 页面测试覆盖（P2）

**问题描述：**
`/metrics` 页面有 loading、error、未登录重定向、数据展示四种状态，当前无任何测试覆盖。

**测试范围：**

```ts
// frontend/tests/app/metrics.page.test.tsx
- 未登录时重定向到 /
- 加载状态显示"加载中..."
- API 失败显示错误信息
- 数据正常时渲染所有 StatCard
- 采集健康度表格渲染 recent_runs
```

**验收标准：**
- [ ] 新增 `/metrics` 页面组件测试
- [ ] mock `api.getDashboardOverview` / `getDashboardActivity` / `getDashboardCollection`
- [ ] 覆盖 loading / error / success / unauth 四种状态

**涉及文件：**
- `frontend/tests/app/metrics.page.test.tsx`（新建）
- `frontend/tests/fixtures/index.ts`（补充 dashboard mock 数据）

---

### T6 — 性能基线执行（P2）

**问题描述：**
`e2e/performance.spec.ts` 已存在但未执行，没有实际性能数据。

**执行步骤：**

```powershell
cd frontend
# 1. 确保 dev server 和后端可访问
# 2. 执行
npx.cmd playwright test e2e/performance.spec.ts

# 3. 记录结果到本文件「性能基线」章节
```

**验收标准：**
- [ ] Playwright performance spec 执行通过
- [ ] 记录每个页面的 DOMContentLoaded、loadComplete、LCP、heap used
- [ ] 如有失败，分析是阈值问题还是真实性能退化

**涉及文件：**
- `frontend/e2e/performance.spec.ts`
- 本文件「性能基线」章节

---

### T7 — RealtimeStore 快照语义优化（P2，可选）

**问题描述：**
新 subscriber 初始只收到空 `quotes`，不会拿到 store 里已有 quote。列表场景可能没问题，但切换/重挂载时会短暂丢实时值。

**修复方案：**

```ts
// frontend/lib/realtimeStore.ts subscribe 方法
subscribe(symbols: string[], callback: SubscriberCallback): () => void {
  const subscriber: Subscriber = { symbols: new Set(symbols), callback }
  this.subscribers.push(subscriber)

  // 新 subscriber 立即收到已有 quote 的快照
  const existingQuotes = new Map<string, RealtimeQuote>()
  symbols.forEach((sym) => {
    // 从当前 store 的 quotes 中筛选已有值
    // 需要额外维护一个全局 quotes Map
  })

  callback({
    quotes: existingQuotes, // 而非空 Map
    source: this._source,
    error: this._error,
    loading: this._loading,
  })
  // ...
}
```

**验收标准：**
- [x] 新 subscriber 能收到已有 quotes 快照
- [x] 相关测试通过（新增 1 个快照语义测试，总测试 177）

**涉及文件：**
- `frontend/lib/realtimeStore.ts`

---

## 性能基线

> 在 T2 build 成功后和 T6 Playwright 执行后填入实际数据。

| 指标 | 目标值 | 当前值 | 状态 |
|---|---|---|---|
| Vitest 测试数 | ≥ 171 | 176 | 通过 |
| TypeScript | 0 error | 0 error | 通过 |
| Lint | 0 error | 0 error | 通过 |
| Build | 成功 | 成功 | 通过 |
| `/` First Load JS | < 180 kB | 131 kB | 通过 |
| `/products` First Load JS | < 180 kB | 131 kB | 通过 |
| `/products/[id]` First Load JS | < 180 kB | 143 kB | 通过 |
| `/metrics` First Load JS | < 180 kB | 96.3 kB | 通过 |
| 首页 DCL | < 3000 ms | ~800 ms | 通过（E2E） |
| 首页 LCP | < 2500 ms | 待测 | 需完整环境 |
| 详情页 DCL | < 3000 ms | 待测 | 需完整环境 |
| 详情页 LCP | < 2500 ms | 待测 | 需完整环境 |

---

## 执行顺序建议

```
T1 (SSE 稳定性) ─┐
                 ├→ 并行 → T3 (测试补全) → T5 (metrics 测试)
T2 (门禁修复) ────┘         │
                            ↓
                     T4 (监控闭环) — 可并行
                            ↓
                     T6 (性能基线) — 依赖 T2
                     T7 (快照语义) — 可选，放最后
```

**推荐轮次：**

- **第一轮（并行）：** T1 + T2
- **第二轮：** T3 + T5
- **第三轮（并行）：** T4 + T6
- **第四轮（可选）：** T7

---

## 回归检查清单

每完成一轮修改后执行：

```powershell
cd frontend
npx.cmd tsc --noEmit
npm.cmd run test
npm.cmd run lint
npm.cmd run build
```

- [ ] `tsc` 通过
- [ ] `test` 全绿（目标 ≥ 171 tests）
- [ ] `lint` 通过
- [ ] `build` 通过
- [ ] 无新增 console warning

---

## 附录：v5 审计问题跟踪

| v5 # | 问题 | 优先级 | 对应本轮任务 | 状态 |
|---|---|---|---|---|
| 1 | SSE 订阅稳定性（数组依赖导致退订/重连） | P0 | T1 | 已完成 |
| 2 | 监控默认 endpoint 不存在 | P1 | T4 | 已完成 |
| 3 | build/lint 门禁不可证明 | P0 | T2 | 已完成 |
| 4 | RealtimeStore 测试不够锋利 | P1 | T3 | 已完成 |
| 5 | 性能基线半闭环 | P2 | T6 | 部分完成（2/5 E2E，待后端就绪补跑登录场景） |
| 6 | 运营指标页无前端测试 | P2 | T5 | 已完成 |
| 7 | RealtimeStore 快照语义缺失 | P2 | T7 | 已完成 |
| 8 | 魔法数字未提取 | P2 | T8 | 已完成 |
| 9 | Vitals 生产环境 console 噪音 | P2 | T9 | 已完成 |

---

## 后端 Agent 待办事项

以下事项依赖后端数据或接口，前端代码已就绪，待后端完成后验证：

| 编号 | 需求 | 前端状态 | 后端需完成 | 验证方式 |
|---|---|---|---|---|
| FUT-07 | 涨跌停视觉标识 | `LimitBadge.tsx`、`isLimitUp`/`isLimitDown` 已实现，`Product`/`RealtimeQuote` 类型已有 `limit_up`/`limit_down` | `RealtimeQuoteDB` 增加 `limit_up`/`limit_down` 字段；采集任务写入；`/api/realtime/*` 返回新字段 | 浏览器验证 QuoteCard/详情页涨跌停标签 |
| FUT-08 | 价格精度按品种 | `formatPrice(value, precision)` 已实现，`Product`/`Variety` 类型已有 `price_precision` | `ProductDB` 增加 `price_precision` 字段；从 `VarietyDB.tick_size` 计算写入 | 浏览器验证所有价格显示位数正确 |
| FUT-10 | 休市提示 | `MarketClosedBanner.tsx` 已调用 `api.getMarketStatus()`，fallback 到本地日历 | 新增 `TradingCalendarDB` + `/api/market/status` 接口 | 浏览器验证非交易日显示提示条 |
| SEC-02 | Cookie 鉴权 | 前端已移除 SSE URL token，使用 `withCredentials=true` | `auth.py` login 返回 `Set-Cookie: access_token`; `dependencies.py` 读取 Cookie; SSE 接口读取 Cookie | E2E 登录场景验证 |
| DB-01 | PostgreSQL 迁移 | 前端无直接改动 | 合并 Alembic 多 head（`7e710d06887b` + `e4d030205a0e`）；确保 `alembic_version` 表存在并 stamp 到最新 | 后端启动后前端 E2E 全量通过 |

> **给后端 agent 的参考：** 前端迭代文档 `BACKEND_ITERATION_FOR_FRONTEND_FIXES.md` 已详细列出后端修改步骤，包括模型、Schema、Router、Alembic 迁移。当前前端代码已与该文档对齐，后端完成后前端无需额外修改。
