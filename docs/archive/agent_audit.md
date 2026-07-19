# Agent 系统架构与能力全面审计

> **历史归档（2026-07-19）**：本审计记录对应 2026-07-04 的 Agent 状态，不再作为当前缺陷基线。当前状态请查看 [`../iteration_plan_20260718_project_audit.md`](../iteration_plan_20260718_project_audit.md)。
>
**审计日期**：2026-07-04
**审计范围**：全部 7 个 Agent、11 个数据工具、4 个分析引擎模块、4 个前端结果卡片、API 路由、LLM 客户端、工具注册表、流水线编排、测试
**审计方法**：逐文件阅读核心实现 + 模拟量化交易者真实使用场景

---

## 目录

1. [架构总览](#一架构总览)
2. [已完成的正确设计](#二已完成的正确设计逐一确认)
3. [真实量化场景下的缺口分析](#三真实量化场景下的缺口分析)
4. [测试覆盖评估](#四测试覆盖评估)
5. [场景适配度总表](#五场景适配度总表)
6. [建议的后续任务优先级](#六建议的后续任务优先级)

---

## 一、架构总览

```
用户自然语言
    │
    ▼
Chat 页 (8 种模式: chat / data / tech_analysis / risk_management /
          analysis_pipeline / factor_mining / strategy_compiler / backtest)
    │  POST /api/agents/chat  (SSE streaming)
    ▼
AgentExecutor (生命周期管理 + 步骤持久化到 agent_tasks / agent_task_steps 表)
    │
    ├── DataAgent          ← LLM (OpenAI function calling) + 规则兜底 (_run_fallback)
    ├── TechAnalysisAgent  ← 纯确定性计算 (本地指标引擎, 无需 LLM)
    ├── RiskManagementAgent← 纯确定性计算 (风控引擎, 无需 LLM)
    ├── AnalysisPipeline   ← Data → Tech → Risk 串行编排 (已实现)
    ├── StrategyCompiler   ← 规则解析器 (基于正则 + 模板匹配, 无需 LLM)
    ├── BacktestAgent      ← DSL 路径 / 传统均线回退路径 (无需 LLM)
    └── FactorMiningAgent  ← 因子 DSL 求值 + IC/分层/回撤评估 (无需 LLM)
```

**关键设计决策**：
- DataAgent 是唯一强依赖 LLM 的 Agent；其余 6 个都是确定性计算，无 API key 也能工作。
- 所有 7 个 Agent 均已实现 `run()` 和 `run_stream()`，流式事件统一使用 `AgentEvent` 结构。
- 前端 Chat 页 7 种 Agent 模式全部走 SSE 流式分支，步骤展开/收起交互统一。

---

## 二、已完成的正确设计（逐一确认）

### 2.1 基础设施扎实

- **`core.py`**：`Agent` / `AgentStep` / `AgentEvent` / `AgentResult` 抽象干净。`AgentEvent` 携带 `step_number` + `role` + `tool_name` + `tool_input` + `tool_output`，前端可直接渲染步骤列表。
- **`executor.py`**：`execute_streaming()` 统一了 SSE 事件推送、步骤持久化和任务状态管理。异常处理完善 —— 包括流式结束后兜底 `update_task_status`，以及 `try/except` 包裹整个流式循环。
- **`tools.py`**：`ToolRegistry` 支持 OpenAI function calling schema 自动生成，`Tool` 基类（类继承）和 `@tool_def`（函数装饰器）两种注册方式都可用。
- **`context.py`**：`AgentContext` 封装 `db` / `user_id` / `task_id`，贯穿整个 Agent 生命周期。

### 2.2 品种别名解析已统一

- **`utils.py:resolve_symbol()`** 采用三级降级策略：
  1. 正则匹配 1~2 位大写字母代码（如 RB、AU、I）
  2. 数据库品种名称 / 代码（`_load_variety_aliases`，带 lru_cache）
  3. 内置 60+ 中文别名表兜底（`_BUILTIN_NAME_MAP`）
- 最长匹配优先，避免「螺纹钢」被「螺纹」覆盖。
- 所有数据工具函数（`_get_variety_info` / `_get_realtime_quote` / `_get_kline_data` / `_get_warehouse_receipts` / `_get_holding_rankings` / `_get_settlement_params` / `_get_price_limits`）以及 TechAnalysisAgent / RiskManagementAgent / AnalysisPipelineAgent / StrategyCompilerAgent 全部统一调用 `resolve_symbol()`。

### 2.3 技术分析引擎有真东西

| 模块 | 文件 | 实现内容 |
|------|------|----------|
| 趋势分析 | `analysis/trend.py` | 均线排列判断 (5>20>60) + ADX 强度 + DMI 方向 |
| 形态识别 | `analysis/pattern.py` | 双顶/双底/三角形收敛 + K 线组合（吞没、锤子线、上吊线、十字星） |
| 背离检测 | `analysis/divergence.py` | MACD/RSI/KDJ 三种指标的顶底背离，基于局部极值算法 |
| 综合评分 | `analysis/composite.py` | 五维度评分：趋势(0-30) + 动量(0-25) + 量能(0-15) + 形态(0-15) + 波动(0-15)，背离调整 ±8 分 |

- `calculate_all_indicators()` 产出 **23 个指标字段**：SMA5/10/20/60、RSI6/24、MACD(DIF/DEA/Bar)、BOLL(Upper/Mid/Lower)、KDJ(K/D/J)、ATR14、CCI14、OBV、ADX14、DMI(+/-)、WR14、量比、成交量变化。
- TechAnalysisAgent 输出固定 **7 个必需字段**：`direction` / `bias` / `money_flow` / `kline_trend` / `key_levels` / `risk_note` / `score`。

### 2.4 策略编译器是纯确定性引擎

- `StrategyParser` 基于关键词路由到 5 个模板方法：
  - **均线交叉**：正则提取均线周期（支持「N日均线/ma/MA」等变体）
  - **MACD**：识别「金叉/死叉」→ DIF 上穿/下穿 DEA
  - **RSI**：提取超买/超卖阈值（默认 30/70）
  - **布林带**：下轨做多 / 上轨做空
  - **突破**：提取 N 日高点/低点突破
- `StrategyValidator`：表达式白名单（36 个合法指标 + 10 个操作符）+ 字段合法性检查 + 交叉操作符需要 `indicator2` + 数值操作符需要 `value`。
- 支持自定义止损/止盈/手数提取（正则：`跌破 N 止损`、`止盈 N`、`N 手`）。

### 2.5 风控系统是业界标准做法

| 模块 | 文件 | 实现内容 |
|------|------|----------|
| 仓位管理 | `risk_management/position_sizing.py` | 固定风险比例法，按止损距离反推仓位，上限检查，保证金联动，回撤关联警告 |
| 止损 | `risk_management/stop_loss.py` | 5 种方法（ATR/固定%/前低前高/支撑阻力/波动率），自动降级 + 合理性质疑（距离>10%或<1%） |
| 回撤控制 | `risk_management/drawdown_control.py` | 三级配置表（低/中/高），含单日亏损限制、总回撤限制、仓位缩减和暂停交易阈值 |

- RiskManagementAgent 默认账户资金 10 万，支持用户通过自然语言切换风险偏好（「保守」「激进」）。
- 输出 5 个维度：仓位管理 / 止损控制 / 止盈控制 / 回撤控制 / 交易纪律。

### 2.6 因子评估有量化基础

- `factor_engine/dsl.py`：支持 `ts_delay` / `ts_delta` / `ts_rank` / `ts_std` / `ts_mean` / `ts_corr` 等时序算子，公式安全校验（禁止危险内置函数）。
- `factor_engine/evaluator.py`：IC / Rank IC / ICIR / 分层回测(默认5层) / 多空组合 / 最大回撤 / Sharpe / 换手率 / 覆盖率。
- 报告自动给出因子有效性的中文总结（基于 Rank IC 绝对值和多空收益方向）。

### 2.7 前端流式体验完整

- [chat/page.tsx](frontend/app/chat/page.tsx) 对 7 种 Agent 模式全部走 SSE 流式分支，步骤展开/收起、事件类型→图标映射（thought→蓝色脑图标、action→琥珀色扳手、observation→绿色闪电等）交互一致。
- 4 个结果卡片完整：
  - `TechAnalysisReportCard`：方向/多空/资金流向/K线走势/关键价位/风险提示 + 17 个指标网格
  - `StrategyResultCard`：DSL 规则 + 入场/出场条件 + 风控参数 + JSON 查看 + 「去回测」提示
  - `BacktestResultCard`：评分 + 4 项核心指标 + 4 项辅助指标 + 交易明细表 + SVG 资金曲线
  - `FactorResultCard`：10 项评估指标 + 分层收益柱状图 + 因子公式展示

### 2.8 数据工具体系完整

已注册 11 个工具：

| 工具 | 数据源 | 用途 |
|------|--------|------|
| `get_variety_info` | varieties 表 | 品种基础信息 |
| `get_realtime_quote` | realtime_quotes 表 | 实时行情 |
| `get_kline_data` | kline_data + fut_daily_data | K 线（自动选最新数据源） |
| `get_continuous_klines` | KlineService | 主力切换拼接 K 线 |
| `get_main_klines` | KlineService | 当前主力合约 K 线 |
| `list_active_varieties` | varieties + realtime_quotes | 活跃品种列表（支持排序/分类） |
| `get_market_status` | trading_calendar 表 | 市场状态（交易日/时段） |
| `get_warehouse_receipts` | fut_wsr 表 | 仓单日报（库存分析） |
| `get_holding_rankings` | fut_holding 表 | 持仓排名（资金流向） |
| `get_settlement_params` | fut_settle 表 | 结算参数（保证金/手续费） |
| `get_price_limits` | fut_price_limits 表 | 涨跌停价格 |

另有 3 个数据库通用查询工具（`query_database` / `list_tables` / `get_table_schema`，位于 `database_tools.py`，暂未纳入版本管理）。

---

## 三、真实量化场景下的缺口分析

以下问题来自模拟真实量化投资者的使用场景。当前系统在已定义的验收场景下能正常工作，但要支撑实际投研工作流，存在以下瓶颈。

### 🔴 严重 — GAP-01：缺少多品种组合能力

**真实场景**：
- "帮我做一个跨品种套利策略：做多螺纹钢，做空热卷，当价差超过 200 点时入场"
- "评估这个因子在全部 45 个活跃品种上的表现"
- "螺纹钢、热卷、铁矿石三个品种的均线交叉策略，哪个夏普最高？"

**现状**：
- `StrategyCompilerAgent` 的 `resolve_symbol()` 只返回第一个匹配，`universe` 始终为 `[symbol]` 单元素列表。
- `BacktestAgent` 的 DSL 回测路径只取 `dsl.universe[0]`（[backtest_agent.py:42](python/services/agent/backtest_agent.py)）。
- `FactorMiningAgent` 的 `extract_factor_universe()` 只支持类别关键词（"黑色系"等 5 个），不支持用户指定具体 2~3 个品种代码。
- 不支持排除语法（如"除螺纹钢外的黑色系"）。

**影响**：跨品种套利、板块轮动、对冲组合这些量化核心场景全部走不通。

**涉及文件**：
- `python/services/agent/utils.py` — `resolve_symbol()` 只返回单个
- `python/services/agent/strategy_compiler_agent.py` — `StrategyParser.parse()` 的 universe 逻辑
- `python/services/agent/backtest_agent.py:42` — 只取 `dsl.universe[0]`
- `python/services/agent/factor_engine/data_loader.py` — `extract_factor_universe()` 品种池解析

### 🔴 严重 — GAP-02：策略条件只支持单条件 + AND 逻辑

**真实场景**：
- "MACD 金叉 **且** RSI 低于 40 **且** 成交量放大 **且** 价格在 20 日均线上方时入场"
- "RSI 超卖 **或** 布林带下轨触碰时入场"
- "连续 3 日收盘价在 5 日均线上方时做多"

**现状**：
- `StrategyCompilerAgent` 的 5 个模板方法都只产出 **单个 condition**。
- `logic` 字段固定为 `"and"` 但从未被使用。
- 没有实现 AND/OR 组合逻辑的解析器。
- 回测引擎侧需要确认是否支持多条件评估（`run_dsl_backtest` 的参数签名支持 `entry_conditions: list`，但实际逻辑未确认）。

**影响**：目前只能表达最简单的单信号策略。任何需要多条件确认的策略无法编译。

**涉及文件**：
- `python/services/agent/strategy_compiler_agent.py` — `StrategyParser` 所有模板方法
- `python/services/backtest/service.py` — `run_dsl_backtest()` 的多条件评估逻辑（需确认）

### 🟡 中等 — GAP-03：回测无法跨策略对比

**真实场景**：
- "回测均线交叉和 MACD 两个策略，比较一下哪个夏普更高"
- "同样的策略在螺纹钢 vs 热卷上的表现对比"

**现状**：`BacktestAgent` 每次只跑一个策略，`_format_result` 只输出单一回测报告。

**涉及文件**：
- `python/services/agent/backtest_agent.py` — `run()` 单策略单品种

### 🟡 中等 — GAP-04：缺少参数优化能力

**真实场景**：
- "5 日和 20 日均线交叉策略，优化一下均线参数，看看 5/10/15/20/30 哪个组合效果最好"
- "MACD 金叉策略，快慢线参数 12/26/9 和 5/35/5 哪个好？"

**现状**：参数完全由用户指定，没有网格搜索或参数扫描能力。

**涉及文件**：
- `python/services/agent/strategy_compiler_agent.py` — 解析后直接生成固定 DSL
- `python/services/agent/backtest_agent.py` — 单次执行

### 🟡 中等 — GAP-05：风控不感知用户已有持仓

**真实场景**：
- "我现在持有 3 手螺纹钢多单，再加 2 手，止损怎么调整？"
- "账户目前浮亏 5%，当前仓位是否需要减仓？"

**现状**：`RiskManagementAgent` 总是从零开始计算（默认 10 万空账户），不知道用户当前仓位。`_DEFAULT_ACCOUNT_BALANCE = 100000` 硬编码。

**涉及文件**：
- `python/services/agent/risk_management_agent.py:38` — 硬编码默认资金
- `python/services/agent/risk_management/drawdown_control.py` — 不读取实际持仓

### 🟡 中等 — GAP-06：因子品种池解析有限

**真实场景**：
- "只看镍和不锈钢这两个品种"
- "除螺纹钢外的所有黑色系品种"

**现状**：`extract_factor_universe()` 依赖 `resolve_symbol()` 单个匹配 + category 关键词匹配。

**涉及文件**：
- `python/services/agent/factor_engine/data_loader.py` — `extract_factor_universe()` 实现

### 🟢 轻度 — GAP-07：AnalysisPipeline 中 Data 和 Tech 可并行但未并行

**现状**：[analysis_pipeline_agent.py:70-131](python/services/agent/analysis_pipeline_agent.py) 是严格的 `await → await → await`。Data（DB 查询 <500ms）和 Tech（指标计算 <200ms）可以同时启动，节省约 0.5s。

**影响**：当前总量也就 2-3 秒，用户感知不强。优先度低。

### 🟢 轻度 — GAP-08：DataAgent 的 fallback 路径仅覆盖中文

**现状**：`_run_fallback` 的排序方向判断（`"涨幅" in query → desc` / `"跌幅" in query → asc`）只在中文场景下工作。

### 🟢 轻度 — GAP-09：database_tools.py 未纳入版本管理

**现状**：[database_tools.py](python/services/agent/database_tools.py) 提供了 `query_database` / `list_tables` / `get_table_schema` 三个强大的 SQL 查询工具，但：
- 不在 git 版本控制中（untracked file）
- SQL 注入防护仅为关键词级别（`_FORBIDDEN_KEYWORDS`），SELECT 子句本身不在白名单范围内
- 缺少测试文件

---

## 四、测试覆盖评估

### 已有测试（6 个文件）

| 测试文件 | 覆盖内容 | 质量 |
|----------|----------|------|
| `test_strategy_compiler.py` | 均线/MACD/RSI/布林带/突破 5 类 + 自定义风控 + 未知品种 + JSON 输出 + 校验器的 5 个边界场景 | ✅ 完整 |
| `test_tech_analysis_output.py` | 7 个必需字段 + 23 个 indicators 完整性 | ✅ 覆盖 |
| `test_analysis_pipeline.py` | 子任务创建/状态传递/汇总报告 data/technical/risk 三段结构 | ✅ 覆盖 |
| `test_symbol_resolution.py` | 内置别名/DB 别名/未知品种/最长匹配 | ✅ 覆盖 |
| `test_data_tools.py` | 排序（涨跌幅升降序/成交量/默认排序）+ 别名在工具层生效 | ✅ 覆盖 |
| `test_agents_core.py` | DataAgent fallback 路径 + 排序测试 | ✅ 已更新 |

### 缺失的测试

| 缺失项 | 对应 GAP | 优先度 |
|--------|----------|--------|
| BacktestAgent DSL 回测路径的独立测试 | — | 🟡 |
| FactorMiningAgent 因子评估流程的完整测试 | — | 🟡 |
| StrategyCompiler 多条件策略模板测试 | GAP-02 | 🔴 |
| SSE 流式事件的自动化测试 | — | 🟢 |
| database_tools.py SQL 注入防护测试 | GAP-09 | 🟡 |

---

## 五、场景适配度总表

模拟一个期货量化交易者的典型使用路径：

| 投研阶段 | 典型问题 | 当前支持度 | 阻塞 GAP |
|----------|----------|-----------|----------|
| **市场扫描** | "今天什么品种涨得多？" | ✅ 完整 | — |
| **单品分析** | "螺纹钢技术面如何？" | ✅ 完整 | — |
| **策略构思** | "如果我做均线交叉会怎样？" | ⚠️ 仅单条件 | GAP-02 |
| **策略回测** | "回测这个策略" | ⚠️ 仅单品种单策略 | GAP-01, GAP-03 |
| **参数优化** | "哪个均线参数最好？" | ❌ 不支持 | GAP-04 |
| **组合构建** | "螺纹+热卷跨品种套利" | ❌ 不支持 | GAP-01 |
| **因子研究** | "这个因子有效吗？" | ⚠️ 品种池有限 | GAP-06 |
| **风控方案** | "我该下几手？" | ⚠️ 不感知持仓 | GAP-05 |
| **完整分析** | "给我螺纹钢的完整报告" | ✅ 完整 | GAP-07 (性能优化，低优先) |

---

## 六、建议的后续任务优先级

### P0 — 核心能力补齐（阻塞量化投研基本工作流）

| 编号 | 任务 | 涉及文件 |
|------|------|----------|
| **GAP-02** | 策略编译器支持多条件 AND/OR 组合 | `strategy_compiler_agent.py` StrategyParser 全部模板方法、`backtest/service.py` run_dsl_backtest 多条件评估 |
| **GAP-01a** | `resolve_symbol()` 支持多品种返回 | `utils.py` resolve_symbol → resolve_symbols、`strategy_compiler_agent.py` universe 构建 |
| **GAP-01b** | BacktestAgent 支持多品种回测 | `backtest_agent.py` run() 循环回测、结果对比输出 |

### P1 — 体验完善（重要的投研辅助能力）

| 编号 | 任务 | 涉及文件 |
|------|------|----------|
| **GAP-05** | 风控接入用户持仓数据 | `risk_management_agent.py` 读取 trade_records 表、调整风控计算 |
| **GAP-03** | 回测支持多策略对比 | `backtest_agent.py` 新增对比模式 |
| **GAP-06** | 因子品种池支持精确指定 + 排除语法 | `factor_engine/data_loader.py` extract_factor_universe |
| **GAP-09** | database_tools.py 纳入版本管理 + 补充测试 | `database_tools.py` + 新测试文件 |

### P2 — 锦上添花（非阻塞，可择机迭代）

| 编号 | 任务 | 涉及文件 |
|------|------|----------|
| **GAP-04** | 参数优化 / 网格搜索 | 可能需要新建 `parameter_optimizer.py` |
| **GAP-07** | AnalysisPipeline Data+Tech 并行化 | `analysis_pipeline_agent.py` 改用 asyncio.gather |
| **GAP-08** | DataAgent fallback 扩展英文支持 | `data_agent.py` _run_fallback 关键词匹配 |

### 测试补齐

| 编号 | 任务 |
|------|------|
| **T-01** | 新增 `test_backtest_agent.py` — DSL 回测路径 + 错误处理 |
| **T-02** | 新增 `test_factor_mining_agent.py` — 因子评估全流程 |
| **T-03** | 新增 `test_multi_condition_strategy.py` — 多条件 AND/OR 编译 + 校验 |
| **T-04** | 新增 `test_database_tools.py` — SQL 查询 + 注入防护 |
| **T-05** | 扩展 `test_strategy_compiler.py` — 多品种 universe 场景 |

---

> **总结一句话**：当前 Agent 系统在「单品分析 + 单条件策略研究」线路上是完整可用的。要支撑一个量化交易者从「市场扫描 → 因子研究 → 策略开发 → 回测验证 → 组合构建 → 风控执行」的完整工作流，需要优先补齐 **多条件策略编译 (GAP-02)**、**多品种组合 (GAP-01)**、**参数优化 (GAP-04)** 和 **策略对比 (GAP-03)** 四个关键缺口。
