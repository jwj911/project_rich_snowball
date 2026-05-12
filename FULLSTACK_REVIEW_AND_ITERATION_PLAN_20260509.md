# 前后端整体评审建议与成熟迭代方案

> 版本：v1.0 Fullstack Review  
> 日期：2026-05-09  
> 范围：`frontend/`、`python/`、数据采集、部署配置、测试体系、现有评审/迭代文档  
> 定位：承接既有后端专项计划与 Lightweight Charts 前端计划，形成一份可直接拆任务执行的全栈路线图。

---

## 1. 执行摘要

项目已经从早期“期货品种展示 + 评论”演进为“登录后的期货行情工作台”。近期迭代完成了多项关键修复：前端统一了认证上下文和应用壳，K 线图切换到 `lightweight-charts`，增加了我的工作区与本地价位标注；后端修复了 PostgreSQL upsert、生产环境配置约束、CORS 变量兼容、ORM 缓存 DTO 化、调度器延迟初始化和更多回归测试。

当前系统的主要矛盾已经不再是“能否跑起来”，而是：

- 前端体验已经有工作台雏形，但业务状态仍分散，本地标注、自选、评论、行情刷新没有形成统一工作流。
- 后端具备新旧双数据层，但 API 仍让前端依赖旧 `products` 兼容层，合约、换月、交易日历等期货核心语义尚未贯通。
- 数据采集能力扩展较快，但生产运行边界、任务状态、失败告警、历史回填与在线服务之间的分工还不够清晰。
- 测试主要集中在后端安全和集成行为，前端仍缺自动化测试；全链路验收仍靠人工观察。
- 文档数量较多，但缺少从产品目标到工程任务的统一优先级视图。

本方案建议下一阶段按“四条主线”推进：

1. **产品闭环**：把行情查看、标注、评论、自选、工作区打通。
2. **行情语义**：从品种视角升级到“品种 + 合约 + 交易日 + 连续合约”视角。
3. **生产化**：拆分采集 worker，补充可观测性、告警、幂等与数据质量检查。
4. **质量体系**：补前端自动化测试、全栈冒烟测试、迁移/回填演练和发布检查清单。

---

## 2. 当前状态评审

### 2.1 前端评审

**优势**

- App Router + Client Components 的组织方式清晰，适合当前业务复杂度。
- `AuthProvider` 已经把登录态从 Navbar 局部状态提升为全局上下文，页面门禁逻辑比早期稳定。
- `useMarketPolling` 将加载、错误、刷新时间、失败次数抽象为 heartbeat，便于后续接入 SSE 或 WebSocket 降级。
- `KlineChart.tsx` 已使用 `lightweight-charts`，具备缩放、十字光标、成交量柱、支撑/阻力价格线等专业交易图能力。
- `components/ui`、`components/market`、`components/workspace` 已经开始形成可复用组件边界。
- 错误态、空态、骨架屏比早期完整，桌面和移动端布局均有考虑。

**主要问题**

| 编号 | 优先级 | 问题 | 影响 |
|------|--------|------|------|
| FE-1 | P0 | 前端没有自动化测试 | 后续改动 K 线、认证、评论时容易回归 |
| FE-2 | P1 | 仍依赖 `localStorage` 存 JWT | XSS 后 token 可被窃取，生产风险较高 |
| FE-3 | P1 | 工作区自选观察仍是占位 | 产品闭环不完整，用户无法沉淀真正关注列表 |
| FE-4 | P1 | 支撑/阻力标注只存本地 | 换设备丢失，无法与后端权限和工作区沉淀联动 |
| FE-5 | P1 | 页面组件仍偏厚 | `products/[id]/page.tsx` 承载数据、状态、布局、评论、标注多个职责 |
| FE-6 | P1 | API 类型与业务状态未统一 | 旧 `Product`、新 `Variety`、`RealtimeQuote` 并行，前端组合成本高 |
| FE-7 | P2 | Navbar 混合导航、占位入口、登录弹窗 | 后续扩展设置、提醒、Agent 状态时会膨胀 |
| FE-8 | P2 | 图表交互缺少键盘和可访问性细节 | 专业用户效率和辅助技术体验不足 |

**总体判断**

前端当前适合进入“产品闭环 + 工程分层”阶段。不要马上引入重型 UI 框架或大规模重写，应先把真实自选、后端标注、评论时间线、行情 API 类型收敛做好，再补测试。

---

### 2.2 后端评审

**优势**

- FastAPI Router 分域清楚，`auth/products/comments/varieties/kline/realtime/health` 边界易懂。
- 关键 P0/P1 安全问题已有明显改善：`SECRET_KEY` 强制校验、生产禁 SQLite、bcrypt、JWT 异常处理、登录限流、XSS 过滤。
- SQLAlchemy 模型已经覆盖用户、评论、品种、实时行情、K 线、Tushare 扩展表、手续费保证金等核心数据。
- `upsert.py` 已按方言选择 PostgreSQL / SQLite insert，解决早期 PostgreSQL upsert 风险。
- 数据采集链路已有 `Collector -> Adapter -> Cleaner -> Upsert -> Pipeline` 分层，扩展真实数据源时不再完全脚本化。
- `data_ingestion_runs`、`/health/ready`、`/health/scheduler` 为可观测性打下了基础。
- pytest 覆盖比早期更完整，包含安全、CORS、缓存、生产配置、PostgreSQL upsert、K 线和评论分页。

**主要问题**

| 编号 | 优先级 | 问题 | 影响 |
|------|--------|------|------|
| BE-1 | P0 | API 仍主要暴露旧 `products` 兼容层给前端 | 新数据层价值没有进入产品主链路，后续迁移成本持续增加 |
| BE-2 | P0 | K 线仍未绑定具体合约 | 主力换月后历史数据语义错误，属于期货业务核心风险 |
| BE-3 | P1 | 缺少合约换月历史和连续合约建模 | 无法可靠解释 AU 主连、当前主力、历史主力的关系 |
| BE-4 | P1 | 交易日历、夜盘归属、节假日未建模 | K 线归档、日线同步和复盘时间轴可能错位 |
| BE-5 | P1 | APScheduler 与 API 进程仍耦合 | 多实例部署会重复跑任务，采集失败和 API 健康语义混在一起 |
| BE-6 | P1 | 限流、缓存、任务状态均为进程内 | 多实例和重启后状态丢失，生产可控性不足 |
| BE-7 | P1 | `ACCESS_TOKEN_EXPIRE_MINUTES` 未从环境变量读取 | `.env.example` 与真实代码不一致 |
| BE-8 | P2 | Decimal/Numeric 到 JSON number 的边界未统一 | 金额、保证金、手续费精度容易在前后端出现不一致 |
| BE-9 | P2 | 缺少统一 Service / Repository 层 | 合约、连续 K 线、工作区 API 继续增加后 Router 会变厚 |

**总体判断**

后端下一阶段的重点不是继续横向加表，而是把“品种、合约、连续行情、用户研究数据”这几个域模型串起来，并建立生产运行边界。尤其 `kline_data` 的合约归属必须优先处理，否则后续图表、回测、复盘、评论关联都会建立在不稳定语义上。

---

### 2.3 数据与采集评审

**优势**

- Mock / AkShare / Tushare 的数据源策略已经可配置。
- Tushare PostgreSQL 历史回填脚本体系较丰富，覆盖日线、结算、仓单、持仓、涨跌停、主力映射、周度统计、手续费保证金。
- Upsert 已经更接近批量、幂等的生产写入方式。

**主要问题**

| 编号 | 优先级 | 问题 | 影响 |
|------|--------|------|------|
| DATA-1 | P0 | 在线采集和历史回填没有统一数据质量报告 | 难以确认哪些品种/日期缺失、重复或异常 |
| DATA-2 | P1 | 回填脚本和应用 pipeline 共享模型但缺少统一任务入口 | 操作依赖人工命令，复现和审计成本高 |
| DATA-3 | P1 | 数据源配额、熔断、重试状态没有统一持久化 | Tushare/AkShare 异常时缺少可解释状态 |
| DATA-4 | P1 | 合约映射只更新当前值，不沉淀 rollover 事件 | 历史可追溯性不足 |
| DATA-5 | P2 | 采集日志与 API 监控未形成指标 | 无法用 dashboard 观察延迟、失败率、最近更新时间 |

---

### 2.4 测试与工程质量评审

**优势**

- 后端测试文件覆盖面已经从安全扩展到生产配置、PostgreSQL upsert 和 API 行为。
- `.env.example`、README、AGENTS 已更新到近期真实端口和当前结构。

**主要问题**

| 编号 | 优先级 | 问题 | 影响 |
|------|--------|------|------|
| QA-1 | P0 | 前端无自动化测试 | 主要用户路径没有机器保护 |
| QA-2 | P1 | 缺少全栈冒烟脚本 | 无法一键验证登录、行情、详情、评论、工作区 |
| QA-3 | P1 | 缺少迁移演练脚本 | SQLite/PG schema 漂移、Alembic head 状态需要人工判断 |
| QA-4 | P2 | 缺少发布 checklist | 端口、CORS、SECRET、scheduler、数据库迁移容易遗漏 |

---

## 3. 迭代原则

1. **先语义，后堆功能**：先修合约、交易日、用户研究数据模型，再做更复杂图表和策略。
2. **兼容层只做过渡**：`/api/products` 可以继续服务旧页面，但新功能应优先走 `/api/varieties`、`/api/contracts`、`/api/workspace`。
3. **前后端联合验收**：每个阶段必须有 API、前端页面、测试、文档四个出口。
4. **生产与开发分明**：Mock 只服务开发；生产数据源失败应暴露 unhealthy 或 degraded，不能静默伪造行情。
5. **小步迁移**：数据库迁移分 expand -> backfill -> switch -> contract 四步，避免一次性破坏已有数据。

---

## 4. 总体路线图

| 阶段 | 主题 | 优先级 | 建议周期 | 核心产出 |
|------|------|--------|----------|----------|
| Phase 0 | 基线确认与文档收敛 | P0 | 1-2 天 | 当前测试可运行、文档索引、发布前检查清单 |
| Phase 1 | 用户工作区闭环 | P0/P1 | 5-7 天 | 后端自选/标注 API、前端真实工作区、评论/标注联动 |
| Phase 2 | 合约与 K 线语义重建 | P0/P1 | 7-10 天 | 合约归属、rollover 历史、连续 K 线接口、前端合约选择 |
| Phase 3 | 数据质量与生产 worker | P1 | 7-10 天 | 独立采集 worker、任务状态、质量报告、熔断/告警 |
| Phase 4 | 前端质量与体验成熟 | P1/P2 | 5-8 天 | Playwright/Vitest、组件拆分、移动端优化、错误恢复 |
| Phase 5 | 实时化与可观测性 | P2 | 7-10 天 | SSE 推送、Redis 状态、Prometheus 指标、dashboard |

---

## 5. Phase 0：基线确认与文档收敛

**目标**：确保下一轮迭代从一个可验证的基线开始。

**任务**

| 任务 | 范围 | 验收标准 |
|------|------|----------|
| P0-0.1 运行后端测试基线 | `python/tests` | `SECRET_KEY=test-secret-key ENABLE_SCHEDULER=0 pytest tests -v` 可运行；失败项记录到 `BACKEND_RUNTIME_ISSUES.md` |
| P0-0.2 运行前端类型检查 | `frontend` | `npx tsc --noEmit` 和 `npm run lint` 结果记录 |
| P0-0.3 确认 Alembic head | `python/alembic` | 空 PG 上 `alembic upgrade head` 成功 |
| P0-0.4 建立发布前 checklist | 新文档或 README 小节 | 覆盖 env、迁移、scheduler、CORS、数据源、健康检查 |
| P0-0.5 清理文档索引 | `README.md` / `AGENTS.md` | 当前全栈计划加入索引，旧文档标明“历史参考”或删除计划 |

**不建议在本阶段做**

- 大规模重构组件。
- 改数据库结构。
- 引入 Redis、SSE、React Query 等新基础设施。

---

## 6. Phase 1：用户工作区闭环

**目标**：把当前“本地标注 + 占位自选 + 评论列表”升级为真实可保存、可查询、可迁移的用户研究工作区。

### 6.1 后端任务

| 任务 | 改动范围 | 说明 | 验收标准 |
|------|----------|------|----------|
| P1-1.1 完善 Watchlist API | `models.py`、`schemas.py`、`routers/watchlists.py` | 基于现有 `WatchlistDB` 增删查改自选，支持 `support_level`、`resistance_level`、`notes` | 登录用户只能访问自己的 watchlist；pytest 覆盖 CRUD 和越权 |
| P1-1.2 新增 PriceLevel/Annotation 模型 | 新迁移、`models.py` | 不建议继续把多价位数组塞到 `WatchlistDB` 单字段；新增 `price_levels` 表更清晰 | 同一用户、同一品种、同一价格、同一类型唯一 |
| P1-1.3 新增 Workspace 聚合 API | `routers/workspace.py` | 返回当前用户评论、标注、自选、最近访问/关注品种 | `/api/workspace/me` 一次请求可驱动工作区首页 |
| P1-1.4 评论关联扩展 | `comments.py`、schema | 评论可选关联 price_level 或 kline 时间点，为后续图表评论联动准备 | 兼容旧评论，新增字段 nullable |

建议新增表：

```text
price_levels
- id
- user_id
- variety_id 或 product_id（迁移期可两者择一，最终用 variety_id）
- type: support/resistance
- price: Numeric(15, 4)
- note: Text
- source: manual/chart_context_menu/imported
- created_at
- updated_at
```

### 6.2 前端任务

| 任务 | 改动范围 | 说明 | 验收标准 |
|------|----------|------|----------|
| P1-2.1 `lib/api.ts` 增加 workspace/watchlist/price-level 方法 | `frontend/lib/api.ts` | 统一 token、错误处理和类型 | 不新增裸 fetch |
| P1-2.2 工作区接真实 API | `workspace/page.tsx`、workspace components | 替换 `WatchlistPanel` 占位和 localStorage 汇总 | 刷新/换设备后自选和标注仍存在 |
| P1-2.3 图表标注同步后端 | `products/[id]/page.tsx`、`KlineChart.tsx` | 右键添加后调用 API；失败时回滚或显示错误 | 支撑/阻力 price line 与后端数据一致 |
| P1-2.4 拆分详情页厚组件 | 新增 `components/market/KlinePanel.tsx`、`components/community/*` | 页面只负责编排和路由参数 | 单文件职责明显下降 |
| P1-2.5 前端表单校验 | 登录/注册/评论/标注 | 显示字段级错误，不只弹通用错误 | 422 响应可读 |

### 6.3 阶段验收

- 用户登录后添加自选、添加支撑位、发表评论，刷新页面后数据仍保留。
- 我的工作区能展示真实自选、真实标注、真实评论时间线。
- 后端 pytest 增加 workspace/watchlist/price-level 覆盖。
- 前端至少完成 TypeScript 检查；若 Phase 4 测试框架已提前接入，则加对应组件/页面测试。

---

## 7. Phase 2：合约与 K 线语义重建

**目标**：解决当前最核心的期货业务风险：K 线只按品种存储，无法可靠处理主力换月和历史合约。

### 7.1 数据模型方案

当前已有 `FutContractDB`，建议不要再新建重复 `ContractDB`，而是在它基础上补齐与品种的关系：

```text
fut_contracts
- id
- ts_code
- symbol
- fut_code
- exchange
- list_date
- delist_date
- contract_type
- is_active
- variety_id 或通过 fut_code/exchange 映射到 varieties
```

新增：

```text
contract_rollovers
- id
- variety_id
- old_contract_id
- new_contract_id
- old_contract_code
- new_contract_code
- effective_date
- source
- created_at

kline_data
- 增加 contract_id nullable
- 回填完成后改为 not null（或至少新数据 not null）
- 唯一键由 variety_id + period + trading_time 迁移为 contract_id + period + trading_time
```

### 7.2 后端任务

| 任务 | 改动范围 | 说明 | 验收标准 |
|------|----------|------|----------|
| P2-1.1 迁移 expand | Alembic、models | `kline_data` 增 `contract_id`，新增 rollover 表 | 旧 API 不受影响 |
| P2-1.2 回填 contract_id | scripts / migration helper | 按当前 `variety.contract_code` 或历史映射回填 | 回填报告列出无法匹配行 |
| P2-1.3 新写入使用 contract_id | pipeline/upsert | `insert_kline_bulk` 根据 contract_code 绑定具体合约 | 同品种不同合约同时间可共存 |
| P2-1.4 新增合约 API | `routers/contracts.py` | `/api/varieties/{symbol}/contracts`、`/api/contracts/{id}/kline` | 前端可切换合约 |
| P2-1.5 连续 K 线 API | service/repository | `/api/varieties/{symbol}/continuous-kline` 基于 rollover 拼接 | 返回点包含 contract_code/source |
| P2-1.6 主力映射沉淀 rollover | `pipeline.run_fut_mapping` | 当前主力变化时写 rollover | 测试覆盖 AU2506 -> AU2512 |

### 7.3 前端任务

| 任务 | 改动范围 | 说明 | 验收标准 |
|------|----------|------|----------|
| P2-2.1 品种详情增加合约选择 | `products/[id]` / `KlinePanel` | 默认主力/连续，支持切具体合约 | UI 上明确显示数据口径 |
| P2-2.2 K 线 tooltip 显示合约 | `KlineChart.tsx` | crosshair 中展示当前 bar 所属 contract_code | 换月处用户可感知 |
| P2-2.3 支撑/阻力绑定口径 | price-level API | 标注可选择绑定品种连续图或具体合约 | 不同合约标注不串 |
| P2-2.4 兼容旧 product id 路由 | routing/api adapter | 详情页仍可从 `/products/{id}` 进入，但内部逐步切新接口 | 无破坏性跳转 |

### 7.4 风险与迁移策略

- 不要一次性删除旧唯一键；先 expand、回填、双写/双读，再切换查询，最后清理。
- `contract_id` nullable 期间，查询必须显式处理 null，不要假设唯一键能挡住重复。
- 连续合约拼接要保留 `contract_code` 元数据，不要只返回裸 OHLC。

---

## 8. Phase 3：数据质量与生产 worker

**目标**：把采集从“应用内定时任务”升级为可审计、可告警、可重复执行的生产数据任务。

### 8.1 后端与运维任务

| 任务 | 改动范围 | 说明 | 验收标准 |
|------|----------|------|----------|
| P3-1.1 拆分 worker 入口 | `python/worker.py` 或 CLI | API 进程 `ENABLE_SCHEDULER=0`，worker 单独运行 scheduler | 多 API 实例不会重复采集 |
| P3-1.2 任务状态表扩展 | `data_ingestion_runs` | 增加 started/finished/duration/source/window/error sample | `/health/scheduler` 能返回最近任务状态 |
| P3-1.3 数据质量报告 | 新 `data_quality_reports` 或脚本输出 | 缺失日期、重复键、异常 OHLC、成交量异常 | 可按品种/日期查询 |
| P3-1.4 数据源熔断 | collector service | 失败率超过阈值暂停一段时间并记录状态 | 不连续打爆外部 API |
| P3-1.5 回填任务统一入口 | `tushare_pg_ingest` | 增加 dry-run、resume、任务记录、统一参数校验 | 回填可重复执行且可追踪 |
| P3-1.6 手续费/保证金接入产品 API | `fut_trade_fee` -> market API | 前端交易信息不再只看旧 product 字段 | API 返回数据来源和更新时间 |

### 8.2 前端任务

| 任务 | 改动范围 | 说明 | 验收标准 |
|------|----------|------|----------|
| P3-2.1 数据新鲜度展示 | `RefreshStatus`、行情卡片 | 显示最近成功采集时间和 degraded 状态 | 用户能区分“无数据”和“数据源异常” |
| P3-2.2 后台任务状态页 | 可在 `/workspace` 或新页面 | 只对管理员/开发模式显示 | 可查看 scheduler 最近任务 |
| P3-2.3 交易信息来源标注 | 品种详情 | 保证金/手续费展示来源、更新时间 | 减少误用过期参数 |

---

## 9. Phase 4：前端质量与体验成熟

**目标**：为现有核心路径补自动化测试，并把页面从“能用”打磨到“可长期迭代”。

### 9.1 测试方案

建议引入：

- **Vitest + React Testing Library**：测试 hooks、纯组件、格式化、API adapter。
- **Playwright**：测试登录、行情列表、品种详情、评论、工作区核心路径。

最小测试集：

| 类型 | 用例 | 验收 |
|------|------|------|
| Unit | `formatNumber`、`getChangeTone` | null/undefined/正负数边界正确 |
| Unit | `useMarketPolling` | 成功、失败、禁用、手动 refresh |
| Component | `QuoteTable` | 排序按钮和空值显示 |
| Component | `KlineChart` | 空数据不崩、异常数据过滤、price lines 更新 |
| E2E | 登录 -> 行情 -> 详情 -> 评论 | 页面无 uncaught error |
| E2E | 添加标注 -> 工作区查看 | 标注可持久化 |

### 9.2 组件重构

| 任务 | 改动范围 | 验收标准 |
|------|----------|----------|
| P4-1 拆 Navbar | `Navbar.tsx` -> `Sidebar`、`MobileNav`、`AuthModal` | 单个组件不再承载所有导航与表单 |
| P4-2 拆详情页 | `ProductHeader`、`KlinePanel`、`TradingInfoPanel`、`CommentPanel` | 页面文件主要是数据编排 |
| P4-3 抽 API hooks | `hooks/useProducts`、`useProductDetail`、`useWorkspace` | 页面不直接处理复杂请求组合 |
| P4-4 统一 design tokens | Tailwind config / globals | 颜色、边框、圆角、字体一致 |
| P4-5 移动端图表体验 | K 线容器与工具栏 | 小屏不遮挡、不溢出、可切周期 |

---

## 10. Phase 5：实时化与可观测性

**目标**：在前面语义和质量稳定后，升级实时行情体验和生产观测能力。

### 10.1 实时推送

建议采用 SSE 作为第一阶段实时方案：

- 对行情这种单向更新，SSE 比 WebSocket 简单。
- 前端保留 30 秒轮询作为 fallback。
- worker 与 API 之间不要用进程内 broadcast，应通过 Redis Pub/Sub、数据库更新时间轮询或消息队列连接。

任务：

| 任务 | 范围 | 验收 |
|------|------|------|
| P5-1 SSE 端点 | `/api/stream/realtime` | 登录用户可订阅自选或热门品种 |
| P5-2 Redis Pub/Sub | worker -> API | worker 更新行情后发布 symbol 事件 |
| P5-3 前端 fallback | `useRealtimeQuotes` | SSE 失败自动回到 polling |
| P5-4 限流与断线控制 | 后端 | 单用户连接数限制，心跳保活 |

### 10.2 可观测性

任务：

| 任务 | 范围 | 验收 |
|------|------|------|
| P5-5 Prometheus 指标 | FastAPI middleware + collector metrics | 请求延迟、错误率、采集成功/失败、缓存命中 |
| P5-6 请求 ID | middleware/logging | 日志可串联一次请求 |
| P5-7 慢查询日志 | SQLAlchemy events 或 DB 层 | 超阈值查询有日志 |
| P5-8 告警规则 | 文档/配置 | 数据源连续失败、K 线断档、DB 不可用 |

---

## 11. 建议任务拆分清单

### Sprint A：基线与工作区（建议先做）

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| A1 | 运行并记录后端/前端基线检查 | P0 | 0.5d |
| A2 | 新增 watchlists router/schema/tests | P0 | 1d |
| A3 | 新增 price_levels 表与 API | P0 | 1.5d |
| A4 | 新增 workspace 聚合 API | P1 | 1d |
| A5 | 前端工作区接真实 API | P1 | 1d |
| A6 | 品种详情标注从 localStorage 迁到后端 | P1 | 1.5d |
| A7 | 文档更新与人工验收 | P1 | 0.5d |

### Sprint B：合约 K 线

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| B1 | 设计并迁移 `kline_data.contract_id` | P0 | 1.5d |
| B2 | 回填 contract_id 脚本和报告 | P0 | 1d |
| B3 | 修改 K 线写入与查询服务 | P0 | 2d |
| B4 | 新增 contracts API | P1 | 1d |
| B5 | 新增 continuous-kline API | P1 | 2d |
| B6 | 前端合约/连续切换 | P1 | 1.5d |
| B7 | 测试与迁移演练 | P0 | 1d |

### Sprint C：生产数据任务

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| C1 | 独立 worker 入口 | P1 | 1d |
| C2 | scheduler 状态与任务历史增强 | P1 | 1.5d |
| C3 | 数据质量报告 | P1 | 2d |
| C4 | 数据源熔断和配额保护 | P1 | 2d |
| C5 | 回填脚本统一 dry-run/resume | P2 | 2d |
| C6 | 前端数据新鲜度展示 | P2 | 1d |

### Sprint D：前端质量

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| D1 | 接入 Vitest/RTL | P1 | 1d |
| D2 | 接入 Playwright 冒烟测试 | P1 | 1.5d |
| D3 | 拆分 Navbar/AuthModal | P2 | 1d |
| D4 | 拆分 ProductDetailPage | P1 | 2d |
| D5 | 抽数据 hooks | P1 | 1.5d |
| D6 | 移动端图表和表格回归 | P2 | 1d |

---

## 12. 风险清单

| 风险 | 等级 | 缓解 |
|------|------|------|
| K 线迁移破坏旧数据 | 高 | expand/backfill/switch/contract 四步迁移，保留旧 API 回退 |
| 前端从 localStorage 迁后端导致用户已有本地标注丢失 | 中 | 首次进入时检测 localStorage，提供导入到后端的迁移逻辑 |
| Tushare/AkShare 配额受限 | 中 | dry-run、熔断、回填窗口限制、任务 resume |
| 引入测试框架导致依赖和配置 churn | 中 | 先最小 Vitest + Playwright，不引入大型状态库 |
| Redis/SSE 过早引入增加复杂度 | 中 | Phase 5 再做，Phase 1-4 保留 polling |
| 旧 `ProductDB` 与新 `VarietyDB` 长期并存 | 高 | 每个新功能优先用新数据层，同时提供 adapter 给旧路由 |

---

## 13. 成功指标

### 产品指标

- 用户可以完成：登录 -> 选品种 -> 看 K 线 -> 添加标注 -> 评论 -> 回工作区复盘。
- 自选和标注跨刷新、跨设备保留。
- 品种详情能明确显示当前数据口径：主力、连续、具体合约。

### 工程指标

- 后端测试稳定通过，新增 workspace、price-level、contract-kline 覆盖。
- 前端至少有核心组件单测和 2 条 E2E 冒烟链路。
- API 进程和采集 worker 可独立运行。
- PostgreSQL 空库可 `alembic upgrade head` 后启动。
- 数据质量报告能回答“某品种某周期是否缺数据”。

### 生产指标

- `/health/ready` 表示 API 就绪，不被 scheduler 状态误伤。
- `/health/scheduler` 能展示最近采集任务和失败原因。
- 数据源失败不会静默降级为 Mock。
- 实时行情数据有明确 `updated_at` 和来源状态。

---

## 14. 与既有文档的关系

- `BACKEND_ITERATION_PLAN_v7_COMPREHENSIVE.md`：后端专项计划，已有许多 P0/P1 已完成，后续应以本文件的 Phase 2/3 作为更新方向。
- `FRONTEND_ITERATION_PLAN_LIGHTWEIGHT_CHARTS.md`：前端图表改版专项，Lightweight Charts 接入已基本完成，后续应把重点转到工作区闭环、后端标注和测试。
- `DATA_PIPELINE_AND_POSTGRES_GUIDE.md`：继续作为数据流水线和 PG 运维细节文档。
- `README.md` / `AGENTS.md`：保留快速入门和 AI 助手上下文，本文件作为总评审与迭代路线入口。

---

## 15. 推荐立即执行顺序

1. 运行 Phase 0 基线检查，确认当前测试和类型检查真实状态。
2. 开 Sprint A，先实现后端 watchlist / price-level / workspace API。
3. 前端工作区接真实 API，并加入 localStorage 标注导入后端的兼容逻辑。
4. 开 Sprint B 前先评审 K 线迁移 SQL 和回填脚本，避免破坏已有行情。
5. 在 Sprint B 完成后，再考虑 worker 拆分和数据质量平台化。

这条路径能最快把项目从“展示型行情社区”推进到“可沉淀用户研究、可解释行情数据、可生产运行”的成熟形态。
