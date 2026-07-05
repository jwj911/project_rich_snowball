# Trader Agent 设计文档

> 角色：交易员 Agent  
> 状态：设计稿，待 review 后进入开发  
> 创建时间：2026-07-04

---

## 1. 背景与目标

### 1.1 背景

当前 Agent 系统已覆盖数据查询、数据质检、技术分析、风控管理、策略回测、因子评估、策略编译、参数优化、策略进化等能力。但缺少一个**以交易员视角为核心**的 Agent：

- `tech_analysis` 给出指标分析报告，但不给出具体交易动作；
- `risk_management` 给出风控方案，但不判断交易方向；
- `backtest` 验证策略，但不主动基于当前行情生成交易计划。

### 1.2 目标

新增 `trader` Agent，模拟一位经验丰富的期货交易员：

1. 支持日内波段、日内剥头皮、中短趋势（2 周 ~ 1 个月）等多种交易风格；
2. 基于多周期 K 线识别趋势（上涨 / 下跌 / 横盘整理 / 区间震荡）；
3. 读懂 K 线背后的多空主力变化；
4. 输出完整的交易计划（方向、入场、止损、止盈、仓位、持有周期、失效条件）；
5. 严格执行止盈止损，确保风险可控。

---

## 2. 角色定位

| 属性 | 说明 |
|------|------|
| Agent ID | `trader` |
| 中文名 | 交易员 / 交易研判 |
| 英文名 | Trader Agent |
| 核心角色 | 基于多周期图表研判，输出具体交易计划与风控方案 |
| 交易风格 | 日内剥头皮、日内波段、中短趋势（2 周 ~ 1 个月） |
| 输出形态 | 交易计划卡片 + 风险说明 |

### 2.1 与其他 Agent 的关系

```
┌─────────────────────────────────────────────┐
│              Trader Agent                    │
│  （交易研判：多周期图表 → 交易计划 → 风控）   │
└──────────────┬──────────────────────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
Data Agent  Tech Agent  Risk Agent
(K线/行情)  (指标/形态)  (仓位/止损)
```

| Agent | 关系 |
|-------|------|
| `data` | 被复用：获取 K 线、实时行情、品种参数 |
| `tech_analysis` | 被复用：趋势、动量、波动、形态、背离 |
| `risk_management` | 被复用：仓位、止损止盈、回撤控制 |
| `backtest` | 可联动：交易计划可交给回测 Agent 验证 |
| `analysis_pipeline` | 可升级：后续将 trader 接入完整分析流水线 |

---

## 3. 能力范围

### 3.1 多周期趋势识别

- 拉取日线、4H、1H、15min、5min 等多个周期 K 线；
- 分别判断每个周期的趋势状态：
  - `uptrend`（上涨趋势）
  - `downtrend`（下跌趋势）
  - `sideways`（横盘整理）
  - `range_bound`（区间震荡）
- 多周期共振分析：大周期定方向，小周期找入场。

### 3.2 K 线多空力量解读

- 识别关键 K 线形态：
  - 吞没形态（Engulfing）
  - 锤子线 / 上吊线（Hammer / Hanging Man）
  - 十字星（Doji）
  - Pin Bar
  - Inside Bar
  - 早晨之星 / 黄昏之星
- 结合成交量与持仓量变化判断主力意图；
- 识别支撑/阻力位、关键高低点、突破/假突破。

### 3.3 交易风格自适应

根据用户意图或品种波动特征自动选择交易风格：

| 风格 | 持仓周期 | 适用场景 | 止损/止盈特点 |
|------|---------|---------|--------------|
| `scalping`（剥头皮） | 数分钟 ~ 数小时 | 高波动、流动性好 | 小止损、小止盈、高胜率 |
| `intraday_swing`（日内波段） | 1 小时 ~ 当日收盘 | 日内有明显趋势 | 跟踪止损、分批止盈 |
| `short_term_trend`（中短趋势） | 数天 ~ 2 周 | 日线级别趋势确立 | 较大止损、目标止盈/跟踪止盈 |
| `medium_term_trend`（中期趋势） | 2 周 ~ 1 个月 | 周线/日线共振 | 趋势跟随、宽止损 |

### 3.4 交易系统输出

每个交易计划必须包含：

| 字段 | 说明 |
|------|------|
| `direction` | 做多 / 做空 / 观望 |
| `entry_condition` | 入场触发条件（价格、形态、突破等） |
| `stop_loss` | 止损位：具体价格 + 金额/比例 |
| `take_profit` | 止盈位：目标位 / 分批止盈 / 跟踪止盈 |
| `position_size` | 仓位建议：基于风险敞口和止损距离计算 |
| `holding_period` | 预计持有周期 |
| `invalidation` | 计划失效条件 |
| `risk_reward_ratio` | 盈亏比 |
| `confidence` | 研判置信度（高 / 中 / 低） |

### 3.5 风控与资金曲线思维

- 单笔风险不超过账户固定比例（默认 1-2%）；
- 回撤控制：连续亏损后的降仓规则；
- 盈亏比评估：只参与 R:R ≥ 1.5:1 的机会；
- 所有输出附带"不构成投资建议"声明。

---

## 4. 系统架构

### 4.1 文件结构

```
python/services/agent/
├── trader_agent.py              # Trader Agent 主类
├── trader/
│   ├── __init__.py
│   ├── market_structure.py      # 市场结构识别（趋势/震荡/支撑阻力）
│   ├── multi_timeframe.py       # 多周期共振分析
│   ├── candlestick.py           # K线形态与多空力量
│   ├── trade_plan.py            # 交易计划生成
│   └── risk_check.py            # 风控校验
```

### 4.2 执行流程

```
用户输入
   │
   ▼
[意图解析] ──▶ 品种 / 风格 / 周期偏好
   │
   ▼
[数据拉取] ──▶ DataAgent 工具：多周期 K 线 + 实时行情 + 品种参数
   │
   ▼
[技术分析] ──▶ TechAnalysisAgent 工具：趋势、动量、形态、背离
   │
   ▼
[交易员研判] ──▶ 多周期共振 + K线多空 + 支撑阻力
   │
   ▼
[交易计划生成] ──▶ 方向 / 入场 / 止损 / 止盈 / 仓位
   │
   ▼
[风控校验] ──▶ RiskManagementAgent 工具：单笔风险、盈亏比、回撤
   │
   ▼
[输出报告]
```

### 4.3 步骤可观测性

每个阶段通过 `Agent._add_step()` 记录：

| 步骤 role | 内容 |
|-----------|------|
| `thought` | 当前阶段判断逻辑 |
| `action` | 调用工具（如 `_get_kline_data`） |
| `observation` | 工具返回结果 |
| `system` | 进度提示 |
| `result` | 最终交易计划 |

---

## 5. 数据结构

### 5.1 输入参数

通过用户自然语言解析，或显式传入：

```python
class TraderInput(BaseModel):
    symbol: str                       # 品种代码，如 "RB2501"
    style: TradingStyle | None = None # 交易风格，未指定则自动推断
    timeframes: list[str] | None = None  # 默认 ["1d", "4h", "1h", "15m", "5m"]
    account_risk_per_trade: float = 0.02  # 单笔风险 2%
    min_risk_reward: float = 1.5      # 最低盈亏比
```

### 5.2 输出数据

```python
class TimeframeAnalysis(BaseModel):
    timeframe: str                    # "1d", "1h" 等
    trend: Literal["uptrend", "downtrend", "sideways", "range_bound"]
    key_levels: list[dict]            # 支撑/阻力位
    candlestick_signals: list[dict]   # K线形态信号
    strength: float                   # 多空力量评分 -1 ~ +1

class TradePlan(BaseModel):
    direction: Literal["long", "short", "neutral"]
    style: TradingStyle
    entry_condition: str
    entry_price: float | None
    stop_loss: float
    take_profit: float | list[float]  # 目标位或分批止盈
    position_size: int | float        # 手数 / 金额
    holding_period: str
    invalidation: str
    risk_reward_ratio: float
    confidence: Literal["high", "medium", "low"]

class TraderOutput(BaseModel):
    symbol: str
    current_price: float
    summary: str                      # 一句话总结
    timeframe_analysis: list[TimeframeAnalysis]
    dominant_trend: str               # 主要趋势
    trade_plan: TradePlan | None      # 不满足条件时为 None
    risk_note: str                    # 风险提示
    disclaimer: str                   # 不构成投资建议
```

---

## 6. 模块详细设计

### 6.1 `market_structure.py` — 市场结构识别

**职责**：识别单周期趋势状态、支撑阻力、关键高低点。

**核心函数**：

```python
def identify_trend(df: pd.DataFrame) -> str:
    """基于均线排列 + HH/HL 或 LH/LL 结构判断趋势"""

def find_support_resistance(df: pd.DataFrame, lookback: int = 20) -> list[dict]:
    """识别近期支撑/阻力位（局部极值 + 成交量确认）"""

def detect_breakout_or_fakeout(df: pd.DataFrame, level: float) -> str:
    """判断是有效突破还是假突破"""
```

**趋势判断规则**：

| 条件 | 趋势 |
|------|------|
| 短期均线上穿长期均线，且高点不断抬高 | `uptrend` |
| 短期均线下穿长期均线，且低点不断降低 | `downtrend` |
| 均线粘合，价格在窄区间内波动 | `sideways` |
| 价格在明显上下轨之间反复震荡 | `range_bound` |

### 6.2 `multi_timeframe.py` — 多周期共振分析

**职责**：汇总多周期趋势，给出"大周期定方向，小周期找入场"的研判。

**核心函数**：

```python
def analyze_multi_timeframe(
    timeframe_data: dict[str, pd.DataFrame]
) -> dict:
    """
    返回：
    - dominant_trend: 主要趋势
    - alignment_score: 周期共振度 0-100
    - entry_timeframe: 推荐入场周期
    - conflict_notes: 周期矛盾说明
    """
```

**共振评分**：

| 多周期状态 | 共振评分 | 操作建议 |
|-----------|---------|---------|
| 日线/4H/1H 同向 | 90-100 | 高置信，顺大势操作 |
| 大周期同向，小周期反向 | 60-80 | 等待小周期回调结束 |
| 大周期方向不明，小周期方向清晰 | 40-60 | 轻仓短线 |
| 各周期方向混乱 | 0-40 | 观望 |

### 6.3 `candlestick.py` — K线形态与多空力量

**职责**：识别 K 线形态，结合成交量/持仓量判断多空力量。

**核心函数**：

```python
def detect_candlestick_patterns(df: pd.DataFrame) -> list[dict]:
    """识别常见 K 线形态"""

def calculate_bull_bear_strength(df: pd.DataFrame) -> float:
    """计算多空力量评分 -1 ~ +1"""

def volume_confirmation(signal: dict, df: pd.DataFrame) -> bool:
    """判断成交量是否确认信号"""
```

**多空力量评分维度**：

- 收盘价位置（实体上半部分偏多头，下半部分偏空头）
- 影线比例（长下影线偏多头，长上影线偏空头）
- 成交量放大方向
- 持仓量变化（增仓上行偏多头，增仓下行偏空头）

### 6.4 `trade_plan.py` — 交易计划生成

**职责**：根据市场结构、多周期共振、K线形态生成具体交易计划。

**核心函数**：

```python
def generate_trade_plan(
    symbol: str,
    current_price: float,
    dominant_trend: str,
    entry_timeframe_analysis: TimeframeAnalysis,
    support_resistance: list[dict],
    style: TradingStyle,
    risk_per_trade: float,
    min_risk_reward: float,
) -> TradePlan | None:
    """
    生成交易计划，不满足条件时返回 None
    """
```

**生成规则示例（日内波段，多头）**：

- 入场：小周期回调结束，出现看涨 K 线形态，且成交量确认；
- 止损：入场 K 线低点下方 1 个 ATR 或关键支撑下方；
- 止盈：最近阻力位或 1.5-2 倍风险距离；
- 仓位：账户 2% 风险 ÷ （入场价 - 止损价）÷ 合约乘数。

### 6.5 `risk_check.py` — 风控校验

**职责**：校验交易计划是否满足风控要求。

**核心函数**：

```python
def validate_trade_plan(plan: TradePlan, account: dict) -> dict:
    """
    校验：
    - 单笔风险是否 <= 账户风险上限
    - 盈亏比是否 >= 最低要求
    - 止损距离是否合理（不过小/过大）
    - 仓位是否超过上限
    """
```

---

## 7. 接口设计

### 7.1 后端接口

复用现有 Agent 路由：

```
POST /api/agents/chat
{
  "agent_type": "trader",
  "content": "帮我看看 RB2501 今天的日内波段机会"
}
```

SSE 流式返回交易研判过程与最终结果。

### 7.2 前端 Chat 模式

新增 `trader` 模式：

```typescript
{
  key: 'trader',
  label: '交易员',
  icon: TrendingUp,
  desc: '多周期图表研判，输出具体交易计划',
  quickPrompts: [
    '帮我看看 RB2501 今天的日内波段机会',
    'CU2501 现在适合剥头皮吗？',
    '给出 P2501 未来两周的趋势交易计划',
    '帮我制定一个豆粕的交易系统'
  ]
}
```

---

## 8. 实现步骤

### Phase 1：核心模块开发

1. 创建 `python/services/agent/trader/` 目录与 5 个子模块；
2. 实现 `market_structure.py` 的趋势识别与支撑阻力；
3. 实现 `multi_timeframe.py` 的多周期共振；
4. 实现 `candlestick.py` 的 K线形态与多空力量；
5. 实现 `trade_plan.py` 的交易计划生成；
6. 实现 `risk_check.py` 的风控校验。

### Phase 2：Agent 主类与接入

1. 创建 `python/services/agent/trader_agent.py`；
2. 在 `python/routers/agents.py` 注册；
3. 在 `python/schemas.py` 更新枚举与校验；
4. 在 `python/services/agent/intent_router.py` 添加意图路由；
5. 在 `python/services/agent/__init__.py` 导出。

### Phase 3：前端接入

1. `frontend/app/chat/page.tsx` 增加 `trader` 模式；
2. `frontend/app/agents/page.tsx` 增加标签；
3. `frontend/lib/api/types.ts` 同步类型。

### Phase 4：测试与文档

1. 编写 `python/tests/test_trader_agent.py`；
2. 后端跑 `pytest python/tests/test_trader_agent.py`；
3. 前端跑 `tsc --noEmit` + `npm run lint`；
4. 更新 `.agents/agents.md` 与 `.agents/roadmap.md`。

---

## 9. 测试计划

### 9.1 单元测试

| 测试文件 | 测试内容 |
|---------|---------|
| `test_trader_market_structure.py` | 趋势识别、支撑阻力、突破判断 |
| `test_trader_multi_timeframe.py` | 多周期共振评分 |
| `test_trader_candlestick.py` | K线形态识别、多空力量评分 |
| `test_trader_trade_plan.py` | 交易计划生成规则 |
| `test_trader_risk_check.py` | 风控校验逻辑 |

### 9.2 集成测试

| 测试文件 | 测试内容 |
|---------|---------|
| `test_trader_agent.py` | TraderAgent.run() 完整链路 |
| `test_agents_router.py` | `/api/agents/chat` trader 模式 SSE 返回 |

### 9.3 验收标准

- [ ] 能正确解析用户输入中的品种、风格、周期偏好；
- [ ] 能输出多周期趋势分析；
- [ ] 能识别常见 K 线形态并给出多空力量评分；
- [ ] 能生成包含方向、入场、止损、止盈、仓位的完整交易计划；
- [ ] 不满足交易条件时（如趋势不明、盈亏比不足）能给出观望建议；
- [ ] 所有输出附带风险提示与免责声明；
- [ ] 前后端类型一致，`tsc --noEmit` 通过；
- [ ] 后端 pytest 全部通过。

---

## 10. 风险提示

- Trader Agent 所有输出仅作为技术研判参考，**不构成投资建议**；
- 实盘交易需结合用户自身资金情况、风险承受能力、市场环境综合判断；
- Agent 无法预测突发事件、政策变化、流动性风险等黑天鹅事件；
- 生成的止损止盈价格基于历史数据和技术规则，不保证未来有效。

---

## 11. 附录

### 11.1 相关文档

- `.agents/agents.md` — Agent 系统架构与开发约束
- `.agents/roadmap.md` — 模块演进状态
- `python/services/agent/core.py` — Agent 基类
- `python/services/agent/tech_analysis_agent.py` — 技术分析 Agent 参考
- `python/services/agent/risk_management_agent.py` — 风控 Agent 参考

### 11.2 待决策问题

1. 是否需要支持"交易系统"模式（即用户要求制定一套规则，而非单次交易计划）？
2. 是否需要与 `backtest` Agent 联动，自动验证生成的交易计划？
3. 是否需要支持用户自定义风险偏好参数（如单笔风险 1% vs 2%）？
4. 是否需要保存历史交易计划并追踪后续表现（类似模拟交易记录）？


---

## 12. 迭代进展记录

### 2026-07-05 第一次迭代：核心功能开发与接入完成

**状态**：已完成 ✅  
**提交目标**：本地 master 分支

#### 本迭代完成内容

1. **Phase 1：核心子模块实现**
   - `python/services/agent/trader/market_structure.py`：趋势识别（上涨/下跌/横盘/震荡）、支撑阻力、突破/假突破判断
   - `python/services/agent/trader/multi_timeframe.py`：多周期共振分析、主导趋势识别、入场周期推荐
   - `python/services/agent/trader/candlestick.py`：吞没、Pin Bar、十字星、Inside Bar、锤子线/上吊线、早晨之星/黄昏之星识别；多空力量评分
   - `python/services/agent/trader/trade_plan.py`：交易计划生成（方向/入场/止损/止盈/仓位/盈亏比/置信度）
   - `python/services/agent/trader/risk_check.py`：风控校验（单笔风险、盈亏比、仓位、回撤提示）

2. **Phase 2：Agent 主类与后端接入**
   - `python/services/agent/trader_agent.py`：TraderAgent 主类实现，支持日内剥头皮、日内波段、中短趋势、中期趋势四种风格
   - 注册到 `python/routers/agents.py`：`_AGENT_CAPABILITIES` 与 `_build_agent()`
   - 更新 `python/schemas.py`：`AgentType` 增加 `TRADER`，`AgentTaskCreate` / `AgentChatRequest` pattern 增加 `trader`
   - 更新 `python/services/agent/intent_router.py`：交易相关关键词路由到 `trader`
   - 更新 `python/services/agent/__init__.py`：导出 `TraderAgent`

3. **Phase 3：前端接入**
   - `frontend/app/chat/page.tsx`：增加 `trader` 模式、快捷提示、图标与描述
   - `frontend/app/agents/page.tsx`：`agentTypeLabels` 增加 `trader: '交易员'`

4. **Phase 4：测试与质量保障**
   - `python/tests/test_trader_modules.py`：12 个单元测试，覆盖趋势、支撑阻力、形态、多空力量、交易计划、风控校验
   - `python/tests/test_trader_agent.py`：6 个集成测试，覆盖 Agent 完整执行链路、数据不足降级、无品种失败、路由注册
   - 后端测试：`18 passed`（trader 专项）
   - 前端检查：`npx tsc --noEmit` 通过，`npm run lint` 无警告错误

#### 验证结果

- [x] 能正确解析用户输入中的品种、风格、周期偏好
- [x] 能输出多周期趋势分析
- [x] 能识别常见 K 线形态并给出多空力量评分
- [x] 能生成包含方向、入场、止损、止盈、仓位的完整交易计划
- [x] 不满足交易条件时（如趋势不明、盈亏比不足）能给出观望建议
- [x] 所有输出附带风险提示与免责声明
- [x] 前后端类型一致，`tsc --noEmit` 通过
- [x] 后端 trader 专项 pytest 全部通过

#### 待后续迭代处理的问题

- [ ] 全量后端 pytest 结果待确认（后台运行中）
- [ ] 是否需要与 `backtest` Agent 联动，自动验证生成的交易计划
- [ ] 是否需要支持用户自定义风险偏好参数（如单笔风险 1% vs 2%，已部分支持 query 解析）
- [ ] 是否需要保存历史交易计划并追踪后续表现
- [ ] 是否需要支持"交易系统"模式（制定一套规则，而非单次交易计划）


### 2026-07-05 第一次迭代补充：测试冲突修复

**问题**：全量 pytest 中 `test_trader_agent.py` 的 2 个集成测试因 `varieties.symbol` 唯一约束冲突而失败。原因是测试使用 `RB` 作为品种代码，与其他测试共享临时数据库时产生冲突。

**修复**：
- `test_trader_agent.py` 中 `_seed_variety_and_contracts()` 改用唯一品种代码 `TRB`（Test Rebar）
- 增加已存在品种复用逻辑，避免重复插入
- 同步更新 query 文本和断言中的品种代码

**验证**：
- trader 专项测试：`18 passed` ✅
- 全量测试（排除 `test_strategy_evolution_agent.py`，该文件依赖未安装的 `sklearn`）：待确认

### 已知环境问题

- `test_strategy_evolution_agent.py` 全部 10 个测试失败，原因是环境缺少 `scikit-learn` 包：`ModuleNotFoundError: No module named 'sklearn'`。
- 该问题与 TraderAgent 无关，属于已有依赖环境问题，建议后续安装 `scikit-learn` 或将其加入 `requirements.lock`。


**全量测试结果**：
- 排除 `test_strategy_evolution_agent.py`（依赖未安装的 `sklearn`）：`812 passed, 7 skipped, 0 failed` ✅
- 完整全量测试（含 strategy_evolution）：`887 passed, 7 skipped, 12 failed`；其中 10 个失败为 strategy_evolution 的 sklearn 依赖缺失，2 个已修复为 trader 测试冲突
