# 前端迭代质量审计报告 v3

> 审计日期：2026-05-25  
> 审计分支：`master`  
> 审计 HEAD：`9e57ae5 test(p3): add klineData/WatchlistButton tests and expand audit logging`  
> 审计目标：复核前端 P0/P1/P2 修复质量，识别回归风险、架构债务和下一轮前端 agent 必须处理的问题。

## 执行摘要

当前前端不是“完全没修”，相反，不少硬伤已经被认真处理：

- `next` 已统一到 `14.2.35`，`npm.cmd ls next` 不再 invalid。
- `npx.cmd tsc --noEmit` 通过。
- `npm.cmd run lint` 通过。
- `npm.cmd run build` 通过。
- 详情页 First Load JS 当前约 `135 kB`，未见 bundle 爆炸。
- access token 已从 `localStorage` 迁到内存态，refresh token 走 HttpOnly cookie。
- SSE URL 不再拼接 token，且 `EventSource` 已设置 `{ withCredentials: true }`。
- 行情中心已经走服务端分页、搜索、筛选、排序参数。
- App Router `error.tsx`、`global-error.tsx` 和 React `ErrorBoundary` 已补上。

但仍不建议直接进入下一阶段功能开发。当前结论是：

> **总体评级：B，需进行一次还债迭代。**

主要原因：

1. `npm.cmd run test` 当前在审计环境中失败，25 个 suite 在 import 前失败，测试门禁不能证明可用。
2. SSE 修复只是局部修复，没有连接复用、多 tab 去重、背压和真实监控。
3. 详情页仍有手写 `setInterval`，和统一轮询/Abort/visibility 策略并存。
4. 登录弹窗 A11y 只修了一半，完整的 `AuthModalShell` 存在但未被 Login/Register 使用。
5. Web Vitals / Sentry 当前仍是 console 级占位，不是生产监控闭环。

## 审计验证结果

在 `frontend/` 下执行：

| 命令 | 结果 | 说明 |
|---|---|---|
| `npm.cmd ls next` | 通过 | 当前解析为 `next@14.2.35` |
| `npx.cmd tsc --noEmit` | 通过 | TypeScript 当前无错误 |
| `npm.cmd run lint` | 通过 | 无 ESLint warning/error |
| `npm.cmd run build` | 通过 | 生产构建成功 |
| `npm.cmd run test` | 失败 | 25 个 suite import 前失败：`Cannot find module '/@fs/D:/Code/project_rich_snowball/frontend/tests/setup.ts'` |

注意：测试失败看起来像沙箱路径映射导致的 Vitest setup 文件解析问题，不是业务断言失败。但由于测试命令是质量门禁，前端 agent 必须在真实本机和 CI 中复核，并保证 `npm.cmd run test` 稳定全绿。

## P0 修复质量

| # | 原问题 | 当前实现 | 评级 | 隐患/要求 | 证据位置 |
|---|---|---|---|---|---|
| 1 | Next 版本与 lock 不一致 | `package.json` / lock / `npm ls next` 已统一到 `14.2.35` | ✅ | 继续保持 `npm ci` 可复现 | `frontend/package.json`、`frontend/package-lock.json` |
| 2 | TypeScript 检查失败 | `npx.cmd tsc --noEmit` 当前通过 | ✅ | 保持测试 fixture 与类型同步 | `frontend/tests/fixtures/index.ts` |
| 3 | 前端测试失败 | 测试文件增多，但 `npm.cmd run test` 当前仍失败 | ❓ | 必须在真实路径/CI 下复核并修到全绿 | `frontend/vitest.config.ts`、`frontend/tests/setup.ts` |
| 4 | token 存储和 SSE token 泄露 | access token 内存态；refresh cookie；SSE URL 不再带 token；EventSource 带 credentials | ✅ | 需要后端 CORS/cookie 策略配合 smoke | `frontend/lib/api/auth.ts`、`frontend/hooks/useRealtimeQuotes.ts` |
| 5 | fetch 无超时/Abort | `requestRaw` 有 15s timeout 和 signal 透传 | ⚠️ | 401 retry 分支未复用 timeout/signal；login fetch 也无 timeout | `frontend/lib/api/request.ts`、`frontend/lib/api/auth.ts` |
| 6 | 超大组件未拆 | 已拆出 API/产品/K 线子组件 | ⚠️ | `KlineChart.tsx` 仍约 342 行，详情页仍约 326 行 | `frontend/components/KlineChart.tsx`、`frontend/app/products/[id]/page.tsx` |
| 7 | 空 catch 静默吞错 | 多数关键操作已有 console/toast/captureMessage | ⚠️ | SSE JSON parse 和部分 fallback 仍吞错或不上报 | `frontend/hooks/useRealtimeQuotes.ts` |
| 8 | 登录弹窗 A11y 未达标 | `ModalShell` 已有 `role="dialog"` / `aria-modal` | ⚠️ | 实际使用的 `ModalShell` 没有焦点陷阱；更完整的 `AuthModalShell` 未接入 | `frontend/components/auth/ModalShell.tsx`、`frontend/components/auth/AuthModalShell.tsx` |

## P1 修复质量

| # | 原问题 | 当前实现 | 评级 | 隐患/要求 | 证据位置 |
|---|---|---|---|---|---|
| 1 | 具体合约 K 线未闭环 | 详情页已接 `useProductKline`，`single` 分支走 `api.getContractKline` | ✅ | 需用浏览器 smoke 验证连续/主力/具体合约切换无旧数据残留 | `frontend/hooks/useProductKline.ts`、`frontend/lib/kline.ts` |
| 2 | SSE fallback 不可恢复 | 已有指数退避重连、visibility 恢复、轮询降级 | ⚠️ | 仍是每个 hook 独立建 `EventSource`，无连接复用、跨 tab 去重和背压 | `frontend/hooks/useRealtimeQuotes.ts` |
| 3 | 页面不可见时仍轮询 | `useMarketPolling` 和 SSE hook 有 visibility 处理 | ⚠️ | 详情页仍有自写 `setInterval`，没有统一 Abort/visibility 策略 | `frontend/hooks/useMarketPolling.ts`、`frontend/app/products/[id]/page.tsx` |
| 4 | 行情列表客户端全量筛选 | 行情中心已传 `skip/limit/search/category/direction/sort` 到后端 | ✅ | 后端接口要继续保证分页总数和分类 header 正确 | `frontend/app/products/page.tsx`、`frontend/lib/api/products.ts` |
| 5 | 请求缓存缺失 | 已引入 SWR，并有 `lib/swr-hooks.ts` | ⚠️ | 主行情列表仍是手写状态；SWR 没形成统一数据层 | `frontend/lib/swr-hooks.ts`、`frontend/hooks/useProductListRealtime.ts` |
| 6 | Error Boundary 缺失 | 已有 React ErrorBoundary、App Router `error.tsx` / `global-error.tsx` | ✅ | 文案和上报仍需整理 | `frontend/app/error.tsx`、`frontend/app/global-error.tsx`、`frontend/components/ErrorBoundary.tsx` |

## P2 修复质量

| # | 原问题 | 当前实现 | 评级 | 隐患/要求 | 证据位置 |
|---|---|---|---|---|---|
| 1 | 魔法数字未提取 | 有 `lib/constants.ts` | ⚠️ | K 线 limits 在 `constants.ts` 和 `lib/kline.ts` 重复定义，单一来源未完成 | `frontend/lib/constants.ts`、`frontend/lib/kline.ts` |
| 2 | 无 bundle analyzer | 已接 `@next/bundle-analyzer` | ✅ | 还缺明确 bundle budget | `frontend/next.config.js` |
| 3 | next config 太简陋 | 已有 `standalone`、安全 headers、CSP 等 | ✅ | CSP 目前仍含 `'unsafe-eval'` / `'unsafe-inline'`，生产前需评估 | `frontend/next.config.js` |
| 4 | 组件/Hook 测试不足 | 测试覆盖明显增加 | ⚠️ | 测试命令当前不可证明全绿 | `frontend/tests/` |
| 5 | 操作成功/失败反馈不足 | 已接 `sonner`，评论等动作有 toast | ✅ | 价位标注、SSE 降级等还可进一步统一提示 | `frontend/app/layout.tsx`、`frontend/app/products/[id]/page.tsx` |
| 6 | 涨跌停/价格精度/休市提示 | 相关组件/字段已出现 | ✅ | 仍需浏览器 smoke 验证真实数据展示 | `frontend/components/market/LimitBadge.tsx`、`frontend/components/market/MarketClosedBanner.tsx` |
| 7 | 前端监控/Web Vitals 缺失 | `web-vitals` 和 `sentry-lite` 已出现 | ⚠️ | 当前只是 console，占了“接入”的名头，没有真实上报、采样、告警 | `frontend/lib/vitals.ts`、`frontend/lib/sentry-lite.ts` |

## 回归风险扫描

| 变动区域 | 风险描述 | 概率 | 影响 | 建议 |
|---|---|---:|---:|---|
| 测试运行 | Vitest 当前 suite import 前失败，CI 可复现性存疑 | 中 | 高 | 优先修到 `npm.cmd run test` 全绿 |
| SSE 实时行情 | 多组件/多 tab 可能重复连接；消息逐条 `setQuotes(new Map(...))`，高频行情下容易抖 | 高 | 高 | 做 `RealtimeProvider` / 连接池 / 批处理 / diff 更新 |
| 详情页数据流 | 自写 interval 与新 hook 并存，错误、abort、visibility 策略不统一 | 中 | 中 | 统一到 `useMarketPolling`、SWR 或专用 detail hook |
| A11y | 弹窗具备基本语义，但焦点陷阱没有落到实际 Login/Register | 中 | 中 | 合并 `ModalShell` 与 `AuthModalShell`，补键盘测试 |
| 监控 | capture 和 Web Vitals 只是 console，不具备线上定位能力 | 高 | 中 | 接真实 endpoint，至少按环境配置开关和采样 |

## 架构债务清单

| 债务项 | 当前实现 | 根治方案 | 还债成本 | 优先级 |
|---|---|---|---|---|
| 测试门禁不可证明 | `npm.cmd run test` 当前失败 | 修 Vitest 路径/CI 配置，真实机全绿 | 0.5-1 天 | P0 |
| 实时连接治理不足 | 每个 `useRealtimeQuotes` 自管 SSE | 全局实时连接管理器，按 symbol 订阅复用 | 2-4 天 | P1 |
| 详情页仍像页面控制器 | 页面里仍有加载、轮询、提交、展示状态 | 提取 `useProductDetail`/mutation hooks，页面只组合 | 1-2 天 | P1 |
| 弹窗组件分裂 | `ModalShell` 与 `AuthModalShell` 重复且实际未用完整版本 | 合并为一个可访问弹窗组件 | 0.5 天 | P1 |
| 监控占位 | sentry-lite / vitals 输出 console | 接真实上报端点和告警 | 1 天 | P2 |
| 设计 token 不彻底 | K 线和布局仍多处 hex | chart/theme token 单一来源 | 1 天 | P2 |

## 代码异味 Top 5

1. **测试命令当前不可通过。**  
   这会让所有“已有测试覆盖”的说法打折。下一轮第一件事不是继续改 UI，而是修测试门禁。

2. **`useRealtimeQuotes` 仍是 hook 级 SSE 管理。**  
   有重连、有 fallback，但没有连接复用、跨 tab 去重、消息背压。行情系统后续一放大，这里很容易成为 Chrome DevTools 的红色海洋。

3. **详情页仍有手写轮询。**  
   `app/products/[id]/page.tsx` 中仍有 `setInterval`，没有复用 `useMarketPolling` 的 abort 和 visibility 逻辑。

4. **A11y 修复存在半成品。**  
   `AuthModalShell` 更完整，但 Login/Register 仍 import `ModalShell`。这类“双实现”三个月后会让修复分叉。

5. **监控只是“看起来接了”。**  
   `sentry-lite` 和 `web-vitals` 当前主要是 console，没有生产上报闭环。对线上白屏率、加载失败率、SSE 降级率帮助有限。

## 性能基线

`npm.cmd run build` 摘要：

| Route | First Load JS | 评价 |
|---|---:|---|
| `/` | 123 kB | 可接受 |
| `/products` | 123 kB | 可接受 |
| `/products/[id]` | 135 kB | 可接受，动态加载 KlineSection 后明显受控 |
| `/workspace` | 123 kB | 可接受 |
| Shared JS | 87.4 kB | 可接受 |

未完成项：

- 未跑 Lighthouse。
- 未测 LCP / CLS / INP。
- 未做长时间运行内存快照。
- 未压测 SSE 高频消息下的 render 次数。

## 下一轮前端 agent 必做清单

### P0：先让质量门禁可信

1. 修复 `npm.cmd run test`，要求真实工作区和 CI 都全绿。
2. 明确失败原因是否为 Vitest `setupFiles` 的 Windows 路径解析或沙箱路径映射。
3. 保持以下命令全部通过：

```powershell
cd frontend
npm.cmd ls next
npx.cmd tsc --noEmit
npm.cmd run lint
npm.cmd run test
npm.cmd run build
```

### P1：修掉会反复暴雷的架构点

1. 合并 `ModalShell` / `AuthModalShell`，让 Login/Register 真正具备焦点陷阱、焦点恢复、Escape 关闭和 `aria-labelledby`。
2. 把详情页自写 `setInterval` 收敛到统一 hook，补 abort、visibility、错误反馈测试。
3. 给 `requestRaw` 的 401 retry 分支补 timeout/signal；给 login fetch 也补 timeout。
4. 为 SSE 做连接复用方案，至少先做到同页订阅复用和批处理 setState。

### P2：补齐生产能力

1. Web Vitals 上报不要停留在 console。
2. `sentry-lite` 要么接真实上报，要么明确标注开发占位，避免误判为生产监控已完成。
3. 整理 K 线常量，避免 `constants.ts` 和 `kline.ts` 两套来源。
4. 加一条浏览器 smoke：登录、行情中心筛选、详情页连续/主力/具体合约切换、添加标注、加入自选、评论。

## 决策建议

本轮建议选择：

> **B. 需进行一次“还债迭代”。**

理由：

- P0 没有明显功能级致命缺陷，但测试门禁当前不可证明。
- P1 中 SSE、详情页轮询、弹窗 A11y 都属于“看起来修了，但还会反复打扰后续迭代”的问题。
- bundle 当前可控，不需要因为性能体积回炉；真正需要还的是运行时架构债和测试可信度。

下一轮不要继续堆新功能。先把测试、SSE、详情页数据流、弹窗 A11y 和监控闭环收干净。
