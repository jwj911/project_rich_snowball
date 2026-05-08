# 期货社区前端迭代方案：Lightweight Charts 改版路线

> 版本：v1.0  
> 日期：2026-05-07  
> 目标：在保证社区私密性和业务可控性的前提下，将当前前端从“基础行情展示”升级为“专业行情社区工作台”。

---

## 1. 背景与结论

当前前端已经具备基础页面链路：

- 首页展示热门期货品种
- 品种列表支持排序
- 品种详情页展示自研 SVG K 线图、支撑位/阻力位、评论区
- Navbar 内提供登录、注册、退出
- 我的评论页展示用户评论历史

代码评审发现的主要问题集中在：

- 登录状态只在局部组件内维护，详情页登录后评论状态不同步
- 详情页强绑定桌面横向布局，移动端不可用
- K 线图对空数据、同价数据、异常数字缺少兜底
- 列表页缺少小屏横向滚动或移动端卡片布局
- 请求失败时缺少用户可见的错误态、重试态、空状态
- 图表标注依赖浏览器原生 `confirm`，交互不专业

结合《期货社区前端改版方案.pdf》的目标，本轮前端改版采用以下技术路线：

**保留 Next.js 14 + React 18 + TypeScript + Tailwind CSS，使用 TradingView Lightweight Charts 替换当前自研 SVG K 线图。**

不采用：

- **TradingView Widget**：接入轻，但 iframe/Widget 模式可控性不足，难以深度实现私密社区标注、评论联动、自定义支撑/阻力位。
- **TradingView Advanced Charts / Charting Library**：能力强，但许可、公开访问、归因和使用边界不适合当前私密社区定位。

采用：

- **Lightweight Charts**：图表交互专业、性能好、包体相对可控，可完全使用自有行情数据，并由社区系统自行管理支撑位、阻力位、标注、评论关联和权限。

---

## 2. 改版原则

### 2.1 私密性优先

交易讨论、个人标注、关注品种、评论内容都属于用户敏感信息。前端不依赖公开第三方图表页面，不将用户标注写入第三方系统。

### 2.2 交易场景优先

所有页面设计先回答一个问题：是否能帮助用户更快完成行情判断、标注、讨论和复盘。

### 2.3 信息密度分层

- L1 速览层：价格、涨跌幅、成交量、自选异动
- L2 概览层：行情列表、热门品种、相关评论
- L3 深度层：K 线图、支撑/阻力位、历史评论、后续策略内容

### 2.4 暗色模式优先

默认暗色主题，保持国内交易习惯：

- 红涨
- 绿跌
- 数字等宽
- 大面积低饱和背景
- 边框和层级代替大面积阴影

### 2.5 渐进替换

不一次性重写所有页面。先补稳定性和架构，再替换 K 线图，再升级布局和视觉。

---

## 3. 技术选型

### 3.1 保留

| 模块 | 技术 | 原因 |
|------|------|------|
| 框架 | Next.js 14 App Router | 当前项目已使用，路由结构清晰 |
| UI | React 18 + TypeScript | 现有代码基础稳定 |
| 样式 | Tailwind CSS | 已接入，适合快速统一样式 |
| 图标 | lucide-react | 已接入，图标风格简洁 |
| API | `frontend/lib/api.ts` | 继续作为统一 API 客户端 |

### 3.2 新增

| 模块 | 建议技术 | 用途 |
|------|----------|------|
| 图表 | `lightweight-charts` | 替代当前自研 SVG K 线图 |
| 状态管理 | Zustand 或 React Context | 管理登录态、自选、UI 状态 |
| 数据请求 | SWR 或轻量自研 hook | 管理 loading/error/refresh/cache |
| 设计变量 | CSS variables + Tailwind extend | 统一颜色、圆角、边框、字体 |

### 3.3 暂缓

| 模块 | 原因 |
|------|------|
| shadcn/ui | 当前组件量不大，可先抽自有基础组件；后续需要复杂表单、菜单、弹窗时再引入 |
| React Query | 当前接口规模可先用 SWR 或自研 hook；如果后续有复杂缓存、分页、乐观更新，再升级 |
| TradingView Advanced Charts | 与私密社区定位不匹配，且许可和接入成本较高 |
| WebSocket | 后端当前仍以轮询为主，前端先保留 30s refresh，后续再接实时推送 |

---

## 4. 目标目录结构

建议逐步演进到以下结构：

```text
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── products/
│   │   ├── page.tsx
│   │   └── [id]/page.tsx
│   └── my-comments/page.tsx
│
├── components/
│   ├── auth/
│   │   ├── LoginModal.tsx
│   │   └── RegisterModal.tsx
│   │
│   ├── community/
│   │   ├── CommentComposer.tsx
│   │   ├── CommentList.tsx
│   │   └── CommentCard.tsx
│   │
│   ├── layout/
│   │   ├── AppShell.tsx
│   │   ├── TopNav.tsx
│   │   ├── Sidebar.tsx
│   │   ├── MobileTabbar.tsx
│   │   └── TickerTape.tsx
│   │
│   ├── market/
│   │   ├── KlineChart.tsx
│   │   ├── KlinePanel.tsx
│   │   ├── QuoteCard.tsx
│   │   ├── QuoteTable.tsx
│   │   ├── PriceChange.tsx
│   │   ├── SupportResistancePanel.tsx
│   │   └── AnnotationMenu.tsx
│   │
│   └── ui/
│       ├── Button.tsx
│       ├── Input.tsx
│       ├── Modal.tsx
│       ├── Badge.tsx
│       ├── EmptyState.tsx
│       ├── ErrorState.tsx
│       └── Skeleton.tsx
│
├── hooks/
│   ├── useAuth.ts
│   ├── useProducts.ts
│   ├── useProductDetail.ts
│   └── usePolling.ts
│
├── lib/
│   ├── api.ts
│   ├── format.ts
│   ├── chart.ts
│   └── constants.ts
│
├── store/
│   ├── auth.ts
│   ├── watchlist.ts
│   └── ui.ts
│
└── styles/
    └── tokens.css
```

迁移原则：

- 页面文件只负责数据组合和布局，不承载大段业务 JSX。
- 行情相关组件放入 `components/market`。
- 评论相关组件放入 `components/community`。
- 登录注册从 `Navbar.tsx` 拆出，避免 Navbar 膨胀。
- 格式化逻辑统一放入 `lib/format.ts`。

---

## 5. Lightweight Charts 接入设计

### 5.1 组件职责

```text
KlinePanel
├── KlineChart
├── AnnotationMenu
├── SupportResistancePanel
└── RelatedComments
```

`KlinePanel` 负责业务组合：

- 拉取/接收 K 线数据
- 接收当前品种信息
- 管理支撑位、阻力位、标注菜单状态
- 与右侧列表、评论区联动

`KlineChart` 只负责图表渲染：

- 初始化 chart instance
- 绘制 candlestick series
- 绘制 volume histogram
- 绘制 price line
- 处理 crosshair、click、context menu、resize
- 在 unmount 时销毁 chart

`SupportResistancePanel` 负责标注列表：

- 展示支撑位
- 展示阻力位
- 编辑价格
- 删除标注
- 切换显示/隐藏

`AnnotationMenu` 负责替代原生 `confirm`：

- 添加支撑位
- 添加阻力位
- 添加备注
- 关闭菜单

### 5.2 数据结构

前端先定义统一标注模型：

```ts
export type PriceAnnotationType = 'support' | 'resistance'
export type PriceAnnotationVisibility = 'private' | 'public'

export interface PriceAnnotation {
  id: string
  productId: number
  symbol: string
  type: PriceAnnotationType
  price: number
  note?: string
  visibility: PriceAnnotationVisibility
  color?: string
  createdBy?: number
  createdAt: string
  updatedAt?: string
  hidden?: boolean
}
```

第一阶段标注可存在前端状态中。第二阶段持久化到后端数据库。

### 5.3 后续后端表建议

后续如果要保存个人标注，可新增：

```text
price_annotations
├── id
├── user_id
├── product_id
├── symbol
├── type                 support / resistance
├── price
├── note
├── visibility           private / public
├── created_at
└── updated_at
```

默认 `visibility = private`，保证用户交易判断不被公开。

### 5.4 图表交互

桌面端：

- 鼠标滚轮缩放
- 鼠标拖拽移动
- 十字线查看 OHLC
- 右键打开 `AnnotationMenu`
- 点击价格线选中对应标注
- 双击价格线进入编辑模式

移动端：

- 手势缩放
- 滑动查看历史
- 长按打开 `AnnotationMenu`
- 右侧面板下沉为折叠区

### 5.5 异常兜底

`KlineChart` 必须处理：

- 空数组
- 同价数据
- high/low 为 null 或非有限数字
- volume 为 0
- 容器宽度为 0
- 后端返回时间格式不合法
- 组件频繁 mount/unmount

图表组件不得因为异常数据渲染出 `NaN` 坐标。

---

## 6. 全局布局设计

### 6.1 桌面端

```text
┌─────────────────────────────────────────────┐
│ TopNav: Logo / 行情快讯 / 搜索 / 用户状态      │
├──────────┬──────────────────────────────────┤
│ Sidebar  │ Main Content                      │
│ 自选      │ Dashboard / 行情中心 / 详情页       │
│ 品种      │                                  │
│ 评论      │                                  │
│ 工具      │                                  │
├──────────┴──────────────────────────────────┤
│ TickerTape: 底部行情滚动条                    │
└─────────────────────────────────────────────┘
```

### 6.2 移动端

```text
┌──────────────────────┐
│ TopNav 简化版          │
├──────────────────────┤
│ Main Content          │
├──────────────────────┤
│ MobileTabbar          │
└──────────────────────┘
```

移动端侧边栏改为底部 Tab：

- 市场
- 品种
- 评论
- 我的

### 6.3 页面改造

| 页面 | 改造目标 |
|------|----------|
| `/` | 从热门卡片页升级为 Dashboard |
| `/products` | 从简单表格升级为行情中心 |
| `/products/[id]` | 从详情页升级为行情工作台 |
| `/my-comments` | 从列表页升级为轻量个人中心 |

---

## 7. 页面规划

### 7.1 首页 Dashboard

模块：

- 市场概览
- 涨跌幅排行
- 成交量排行
- 热门品种
- 最新评论
- 我的关注

第一阶段可先使用现有 `/api/products` 和 `/api/comments/user/{username}` 能力，避免等待新后端。

### 7.2 行情中心 `/products`

桌面端：

- 专业行情表格
- 支持排序
- 支持横向滚动
- 支持搜索
- 支持品种分类
- 支持自选星标

移动端：

- 卡片化行情列表
- 显示名称、代码、价格、涨跌幅、成交量
- 点击进入详情

### 7.3 品种详情 `/products/[id]`

桌面端布局：

```text
┌────────────────────────────────────────────┐
│ 品种标题 / 最新价 / 涨跌幅 / 更新时间          │
├──────────────────────────────┬─────────────┤
│ KlinePanel                   │ 交易信息      │
│                              │ 支撑/阻力     │
│                              │ 预警设置占位   │
├──────────────────────────────┴─────────────┤
│ 评论区                                      │
└────────────────────────────────────────────┘
```

移动端布局：

```text
品种摘要
KlinePanel
交易信息折叠区
支撑/阻力折叠区
评论区
```

### 7.4 我的评论 `/my-comments`

模块：

- 用户摘要
- 评论列表
- 空状态引导
- 未登录状态引导登录

---

## 8. 状态管理设计

### 8.1 Auth Store

解决当前登录态不共享的问题。

```ts
interface AuthStore {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<void>
  loadMe: () => Promise<void>
  logout: () => void
}
```

使用方：

- `TopNav`
- `CommentComposer`
- `MyCommentsPage`
- `ProductDetailPage`

### 8.2 Watchlist Store

第一阶段使用 localStorage：

```ts
interface WatchlistStore {
  symbols: string[]
  toggle: (symbol: string) => void
  has: (symbol: string) => boolean
}
```

### 8.3 UI Store

管理：

- 主题
- Sidebar 展开状态
- 登录弹窗
- 注册弹窗
- 全局搜索弹窗

---

## 9. API 与请求状态

当前 `api.ts` 可继续保留，但建议拆出请求状态 hook：

```ts
interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}
```

页面必须区分：

- loading
- error
- empty
- success

错误态统一使用 `ErrorState` 组件：

- 显示失败原因
- 提供重试按钮
- 对 401 做登录提示

空状态统一使用 `EmptyState` 组件：

- 首页无品种
- 列表无搜索结果
- 评论为空
- 未登录

---

## 10. 视觉规范

### 10.1 色彩

```css
:root {
  --bg: #0f172a;
  --surface: #111827;
  --panel: #1e293b;
  --panel-soft: #172033;
  --border: #263244;

  --text: #f1f5f9;
  --muted: #94a3b8;
  --subtle: #64748b;

  --brand: #3b82f6;
  --up: #ff6b6b;
  --down: #4ade80;
  --warning: #f59e0b;
  --success: #22c55e;
  --danger: #ef4444;
}
```

说明：

- `--up` 用于国内红涨
- `--down` 用于国内绿跌
- `--brand` 用于按钮、链接、选中态
- 大面积背景只使用深蓝/深灰，不使用大面积渐变

### 10.2 字体

```css
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
    "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
}

.font-mono {
  font-family: "JetBrains Mono", "Roboto Mono", Consolas, monospace;
}
```

### 10.3 组件风格

- 圆角统一 8px
- 行情卡片不使用大阴影
- 弹窗、下拉菜单允许轻微阴影
- 边框使用 1px
- 动画时间不超过 200ms
- 不使用夸张装饰背景
- 不使用大面积纯单色蓝紫风格
- 表格数字右对齐
- 价格和百分比使用等宽字体

---

## 11. 可访问性与快捷键

第一阶段：

- 弹窗支持 `ESC` 关闭
- 登录/注册弹窗有明确 title
- 按钮有 disabled/loading 状态
- 表格排序按钮有 `aria-sort` 或文本提示
- 图表标注菜单可通过键盘关闭

第二阶段：

- `/` 打开全局搜索
- `1-4` 切换主导航
- `N` 新建讨论，占位即可
- 移动端长按图表打开标注菜单

---

## 12. 性能目标

第一阶段：

- 保持 30 秒轮询
- 页面卸载清理 interval
- 图表组件 unmount 时销毁实例
- 避免每次 render 重建 chart
- K 线数据转换使用 `useMemo`

第二阶段：

- 行情列表虚拟滚动
- 图表库按页面懒加载
- 评论列表分页
- 预留 WebSocket/SSE 接口

---

## 13. 分阶段实施计划

### 阶段一：稳定性与架构收敛

目标：先修掉当前影响使用的缺陷。

任务：

- 新增全局登录态管理
- 拆出登录/注册弹窗
- 首页、列表、详情、我的评论补齐错误态和空状态
- 品种列表补移动端横向滚动或卡片布局
- 详情页补响应式布局
- K 线图补空数据和异常数据兜底
- 固定 ESLint 配置，避免 `npm run lint` 进入交互初始化

验收：

- 登录后详情页无需刷新即可评论
- 移动端详情页不横向溢出
- API 失败时用户看到错误和重试按钮
- `npx.cmd tsc --noEmit` 通过
- `npm.cmd run lint` 可非交互执行

### 阶段二：Lightweight Charts 替换 K 线图

目标：建立专业图表底座。

任务：

- 安装 `lightweight-charts`
- 新建 `components/market/KlineChart.tsx`
- 将后端 K 线数据转换为 Lightweight Charts 数据格式
- 支持蜡烛图
- 支持成交量柱
- 支持十字线
- 支持自适应 resize
- 支持支撑位/阻力位 price line
- 使用 `AnnotationMenu` 替代浏览器 `confirm`

验收：

- 桌面端可缩放、拖拽、查看十字线
- 移动端可滑动查看
- 支撑位/阻力位可新增、删除、显示
- 图表无数据时显示空状态，不显示 mock 数据冒充真实行情

### 阶段三：全局布局与视觉升级

目标：从普通页面升级为行情社区工作台。

任务：

- 新增 `AppShell`
- 新增 `TopNav`
- 新增 `Sidebar`
- 新增 `MobileTabbar`
- 新增 `TickerTape`
- 首页改为 Dashboard
- 列表页改为行情中心
- 详情页改为交易工作台
- 统一圆角、边框、字体、颜色 token

验收：

- 桌面端有稳定侧边栏和主内容区
- 移动端有底部 Tab
- 页面视觉统一，圆角、颜色、间距一致
- 核心行情信息优先级清晰

### 阶段四：社区标注持久化

目标：让支撑/阻力位成为社区能力。

任务：

- 设计并接入后端标注 API
- 默认私密标注
- 支持用户手动设为公开
- 支持按品种读取我的标注
- 支持删除、隐藏、编辑备注
- 详情页展示“我的标注”和“公开标注”两组视图

验收：

- 用户标注默认不公开
- 刷新页面后标注仍存在
- 未登录用户不能创建私密标注
- 删除标注后图表同步移除价格线

### 阶段五：后续增强

候选能力：

- 自选品种持久化到后端（已确认必须加入后端后续迭代）
- 价格预警
- WebSocket 或 SSE 实时行情
- 评论与图表时间点联动
- 帖子系统
- 策略广场
- 回测报告卡片

---

## 14. 近期推荐开发顺序

建议接下来按以下顺序开工：

1. 固定 ESLint 配置和基础工具链
2. 新增 `AuthStore`，修复详情页登录态不同步
3. 抽 `ErrorState`、`EmptyState`、`Button`、`Input`
4. 改造详情页响应式布局
5. 安装并接入 `lightweight-charts`
6. 替换当前 `KlineChart.tsx`
7. 实现支撑/阻力位 price line 和 `AnnotationMenu`
8. 再做 AppShell 和整体视觉升级

这个顺序的好处是：

- 第一周就能修复真实使用问题
- 图表替换可以独立验证
- 不会被论坛、策略广场、WebSocket 等后续能力拖慢
- 每个阶段都有清晰验收标准

---

## 15. 权限与依赖确认

后续开发中可能需要确认以下操作：

- 安装新前端依赖：`lightweight-charts`
- 如采用 Zustand：安装 `zustand`
- 如采用 SWR：安装 `swr`
- 如需要浏览器验证：启动 `npm run dev`
- 如需要完整构建验证：运行 `npm run build`
- 当前 Windows 环境中 `3000` 可能落在系统 TCP 排除端口段内，前端开发服务默认使用 `127.0.0.1:3200`

所有涉及安装依赖、启动服务、沙箱外构建或网络访问的操作，应在执行前向项目负责人确认。

---

## 16. 最终目标

本轮改版完成后，前端应达到以下状态：

- 视觉上像专业行情社区，而不是普通数据展示页
- 交互上支持真实交易者常用的图表查看和价位标注
- 私密性上不依赖公开第三方图表社区能力
- 技术上保留 Next.js 现有优势，同时具备后续扩展论坛、策略广场、通知中心的空间
- 代码上页面更薄，业务组件更清晰，状态和错误处理更稳定

---

## 17. OpenAlice 参考后的前端框架调整

> 版本：v1.1  
> 日期：2026-05-08  
> 参考来源：[OpenAlice GitHub](https://github.com/TraderAlice/OpenAlice)、[OpenAlice 官网](https://www.traderalice.com/)、[OpenAlice Docs](https://www.openalice.ai/docs/getting-started/what-is-openalice)  
> 结论：不照搬 OpenAlice 的 AI 自动交易和多券商执行能力，但吸收它的“统一工作区、完整生命周期、可审计操作、风险守卫、事件驱动提醒”这些前端产品框架。

### 17.1 可借鉴的 OpenAlice 思路

OpenAlice 的网页和文档强调三个产品支柱：

- **Full-spectrum**：跨资产、跨数据源统一到一个工作台。
- **Full-lifecycle**：从研究、入场、监控、风险管理到退出决策，覆盖完整交易生命周期。
- **Full-control**：所有交易动作有版本历史、安全检查，并在人类明确批准后才执行。

对应到本项目，当前定位仍是“期货行情交流社区”，不做真实下单。因此应转换为：

- **统一行情工作区**：把首页、全部品种、详情页重构为同一套市场工作台，而不是几个孤立页面。
- **研究-标注-讨论-复盘闭环**：用户看行情、画价位、写评论、回看历史评论，是我们的完整生命周期。
- **可审计社区动作**：评论、价位标注、自选、预警等操作要有清晰状态、时间、来源和撤销/编辑入口。
- **风险与隐私守卫**：默认私密标注，不鼓励用户公开敏感交易判断；公开内容需要显式选择。
- **事件驱动提醒**：先做前端“预警中心”和“刷新事件流”框架，后续再由后端 SSE/WebSocket/定时任务接入。

### 17.2 不应照搬的部分

OpenAlice 面向个人 AI 交易代理，核心包括 UTA、Trading-as-Git、Guard Pipeline、Broker、Account Snapshot、AI Provider、Telegram/MCP 等能力。我们当前项目不应直接引入：

- 多券商账户和真实下单执行。
- AI 自动交易、自动调仓、自动风控。
- Telegram/MCP 多连接器。
- 文件驱动配置中心和完整事件总线。
- 过重的 monorepo / Turborepo 架构。

原因：

- 当前后端是 FastAPI + SQLite 的社区产品，不是交易执行系统。
- 用户数据以行情、评论、标注为核心，安全边界应保持简单。
- 前端依赖和状态层应渐进增强，避免在图表稳定前引入过多基础设施。

### 17.3 新的前端信息架构

建议把前端从“页面集合”升级为“行情社区工作台”：

```text
行情工作台
├── 市场总览
│   ├── 热门品种
│   ├── 涨跌排行
│   ├── 成交量/活跃度
│   └── 数据更新时间
├── 品种研究
│   ├── K 线图
│   ├── 技术指标
│   ├── 支撑/阻力
│   └── 相关评论
├── 我的工作区
│   ├── 自选品种
│   ├── 我的标注
│   ├── 我的评论
│   └── 预警草稿
├── 社区讨论
│   ├── 品种评论
│   ├── 热门观点
│   └── 评论历史
└── 系统状态
    ├── 行情刷新状态
    ├── 数据源健康
    └── 后续事件流入口
```

这套结构里的“我的工作区”就是本项目版的轻量 UTA：不代表交易账户，而代表用户在社区里的行情研究上下文。

### 17.4 页面路由建议

短期保留现有路由，避免大规模迁移：

```text
/
/products
/products/[id]
/my-comments
```

中期新增：

```text
/workspace
/workspace/watchlist
/workspace/annotations
/alerts
/activity
```

路由职责：

- `/`：市场总览，类似 OpenAlice 的统一入口，但聚焦行情和社区活跃度。
- `/products`：专业行情表格，支持排序、筛选、分组、移动端卡片。
- `/products/[id]`：品种研究工作台，承载图表、标注、评论、技术分析。
- `/workspace`：用户自己的研究上下文，自选、标注、评论、预警集中展示。
- `/activity`：操作与数据事件流，先展示评论/标注/刷新记录，后续承接通知中心。

当前 `/workspace` 中的“自选观察”只是前端占位和活跃品种入口。后续后端迭代必须补齐真实自选能力：

```text
watchlists
├── id
├── user_id
├── product_id / variety_id
├── sort_order
├── note
├── created_at
└── updated_at
```

建议 API：

- `GET /api/watchlist`：读取当前用户自选品种。
- `POST /api/watchlist`：添加品种到自选。
- `PATCH /api/watchlist/{id}`：更新排序、备注等用户私有信息。
- `DELETE /api/watchlist/{id}`：移除自选。

前端接入后，`WatchlistPanel` 应从真实 API 读取，不再使用热门/活跃品种占位数据。

### 17.5 组件框架更新

在原第 4 节目录结构基础上，建议新增三个模块：

```text
frontend/
├── components/
│   ├── activity/
│   │   ├── ActivityFeed.tsx
│   │   ├── ActivityItem.tsx
│   │   └── RefreshStatus.tsx
│   ├── alerts/
│   │   ├── AlertRuleCard.tsx
│   │   ├── AlertRuleEditor.tsx
│   │   └── AlertStatusBadge.tsx
│   ├── workspace/
│   │   ├── WorkspaceSummary.tsx
│   │   ├── WatchlistPanel.tsx
│   │   ├── MyAnnotationsPanel.tsx
│   │   └── MyResearchTimeline.tsx
│   ├── community/
│   ├── layout/
│   ├── market/
│   └── ui/
├── hooks/
│   ├── useMarketPolling.ts
│   ├── useWorkspace.ts
│   ├── useActivityFeed.ts
│   └── useAlertRules.ts
├── store/
│   ├── auth.ts
│   ├── market.ts
│   ├── workspace.ts
│   └── ui.ts
└── lib/
    ├── api.ts
    ├── events.ts
    ├── format.ts
    └── guards.ts
```

命名说明：

- `workspace`：用户个人行情研究上下文。
- `activity`：评论、标注、刷新、预警等事件展示层。
- `alerts`：价格预警和条件提醒，第一阶段可只做前端草稿。
- `guards.ts`：不是交易风控，而是前端内容与操作守卫，例如未登录禁止评论、公开标注二次确认、敏感内容提示。

### 17.6 状态管理边界

借鉴 OpenAlice “接口层、核心层、领域层、自动化层”的分层，但保持轻量：

```text
UI Layer
  页面、布局、按钮、表格、图表

Client Core
  AuthProvider / market store / workspace store / polling hooks

Domain Modules
  market / community / annotations / alerts / activity

Backend API
  FastAPI routers: products, varieties, realtime, kline, comments, auth
```

状态归属：

- 登录用户、token：`AuthProvider`，后续可迁入 `store/auth.ts`。
- 行情列表、轮询状态：`hooks/useMarketPolling.ts` 或 `store/market.ts`。
- 图表交互局部状态：留在 `KlinePanel`，避免全局污染。
- 自选、标注、预警草稿：`store/workspace.ts`，后端 API 可用后再持久化。
- 弹窗、侧栏、移动端导航：`store/ui.ts`。

暂不建议立即引入复杂数据层。当前可以先用 React Context + 自研 hooks；当接口缓存、分页、乐观更新变多时，再引入 SWR 或 TanStack Query。

### 17.7 Trading-as-Git 的社区化改造

OpenAlice 的 Trading-as-Git 是 `stage -> commit -> push`，用于真实交易前审批。我们可以把它降级为“研究动作草稿流”：

```text
draft -> publish/private-save -> history
```

对应功能：

- 标注草稿：用户在图表上点价位，先进入草稿态。
- 保存私密：默认只自己可见。
- 发布公开：需要显式点击公开，并提示“公开后其他用户可见”。
- 历史记录：记录标注创建、编辑、删除、评论关联。

前端文案建议：

- 不使用“下单、执行、推送”等容易误导的词。
- 使用“保存标注、公开观点、撤回公开、编辑备注、查看历史”。

### 17.8 Guard Pipeline 的社区化改造

OpenAlice 的 Guard 是交易执行前的安全检查。我们这边可做成前端和 API 双层守卫：

- 未登录守卫：评论、私密标注、自选、预警必须登录。
- 隐私守卫：标注默认私密，公开前二次确认。
- 内容守卫：评论长度、空内容、HTML 转义状态可见。
- 行情守卫：价格为空、K 线为空、异常数字时给出明确降级 UI。
- 频率守卫：刷新按钮有冷却和 loading 状态，避免重复请求。
- 移动端守卫：详情页关键操作在小屏不被隐藏。

这些守卫应沉淀到 `lib/guards.ts` 和复用组件里，而不是散落在页面 JSX 中。

### 17.9 Heartbeat 的社区化改造

OpenAlice 的 Heartbeat 是定期检查市场并在重要时提醒。我们可以分三步实现：

1. **前端状态心跳**：显示最后刷新时间、下一次刷新倒计时、失败次数、手动重试。
2. **本地预警草稿**：用户可创建“价格高于/低于某值”的规则，但先不保证后台提醒。
3. **后端事件推送**：接入 SSE/WebSocket 或轮询 `/api/activity`，展示价格触发、评论回复、数据源异常。

第一阶段只需要 UI 框架和状态字段：

```ts
export interface MarketHeartbeat {
  status: 'idle' | 'refreshing' | 'healthy' | 'stale' | 'error'
  lastUpdatedAt?: string
  nextRefreshAt?: string
  failureCount: number
  message?: string
}
```

### 17.10 迭代优先级调整

原第 14 节的开发顺序建议调整为：

1. 固定 ESLint、TypeScript、基础 UI 组件和 `AuthProvider`。
2. 抽 `useMarketPolling`，统一首页、列表页、详情页刷新状态。
3. 建立 `AppShell`，形成桌面侧栏 + 移动底部导航 + 顶部状态条。
4. 改造首页为“市场总览”，新增刷新状态、涨跌排行、成交量摘要。
5. 改造 `/products/[id]` 为“品种研究工作台”，先稳定响应式布局。
6. 接入 `lightweight-charts`，替换自研 SVG K 线图。
7. 实现私密标注草稿、支撑/阻力 price line、非原生 `AnnotationMenu`。
8. 新增 `/workspace`，聚合我的评论、自选占位、我的标注占位。
9. 新增 `/activity` 的只读事件流框架，先展示前端生成事件。
10. 后端补标注、自选、预警、事件流 API 后，再逐步持久化。

### 17.11 新增验收标准

产品体验：

- 用户进入首页后，能在 10 秒内判断市场整体涨跌、活跃品种和数据是否新鲜。
- 用户进入品种详情后，首屏能同时看到价格、K 线、支撑/阻力、评论入口。
- 用户知道哪些内容是私密的，哪些内容会公开。
- 移动端能完成查看行情、进入详情、阅读评论、提交评论。

技术架构：

- 页面文件只负责数据编排和布局，不承载大段业务逻辑。
- 行情刷新、错误、空状态有统一 hook 和 UI。
- 图表交互状态不泄漏到全局 store。
- 评论、标注、自选、预警这些用户动作有统一的权限守卫。
- 新增依赖必须服务于明确模块，不为“未来可能需要”提前安装。

风险边界：

- 所有 UI 文案避免暗示平台能保证收益或自动交易。
- 任何“策略、预警、观点”均表达为用户研究辅助，不表达为投资建议。
- 未实现真实后台提醒前，预警功能必须标注为本地草稿或前台监控能力。
