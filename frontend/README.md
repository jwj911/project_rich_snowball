# 前端说明与迭代计划

> 最后更新：2026-07-18。本文档聚焦 `frontend/`，根目录 `README.md` 负责全栈启动与后端说明。

## 当前定位

前端当前是登录后的期货行情与研究工作台，核心目标是帮助用户查看行情、筛选品种、复盘 K 线、维护云端支撑/阻力标注、发表评论，并在个人工作区汇总自选和研究历史。

它还不是交易终端：当前没有真实下单、撤单、持仓、资金账户、风控确认、成交回报等交易闭环。如果后续要进入交易域，建议先做模拟下单安全闭环，再讨论真实交易接入。

## 技术栈

| 分类 | 当前方案 |
| --- | --- |
| 框架 | Next.js 14.2.35 App Router |
| UI Runtime | React 18.2 |
| 语言 | TypeScript 5.3，`strict: true` |
| 样式 | Tailwind CSS 3.4 |
| 图标 | `lucide-react` |
| K 线 | `lightweight-charts` 5.2 |
| 请求 | 自定义 `ApiService` + `fetch` |
| 状态 | React Context + 页面/组件本地状态 |
| 测试 | Vitest 4.1.7（33 个测试文件 / 192 个测试）+ jsdom + Testing Library；Playwright 6 个 spec |

## 目录职责

```text
frontend/
├── app/                         # 页面路由
│   ├── page.tsx                 # 行情工作台
│   ├── products/page.tsx        # 行情中心
│   ├── products/[id]/page.tsx   # 品种详情
│   ├── workspace/page.tsx       # 我的工作区
│   └── my-comments/page.tsx     # 我的评论
├── components/
│   ├── auth/                    # AuthProvider、登录门禁
│   ├── activity/                # 刷新/轮询状态
│   ├── layout/                  # AppShell
│   ├── market/                  # 行情卡片、表格、价格变化、技术分析
│   ├── workspace/               # 工作区摘要、标注、评论、自选
│   └── ui/                      # 基础按钮、输入框、空/错状态
├── hooks/
│   ├── useMarketPolling.ts      # HTTP 轮询、并发保护、AbortSignal、heartbeat
│   ├── useRealtimeQuotes.ts     # SSE 优先，HTTP 轮询降级
│   ├── usePriceLevels.ts        # 云端价位标注 + localStorage 降级
│   └── useWatchlistRealtime.ts  # 自选实时监听兼容层
├── lib/
│   ├── api.ts                   # API 对外导出入口
│   ├── api/                     # client、types、products、market、workspace
│   ├── priceLevels.ts           # 价位标注缓存、排序去重、本地导入工具
│   └── format.ts                # 数字、百分比、东八区时间、相对时间
└── tests/                       # Vitest 测试与人工检查清单
```

## 运行命令

```powershell
cd D:\Code\project_rich_snowball\frontend
npm install
npm run dev
```

默认地址：`http://127.0.0.1:3200`

常用验证：

```powershell
npx tsc --noEmit
npm run lint
npm run test
npm run build
```

Windows PowerShell 遇到执行策略限制时使用：

```powershell
npx.cmd tsc --noEmit
npm.cmd run lint
npm.cmd run test
npm.cmd run build
```

## 已落实的架构优点

- API 调用集中在 `lib/api.ts` 的 `api` 导出，页面里基本没有裸 `fetch`；内部已拆到 `lib/api/` 的 client、types 和领域模块。
- `ApiError` 已经提供统一错误类型，后续应继续基于 `status` / `code` / `retryAfter` 做错误分流。
- 首页、行情中心、工作区复用 `useMarketPolling`，已具备并发保护、卸载 abort、刷新状态和失败计数。
- 实时行情 hook 采用 SSE 优先、HTTP 轮询降级，方向正确。
- K 线图使用成熟库 `lightweight-charts`，已避免随数据刷新反复销毁重建，并使用 Map 优化十字光标查找。
- `Navbar` 已拆出桌面/移动导航与登录/注册弹窗，导航容器只保留组合和弹窗状态。
- 价位标注、自选、工作区聚合已经从占位转为后端同步；`usePriceLevels` 已把缓存读写、排序去重和本地导入批量构造拆到 `lib/priceLevels.ts`。
- `PriceFlash` 已提供价格变化反馈，`format.ts` 已固定 `Asia/Shanghai`。
- 已有 Vitest 自动化测试覆盖格式化工具、核心轮询 hook、价位标注 hook、K 线工具、认证错误流和部分组件。

## 当前主要问题

| 优先级 | 问题 | 影响 |
| --- | --- | --- |
| P1 | 部分行情组件仍偏大 | 展示细节后续扩展成本较高；API 层和价位标注工具已先拆出领域模块 |
| P1 | 详情页 quote 后续可进一步接 `useRealtimeQuotes` | 当前轮询已统一，但实时状态表达还有提升空间 |
| P1 | 行情列表尚未虚拟滚动 | 桌面/移动重复 DOM 已消除，合约数量继续扩大后仍需虚拟滚动 |
| P2 | 认证状态仍是单一 Context | 后续偏好、实时连接、交易态增加后重渲染粒度偏粗 |
| P2 | 可访问性不完整 | K 线、表单、颜色表达仍需继续加强 |
| P2 | 页面级测试与 Playwright 尚未纳入 CI | 关键登录、行情和工作区流程缺少发布门禁 |
| P2 | CI coverage 与性能门禁仍需提高 | 当前后端 coverage 阈值为 30%，前端 Lighthouse 尚未形成趋势比较 |

Phase 0「可运行性收口」已完成：`npm run test` 为 `192 passed`，`npx tsc --noEmit`、`npm run lint`、`npm run build` 均通过。后续前端工作与全栈路线同步，优先进入行情读模型和 E2E 门禁建设。

## 下一步迭代规划

### 1. 行情读模型配合与页面验收（1-2 天）

- 配合后端统一 `/api/varieties` 的主力日线与实时快照 fallback 契约。
- 为行情中心、品种详情补齐主力数据存在/缺失/过期三种状态的页面级测试。
- 让详情页错误态优先使用 `ApiError.status`，并统一展示数据来源和更新时间。

验收标准：Mock SQLite 与 PostgreSQL 样本环境页面均可加载；`npm run lint`、`npx tsc --noEmit`、`npm run test` 通过。

### 2. 组件拆分与请求策略统一（3-5 天）

- 将品种详情页拆为 `ProductHeader`、`KlineSection`、`LevelEditor`、`TradingInfo`、`CommentPanel`。
- 将 Navbar 中的 `ModalShell`、`LoginModal`、`RegisterModal` 拆入 `components/auth/`。已完成。
- 将 Navbar 的桌面/移动导航拆入 `components/layout/`。已完成。
- 将详情页轮询改为复用 `useMarketPolling` 或 `useRealtimeQuotes`。
- 把技术指标计算从 `TechnicalAnalysisPanel` 抽到纯函数模块，并补单测。
- 将 `lib/api.ts` 拆为 `lib/api/client.ts`、`types.ts`、`products.ts`、`market.ts`、`workspace.ts`，对外仍通过 `lib/api.ts` 导出。已完成。

验收标准：核心页面/组件单文件控制在 300 行以内；请求逻辑与展示组件职责分离。

### 3. 行情性能与交互体验（3-5 天）

- `usePriceLevels` 已补云端加载、保存成功、云端失败本地降级和缓存 fallback 测试。
- `usePriceLevels` 已把缓存读写、排序去重和本地导入批量构造抽到 `lib/priceLevels.ts`，并补工具测试。
- `QuoteTable` 已拆出桌面表格、移动卡片列表和分页控件，并按视口只挂载当前视图。
- `QuoteRow` / `QuoteCard` 继续 memo 化并检查 props 稳定性。
- 评估引入 `@tanstack/react-virtual`，只在合约数量超过阈值时启用虚拟滚动。
- 避免移动端和桌面端同时挂载大量行情 DOM。已完成。
- 强化价格变化反馈和刷新状态文案。

验收标准：500 条合约数据下筛选、排序、滚动仍流畅；刷新不打断用户阅读。

### 4. 测试与工程化（持续）

- 补 `QuoteTable` 筛选排序测试。
- 补登录/注册弹窗测试。
- 补评论提交、价位标注、自选切换测试。
- 引入 Playwright smoke：登录、行情中心、详情页、工作区。
- 建立 GitHub Actions：lint、type-check、test、build。

验收标准：每个前端 PR 自动跑基础质量门禁；关键页面至少有 smoke 覆盖。

### 5. 后端 Phase 5.9 Refresh Token 配合准备（等待后端 API）

后端完整 Review 中将 `5.9 Refresh Token 机制` 标记为下轮重点，并明确需要前端同步配合。当前已接入 HttpOnly refresh cookie：`frontend/lib/api/client.ts` 仅将 access token 写入 `localStorage`，普通请求遇到 401 会先 refresh 并重试一次，refresh 失败才清理登录态并触发登录弹窗事件。

建议后端契约：

- `POST /api/auth/login`：返回 `access_token`、`token_type`、`expires_in`，同时通过 `Set-Cookie` 写入 HttpOnly refresh token。
- `POST /api/auth/refresh`：使用 HttpOnly refresh cookie，返回新的 `access_token`、`expires_in`，并旋转 refresh token。
- `POST /api/auth/logout`：吊销 refresh token，并清理 refresh cookie。
- access token 建议短有效期，例如 15 分钟；refresh token 建议 7 天，可吊销、可旋转。
- refresh token 不暴露给 JavaScript，使用 `HttpOnly`、`Secure`、`SameSite` cookie。

前端待后端 API 就绪后实施：

- 在 `ApiService` 中新增 `refreshAccessToken()`，普通 `request()` 遇到 401 时先刷新 access token，再对原请求做一次 retry。
- 为 refresh 增加单飞锁（例如 `refreshPromise`），避免多个并发 401 同时触发多次 refresh。
- `AuthProvider` 初始化时先尝试 refresh，再调用 `getMe()`；refresh 失败才进入未登录态。
- `logout()` 改为调用 `/api/auth/logout`，无论后端成功与否都清理本地 access token 与用户态。
- `createRealtimeStreamToken()` 继续走统一 `request()`，确保 access token 过期时可以自动 refresh 后再创建 SSE stream token。
- 401 且 refresh 失败时统一提示“登录已过期”，并引导打开登录弹窗；429 限流时显示“请求过于频繁，请稍后再试”，不要混同为普通网络错误。
- 前端可短期兼容旧登录响应，仅包含 `access_token` 时仍保持现有行为；后端新契约稳定后再逐步迁移为内存 access token + HttpOnly refresh cookie。

测试要求：

- 登录成功保存/更新 access token。
- 应用启动时 refresh 成功后恢复登录态。
- 普通请求 401 后自动 refresh 并 retry 原请求。
- refresh 失败后清理登录态并不重复 retry。
- 并发多个 401 时只发起一次 refresh。
- logout 调用后端吊销接口并清理本地状态。
- SSE 创建 stream token 时 access token 过期也能通过 refresh 恢复。

验收标准：后端 5.9 API 就绪后，前端 `npm run lint`、`npx tsc --noEmit`、`npm run test`、`npm run build` 全部通过；登录、刷新、退出、SSE 实时行情、401/429 错误体验均有自动化测试覆盖。

### 6. 产品边界与交易域准备（按产品决策）

- 如果仍定位为社区行情：在界面和文档明确“不支持真实交易”。
- 如果要做模拟交易：先实现下单预览、二次确认、loading 锁、失败保留输入、成功回执。
- 如果要接真实交易：必须先补权限、审计、资金/持仓一致性、风控提示、幂等提交和异常回滚方案。

## 编码注意事项

- 所有源码和 Markdown 文档统一 UTF-8。
- 中文文案修改后要在浏览器中查看真实显示，避免把 mojibake 当成正常文案继续扩展。
- 不要提交 `.next/`、`node_modules/`、日志、`tsconfig.tsbuildinfo` 等生成物。
