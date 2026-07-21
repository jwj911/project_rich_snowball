<!-- .agents/roadmap.md — 模块演进状态与待处理事项 -->

## 主要模块演进状态

### Phase 0：可运行性收口 — 已完成（2026-07-18）

- Mock 初始化补齐 `FutMainDailyDataDB` 主力日线，恢复 `/api/varieties` 列表数据
- 同步前端 `useProductKline` 测试契约，修复后端 schema 测试的执行顺序依赖
- `requirements.txt` / `requirements.lock` 补齐 `scikit-learn`、`feedparser` 及其依赖
- Python `ruff check .`、后端全量 pytest、前端 Vitest、TypeScript、ESLint、production build 全部通过
- 当前基线：后端 `965 passed, 8 skipped, 0 failed`；前端 `195 passed, 0 failed`
- 详细记录：[docs/iteration_plan_20260718_project_audit.md](../docs/iteration_plan_20260718_project_audit.md)

### Phase 1：行情读模型收敛 — 已完成（2026-07-18）

- `/api/varieties` 查询收敛到 `MarketDataService`
- 主力日线优先、实时快照 fallback、无数据状态和来源字段统一
- 新增 `upsert_fut_main_daily_bulk`、主力日线 pipeline 和 scheduler job
- 增加 SQLite/PG 读写回归与 `data_source` / `data_freshness` 测试

### Phase 2：执行可靠性与生产拓扑 — 已完成（2026-07-19）

- Agent 步骤持久化改为任务级事务，避免步骤级 `commit()` 带来的 SQLite 锁竞争
- `docker-compose.yml` 中 backend 关闭 scheduler，新增独立 worker 作为唯一 scheduler owner
- backend CI 增加 direct dependency/lock 漂移检查、PostgreSQL API smoke，coverage 门槛提升到 `40%`
- frontend CI 增加 PostgreSQL + Alembic + backend 启动和 Playwright Chromium smoke
- 新增 `fut_main_daily_data` Alembic 迁移 `f7a8b9c0d1e2`，并验证 `(variety_id, ts_code, period, trade_date)` 唯一键
- 升级 `python-multipart`、`scikit-learn`、`starlette` 到无已知漏洞版本，lock 漂移检查保持通过
- 本地后端全量：`965 passed, 8 skipped, 0 failed`；覆盖率 `71.97%`
- Backend CI #22：Alembic、PostgreSQL pytest、API smoke、Ruff、`pip-audit` 全部通过
- 前端 Vitest：`195 passed, 0 failed`；TypeScript、ESLint、production build 通过
- Frontend CI #28（run `29670891119`）：PostgreSQL migration、backend、frontend build/start、Chromium Playwright、Vitest、Lighthouse 全部通过
- 详情页价位标注 E2E 使用精确 heading 定位，`usePriceLevels` 增加主力范围隔离和 optimistic mutation 保护
- 详细记录：[docs/iteration_plan_20260718_project_audit.md](../docs/iteration_plan_20260718_project_audit.md)

下一阶段：进入 Phase 3「文档与发布治理」，建立唯一现状基线、发布清单和历史计划归档规则。

### Phase 3：文档与发布治理 — 首批完成（2026-07-19）

- `docs/iteration_plan_20260718_project_audit.md` 作为当前迭代唯一事实源
- 新增 [`docs/release_checklist_20260719.md`](../docs/release_checklist_20260719.md)，统一代码、迁移、数据、权限、浏览器、备份和回滚检查
- ProductDB 退场计划、旧前端质量清单和旧前端路线图移动到 `docs/archive/`，并标记为历史记录
- 已完成的 Agent/项目审计、P0-P2、Phase 5 及 2026-07-05 修复记录移动到 `docs/archive/`，保留历史上下文但不再作为当前执行入口
- `.agents/data.md` 移除已退场的兼容层调度任务，更新归档链接

### Phase 3：文档与发布治理 — 第三批完成（2026-07-21）

- 新增 [`docs/releases/README.md`](../docs/releases/README.md)，固定工程基线和生产发布记录格式；
- 新增 [`docs/releases/20260721_engineering_baseline.md`](../docs/releases/20260721_engineering_baseline.md)，记录 Phase 3 文档治理基线，并明确其不是生产发布；
- `AGENTS.md`、`README.md`、`.agents/operations.md` 已接入发布记录入口；
- 未执行的生产检查保持未勾选，避免用历史 CI 结果冒充本次生产验收。

Phase 3 后续只在真实发布窗口填写生产记录；工程风险治理进入 Phase 4。

### Phase 4：远期风险与安全 — 第一项完成（2026-07-21）

- Agent `query_database` 已切换到 `sqlglot` AST 只读校验；
- 覆盖单语句、SELECT/集合查询根节点、DML/DDL/事务节点、危险函数、CTE/子查询和 schema/table 白名单；
- 新增 `sqlglot` 直接依赖与锁定版本，补充 31 个数据库工具回归用例；
- 详细记录：[`docs/phase4_sql_ast_readonly.md`](../docs/phase4_sql_ast_readonly.md)

### Phase 1~3：用户工作区、合约 K 线、生产边界 — 已完成

- `price_levels` / `watchlists` / `workspace` 云端同步闭环
- `contract_rollovers` + 连续 K 线拼接 + 合约切换
- 独立 worker、`ENABLE_SCHEDULER=0` 默认、数据源熔断、数据质量检查

### Phase 4：ProductDB 全面退场 — 已完成（2026-05-28）

- 删除 `products` 物理表及所有废弃代码，品种数据统一走 `VarietyDB`
- pytest 全部通过

### 前端监控闭环 — 已完成（2026-06-01）

- 后端：`POST /api/log/frontend` + `FrontendLogDB` + Alembic 迁移
- `sentry-lite.ts` + `lib/vitals.ts`：无论 Sentry 是否启用，总是同时发送到后端日志端点
- 后端 `GET /api/log/frontend` 支持 admin 查询全部 / 普通用户查询自己的日志

### CSRF 防护 — 已完成（2026-05-29）

- 后端 `dependencies.py` 方法感知鉴权
- `test_csrf_protection.py` 覆盖写接口拒绝/读接口兼容

### SSE 鉴权统一 — 已完成（2026-05-29）

- 方案 B：废弃 stream-token，SSE 鉴权统一走 cookie-only 路径
- `/api/realtime/stream-token` endpoint 标记 `deprecated=True`
- SSE 连接为进程内状态，单实例或 sticky session 部署

### 交易时段 badge 后端权威化 — 已完成（2026-05-29）

- `useMarketStatus()` SWR hook 统一消费 `/api/market/status`
- `MarketSessionBadge` 和 `MarketClosedBanner` 共用同一份后端状态

### 价位标注 batch scope/contract 补齐 — 已完成（2026-05-29）

- `PriceLevelBatchItem` schema 与单条在 scope/contract_id 语义上完全一致
- 重复检测 key 扩展为 `(variety_id, type, price, scope, contract_id)`

### Lighthouse 性能基线 — 已完成（2026-05-29）

- `scripts/lighthouse-baseline.js`：headless Chrome 测量首页未登录态性能
- 报告保存到 `.lighthouse/latest.json`
- `frontend-ci.yml` 集成 Lighthouse，build 后自动跑基线

### 标注价格精度统一 — 已完成（2026-05-29）

- `formatPricePayload(price, precision)` 专用于 API payload 格式化
- `usePriceLevels` 创建/迁移标注时使用 `formatPricePayload()` 替代 `toFixed(2)`

### SSE URL 截断 — 已完成（2026-05-29）

- `frontend/lib/realtimeStore.ts`：`buildSseUrl` 当 symbol 数量 >30 时省略 `symbols` 参数
- 后端 `symbols` 为空时自动订阅全部活跃品种

### 精度中立化 — 已完成（2026-05-29）

- K 线价格显示统一使用 `formatPrice`，支持品种级别 `price_precision` 配置
- `CrosshairTooltip`、`KlineChartHeader`、`PriceChange` 等组件接入精度配置

### AI Chat（期货助手）— 已完成（2026-06-01）

**后端**

- `ChatMessageDB` 模型 + Alembic 迁移
- Router `/api/chat`：历史记录查询 + 发送消息 + 清空对话
- AI 服务 `services/ai_chat.py`：OpenAI 兼容 API，自动检索 `RealtimeQuoteDB` + `OpinionDB` 作为上下文
- 未配置时返回友好提示（不阻断应用启动）

**前端**

- `/chat` 页面：ChatGPT 风格对话界面
- 导航：`secondaryNavGroups` 新增「AI 助手」

### Portfolio（模拟持仓）— 已完成（2026-06-01）

**后端**

- `TradeRecordDB` 模型 + Alembic 迁移
- Router `/api/portfolio`：列表（含实时浮动盈亏）+ 创建 + 平仓 + 删除
- 盈亏公式：`long: (exit - entry) * qty * multiplier`，`short: (entry - exit) * qty * multiplier`

**前端**

- `/portfolio` 页面：盈亏统计面板 + 交易卡片列表
- 导航：`secondaryNavGroups` 新增「模拟持仓」

### Price Alert（价格预警）— 已完成（2026-06-01）

**后端**

- `PriceAlertDB` 模型 + Alembic 迁移
- Router `/api/price-alerts`：CRUD + 触发查询
- Scheduler 集成：`refresh_realtime_quotes` 成功后调用 `_check_price_alerts()`

**前端**

- API 层：`lib/api/price_alerts.ts`
- 品种详情页 `PriceAlertPanel`：表单 + 列表 + 删除

### Opinions（交易观点/日记）— 已完成（2026-05-30）

**后端**

- `opinions` 表 + 生命周期字段（`status/closed_at/actual_outcome`）
- Router `/api/opinions`：公开列表 + 个人时间线 + CRUD
- `OpinionService` 作为 service 层试点，router 仅负责 HTTP 契约转换

**前端**

- `/opinions` 页面：双标签页「全部观点」+「我的观点」
- 筛选：品种、方向、状态

### News（新闻资讯）— 已完成（2026-05-30）

**后端**

- `NewsSourceDB` / `NewsArticleDB` 模型
- RSS 抓取 + AI 摘要（`services/news_fetcher.py`）
- Router `/api/news`：源管理 + 文章列表 + 单篇摘要
- **手动抓取后台化**（2026-06-24）：`/api/news/fetch` 与 `/api/news/sources/{id}/fetch` 改为通过 `BackgroundTasks` 提交后台任务，立即返回 `NewsFetchTaskResponse`，不再同步阻塞 HTTP 请求；新增 `fetch_source_background` / `fetch_all_enabled_sources_background` 函数，内部独立创建 `SessionLocal` 会话

**前端**

- `/news` 页面：来源筛选 + 标题搜索 + AI 解读
- 搜索输入已接入 `useDebouncedValue`

### 前端 Sprint 2：体验优化 — 已完成（2026-06-04）

- **搜索防抖**（P2-1）：新建 `useDebouncedValue.ts`，products 和 news 页面搜索输入防抖 250ms，消除请求洪峰和 UI 闪烁
- **Token 安全评估**（P2-2）：选择方案 C（保守），新建 `frontend/docs/SECURITY_RISKS.md` 记录 RISK-001（access token 存 localStorage）及后续行动项
- **实时行情 Store 语义清晰化**（P2-3）：`realtimeStore.ts` 的 `notifyAll` 同时提供 `snapshot`（全量）和 `delta`（增量），`useRealtimeQuotes.ts` 明确区分增量合并与全量替换场景
- **Lighthouse 端口基线修复**（P2-4）：`.lighthouse/latest.json` url 修正为 `http://127.0.0.1:3200`，与 `npm run dev` 实际端口一致
- **验证**：`npx tsc --noEmit` 通过，`npm run lint` 通过，`useDebouncedValue.test.ts` 通过

### 前端 Sprint 3：架构清理 — 已完成（2026-06-05）

- **导航组件去重**（P3-1）：删除死代码 `SideNav.tsx` 和 `MobileNav.tsx`（无任何页面引用）；`Navbar.tsx` 从 `navigation.ts` 导入 `isActivePath`，消除内联重复定义。遵循“如无必要勿增实体”，不强行拆分 Navbar
- **测试覆盖补齐**（P3-2）：新建 `e2e/metrics.spec.ts`（未登录门禁 + 已登录直达不跳转 + 指标卡片显示）、`e2e/news.spec.ts`（未登录门禁 + 已登录加载 + 搜索框防抖）
- **验证**：`npx tsc --noEmit` 通过，`npm run lint` 通过，单元测试通过

### 后端 Roadmap V3 阶段四：扩展性与限流 — 已完成（2026-06-05）

- **高成本 GET 限流**：`/api/realtime/batch`（60s/100req）、`/api/realtime/stream`（60s/30req）增加独立限流窗口
- **SSE 独立限流**：按 IP 限流，超限时返回 429 而非静默断开
- **登录/注册限流 Redis 化**：与全局限流 middleware 统一，使用 `check_rate_limit`（Redis 优先+内存降级）；action key 独立（`auth:register`/`auth:login`）
- **Redis 空值标记修复**：用常量字符串 `__CACHE_EMPTY__` 替代 dict 对象，穿透防护在 Redis 路径稳定
- **SSE query token 移除**：标记 `deprecated=True`；鉴权改为 cookie 优先，token 仅降级兼容

### 后端 Roadmap V3 阶段五：CI/运维与架构优化 — 已完成（2026-06-05）

- **CI 增强**：backend-ci.yml 增加 Alembic 迁移一致性检查（CI 内嵌 PostgreSQL service）+ pytest-cov（当前阈值 40%）
- **运维文档补齐**：`python/docs/sse_scaling_strategy.md`（SSE 部署约束）、`python/docs/kline_partitioning.md`（K 线表分区策略）
- **交易日历预测告警**：`services/trading_calendar.py` 使用预测年份时输出 warning 日志
- **Service 层试点**：`routers/opinions.py` 提取 `OpinionService`，router 仅负责 HTTP 契约转换
- **compose backend service**：取消 backend 注释，配置健康检查、环境变量、端口映射

### Agent 系统 Phase 0~2 — 已完成（2026-07-04）

**Phase 0：基座修复与边界收敛**

- Alembic revision 冲突修复；`agent_tasks` / `agent_task_steps` 表模型与迁移完成
- 统一 `AgentEvent` schema（start/thought/action/observation/result/error/done）前后端一致
- Tool 注册与执行入口收敛：`@register_tool` 装饰器 + `_execute_tool` 服务层调用
- 复用 `services/ai_chat.py` 作为 LLM client

**Phase 1：DataAgent**

- 品种别名解析（黄金→AU，螺纹钢→RB，原油→SC）
- 5 个数据工具：get_variety_info、get_realtime_quote、get_kline_data、list_active_varieties、get_market_status
- 规则优先解析 + LLM fallback 的意图理解

**Phase 2：TechAnalysisAgent + RiskManagementAgent**

- 后端纯 numpy/pandas 指标库 `python/lib/technical_indicators.py`（12 个指标）
- 技术分析子模块：trend、pattern、divergence、composite（5 维度 0-100 综合评分）
- 风控子模块：position（仓位管理）、stop_loss（5 种止损）、take_profit（5 种止盈）、drawdown（回撤控制）
- 前端 Chat 页升级为 8 种模式切换
- 流式 SSE 展示 Agent 执行过程（步骤展开/收起）

**前端**

- `/chat` 页面重构：模式切换标签 + Agent 执行步骤可视化
- API 层新增 `lib/api/agents.ts`

**体验修复计划 P0/P1（2026-07-04）**

- **流式真实化**：`core.py` 新增 `PROGRESS` 事件与 `map_role_to_event_type`；全部本地 Agent 的 `run_stream` 先 `start`，过程中实时 `thought/action/observation/progress`，最后 `result/error + done`，避免「执行完再回放」。
- **执行器批量提交**：`executor.py` 步骤持久化由 per-step `commit()` 改为批量提交，解决 SQLite `database is locked`。
- **LLM 客户端加固**：`llm_client.py` 共享 `httpx.AsyncClient`、指数退避重试（最多 3 次）、记录上游状态码与响应摘要。
- **风控参数真实化**：`risk_management_agent.py` 浮动盈亏与止损计算使用品种真实 `multiplier` / `tick_size`；移除账户余额 50% 错误兜底；持仓加载失败改 `warning`。
- **策略 DSL 语义修正**：`strategy_compiler_agent.py` 中 MACD+成交量条件改为 `volume > volume_sma * mult`（通过 `transform: multiply_indicator2` 表达）；删除重复 `_is_valid_indicator`。
- **数据 bad 降级**：`analysis_pipeline_agent.py` preflight `bad` 时返回「数据现状报告」+ `completed` 状态，不再直接失败。
- **移除悬空能力**：`routers/agents.py` 与 `schemas.py` 移除未实现的 `orchestrator` 类型。
- **前端 SSE 治理**：`agents.ts` 支持 `AbortSignal`、`event:` 标签解析、malformed 行提示；`chat/page.tsx` 增加 `AbortController` 与停止按钮。
- **测试补强（历史记录）**：新增 `tests/test_agent_streaming.py`、`tests/test_agent_data_preflight.py`；该阶段后端曾达到 `669 passed, 7 skipped, 0 failed`，当前统一基线见本文顶部 Phase 0。

### TraderAgent 新增上线（2026-07-05）

**目标**：新增交易员 Agent，模拟经验丰富的期货交易员，基于多周期图表研判输出具体交易计划。

**后端**

- 新增 `services/agent/trader_agent.py`：交易员 Agent 主类，支持四种交易风格（scalping / intraday_swing / short_term_trend / medium_term_trend）
- 新增 `services/agent/trader/` 子模块：
  - `market_structure.py`：趋势识别、支撑阻力、突破/假突破判断
  - `multi_timeframe.py`：多周期共振分析与入场周期推荐
  - `candlestick.py`：K线形态识别与多空力量评分
  - `trade_plan.py`：交易计划生成（方向/入场/止损/止盈/仓位/盈亏比/置信度）
  - `risk_check.py`：风控校验（单笔风险、盈亏比、仓位、回撤提示）
- 接入 `routers/agents.py`：`_AGENT_CAPABILITIES` 与 `_build_agent()` 增加 `trader`
- 更新 `schemas.py`：`AgentType.TRADER` + task/chat 请求 pattern
- 更新 `services/agent/intent_router.py`：交易相关关键词路由到 `trader`
- 更新 `services/agent/__init__.py`：导出 `TraderAgent`

**前端**

- `frontend/app/chat/page.tsx`：Chat 页增加 `trader` 模式、快捷提示、图标与描述
- `frontend/app/agents/page.tsx`：`agentTypeLabels` 增加 `trader: '交易员'`

**测试**

- `tests/test_trader_modules.py`：12 个单元测试
- `tests/test_trader_agent.py`：6 个集成测试
- trader 专项测试 18 个全部通过；前端 `tsc --noEmit` + `lint` 通过

**设计文档**

- `docs/trader_agent_design.md`：完整设计文档 + 迭代进展记录

### 策略/回测/预警新模块 — 持续迭代中

- `strategies` / `backtest_runs` / `alert_events` / `alert_event_user_states` 等表已加入模型
- 后端 routers：`strategies.py`、`alerts.py`
- 前端页面：`/strategies`、`/alerts`、`/agents`、`/agents/detail`
- 相关 pytest 已覆盖核心链路：`test_strategies.py`、`test_backtest_agent.py`、`test_alert_events.py`、`test_strategy_compiler.py`

## 待处理 P1 事项

以下事项在当前代码中已有对应测试或部分修复，但仍是生产就绪前需要持续关注的高优先级项：

1. **前端日志鉴权与 payload 限制**：`frontend_logs.py` 已鉴权，但需继续限制单条日志大小、JSON 深度、自定义 key 数量，防止存储滥用。
2. ~~**RSS URL 校验与抓取超时**：`news_fetcher.py` 已显式拒绝非 http/https 及内网/本地/link-local 地址，httpx 请求超时 10s、最大重定向 3 次，并由 schema 层前置校验。~~ **已修复**。
3. **价位标注并发重复**：`price_levels` 表已建立 partial unique index，确保 `(variety_id, type, price, scope, contract_id)` 在 `contract_id IS NULL` 分支唯一。
4. **评论外键冲突**：删除品种或合约时需保证关联评论有级联或软删除策略，避免 500。
5. **实时行情批量 symbol 上限**：`/api/realtime/batch` 应对请求 symbol 数量做硬性上限。
6. **交易观点 reason 字段清洗**：与评论一致，使用 `html.escape()` 或等价 sanitize，防止 XSS。

新功能开发时应优先处理上述安全/稳定性项，并补充对应 pytest / 单元测试。

## 待处理 P2 风险接受项

以下问题已被识别，但在当前阶段作为**风险接受项**处理，不影响当前产品形态上线；后续可按业务增长逐步推进：

1. ~~**API 版本治理**：当前所有接口统一在 `/api/` 前缀下，无 `/api/v1` 版本隔离。~~ **已修复（2026-06-24）**：新增 `ApiVersionMiddleware`，`/api/v1/*` 透明映射到 `/api/*`，`/api/` 继续兼容；前端可逐步迁移，详见 `BACKEND_API_VERSIONING_GUIDE.md`。
2. **`kline_data` 表分区/归档**：K 线数据目前单表存储，PostgreSQL 大数据量场景下需按 `trading_time` + `period` 做 range partition 并冷数据归档。方案已记录在 `python/docs/kline_partitioning.md`。
3. ~~**RSS fetch 后台化**：`/api/news/sources/{id}/fetch` 在 API 请求内同步执行，慢源可能导致请求超时。~~ **已修复（2026-06-24）**：手动触发接口改为 `BackgroundTasks` 异步执行。
4. ~~**自动备份/恢复演练**：`python/docs/postgres_backup_runbook.md` 已提供手动 runbook，但尚未自动化。~~ **已修复（2026-06-24）**：新增 `python/scripts/backup_postgres.py`（逻辑/物理备份 + 过期清理）与 `python/scripts/restore_postgres.py`（恢复演练 + 核心表行数校验），支持 `DATABASE_URL` / `PG*` 环境变量与 `--dry-run`。
5. **`database_tools.py` SQL 安全加固**：当前使用正则白名单 + 字符串匹配做 SQL 校验，存在被绕过的理论风险；远期应引入 SQL parser 与参数化查询，作为 P2 风险接受项。

> 注：上述列表随修复迭代更新；已修复项保留 ~~删除线~~ 以便追溯。
