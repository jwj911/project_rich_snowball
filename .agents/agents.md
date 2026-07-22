<!-- .agents/agents.md — Agent 系统 -->

Agent 系统按「功能能力」拆分，每个 Agent 有清晰边界、稳定输入输出、可测试的工具调用链路。当前已完成 Phase 0~2 与体验修复计划 P0/P1：DataAgent、DataQualityAgent、TechAnalysisAgent、RiskManagementAgent、AnalysisPipelineAgent、StrategyCompilerAgent、BacktestAgent、FactorMiningAgent 均已上线并接入真实进度流式；TraderAgent 已新增上线；OrchestratorAgent 已从能力列表中移除，避免展示悬空能力。

## 架构原则

1. **确定性计算优先**：数据查询、指标计算、形态识别全部走确定性代码（numpy/pandas），LLM 只负责意图理解、工具选择、报告表达。
2. **单 Agent 稳定后再编排**：DataAgent、TechAnalysisAgent、RiskManagementAgent 已稳定；AnalysisPipelineAgent 已实现 Data + Tech + Risk 的硬编码编排；远期再引入通用 OrchestratorAgent。
3. **步骤可观测**：每个 Agent 执行过程拆分为 thought → action → observation → result，持久化到 `agent_task_steps` 表，前端通过 SSE 流式展示。
4. **流式体验优先**：本地确定性 Agent（tech_analysis / risk_management / backtest / factor_mining / strategy_compiler / analysis_pipeline / data_quality / trader）的 `run_stream` 通过后台任务 + 进度队列实时 yield 步骤/进度事件，避免「执行完再回放」的伪流式。
5. **风险提示默认包含**：所有 Agent 输出必须附带「不构成投资建议」声明，但不要让声明淹没核心结论。
6. **数据不足时优雅降级**：`analysis_pipeline` 在 K 线数据质量 `bad` 时不再直接失败，而是降级为「数据现状报告」并返回 `completed` 状态。

## 功能 Agent 划分

| Agent | 状态 | 职责 | 关键能力 |
|-------|------|------|----------|
| **DataAgent** | ✅ 已完成 | 数据查询与整理 | 品种信息、实时行情、K 线、市场状态、持仓/仓单/结算等扩展数据 |
| **DataQualityAgent** | ✅ 已完成 | 数据质检 | 检查 K 线覆盖、OHLC 异常、缺口、实时行情可用性 |
| **TechAnalysisAgent** | ✅ 已完成 | 技术面分析 | 趋势（均线/ADX/DMI）、动量（MACD/RSI/KDJ/CCI/WR）、波动（ATR/布林带）、量价（OBV/量比）、形态（双顶/双底/三角形/K 线形态）、背离检测、综合评分 0-100 |
| **RiskManagementAgent** | ✅ 已完成 | 风控方案生成 | 仓位管理（固定风险比例法，保守/中等/激进）、5 种止损、5 种止盈、回撤控制规则、交易纪律；使用品种真实 multiplier / tick_size |
| **AnalysisPipelineAgent** | ✅ 已完成 | 完整分析流水线 | 并行 Data + Tech，串行 Risk，数据 bad 时降级 |
| **StrategyCompilerAgent** | ✅ 已完成 | 自然语言策略 DSL | 把「突破 20 日高点且放量做多，跌破 10 日线止损」转成结构化 JSON + 可读解释 |
| **BacktestAgent** | ✅ 已完成 | 策略回测 | 解析口头策略、历史回测、收益/回撤/胜率/评分 |
| **FactorMiningAgent** | ✅ 已完成 | 因子评估与筛选 | IC / Rank IC / 分层回测 / IC 衰减 / 稳定性统计 |
| **TraderAgent** | ✅ 已完成 | 交易研判与计划 | 多周期趋势识别、K线形态与多空力量、交易计划生成（方向/入场/止损/止盈/仓位）、风控校验；支持剥头皮、日内波段、中短趋势、中期趋势 |
| **OrchestratorAgent** | 🔄 P2 远期 | 复杂任务编排 | 自动拆解多 Agent 任务、串行/并行执行、子任务状态汇总（已从能力列表中移除，避免悬空能力） |

## 后端核心模块

- `services/agent/core.py`：`BaseAgent` 基类、`ToolRegistry` 工具注册表、`AgentResult` / `AgentEvent` schema；新增 `PROGRESS` 事件类型与 `_stream_run()` 通用流式辅助
- `services/agent/executor.py`：执行引擎，负责任务创建、步骤持久化、流式事件发射；Phase 2 已改为任务级批量提交，降低 SQLite 锁竞争
- `services/agent/llm_client.py`：OpenAI 兼容调用；共享 `httpx.AsyncClient`、指数退避重试（最多 3 次）、HTTP 状态码与响应摘要记录
- `services/agent/data_agent.py` / `data_tools.py`：DataAgent 实现与工具
- `services/agent/tech_analysis_agent.py`：TechAnalysisAgent 实现
- `services/agent/risk_management_agent.py`：RiskManagementAgent 实现
- `services/agent/risk_management/stop_loss.py`：止损计算，支持按 `tick_size` 取整
- `services/agent/analysis_pipeline_agent.py`：完整分析流水线，支持数据 bad 降级
- `services/agent/strategy_compiler_agent.py`：策略 DSL 编译
- `services/agent/backtest_agent.py`：回测 Agent
- `services/agent/factor_mining_agent.py`：因子挖掘 Agent
- `services/agent/data_quality_agent.py`：数据质检 Agent
- `services/agent/trader_agent.py`：交易员 Agent
- `services/agent/trader/`：trader 子模块（market_structure、multi_timeframe、candlestick、trade_plan、risk_check）
- `services/agent/analysis/`：trend、pattern、divergence、composite 四个分析子模块
- `services/agent/risk_management/`：position、stop_loss、take_profit、drawdown 四个风控子模块
- `python/lib/technical_indicators.py`：纯 numpy/pandas 指标库，不依赖 LLM
- `routers/agents.py`：`/api/agents/tasks`（创建任务）、`/api/agents/tasks/{id}`（查询结果）、`/api/agents/chat`（SSE 流式对话）；已移除未实现的 `orchestrator` 类型

## 测试覆盖

- `tests/services/agent/`：Agent 子模块单元测试（技术分析输出、数据工具、DSL、因子引擎等）
- `tests/test_agents_core.py`：核心执行器、ToolRegistry、基础 Agent 状态持久化
- `tests/test_agents_router.py`：Agent 任务 CRUD 与鉴权
- `tests/test_agent_data_preflight.py`：数据预检拦截（回测/因子/流水线在数据 bad 时提前报告）
- `tests/test_agent_streaming.py`：流式事件序列、降级路径、成交量语义、multiplier/tick_size 使用
- `tests/test_analysis_pipeline.py`：流水线子任务创建与状态传播
- `tests/test_backtest_agent.py`、`tests/test_strategy_compiler.py`、`tests/test_factor_mining_agent.py`、`tests/test_data_quality_agent.py`：对应 Agent 核心链路
- `tests/test_trader_modules.py`、`tests/test_trader_agent.py`：TraderAgent 子模块与集成测试

当前 Agent 相关 pytest 已新增 trader 专项 18 个；项目已补齐 `scikit-learn` lock，最近一次全量后端测试为 `978 passed, 8 skipped, 0 failed`，前端 Vitest 为 `195 passed, 0 failed`。Backend CI #22、Frontend CI #28 和 Phase 4 Backend CI 均已通过。

## 数据库模型

- `agent_tasks`：任务主表（id、user_id、parent_task_id、agent_type、query、status、result_json、error_message、started_at、finished_at、created_at）
- `agent_task_steps`：执行步骤表（task_id、step_number、role、content、tool_name、tool_input_json、tool_output_json、created_at）

## 前端集成

- `frontend/app/chat/page.tsx`：10 种模式切换的 Chat 界面（含 trader），支持流式展示 Agent 执行步骤；新增 `progress` 事件处理、`AbortController` 取消、停止按钮
- `frontend/lib/api/agents.ts`：Agent API 封装；`agentChatStream` 支持 `AbortSignal`、`event:` 标签解析、malformed 行回调
- `frontend/app/agents/page.tsx`：Agent 工作台，展示能力状态与任务记录
- 新增 Agent 相关类型在 `frontend/lib/api/types.ts` 中维护，必须与后端 schema 同步

## 开发约束

- 新增 Agent 类型必须继承 `BaseAgent`，实现 `run(query, context)` 接口。
- Tool 注册必须使用 `@register_tool(name, description, params_schema)` 装饰器。
- Agent 执行步骤必须写入 `agent_task_steps`（role ∈ {thought, action, observation, system, error}）。
- 流式事件类型新增时，前后端 `AgentEvent` 枚举必须同步更新；当前事件类型：`start`、`progress`、`thought`、`action`、`observation`、`result`、`error`、`done`。
- 涉及 Agent 改动至少运行 `python -m py_compile` 和相关 pytest。
- 策略 DSL 新增 `transform` 字段（如 `multiply_indicator2`）时，需同步更新策略编译器、DSL schema 校验与回测引擎消费侧；当前回测引擎尚未消费 `multiply_indicator2`，仅验证 DSL 生成。
- `services/agent/database_tools.py` 的查询入口已使用 `sqlglot` AST 做单语句、只读节点、危险函数、表白名单和私有数据 owner 谓词改写；复杂私有关联查询继续补充 PostgreSQL 专项回归。
