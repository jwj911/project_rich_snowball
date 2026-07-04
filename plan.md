# Agent 模块开发计划

> 期货交流社区 — Agent 系统迭代计划  
> 规划日期：2026-07-04（更新：2026-07-07）  
> 基准分支：`master`  
> 核心原则：先夯实单 Agent 能力，再做多 Agent 编排；先让结果可验证，再让系统更智能。  
> 当前阶段：Phase 2 已完成（DataAgent + TechAnalysisAgent + RiskManagementAgent），Phase 3 待启动

---

## 1. 总体方向

Agent 系统按“功能能力”拆分，而不是先做一个大而全的交易助手。每个 Agent 都应有清晰边界、稳定输入输出、可测试的工具调用链路。

目标能力：

1. 理解用户自然语言意图，例如“最近 7 天黄金走势怎么样”。
2. 将需求解析为结构化任务，例如品种、周期、时间窗口、数据需求、输出风格。
3. 调用确定性数据和分析工具，而不是让 LLM 直接猜结论。
4. 根据任务类型路由到 DataAgent、TechAnalysisAgent、RiskManagementAgent、StrategyCompilerAgent、FactorMiningAgent 等功能 Agent。
5. 等单 Agent 稳定后，再引入 OrchestratorAgent 做复杂任务拆解和 sub-agent 编排。

---

## 2. 当前状态

### 已有基础

| 模块 | 当前状态 | 说明 |
|------|----------|------|
| `python/services/agent/` | ✅ 稳定 | Agent 基类、Tool 注册表、DataAgent、TechAnalysisAgent、RiskManagementAgent、Executor、Context |
| `python/routers/agents.py` | ✅ 稳定 | `/api/agents/tasks` 和 `/api/agents/chat` (SSE 流式)，支持 4 种 Agent 类型 |
| `agent_tasks` / `agent_task_steps` | ✅ 已迁移 | 模型、Alembic 迁移、前后端 schema 一致 |
| `frontend/app/chat/page.tsx` | ✅ 已升级 | 4 种模式切换（AI 助手 / 数据助手 / 技术分析 / 风控管理），流式展示执行过程 |
| `python/lib/technical_indicators.py` | ✅ 已完成 | 后端纯 numpy/pandas 指标库：SMA/EMA/RSI/MACD/BOLL/KDJ/ATR/CCI/OBV/ADX/WR/量比 |
| `python/services/agent/analysis/` | ✅ 已完成 | 趋势分析、形态识别、背离检测、综合评分（5 维度 0-100） |
| `python/services/agent/risk_management/` | ✅ 已完成 | 仓位管理、5 种止损方法、5 种止盈方法、回撤控制、完整风控计划生成 |
| `services/ai_chat.py` | ✅ 复用中 | 现有 OpenAI 兼容调用，Agent 直接复用，无需额外封装 |

### 待收敛问题（非阻塞）

1. ~~Alembic revision 冲突~~ — 已解决，`a1b2c3d4e5f6` 已 stamp 到 head。
2. ~~Tool 注册表双轨逻辑~~ — 已收敛：DataAgent 通过 `_execute_tool` 内部调用服务层函数，Tool 注册表用于 LLM function schema 和文档生成。
3. ~~流式事件 schema 漂移~~ — 当前前后端 `event_type` 枚举（start/thought/action/observation/result/error/done）已稳定，后续新增类型需同步更新 schema。
4. **RiskManagementAgent 当前默认账户资金 10 万** — 后续需支持用户自定义账户余额、风险偏好参数传入。
5. **TechAnalysisAgent 综合评分模型需实盘验证** — 当前 5 维度评分权重为经验值，需在 5+ 品种上交叉验证。

---

## 3. 功能 Agent 划分

### 3.1 DataAgent ✅

职责：获取和整理数据，不做复杂主观判断。

能力范围：
- 品种基础信息：名称、交易所、类别、合约、手续费、保证金。
- 实时行情：最新价、涨跌幅、成交量、持仓、涨跌停。
- K 线数据：日线、分钟线、主力/连续/具体合约口径。
- 市场状态：交易日、交易时段、下一交易日。
- 扩展数据：持仓排名、仓单、结算、涨跌停、期限结构。

验收示例：
- “螺纹钢最新价格是多少”
- “列出所有有色金属品种”
- “黄金最近 7 个交易日 K 线”
- “当前市场是否开盘”

### 3.2 TechAnalysisAgent ✅

职责：基于确定性技术指标和经典技术分析框架，给出走势判断和风险提示。

能力范围：
- 趋势：均线排列（5/10/20/60/120/250）、高低点结构、ADX 强度、DMI 多空方向。
- 动量：MACD、RSI(6/12/24)、KDJ、CCI、WR。
- 波动：ATR、布林带、区间振幅。
- 量价：成交量变化、量比、OBV。
- 形态：双顶/双底、三角形收敛、吞没、锤子线、上吊线、十字星。
- 背离：价格 vs MACD/RSI/KDJ 顶背离/底背离。
- 结论：综合评分 0-100、偏强/偏弱/震荡评级、关键价位、风险点。

验收示例：
- “分析螺纹钢日线技术面”
- “黄金技术面如何？”
- “铜的走势技术判断”

### 3.3 RiskManagementAgent ✅

职责：基于技术分析或用户策略，生成完整的交易风控方案。

能力范围：
- **仓位管理**：基于固定风险比例法，反推建议手数；支持保守/中等/激进风险偏好。
- **止损控制**：ATR 倍数、固定百分比、前低/前高、支撑阻力位、波动率 5 种方法。
- **止盈控制**：风险收益比、ATR 倍数、目标位、移动止盈、固定百分比 5 种方法。
- **回撤控制**：单日亏损上限、总回撤上限、仓位缩减规则、连续亏损暂停规则。
- **交易纪律**：建仓规则、加仓/减仓条件、持仓监控、复盘触发条件。

输出格式：结构化 JSON + Markdown 报告（含止损价、止盈价、仓位、R:R 比、回撤规则）。

验收示例：
- “螺纹钢做多风控方案”
- “黄金做空仓位怎么控制”
- “原油 5000 元做空风控”
- “铜的止损止盈怎么设”

### 3.4 StrategyCompilerAgent（P1）

职责：把用户自然语言转成结构化策略定义，供回测、预警、模拟交易复用。

示例输入：

```text
螺纹钢突破 20 日高点且成交量放大时做多，跌破 10 日均线止损
```

目标输出：

```json
{
  "universe": ["RB"],
  "direction": "long",
  "entry": [
    "close > rolling_max(high, 20)",
    "volume > sma(volume, 20) * 1.5"
  ],
  "exit": [
    "close < sma(close, 10)"
  ],
  "risk": {
    "stop_loss": null,
    "position_size": null
  },
  "timeframe": "1d"
}
```

第一阶段只做解析和校验，不直接下单，不自动执行交易。

验收示例：
- “突破 20 日高点且放量做多，跌破 10 日线止损”可转成结构化策略。
- 非法字段、模糊条件能给出追问或校验失败原因。

### 3.5 FactorMiningAgent（P1）

职责：选择、计算、评估和解释因子。

能力范围：
- 接入用户已有因子库。
- 统一因子定义：输入字段、计算窗口、输出序列、适用品种。
- 因子评估：IC、Rank IC、分层回测、IC 衰减、稳定性、样本外表现。
- 因子筛选：找出有效、失效、冗余、互补因子。
- 后期主动挖掘：组合基础算子，生成候选因子并自动评估。

阶段重点：先评估已有因子，再做主动挖掘。

验收示例：
- 对指定品种池和时间窗口输出因子排名。
- 报告包含 IC、分层收益、样本数、缺失率、风险提示。

### 3.6 ReportAgent（P1）

职责：把结构化分析结果组织成面向用户的回答。

原则：
- 不负责计算。
- 不修改上游结论。
- 只做表达、排序、解释、风险提示。

### 3.7 OrchestratorAgent（P2）

职责：复杂任务拆解和 sub-agent 调度。

只在单 Agent 稳定后引入。当前 3 个核心单 Agent（Data / TechAnalysis / RiskManagement）已稳定，可考虑轻量 Orchestrator 试点。

示例复杂任务：

```text
帮我找出黑色系里技术面最强、风险收益比最好的品种
```

拆解：
1. DataAgent 获取黑色系品种池。
2. TechAnalysisAgent 批量分析技术面。
3. RiskManagementAgent 评估各品种风控方案（R:R 比）。
4. ReportAgent 汇总排名和解释。

---

## 4. 开发阶段

### Phase 0：基座修复与边界收敛 ✅（已完成）

目标：让现有 Agent 骨架可迁移、可测试、可扩展。

任务：
- ~~修复 Alembic revision 冲突。~~ ✅
- ~~修复任务状态持久化：失败必须落为 `failed`。~~ ✅
- ~~统一 `AgentResult.status` 与 `agent_tasks.status`。~~ ✅
- ~~统一 Tool 注册和执行入口。~~ ✅
- ~~建立 `AgentEvent` schema：start、thought、action、observation、result、error、done。~~ ✅
- ~~复用现有 `services/ai_chat.py` 作为 LLM client。~~ ✅
- 补 Agent 核心 pytest — 待完成（当前为手动验证）。

验收：
- Alembic migration graph 正常。✅
- DataAgent 未配置 API key 时任务状态为 `failed`。✅
- 工具调用步骤能稳定写入 `agent_task_steps`。✅
- 前端能收到一致的流式事件。✅

### Phase 1：DataAgent 夯实 ✅（已完成）

目标：让系统能稳定理解并完成单类数据查询。

任务：
- ~~实现 `QueryParser`：规则优先，LLM fallback。~~ ✅（当前 DataAgent 通过正则+规则解析，够用）
- ~~建立品种别名解析：黄金 -> AU，螺纹钢 -> RB，原油 -> SC。~~ ✅
- ~~支持时间窗口解析。~~ ✅（K 线 limit 参数）
- ~~补齐 DataAgent 工具。~~ ✅（get_variety_info, get_realtime_quote, get_kline_data, list_active_varieties, get_market_status）
- ~~DataAgent 输出结构化结果和自然语言摘要。~~ ✅
- ~~前端 Chat 展示结构化执行过程。~~ ✅

验收：
- “螺纹钢最新价格是多少” ✅
- “列出有色金属涨幅前 5” — 排序功能待补齐（当前无按涨跌幅排序）
- “黄金最近 7 个交易日 K 线” ✅

### Phase 2：TechAnalysisAgent + RiskManagementAgent ✅（已完成）

目标：完成经典技术分析能力和风控方案生成。

任务：
- ~~新建后端指标库：`python/lib/technical_indicators.py`。~~ ✅
- ~~支持 SMA、EMA、MACD、RSI、BOLL、KDJ、ATR、CCI、OBV、ADX、WR、量比。~~ ✅
- ~~新建分析模块：trend、pattern、divergence、composite。~~ ✅
- ~~实现 `TechAnalysisAgent`。~~ ✅
- ~~实现 `RiskManagementAgent`：仓位、止损、止盈、回撤、交易纪律。~~ ✅
- ~~将 `tech_analysis`、`risk_management` 路由到对应 Agent。~~ ✅
- ~~前端 Chat 页支持 4 种模式切换。~~ ✅

验收：
- “分析螺纹钢日线技术面” ✅ — 输出综合评分、趋势、形态、背离、指标值。
- “黄金技术面如何？” ✅ — 同上。
- “螺纹钢做多风控方案” ✅ — 输出仓位、止损、止盈、回撤规则、交易纪律。
- 后端指标单测 — 待补充（当前为手动验证）。

### Phase 3：StrategyCompilerAgent（P1）

目标：把自然语言策略转成结构化策略 DSL。

任务：
- 设计策略 DSL schema。
- 支持 universe、timeframe、entry、exit、risk、position、filters。
- 实现表达式白名单和字段校验，禁止任意代码执行。
- 支持自然语言解析到 DSL。
- 输出可读解释和机器可用 JSON。
- 为后续回测、预警、模拟交易预留接口。

验收：
- “突破 20 日高点且放量做多，跌破 10 日线止损”可转成结构化策略。
- 非法字段、模糊条件能给出追问或校验失败原因。

### Phase 4：FactorMiningAgent 基础版（P1）

目标：先把已有因子接入统一框架，并能评估有效性。

任务：
- 设计 `Factor` 基类和 `FactorRegistry`。
- 接入用户已有因子库。
- 建立因子数据加载器：OHLCV、持仓、仓单、期限结构。
- 实现 IC、Rank IC、分层回测、IC 衰减、稳定性统计。
- 实现 `FactorMiningAgent` 基础版：选择因子、跑评估、解释结果。

验收：
- 对指定品种池和时间窗口输出因子排名。
- 报告包含 IC、分层收益、样本数、缺失率、风险提示。

### Phase 5：轻量 Orchestrator（P2）

目标：让复杂请求可以自动拆成多个单 Agent 任务。

任务：
- 实现任务计划结构：steps、dependencies、agent_type、input、output。
- 支持串行执行。
- 支持无依赖任务并行执行。
- 支持子任务状态展示。
- 初期不做复杂 DAG UI，先在 Chat 页展示任务树。

验收：
- “分析黑色系所有品种，找出技术面最强和最弱的”能拆解并汇总。
- “找技术面偏强且风险收益比好的品种”能调用 DataAgent、TechAnalysisAgent、RiskManagementAgent。

### Phase 6：主动因子挖掘（P2）

目标：让 Agent 主动扫描和发现候选因子。

任务：
- 基于已有因子做组合和变体。
- 支持批量评估和结果缓存。
- 支持样本内 / 样本外切分。
- 增加过拟合约束：样本数、稳定性、分层单调性、换手。
- 输出候选因子、失效原因和下一步实验建议。

验收：
- 对指定品种池定期生成候选因子报告。
- 报告区分有效、待观察、无效因子。

---

## 5. 推荐开发顺序

1. ~~Phase 0：先修现有 Agent 基座。~~ ✅
2. ~~Phase 1：完成 IntentRouter 和 DataAgent。~~ ✅
3. ~~Phase 2：完成 TechAnalysisAgent + RiskManagementAgent。~~ ✅
4. **Phase 3：StrategyCompilerAgent** — 当前优先（策略 DSL 是串联技术+风控的桥梁）。
5. Phase 4：FactorMiningAgent 基础评估。
6. Phase 5：轻量 Orchestrator（试点 Data + TechAnalysis + RiskManagement 组合）。
7. Phase 6：主动因子挖掘。

---

## 6. 工程约束

- 数据和指标计算优先走确定性代码，LLM 负责意图理解、工具选择、报告表达。
- 新增业务错误使用 `python/errors.py` 的 `ErrorCode` 和 `ServiceError`。
- 前端 API 调用统一走 `frontend/lib/api/client.ts`。
- 价格 payload 使用 `formatPricePayload`，展示使用 `formatPrice`。
- 涉及 Agent 后端改动至少运行：
  - `python -m py_compile`（已验证通过）
  - 相关 pytest（待补充）
- 涉及前端改动至少运行：
  - `npx tsc --noEmit`（已验证 0 错误）
  - 必要时 `npm run lint`（已验证无警告）
- Agent 输出必须包含“不构成投资建议”的风险提示，但不要让提示淹没核心结论。

---

## 7. 任务清单

### Sprint A：基座稳定 ✅

- [x] 修复 Alembic revision 冲突。
- [x] 修复失败任务状态持久化。
- [x] 建立统一 `AgentEvent` schema（前后端一致）。
- [x] 复用 `services/ai_chat.py` 作为 LLM client。
- [x] 收敛 Tool 执行入口（schema 注册 + 服务层调用）。
- [ ] 增加 Agent 核心 pytest（待补充）。

### Sprint B：DataAgent ✅

- [x] 品种别名解析（黄金->AU，螺纹钢->RB 等）。
- [x] 补齐 5 个数据工具（品种/行情/K线/列表/市场状态）。
- [x] DataAgent 输出结构化结果 + 自然语言摘要。
- [x] 前端 Chat 展示结构化执行过程（步骤展开/收起）。
- [ ] 数据工具增加排序能力（涨幅/跌幅排序）。

### Sprint C：TechAnalysisAgent ✅

- [x] 后端指标库（12 个指标，纯 numpy/pandas）。
- [x] 分析模块：trend、pattern、divergence、composite。
- [x] TechAnalysisAgent 实现（K线获取 -> 指标计算 -> 分析 -> 报告）。
- [x] 前端 Chat 增加“技术分析”模式。
- [ ] 指标单测覆盖（待补充）。
- [ ] 综合评分权重实盘验证（待补充）。

### Sprint D：RiskManagementAgent ✅

- [x] 仓位管理：固定风险比例法，支持 3 种风险偏好。
- [x] 止损：5 种方法（ATR/固定%/前低/支撑阻力/波动率）。
- [x] 止盈：5 种方法（R:R/ATR/目标位/移动止盈/固定%）。
- [x] 回撤控制：单日/总回撤/连续亏损/暂停规则。
- [x] 交易纪律：建仓/加仓/减仓/监控/复盘规则。
- [x] 前端 Chat 增加“风控管理”模式。
- [ ] 支持用户自定义账户资金、风险偏好（当前硬编码 10 万/中等）。
- [ ] 支持用户自定义入场价、止损/止盈（当前自动计算或从 query 提取）。

### Sprint E：StrategyCompilerAgent（当前优先）

- [ ] 设计策略 DSL schema（JSON 结构）。
- [ ] 自然语言解析到 DSL（LLM + 规则校验）。
- [ ] 表达式白名单（禁止任意代码执行）。
- [ ] 输出可读解释 + 机器可用 JSON。
- [ ] 与 TechAnalysisAgent、RiskManagementAgent 联动（策略 -> 风控方案）。

### Sprint F：FactorMiningAgent（后续）

- [ ] Factor 基类和 FactorRegistry。
- [ ] 因子数据加载器（OHLCV + 持仓/仓单/期限结构）。
- [ ] IC / Rank IC / 分层回测 / IC 衰减。
- [ ] FactorMiningAgent 基础版（评估 + 解释）。

### Sprint G：Orchestrator（远期）

- [ ] 任务计划结构（steps + dependencies）。
- [ ] 串行/并行执行引擎。
- [ ] 子任务状态展示（Chat 页任务树）。
- [ ] 试点：Data + TechAnalysis + RiskManagement 组合查询。

---

## 8. MVP 验收样例

当前已能稳定回答：

1. ✅ “黄金最新价格是多少？”（DataAgent）
2. ✅ “最近 7 天黄金走势怎么样？”（TechAnalysisAgent）
3. ✅ “螺纹钢做多风控方案”（RiskManagementAgent）
4. ✅ “铜的止损止盈怎么设？”（RiskManagementAgent）
5. ~~“列出黑色系涨幅前 5 的品种。”~~（DataAgent 待补齐排序能力）
6. ~~“突破 20 日高点且放量做多，跌破 10 日线止损，帮我转成策略。”~~（StrategyCompilerAgent 待实现）

下一轮新增目标样例：
- “帮我制定一个螺纹钢趋势跟踪策略：20日线上做多，跌破20日线止损，止盈按2倍R:R。”
- “评估黄金近30日的动量因子表现。”
- “分析黑色系所有品种，技术面最强的是哪个？风险收益比最好的是哪个？”
