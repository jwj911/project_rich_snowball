# 数据与 Agent 能力后续迭代计划

**日期**：2026-07-04

**适用范围**：数据质量、数据目录、Agent 可用数据上下文、LLM 配置、主力连续数据、数据宽表审计

**目标**：让 Agent 在回答、回测、因子评估、策略编排前，明确知道“有哪些数据、数据是否可信、该用哪种数据口径、LLM 是否可用”。

> **当前状态校正（2026-08-02）**：本文记录的 Milestone A-E 与后续 R3/R4 已完成，主体保留为
> 历史设计和交付记录，不再承载当前“下一步”。当前唯一迭代事实源是
> [`Post-R9 迭代路线图`](iteration_plan_20260802_post_r9.md)。Data Catalog 后端与质量上下文
> 已实现；用户可见的只读 Data Catalog 前端仅为 Post-R9 产品候选，未排期且必须另立规格。

---

## 1. 总体方向

当前系统已经具备行情、K 线、策略、回测、因子评估和多 Agent 基础能力。下一阶段的重点不应只是继续增加 Agent 数量，而是补齐数据地基：

1. 建立 DataQualityAgent，负责数据盘点、质量检查、健康评分和可用性解释。
2. 建立 Data Catalog，让所有 Agent 都能查询“当前系统可用的数据资产”。
3. 建立用户级 LLM 配置 API，让 DataAgent 等 LLM Agent 不只依赖环境变量。
4. 将主力连续数据交给数据管道方向实现，明确验收标准。
5. 对数据宽表工作做独立审计，确保字段、血缘、质量、刷新机制可用于因子与策略。

---

## 1.1 当前完成状态（2026-07-04 更新）

已完成：

0. **已合入本地 `master`**
   - DataQualityAgent、Data Catalog、用户级 LLM 配置三项最小闭环已在本地 `master` 分支代码中落地。
   - 本轮继续在本地 `master` 上推进 Milestone C+，未切换到历史 `codex/new_fronted` 等风险分支。

1. **Milestone A：DataQualityAgent 最小闭环**
   - 已新增 `agent_type=data_quality`，标签为“数据质检”，`requires_llm=false`。
   - 已新增 `python/services/data_quality/` 服务包，包含 `checks.py`、`coverage.py`、`scoring.py`、`service.py`、`types.py`。
   - 已支持 `kline_data` 和 `realtime_quotes` 的首版检查。
   - K 线 P0 检查已覆盖 OHLC 合法性、成交量非负、重复记录、日 K 疑似缺口、覆盖摘要。
   - 已接入 `/api/agents` 能力列表、任务创建、SSE 流式执行和 Chat 页“数据质检”模式。
   - 已增加后端测试：正常 K 线、OHLC 异常、缺数据、无 LLM 可用性。

2. **Milestone B：Data Catalog 最小闭环**
   - 已新增 `python/services/data_catalog.py`，当前采用动态查询 SQLAlchemy ORM + 业务配置，不新建目录表。
   - 已纳入数据集：`varieties`、`fut_contracts`、`realtime_quotes`、`kline_data`、`contract_rollovers`、`fut_daily_data`、`fut_settle`、`fut_wsr`、`fut_holding`、`fut_price_limits`、`fut_weekly_detail`、`trade_records`、`strategies`、`backtest_runs`。
   - 已给 DataAgent 注册工具：`list_available_datasets()`、`get_dataset_profile(dataset_name)`、`get_symbol_data_coverage(symbol, period?)`、`get_data_quality_summary(symbol?, dataset_name?)`。
   - DataAgent 无 LLM fallback 已能回答“现在库里有哪些可用数据”。
   - 已增加 Data Catalog 服务与工具测试。

3. **Milestone C：用户级 LLM 配置**
   - 已新增用户级 LLM 配置模型 `user_llm_configs` 与迁移。
   - 已新增 API：`GET /api/llm-config`、`PUT /api/llm-config`、`POST /api/llm-config/test`、`DELETE /api/llm-config/api-key`。
   - API Key 使用应用级密钥派生加密存储；接口只返回 `has_api_key` 和 `api_key_masked`，不回显明文。
   - `/settings` 已新增“AI 配置”区块，支持 Provider、Base URL、Model、API Key、测试连接、清除 Key。
   - `AgentLLMClient` 已支持用户配置优先、系统环境变量兜底。
   - DataAgent 和普通 AI Chat 已使用用户级配置解析结果。
   - 已增加 LLM 配置 API、脱敏、能力启用、AgentLLMClient 解析测试。

4. **Milestone C+：Agent 数据前置检查**
   - BacktestAgent 已在进入回测引擎前调用 Data Catalog / Data Quality 检查 `kline_data` 覆盖和质量。
   - K 线质量为 `bad` 时，BacktestAgent 默认拒绝回测；`warning` 时继续执行并在结果报告写入数据质量提示。
   - FactorMiningAgent 已在加载面板和计算因子前读取 Data Catalog，校验公式所需字段；缺少 `amount/open_interest/turnover_rate` 等字段时返回明确错误。
   - AnalysisPipelineAgent 已在 DataAgent / TechAnalysisAgent / RiskManagementAgent 前增加数据可用性检查；`bad` 时停止流水线，`warning` 时继续并在最终报告保留风险提示。
   - 已增加 `tests/test_agent_data_preflight.py` 覆盖回测 bad 拒绝、因子缺字段失败、流水线 bad 停止，并修复 `test_factor_mining_agent.py` 测试夹具的数据复用问题。

5. **Milestone D/E：多视图研究宽表与连续数据接入**
   - 已新增 `docs/data_wide_table_audit.md`。
   - 已新增 `agent_market_panel_daily`，完成 `raw_contract`、主力连续、前复权和后复权日频视图、
     换月/复权/build trace 血缘、质量状态与幂等重建。
   - 已复用 `data_ingestion_runs` 记录构建批次、可恢复重试和质量快照；Data Catalog、
     DataQualityAgent、FactorMiningAgent 与 BacktestAgent 已支持显式 `data_view` 消费。
   - 仅独立 worker 注册日频宽表任务，常规 20 交易日预热且迟到换月从最早影响日回推，
     详见 `docs/r3_raw_contract_market_panel.md`。

以下 targeted 计数是 2026-07-04 前后各里程碑的历史验证记录，不是当前全量测试基线：

```powershell
cd python
.venv/Scripts/python.exe -m pytest tests/test_data_catalog.py tests/test_data_quality_agent.py tests/test_llm_config.py tests/test_agents_core.py -q
# 24 passed

.venv/Scripts/python.exe -m pytest tests/test_agent_data_preflight.py tests/test_data_catalog.py tests/test_data_quality_agent.py tests/test_factor_mining_agent.py tests/services/agent/test_analysis_pipeline.py -q
# 30 passed
```

---

## 2. 迭代优先级

| 优先级 | 主题 | 当前状态 | 目标 | 责任建议 |
|---|---|---|---|---|
| P0 | DataQualityAgent | **已完成最小闭环** | 数据质量可查询、可解释、可被其它 Agent 调用 | 当前线程/Agent |
| P0 | Data Catalog | **已完成最小闭环** | Agent 知道可用表、覆盖范围、更新时间、质量状态 | 当前线程/Agent |
| P0 | LLM 配置 API | **已完成最小闭环** | 用户可配置自己的 OpenAI 兼容 API，系统默认可兜底 | 当前线程/Agent |
| P1 | Agent 数据前置检查 | **已完成最小闭环** | 回测/因子/技术分析前自动检查数据可用性 | 当前线程/Agent |
| P1 | 数据宽表审计与多视图实现 | **已完成** | 四种日频视图可重建、可追溯、可被目录和 Agent 显式选择 | 当前线程 |
| P1 | 主力连续数据管道 | **已完成** | 主力连续/前后复权、换月血缘、独立 worker 调度 | 当前线程 |

---

## 3. DataQualityAgent 设计

### 3.1 定位

DataQualityAgent 是确定性 Agent，默认不依赖 LLM。它的职责是回答：

- 当前有哪些数据可以用？
- 某个品种/周期/日期区间的数据是否完整？
- 某次回测或因子评估的数据可信度如何？
- 哪些数据问题需要先修复？

### 3.2 新增 Agent 类型

建议新增：

```text
agent_type = data_quality
label = 数据质检
requires_llm = false
```

需要更新：

- `python/schemas.py`
- `python/routers/agents.py`
- `python/services/agent/__init__.py`
- `frontend/app/chat/page.tsx`
- `frontend/components/agent/*` 如需专用展示卡片
- `frontend/lib/api/types.ts`

### 3.3 核心能力

第一版建议支持 5 类任务：

| 能力 | 示例问题 | 输出 |
|---|---|---|
| 数据资产盘点 | “现在库里有哪些可用数据？” | 表级覆盖摘要 |
| 品种数据覆盖 | “螺纹钢日 K 数据完整吗？” | 日期范围、缺口、异常数 |
| K 线质量检查 | “检查 RB 的 1d K 线质量” | OHLC 异常、重复、缺交易日 |
| 回测前检查 | “这个策略能不能用 RB 近 3 年数据回测？” | pass/warning/fail |
| 数据问题解释 | “为什么因子评估失败？” | 缺字段、缺品种、缺周期说明 |

### 3.4 服务层建议

新增服务模块：

```text
python/services/data_quality/
├── __init__.py
├── checks.py              # 单项规则
├── coverage.py            # 覆盖范围统计
├── scoring.py             # 健康评分
├── service.py             # 对 Agent/Router 的统一入口
└── types.py               # dataclass / TypedDict
```

第一版不要急着建复杂任务表，可以先实时查询；如果性能有压力，再增加快照表。

### 3.5 检查规则

P0 规则：

- `high >= max(open, close, low)`
- `low <= min(open, close, high)`
- `open/high/low/close > 0`
- `volume >= 0`
- 同一 `variety_id + contract_id + period + trading_time` 不重复
- 日 K 日期覆盖范围
- 最近更新时间
- `contract_id` 缺失比例
- 主力映射缺失比例

P1 规则：

- 交易日历缺口检测
- 价格极端跳变
- 成交量极端跳变
- 主力换月断点
- 结算价与收盘价偏离
- 多数据源交叉对账

### 3.6 输出结构

AgentResult.data 建议固定：

```json
{
  "scope": {
    "symbol": "RB",
    "period": "1d",
    "start_date": "2023-01-01",
    "end_date": "2026-07-04"
  },
  "status": "warning",
  "score": 82,
  "coverage": {
    "first_date": "2020-01-02",
    "last_date": "2026-07-03",
    "row_count": 1432,
    "missing_dates": 3
  },
  "issues": [
    {
      "severity": "warning",
      "code": "KLINE_MISSING_DATES",
      "message": "发现 3 个疑似缺失交易日",
      "sample": ["2024-10-08"]
    }
  ],
  "recommendations": [
    "可用于趋势回测，但建议先补齐缺失日 K。"
  ]
}
```

---

## 4. Data Catalog 设计

### 4.1 目标

Data Catalog 是给 Agent 使用的数据地图。它不只是文档，而应有 API/工具可查询。

Agent 至少应该知道：

- 有哪些数据表。
- 每张表的业务含义。
- 数据粒度。
- 日期覆盖范围。
- 品种覆盖范围。
- 最近更新时间。
- 质量状态。
- 哪些 Agent 可以使用。

### 4.2 推荐第一版工具

给 Agent 注册以下工具：

```text
list_available_datasets()
get_dataset_profile(dataset_name)
get_symbol_data_coverage(symbol, period?)
get_data_quality_summary(symbol?, dataset_name?)
```

### 4.3 推荐数据集清单

第一版纳入：

- `varieties`
- `fut_contracts`
- `realtime_quotes`
- `kline_data`
- `contract_rollovers`
- `fut_daily_data`
- `fut_settle`
- `fut_wsr`
- `fut_holding`
- `fut_price_limits`
- `fut_weekly_detail`
- `trade_records`
- `strategies`
- `backtest_runs`
- 后续新增的数据宽表

### 4.4 实现路线

第一阶段可以不建表，动态查询 SQLAlchemy metadata + 业务配置。

第二阶段再落库：

```text
data_catalog_datasets
data_catalog_snapshots
data_quality_issues
```

---

## 5. LLM 配置 API

### 5.1 当前问题

当前 LLM 主要依赖环境变量：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

这会导致普通用户无法在前端自行配置，DataAgent 也只能根据系统环境判断是否可用。

### 5.2 建议设计

保留系统默认配置，同时增加用户级配置。

优先级：

1. 用户自己的配置。
2. 系统环境变量默认配置。
3. 未配置时返回明确错误和引导。

### 5.3 API

```text
GET    /api/llm-config
PUT    /api/llm-config
POST   /api/llm-config/test
DELETE /api/llm-config/api-key
```

### 5.4 响应结构

```json
{
  "provider": "openai-compatible",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "has_api_key": true,
  "api_key_masked": "sk-...abcd",
  "uses_system_default": false,
  "updated_at": "2026-07-04T10:00:00Z"
}
```

### 5.5 数据库建议

新增表：

```text
user_llm_configs
```

字段建议：

- `id`
- `user_id`
- `provider`
- `base_url`
- `model`
- `api_key_encrypted`
- `is_active`
- `created_at`
- `updated_at`

安全要求：

- API 永远不回显明文 key。
- 日志脱敏。
- 测试接口只返回连接是否成功和模型名。
- 如果第一版来不及做 KMS，可先使用应用级密钥加密；不要明文存储。

### 5.6 前端设置页

在 `/settings` 增加 “AI 配置” 区块：

- Provider
- Base URL
- Model
- API Key
- 测试连接按钮
- 使用系统默认配置提示

---

## 6. 主力连续数据管道分工

### 6.1 为什么交给数据管道 Agent

主力连续数据是数据工程问题，不是 LLM 对话问题。它需要可重跑、可增量、可回溯、可验收。

### 6.2 任务拆分

建议分配给更适合的数据管道 Agent，任务包括：

1. 明确主力合约切换规则。
2. 生成主力连续 K 线。
3. 生成前复权/后复权连续价格。
4. 标记换月日和跳空。
5. 提供数据口径参数给回测和因子引擎。
6. 补齐测试和验收文档。

### 6.3 验收标准

- 能对单品种全量重建。
- 能按日期增量更新。
- 能解释每一次换月来源。
- 回测时可以选择：
  - `raw_contract`
  - `main_continuous`
  - `main_back_adjusted`
  - `main_forward_adjusted`
- DataQualityAgent 能检查连续合约断点。

---

## 7. 数据宽表审计清单

数据宽表由另一个 Agent 实现后，需要审计以下内容。

### 7.1 字段完整性

基础字段：

- `symbol`
- `trading_date`
- `period`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`
- `open_interest`

派生字段：

- `ret_1`
- `ret_5`
- `ret_20`
- `gap`
- `amplitude`
- `intraday_range`
- `turnover_rate`
- `volume_ratio`

扩展字段：

- `warehouse_receipt`
- `holding_rank`
- `settlement`
- `limit_up`
- `limit_down`
- `basis`
- `term_structure`

### 7.2 血缘与口径

每个字段必须说明：

- 来源表。
- 计算公式。
- 数据口径。
- 是否复权。
- 是否受主力换月影响。
- 缺失值处理方式。

### 7.3 性能与索引

必备索引：

```text
(symbol, trading_date)
(trading_date)
(period, symbol, trading_date)
```

如果支持多口径：

```text
(data_view, symbol, trading_date)
```

### 7.4 质量门禁

宽表刷新后必须执行：

- row count 对账。
- 日期范围对账。
- OHLC 合法性。
- 派生字段空值比例。
- 与原始 K 线抽样对账。
- 最近 N 日增量刷新校验。

---

## 8. Agent 集成路线

### 8.1 BacktestAgent

回测前调用：

```text
get_symbol_data_coverage(symbol, period)
get_data_quality_summary(symbol, dataset_name="kline_data")
```

如果质量为 `bad`，默认拒绝回测或明确提示。

### 8.2 FactorMiningAgent

因子评估前调用：

```text
list_available_datasets()
get_symbol_data_coverage(symbols)
```

如果因子需要 `amount/turnover_rate/open_interest`，但宽表没有对应字段，需要返回明确错误。

### 8.3 DataAgent

DataAgent 应优先通过 Data Catalog 选择工具，而不是只靠 LLM 猜测。

### 8.4 AnalysisPipelineAgent

流水线第一步增加数据可用性检查：

```text
DataQualityAgent → DataAgent → TechAnalysisAgent → RiskManagementAgent
```

---

## 9. 推荐里程碑

### Milestone A：数据质量 Agent 最小闭环（已完成）

交付：

- 已交付 `DataQualityAgent`
- 已交付 `data_quality_service`
- 已交付 K 线质量检查
- 已交付数据覆盖摘要
- 已交付 Chat/Agent 工作台可调用
- 已交付后端单元测试

验收：

- 已能回答“检查 RB 日 K 数据质量”。
- 已能返回固定结构化结果。
- 已支持无 LLM key 时可用。

### Milestone B：Data Catalog（已完成最小闭环）

交付：

- 已交付数据目录服务 `DataCatalogService`
- 已交付 Agent 工具注册
- 已交付覆盖范围查询
- 已交付数据集 profile
- 前端展示暂未做，保留为后续可选增强

验收：

- DataAgent 已能回答“当前有哪些数据可用”。
- BacktestAgent 自动读取覆盖范围尚未接入，移入下一阶段“Agent 数据前置检查”。

### Milestone C：LLM 配置（已完成最小闭环）

交付：

- 已交付用户级 LLM 配置表
- 已交付配置 API
- 已交付测试连接 API
- 已交付设置页 AI 配置区块
- 已交付 AgentLLMClient 支持用户配置优先

验收：

- 已支持未配置用户 key 时使用系统默认。
- 已支持用户配置 key 后 DataAgent 使用用户配置。
- 已验证 API 不回显明文 key。

### Milestone C+：Agent 数据前置检查（已完成最小闭环）

交付：

- 已交付 BacktestAgent 回测前调用 `get_symbol_data_coverage(symbol, period)`。
- 已交付 BacktestAgent 回测前调用 `get_data_quality_summary(symbol, dataset_name="kline_data")`。
- 已交付 K 线质量为 `bad` 时默认拒绝回测并返回明确失败原因。
- 已交付 K 线质量为 `warning` 时允许继续，并在回测结果中写入质量提示。
- 已交付 FactorMiningAgent 因子评估前调用 `list_available_datasets()` 与 `get_symbol_data_coverage(symbols)`。
- 已交付 FactorMiningAgent 对因子所需字段做前置校验，例如 `amount`、`open_interest`、`turnover_rate`。
- 已交付 AnalysisPipelineAgent 第一阶段加入数据可用性检查，再进入 DataAgent / TechAnalysisAgent / RiskManagementAgent。
- 已交付后端测试覆盖 bad 阻断、缺字段失败和流水线停止；warning 继续路径已在实现中保留。

验收：

- 已验证回测请求在缺少 K 线数据时不会直接进入回测引擎。
- 已验证回测结果能说明使用的数据集、周期、覆盖范围和数据质量状态。
- 已验证因子评估缺字段时返回明确错误，而不是在计算阶段隐式失败。
- 已验证完整分析流水线第一步能展示数据检查结果。

### Milestone D/E：数据宽表审计与连续数据接入（已完成）

交付：

- 已交付宽表字段审计报告：`docs/data_wide_table_audit.md`
- 已交付数据血缘审计报告
- 已交付刷新机制审计
- 已交付索引和性能建议
- 已交付质量门禁建议
- 已交付 `agent_market_panel_daily` 的 `raw_contract`、`main_continuous`、
  `main_back_adjusted`、`main_forward_adjusted` / `1d` 宽表、幂等重建服务与 dry-run 脚本
- 已接入 Data Catalog 和 DataQualityService
- 已接入构建批次、连接类错误重试和无原始行情样本的质量快照
- 已接入换月、复权和 build trace 血缘；DataQualityAgent 检查连续日期、换月与血缘
- 已接入 FactorMiningAgent、BacktestAgent 的显式 `data_view`，原始合约要求具体合约
- 已接入独立 worker 调度、20 交易日预热和迟到换月回推

验收：

- 四种视图均可构建、重建和解释字段/换月/复权血缘。
- 因子和回测只有显式选择时才使用宽表，保留历史 K 线默认语义。
- C+ 保护继续有效：因子缺字段会明确失败，回测/流水线会先检查所选数据口径质量。

## 10. 风险与注意事项

1. 不要让 LLM 自己判断数据是否可信，质量检查必须由确定性规则给出。
2. Data Catalog 不能只写文档，必须提供 Agent 可调用的服务或工具。
3. 用户 API key 不得明文返回，不得进入日志。
4. 宽表不要只追求字段多，必须保留字段血缘和刷新校验。
5. 主力连续数据必须支持重建，否则后续策略结果无法复现。
6. 数据质量结果应允许 warning，不要因为轻微缺口阻塞所有分析。

---

## 11. 当前下一步（Post-R9 状态校正）

宽表最小实现与主力连续数据接入已由 R3 完成；DSL transform 契约、日频
walk-forward、报告与生命周期持久化已由 R4 完成，见
[`r4_dsl_walk_forward_validation.md`](r4_dsl_walk_forward_validation.md)。

原“后续进入 R5”的表述是 2026-07-04 历史计划，R5-R9 后续均已闭环，不再作为当前入口。
当前项目级下一步由
[`Post-R9 迭代路线图`](iteration_plan_20260802_post_r9.md) 统一管理：R10“CSP 脱敏证据
归类与 S2 准入报告”非生产工程基线已完成，R11 受生产操作者门禁阻塞；不从本文直接启动新的
数据工程实施。

Data Catalog 方向仅保留 P-C2 候选：为授权用户提供只读目录和质量上下文。后端现状见
[`data_catalog.py`](../python/services/data_catalog.py)，回归证据见
[`test_data_catalog.py`](../python/tests/test_data_catalog.py) 与
[`R3 多视图研究宽表`](r3_raw_contract_market_panel.md)。前端候选必须先明确可见范围、只读
权限、质量语义、缓存分页、隐私边界和测试成本，再建立独立规格；当前状态为候选、未排期。
