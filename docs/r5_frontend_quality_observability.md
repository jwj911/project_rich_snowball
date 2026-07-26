# R5：前端质量与观测趋势

> 实施日期：2026-07-26
> 状态：已完成工程实现与本地验证；生产发布验证仍需在 R6 发布窗口执行。
> 对应计划：[后续迭代计划](iteration_plan_20260724_follow_up.md)

## 1. 目标与边界

R5 在不改变既有认证与交易数据边界的前提下，处理以下质量风险：

1. 让 Lighthouse 结果可按路由、提交和 CI 运行关联，并可作跨提交对比；
2. 基于实际行情列表的服务端分页上界决定是否引入虚拟滚动；
3. 覆盖详情页的加载失败、实时行情降级、评论失败和价位标注失败；
4. 记录 CSP 与 access token 存储的迁移条件，不进行未经 CSRF 设计验证的 cookie-only 改造。

Lighthouse 仅采集公开渲染路径 `/` 与 `/products`。带登录态、动态 K 线和写操作的详情页由
Playwright smoke 覆盖，不能把 Lighthouse 无登录结果解读为详情页的性能结论。

## 2. Lighthouse 趋势产物

`frontend/scripts/lighthouse-baseline.js` 现在在一次运行中采集命名路由集，默认：

```text
home=/
products=/products
```

可通过 `LIGHTHOUSE_ROUTES` 覆盖，例如：

```powershell
$env:LIGHTHOUSE_ROUTES='home=/,products=/products'
npm run lighthouse -- http://127.0.0.1:3200
```

每条路由记录包含：

- 路由标签、路径与实际 URL；
- FCP、LCP、TBT、CLS、Speed Index、TTI、DOM 大小、请求数和资源体积；
- Git commit SHA、ref、repository、CI run ID / attempt、workflow、事件类型和采集时间；
- 对同一 ref 的上一个不同 commit 的指标 delta；
- 该路由的阈值失败列表。

产物位于 `frontend/.lighthouse/`：

| 文件 | 用途 |
|---|---|
| `lighthouse-trend.json` | 当前 CI 运行、当前路由结果和可读取的历史快照 |
| `lighthouse-history.json` | 跨运行可合并的历史输入，按 `commit SHA + route` 去重，默认最多保留 240 条 |
| `latest.json` | 兼容旧工具的当前完整 trend 报告 |

`frontend-ci.yml` 会尝试恢复名称为 `lighthouse-trend-history` 的最近未过期 artifact，再上传新的
三个 JSON 文件并保留 90 天。没有历史 artifact、artifact 不可读或 API 权限不足只会让比较从空历史
重新开始，不能跳过当前 Lighthouse 运行。

阈值保持已有 CI baseline：

```text
LCP <= 5000 ms
FCP <= 3000 ms
TBT <= 600 ms
CLS <= 0.25
Speed Index <= 5000 ms
```

这些阈值是 CI 回归门槛，不是用户真实设备或生产 RUM SLO。性能比较只应在同一 CI runner、
同一 production build 配置和同一命名路由下解释。

## 3. 行情列表容量决策

当前 `/products` 使用服务端分页，`MARKET_PAGE_SIZE = 20`。`QuoteTable` 为响应式布局同时保留
移动卡片与桌面表格 DOM，因此单页至多挂载 20 个业务条目对应的双视图 DOM。

结论：当前不引入虚拟滚动依赖。现有 20 条硬上界远低于虚拟列表的收益阈值，并且分页可以限制 API
响应、排序和浏览器节点数。`frontend/lib/marketPagination.ts` 固定：

```text
MARKET_PAGE_SIZE = 20
MARKET_VIRTUALIZATION_REVIEW_THRESHOLD = 100
```

以下任一变化发生时，必须先以生产样本复测，再决定是否使用 `@tanstack/react-virtual`：

1. 单页上界拟提高到 100 行以上；
2. 产品要求无限滚动或一次加载大于 100 个品种；
3. 桌面与移动视图改为同时显示，或在中低端设备上出现可复现的滚动/输入掉帧；
4. Lighthouse 中 `/products` 的 DOM 大小、LCP 或 TBT 在同基线下出现持续回归。

重新评估必须同时检查：键盘导航、屏幕阅读器行号和总数、滚动定位、排序/筛选后焦点、分页缓存、
移动与桌面断点，以及 20、100、500 条合成数据的渲染证据。不能仅因总品种数增长而替换当前服务端
分页。

## 4. 详情页失败态

`ProductDetailPage` 现在有明确的页面级行为：

| 场景 | 用户可见行为 | 数据处理 |
|---|---|---|
| 详情请求失败 | `ErrorState` 显示错误与重试 | 不展示不完整详情 |
| 实时行情失败 | 保留详情和最近收盘字段，显示“实时行情暂不可用”状态 | SWR 继续按既有间隔重试 |
| 评论写入失败 | 评论区内显示服务端错误 | 输入不被清空 |
| 价位标注写入失败 | 详情侧栏显示已本地回退说明 | `usePriceLevels` 写入用户本地缓存 |

`frontend/e2e/product-detail.spec.ts` 通过 Playwright route interception 覆盖以上四种情况，不依赖
真实服务的临时故障。既有正向 K 线、合约切换、自选、标注、评论和返回行情中心 smoke 保留。

## 5. CSP 与 access token 风险评估

### 当前状态

- CSP 在 `frontend/next.config.js` 中仍包含
  `script-src 'self' 'unsafe-eval' 'unsafe-inline'` 与
  `style-src 'self' 'unsafe-inline'`；
- `access_token` 会通过 HttpOnly cookie 支持 SSE 和兼容的只读请求，也仍在
  `localStorage['futures_access_token']` 中保存，供前端为写请求设置 `Authorization: Bearer`；
- `refresh_token` 仅通过 HttpOnly、`SameSite=Lax` cookie 轮换；
- 写请求拒绝 access cookie 回退，避免 cookie-only 写操作绕过当前 CSRF 边界；
- refresh 新生成的 access token 现在同步轮换 `access_token` cookie；logout 同时清理 refresh 和
  access cookies，避免 SSE 在刷新后继续携带过期 token。

`localStorage` access token 在发生 XSS 时可被窃取，因此是已记录的风险接受项，而不是长期安全终态。
当前 CSP 中的 `unsafe-inline` / `unsafe-eval` 也不能被当作充分的 XSS 缓解措施。

### 分阶段迁移

| 阶段 | 变更 | 验收与停止条件 |
|---|---|---|
| S0，当前 | 固化 token/cookie 轮换和 Lighthouse/错误态证据 | refresh、logout、SSE 重连、写请求 Bearer 和 CSRF 回归必须通过 |
| S1，报告模式 | 在不改变 enforce CSP 的情况下增加 CSP Report-Only endpoint、采样与告警 | 收集完整业务周期报告；任何 Next runtime、图表、SSE、API 或登录违规先修复，不收紧 enforce |
| S2，nonce/hash 收紧 | 为可控 inline 脚本迁移 nonce/hash，移除不再需要的第三方与动态执行来源，逐项收紧 `script-src` | production build、登录、刷新、退出、SSE、详情写操作和全部浏览器 smoke 通过；报告无未知违规 |
| S3，内存 access token | 登录/刷新只将短 access token 保存在内存，refresh cookie 负责恢复会话；所有写请求继续携带 Bearer | 必须先完成跨刷新恢复、并发 401 单飞、失效处理、SSE cookie 轮换与 CSRF 回归；失败即回退到 S0，不切 cookie-only 写请求 |
| S4，cookie-only 可行性评审 | 仅在服务端提供 origin/CSRF token、cookie scope、跨子域与 SSE 多实例方案后评审 | 未证明每个状态变更接口的 CSRF 防护前，禁止删除 Bearer 要求或启用 cookie-only 写请求 |

S1 至 S4 需要在独立安全迭代实施。R5 不改变 CSP enforce 策略，也不移除 `localStorage` token，避免把
未验证的认证迁移伪装成安全修复。

## 6. 验证记录

本地工程验证已通过：

```text
npx tsc --noEmit                              passed
npm run lint                                  passed
npm run test                                  34 files, 200 passed
npm run build                                 passed
npx playwright test market + product detail  18 passed
pytest refresh token + CSRF                   17 passed
```

Production build 的 First Load JS 为 `/products` 132 kB、`/products/[id]` 147 kB，均低于
180 kB 预算。隔离 SQLite API 上的 Lighthouse 结果如下：

| 路由 | 性能分 | FCP | LCP | TBT | CLS | SI |
|---|---:|---:|---:|---:|---:|---:|
| `/` | 97 | 911 ms | 2566 ms | 0 ms | 0 | 911 ms |
| `/products` | 94 | 1367 ms | 2952 ms | 0 ms | 0 | 1367 ms |

两条路由均通过当前阈值。隔离数据库、浏览器测试产物和本地 Lighthouse JSON 已清理；趋势结果不应作为
源码或 benchmark 文件提交。

生产 CSP、真实浏览器配置、发布前 smoke、Lighthouse 趋势结果和 artifact 可读性仍必须按 R6
发布窗口重新执行，不能由本地或历史 CI 代替。
