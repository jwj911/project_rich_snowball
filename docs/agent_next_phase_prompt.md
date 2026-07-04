# Agent 系统下阶段开发 Prompt

> 目标：夯实 Agent 核心能力 + 修复体验问题，完成最初产品目标。

## 目标

让项目中的 Agent 系统真正兑现最初定义的产品能力，同时修复当前已知的 bug 和体验缺陷。用户用自然语言提问，Agent 能独立完成完整任务链并给出可直接使用的结果。

本次不新增 Agent 类型，重点补齐：
- 单 Agent 端到端体验
- 多 Agent 串联可靠性
- 当前已知 bug 修复

## 当前已知事实

- 已有 Agent：`DataAgent`、`TechAnalysisAgent`、`RiskManagementAgent`、`AnalysisPipelineAgent`、`FactorMiningAgent`、`StrategyCompilerAgent`、`BacktestAgent`。
- `AnalysisPipelineAgent` 已实现 Data → Tech → Risk 的串行流水线。
- 前端 Chat 页支持 8 种模式，并有对应结果卡片。
- 基础设施完整：基类、Executor、工具注册、流式事件、LLM Client 均已就绪。

## 核心验收场景（必须全部跑通）

### 场景 1：自然语言策略 → 可执行策略

用户输入：
> 「螺纹钢 5 日均线上穿 20 日均线时做多，跌破 20 日均线时平仓」

系统应输出：
- 结构化 DSL（entry/exit/universe/timeframe/direction/risk）
- 该策略能否在当前数据下被回测引擎执行
- 前端 `StrategyResultCard` 正确渲染策略规则

当前问题：`StrategyCompilerAgent` 只实现了 `run()`，前端 Chat 中无法看到中间步骤；需要确认其解析规则能否覆盖均线交叉、MACD、RSI、布林带、突破这 5 类策略。

### 场景 2：品种走势 → 经典技术分析结论

用户输入：
> 「螺纹钢最近走势怎么样？」或「黄金技术面如何？」

系统应输出：
- 近 N 日 K 线数据
- 趋势方向（向上 / 向下 / 震荡）
- 多空倾向（偏多 / 偏空 / 中性）
- 资金流向判断（量价配合/背离等）
- 关键价位（支撑/阻力/均线位置）
- 综合评分与风险提示

当前问题：`TechAnalysisAgent` 有指标计算，但需验证其输出结构是否稳定包含「方向、资金流向、K线走势」三类结论；前端 `TechAnalysisReportCard` 是否完整展示。

### 场景 3：复杂分析请求 → 自动多 Agent 串联

用户输入：
> 「帮我完整分析螺纹钢」

系统应依次：
1. `DataAgent` 获取品种信息 + 最新行情
2. `TechAnalysisAgent` 生成技术面报告
3. `RiskManagementAgent` 给出风控方案
4. `AnalysisPipelineAgent` 汇总成一份包含「品种概况 / 技术面结论 / 风控建议」的完整报告

当前问题：流水线已实现，但需验证子任务持久化、主任务步骤展示、失败时子任务状态是否准确。

## 本次任务

### 一、Bug 修复

1. **统一品种别名解析**
   - 确认 `python/services/agent/utils.py` 中的 `resolve_symbol()` 是否覆盖常见品种。
   - 修复 TechAnalysisAgent / RiskManagementAgent / DataAgent 各自解析品种时的不一致问题，全部统一调用 `resolve_symbol()`。

2. **修复 TechAnalysisAgent 输出结构不稳定**
   - 要求 `run()` 返回的 `AgentResult.data` 必须固定包含以下字段：
     - `direction`：趋势方向
     - `bias`：多空倾向
     - `money_flow`：资金流向判断
     - `kline_trend`：K线走势描述
     - `score` / `rating`
     - `key_levels`：支撑/阻力/均线
     - `risk_note`
   - 如果 `composite.py` 未输出这些字段，补齐计算逻辑。

3. **修复 DataAgent 排序能力**
   - 验证 `list_active_varieties` 工具是否支持 `sort_by` 和 `sort_order`。
   - 确保「有色金属涨幅前 5」这类查询能正确返回排序结果。

4. **修复前端 `[id]` 动态路由兼容性问题**（如仍存在）
   - 如 `frontend/app/agents/[id]/page.tsx` 仍导致 Windows 构建失败，改为 `frontend/app/agents/detail/page.tsx` 并在链接中使用查询参数。

### 二、体验夯实

1. **补齐单 Agent 的 `run_stream()` 实现**
   - `StrategyCompilerAgent`：yield「解析意图 → 提取策略要素 → 生成 DSL → 校验 → 返回」各阶段事件。
   - `FactorMiningAgent`：yield「解析公式/品种池 → 加载数据 → 计算因子 → 评估 → 生成报告」各阶段事件。
   - `BacktestAgent`：yield「解析策略 → 获取数据 → 运行回测 → 计算指标 → 返回结果」各阶段事件。
   - 确保每个事件都带 `step_number` 和 `role`，前端步骤列表能正确渲染。

2. **前端 Chat 页统一所有 Agent 的流式体验**
   - 确认 `data`、`tech_analysis`、`risk_management`、`analysis_pipeline`、`factor_mining`、`strategy_compiler`、`backtest` 均走 SSE 流式分支。
   - 统一展示步骤展开/收起交互。

3. **完善 TechAnalysisReportCard**
   - 展示方向、多空倾向、资金流向、K线走势、关键价位、综合评分、风险提示。
   - 指标网格补充 ATR、MA5/MA10/MA20、成交量变化。

4. **完善 StrategyResultCard**
   - 展示解析后的 DSL 规则、品种、周期、方向、入场/出场条件、风控规则。
   - 提供「去回测」按钮或提示。

### 三、测试补齐

1. **新增/更新测试文件**
   - `python/tests/services/agent/test_tech_analysis_output.py`：验证 TechAnalysisAgent 输出包含全部必需字段。
   - `python/tests/services/agent/test_strategy_compiler.py`：对均线/MACD/RSI/布林带/突破 5 类策略分别测试。
   - `python/tests/services/agent/test_analysis_pipeline.py`：验证子任务创建、状态传递、汇总报告。
   - `python/tests/services/agent/test_symbol_resolution.py`：验证品种别名解析。

2. **全量测试通过**
   - 运行 `cd python && python -m pytest tests/ -q`，确保无失败。

### 四、端到端手动验收

启动前后端，在 Chat 页分别输入以下例句，确认结果正确、步骤可见、卡片渲染完整：

1. 「螺纹钢 5 日均线上穿 20 日均线时做多，跌破 20 日均线时平仓」
2. 「黄金技术面如何？」
3. 「帮我完整分析螺纹钢」
4. 「有色金属涨幅前 5」

把每个场景的实际输入/输出截图或文本保存到 `docs/agent_acceptance.md`。

## 不要做

- 不要新增 Agent 类型（如 OrchestratorAgent、智能调度）。
- 不要引入新的 LLM 模型或替换 LLM Client。
- 不要重构前端路由或导航。
- 不要修改回测引擎核心逻辑。

## 输出要求

- 先列出需要修改/新增的文件清单。
- 每完成一个子任务，给出验证命令和结果。
- 修复完 bug 后先跑测试，再进入体验补齐。
- 最后提交到本地 master，拆分为 2~3 个 commit（bugfix、feat/agent-experience、test/docs）。
- 附上手写验收记录（4 个场景的输入/输出摘要）。
