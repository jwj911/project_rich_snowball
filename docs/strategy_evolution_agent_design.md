# 自进化策略 Agent — 架构设计文档

> **状态**：设计阶段 | **日期**：2026-07-04 | **作者**：AI Agent

---

## 1. 问题定义

### 1.1 当前系统的能力边界

现有系统已具备以下能力：

| 能力 | 实现 | 限制 |
|------|------|------|
| 策略 DSL | `strategy_compiler_agent.py` — 7 种模板，规则匹配 NL→DSL | 用户必须手动描述策略意图 |
| 策略回测 | `services/backtest/engine.py` — 向量化回测，完整指标 | 单策略单品种，无批量对比 |
| 参数优化 | `services/backtest/optimization_engine.py` — 网格搜索 | 仅参数调优，不改变策略结构 |
| 因子评估 | `factor_mining_agent.py` — IC/Rank IC/分层回测 | 用户必须手动提供因子公式 |
| 因子 DSL | `factor_engine/dsl.py` — 28 个算子，安全 AST 求值 | 无自动因子发现 |
| 多 Agent 编排 | `analysis_pipeline_agent.py` — parallel + serial DAG | 硬编码流程，非自适应 |

**核心缺失**：系统无法从价格数据中**自动发现**交易策略。"自进化"意味着系统观察价格变化 → 自动生成候选策略 → 回测验证 → 迭代优化 → 持续跟踪。

### 1.2 自进化策略 Agent 的目标

> 给定一个品种（或品种池）和周期，Agent 自动完成：市场状态识别 → 因子发现 → 策略生成 → 回测评估 → 进化优化 → 持续性跟踪，产出可直接用于交易的策略 DSL。

---

## 2. 核心设计理念

### 2.1 闭环进化架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      Strategy Evolution Loop                     │
│                                                                  │
│   Price Data ──→ Market Regime ──→ Factor Discovery ──→ Strategy│
│                                      ↑                    Gen   │
│                                      │                    ↓     │
│                               Factor Pool            Population │
│                                      │                    ↓     │
│                                      │              Backtest    │
│                                      │                    ↓     │
│                               ┌──────┘              Fitness     │
│                               │                        ↓        │
│                               └──── Evolution ◀────────┘        │
│                                   (mutate/crossover/select)      │
│                                                                  │
│   Output: Optimized Strategy DSL → Lifecycle Tracking → Report   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 设计原则（与现有 Agent 系统一致）

1. **确定性计算优先** — 因子求值、回测、适应度计算全部用 numpy/pandas；LLM 仅负责意图理解与报告生成
2. **可观测** — 每一代进化状态持久化到 DB，前端 SSE 流式展示
3. **安全沙箱** — 因子公式生成后必须通过 `validate_factor_formula()` 校验
4. **风险提示默认包含** — 所有输出附带过拟合警告

### 2.3 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 进化算法 | 遗传算法 (GA) + 贝叶斯优化 | GA 适合离散结构搜索（条件组合）；BO 适合连续参数精调 |
| 策略表示 | 现有 Strategy DSL (JSON) | 复用现有编译器和回测引擎，无需额外转换 |
| 因子生成 | 遗传编程 + 模板采样 | GP 探索新颖组合；模板保证最低质量 |
| 适应度函数 | 多目标加权（Sharpe + 稳定性 + 鲁棒性 - 复杂度） | 避免单指标过拟合 |
| 品种处理 | 单品种深度优化 + 跨品种鲁棒性验证 | 先找到品种特化策略，再验证泛化能力 |
| 计算时机 | 夜间批量 + 手动触发 | 进化计算密集，不适合实时 |

---

## 3. 系统架构

### 3.1 模块划分

```
python/services/agent/
├── strategy_evolution_agent.py    # 主 Agent（继承 Agent 基类）
├── evolution/
│   ├── __init__.py
│   ├── market_regime.py           # 市场状态识别
│   ├── factor_discovery.py        # 因子自动发现（遗传编程 + 模板）
│   ├── strategy_population.py     # 策略种群管理
│   ├── genetic_operators.py       # 选择/交叉/变异算子
│   ├── fitness.py                 # 多维适应度评分
│   └── strategy_lifecycle.py      # 策略生命周期跟踪
```

### 3.2 数据模型（新增 Alembic 迁移）

```sql
-- 进化运行记录
CREATE TABLE strategy_evolution_runs (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id),
    config_json     JSONB NOT NULL,          -- 进化配置
    status          VARCHAR(20) NOT NULL,     -- pending/running/completed/failed
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    generations     INTEGER,                 -- 总代数
    population_size INTEGER,                 -- 种群大小
    best_strategy_id INTEGER REFERENCES strategies(id),
    summary_json    JSONB,                   -- 进化摘要
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 每代快照
CREATE TABLE strategy_generations (
    id                SERIAL PRIMARY KEY,
    evolution_run_id  INTEGER REFERENCES strategy_evolution_runs(id),
    generation_number INTEGER NOT NULL,
    population_json   JSONB NOT NULL,        -- 种群中所有个体 + 适应度
    best_fitness      FLOAT,
    avg_fitness       FLOAT,
    diversity_score   FLOAT,                 -- 种群多样性
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- 策略生命周期
CREATE TABLE strategy_lifecycle (
    id                      SERIAL PRIMARY KEY,
    strategy_id             INTEGER REFERENCES strategies(id) UNIQUE,
    source                  VARCHAR(20) NOT NULL,  -- manual / evolved
    evolution_run_id        INTEGER REFERENCES strategy_evolution_runs(id),
    status                  VARCHAR(20) NOT NULL,  -- active / paper_trading / degraded / retired
    in_sample_metrics       JSONB,
    out_of_sample_metrics   JSONB,
    walk_forward_metrics    JSONB,
    last_evaluated_at       TIMESTAMPTZ,
    performance_trend       VARCHAR(20),           -- improving / stable / declining
    decay_score             FLOAT,                 -- 0=no decay, 1=fully decayed
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.3 数据流

```
用户触发 (chat 或 API) 或 Scheduler 定时任务
    │
    ▼
StrategyEvolutionAgent.run(query)
    │
    ├─[1] 解析意图：品种池、周期、进化配置
    │      └─ resolve_symbols() + 默认配置合并
    │
    ├─[2] 数据前置检查
    │      └─ DataCatalogService — K 线覆盖 + 质量
    │
    ├─[3] 市场状态识别
    │      └─ evolution/market_regime.py
    │         输入：OHLCV DataFrame
    │         输出：regime label + confidence
    │         (trending_up / trending_down / range_bound /
    │          high_vol / low_vol / breakout)
    │
    ├─[4] 因子自动发现
    │      └─ evolution/factor_discovery.py
    │         ├─ 模板生成：预设因子模板 + 参数采样 → 100-200 个
    │         ├─ 遗传编程：随机组合 DSL 算子 → 50-100 个
    │         └─ 评估过滤：IC + Rank IC → 保留 Top-20
    │
    ├─[5] 策略种群初始化
    │      └─ evolution/strategy_population.py
    │         将 Top 因子组合为完整的 entry/exit/risk DSL
    │         种群大小：默认 50，可配置
    │
    ├─[6] 进化循环 (N 代)
    │    │
    │    ├─[6a] 回测评估（并行）
    │    │   └─ run_dsl_backtest() × population_size
    │    │      每笔回测 < 100ms，50 个约 5s
    │    │
    │    ├─[6b] 适应度计算
    │    │   └─ evolution/fitness.py
    │    │      multi_objective_fitness(backtest_result, regime)
    │    │
    │    ├─[6c] 选择
    │    │   └─ tournament_selection(population, k=3)
    │    │
    │    ├─[6d] 交叉 + 变异
    │    │   └─ evolution/genetic_operators.py
    │    │      crossover(parent_a, parent_b) → 2 children
    │    │      mutate(child) → 轻微变化
    │    │
    │    └─[6e] 精英保留
    │        └─ 保留 Top-5 直接进入下一代
    │
    ├─[7] 最终评估
    │    ├─ 样本外 (out-of-sample) 验证
    │    ├─  Walk-forward 分析
    │    └─ 跨品种鲁棒性检验
    │
    ├─[8] 策略生命周期更新
    │    └─ evolution/strategy_lifecycle.py
    │       比较新旧策略，标记退化策略
    │
    └─[9] 报告生成
         └─ Markdown 报告 + 结构化 data
```

---

## 4. 核心模块详细设计

### 4.1 Market Regime Detection（市场状态识别）

**文件**：`python/services/agent/evolution/market_regime.py`

**目的**：在生成策略前识别市场状态，让策略能够适配不同环境，也为适应度评估提供上下文。

**实现**：纯 numpy/pandas，无 LLM 依赖。

```python
@dataclass
class MarketRegime:
    regime: str          # trending_up / trending_down / range_bound /
                         # high_volatility / low_volatility / breakout
    confidence: float    # 0-1
    metrics: dict        # 详细指标

def detect_regime(df: pd.DataFrame) -> MarketRegime:
    """基于多维度指标识别市场状态"""
    # 1. 趋势强度：ADX (14)
    adx = compute_adx(df, 14)
    
    # 2. 趋势方向：MA 斜率 (20, 60)
    ma20_slope = linear_slope(df.close.rolling(20).mean(), 5)
    ma60_slope = linear_slope(df.close.rolling(60).mean(), 10)
    
    # 3. 波动率：ATR / close 百分位 (252 天)
    atr_pct = compute_atr(df, 14) / df.close
    vol_percentile = atr_pct.rank(pct=True).iloc[-1]
    
    # 4. 区间化程度：Bollinger 带宽百分位
    bb_width = (boll_upper - boll_lower) / boll_mid
    bb_percentile = bb_width.rank(pct=True).iloc[-1]
    
    # 5. Hurst 指数（趋势持续性）
    hurst = compute_hurst(df.close, max_lag=20)
    
    # 综合判断
    ...
```

**用途**：
- 策略生成时：限制搜索空间（如震荡市偏向均值回归策略）
- 适应度评估时：同状态下的回测结果更具可比性
- 生命周期跟踪时：检测策略是否因市场状态切换而失效

### 4.2 Factor Auto-Discovery（因子自动发现）

**文件**：`python/services/agent/evolution/factor_discovery.py`

**目的**：自动生成和筛选具有预测能力的因子公式，作为策略的构建块。

**双重策略**：

#### A. 模板生成（覆盖已知有效模式）

```python
FACTOR_TEMPLATES = [
    # 动量类
    ("close / ts_delay(close, {lookback}) - 1", {"lookback": [1,3,5,10,20,60]}),
    ("ts_mean(close, {fast}) / ts_mean(close, {slow}) - 1", 
     {"fast": [3,5,10], "slow": [10,20,60]}),
    ("ts_delta(close, {lookback}) / ts_std(close, {lookback})", 
     {"lookback": [10,20]}),
    
    # 波动率类
    ("ts_std(close, {window}) / ts_mean(close, {window})", 
     {"window": [5,10,20,60]}),
    ("(high - low) / ts_mean(close, {window})", 
     {"window": [5,10,20]}),
    
    # 量价关系
    ("volume / ts_mean(volume, {window}) - 1", 
     {"window": [5,20,60]}),
    ("ts_corr(close, volume, {window})", 
     {"window": [10,20,60]}),
    
    # 反转类
    ("-1 * (close / ts_delay(close, {lookback}) - 1)", 
     {"lookback": [1,3,5]}),
    ("-1 * ts_zscore(close, {window})", 
     {"window": [5,10,20]}),
    
    # 突破类
    ("close / ts_max(high, {window}) - 1", 
     {"window": [10,20,60,120]}),
    ("close / ts_min(low, {window}) - 1", 
     {"window": [10,20,60,120]}),
    
    # 复合类
    ("ts_mean(close, {fast}) / ts_mean(close, {slow}) * ts_std(volume, {vol_window})", 
     {"fast": [5,10], "slow": [20,60], "vol_window": [5,20]}),
]
```

#### B. 遗传编程（探索新颖组合）

复用现有 `factor_engine/dsl.py` 的 28 个算子，进行遗传编程：

```python
# 算子分为终结符和函数
TERMINALS = ['open', 'high', 'low', 'close', 'volume']

FUNCTIONS = {
    # 一元函数
    'unary': ['ts_delay', 'ts_delta', 'ts_mean', 'ts_std', 'ts_rank', 
              'ts_zscore', 'ts_max', 'ts_min', 'rank', 'zscore', 
              'abs', 'log', 'sqrt', 'sign', 'ts_skew', 'ts_kurt'],
    # 二元函数
    'binary': ['ts_corr', 'ts_cov', 'ts_regression_beta'],
    # 算术运算
    'arithmetic': ['+', '-', '*', '/'],
}

def generate_random_factor(depth: int = 3) -> str:
    """随机生成一棵表达式树，返回合法因子公式"""
    ...

def mutate_factor(formula: str) -> str:
    """对因子公式进行变异：替换算子/参数/子树"""
    ...
```

**因子筛选流水线**：

```
生成 200-300 个候选因子
    ↓
validate_factor_formula() 安全校验（排除 5-10% 非法公式）
    ↓
load_panel_data() 加载面板数据
    ↓
evaluate_factor() 求值
    ↓
evaluate_factor_performance() — IC / Rank IC
    ↓
过滤：|Rank IC| > 0.02 且 ICIR > 0.3
    ↓
去重：因子间相关性 < 0.7
    ↓
Top-20 因子进入策略构建池
```

### 4.3 Strategy Population（策略种群）

**文件**：`python/services/agent/evolution/strategy_population.py`

**目的**：将因子组合为完整的可回测策略 DSL。

```python
@dataclass
class StrategyIndividual:
    """种群中的一个策略个体"""
    id: str                          # 唯一标识
    dsl: dict                        # StrategyDSL.to_dict()
    fitness: float | None = None     # 适应度评分
    backtest_result: dict | None = None
    generation: int = 0
    parent_ids: list[str] = []       # 谱系追踪
    mutation_history: list[str] = [] # 变异历史

def initialize_population(
    factors: list[FactorCandidate],
    symbol: str,
    timeframe: str,
    population_size: int = 50,
    direction: str = "long",
) -> list[StrategyIndividual]:
    """从因子池初始化策略种群。
    
    每个策略 = 入场条件（1-3 个因子） + 出场条件（1-2 个因子） + 风控参数
    """
```

**策略编码**（基因型 → 表现型）：

```
Gene (编码):
{
  "entry_signals": [
    {"factor": "ts_rank(close, 20)", "threshold": 0.8, "direction": "above"},
    {"factor": "volume / ts_mean(volume, 20)", "threshold": 1.5, "direction": "above"}
  ],
  "entry_logic": "and",          # and | or
  "exit_signals": [
    {"factor": "close / ts_mean(close, 10)", "threshold": 0.95, "direction": "below"}
  ],
  "exit_logic": "and",
  "stop_loss_atr_mult": 2.0,
  "take_profit_rr_ratio": 2.0,
  "position_size_pct": 0.2
}

↓ StrategyCompilerAgent.transpile() ↓

Phenotype (Strategy DSL):
{
  "name": "auto-evolved-strategy-abc123",
  "universe": ["RB"],
  "timeframe": "1d",
  "direction": "long",
  "entry": {
    "conditions": [...],  # 从因子转换的标准 DSL 条件
    "logic": "and"
  },
  "exit": {
    "conditions": [...],
    "logic": "and"
  },
  "risk": {
    "stop_loss": {"type": "atr_multiple", "value": 2.0},
    "take_profit": {"type": "risk_reward_ratio", "value": 2.0}
  }
}
```

关键点：因子不是直接作为 DSL condition（因为 DSL 的 indicator 白名单有限）。需要扩展 `_compute_indicator()` 支持因子值的预计算列，或者在回测时将因子值作为自定义序列注入。

**方案**：扩展 `run_dsl_backtest()` 支持 `custom_columns` 参数：

```python
def run_dsl_backtest(
    ...,
    custom_columns: dict[str, pd.Series] | None = None,
):
    """custom_columns 允许注入预计算的因子序列作为条件中的 indicator 引用"""
```

### 4.4 Genetic Operators（遗传算子）

**文件**：`python/services/agent/evolution/genetic_operators.py`

#### 选择算子

```python
def tournament_selection(
    population: list[StrategyIndividual],
    tournament_size: int = 3,
) -> StrategyIndividual:
    """锦标赛选择：随机选 k 个，返回适应度最高的"""
    tournament = random.sample(population, min(tournament_size, len(population)))
    return max(tournament, key=lambda x: x.fitness or -float('inf'))

def roulette_selection(
    population: list[StrategyIndividual],
) -> StrategyIndividual:
    """轮盘赌选择（适应度比例）"""
    fitnesses = [max(ind.fitness or 0, 0.001) for ind in population]
    total = sum(fitnesses)
    probs = [f / total for f in fitnesses]
    return random.choices(population, weights=probs, k=1)[0]
```

#### 交叉算子

```python
def crossover(
    parent_a: StrategyIndividual,
    parent_b: StrategyIndividual,
) -> tuple[StrategyIndividual, StrategyIndividual]:
    """策略交叉：交换入场/出场条件或风控参数"""
    child_a_dsl = copy.deepcopy(parent_a.dsl)
    child_b_dsl = copy.deepcopy(parent_b.dsl)
    
    # 随机选择交叉点
    crossover_point = random.choice([
        'entry_conditions',   # 交换入场条件
        'exit_conditions',    # 交换出场条件
        'risk_params',        # 交换风控参数
        'entry_logic',        # 交换逻辑门
    ])
    
    if crossover_point == 'entry_conditions':
        # 交换部分入场条件
        ...
    elif crossover_point == 'exit_conditions':
        # 交换出场条件
        ...
    elif crossover_point == 'risk_params':
        # 交换止损/止盈/仓位设置
        ...
    
    return (StrategyIndividual(dsl=child_a_dsl, parent_ids=[parent_a.id, parent_b.id]),
            StrategyIndividual(dsl=child_b_dsl, parent_ids=[parent_a.id, parent_b.id]))
```

#### 变异算子

```python
MUTATION_TYPES = [
    'change_threshold',     # 因子阈值微调 ±10-30%
    'swap_factor',          # 替换一个因子（从因子池中取）
    'add_condition',        # 添加一个入场/出场条件
    'remove_condition',     # 移除一个条件（若 >1 个）
    'change_logic',         # AND ↔ OR 切换
    'adjust_stop_loss',     # 止损倍数微调
    'adjust_take_profit',   # 止盈倍数微调
    'change_timeframe',     # 周期切换
    'simplify',             # 删除冗余条件
]

def mutate(
    individual: StrategyIndividual,
    factor_pool: list[FactorCandidate],
    mutation_rate: float = 0.3,
    mutation_strength: float = 0.1,
) -> StrategyIndividual:
    """对策略个体进行变异。
    
    mutation_rate: 每个变异操作的发生概率
    mutation_strength: 参数变异的幅度（如阈值的 ±10% 调整）
    """
```

### 4.5 Multi-Dimensional Fitness（多维适应度）

**文件**：`python/services/agent/evolution/fitness.py`

**目的**：防止单指标（如总收益）导致的过拟合。综合多维度评估策略质量。

```python
@dataclass
class FitnessScore:
    total: float                    # 综合评分 0-100
    components: dict[str, float]    # 各维度得分
    weights: dict[str, float]       # 各维度权重

def multi_objective_fitness(
    backtest_result: dict,
    out_of_sample_result: dict | None = None,
    regime: MarketRegime | None = None,
    complexity: int = 1,  # DSL 条件数量
    config: dict | None = None,
) -> FitnessScore:
    """多维适应度评分
    
    维度：
    1. 风险调整收益 (30%) — Sharpe, Calmar
    2. 稳定性 (25%) — 样本内外一致性, 逐年收益标准差
    3. 交易质量 (20%) — 胜率, 盈亏比, 交易频率合理性
    4. 鲁棒性 (15%) — 跨品种/跨参数敏感性
    5. 简洁性 (10%) — 条件数惩罚（奥卡姆剃刀）
    """
    components = {}
    
    # 1. 风险调整收益
    sharpe = backtest_result['metrics']['sharpe']
    calmar = backtest_result['metrics']['annualized_return_pct'] / max(
        backtest_result['metrics']['max_drawdown_pct'], 0.1)
    components['risk_adj_return'] = min(max(sharpe * 10 + calmar * 0.5, 0), 100)
    
    # 2. 稳定性
    if out_of_sample_result:
        oos_return = out_of_sample_result['metrics']['total_return_pct']
        is_return = backtest_result['metrics']['total_return_pct']
        # 样本内外收益比值（OOS/IS），越接近 1 越好
        consistency = 1.0 - abs(oos_return - is_return) / max(abs(is_return), 1.0)
        components['stability'] = max(min(consistency * 100, 100), 0)
    else:
        components['stability'] = 50  # 无 OOS 数据时中性
    
    # 3. 交易质量
    win_rate = backtest_result['metrics']['win_rate_pct']
    profit_factor = backtest_result['metrics']['profit_factor']
    trade_count = backtest_result['metrics']['trade_count']
    # 交易太少 = 过拟合嫌疑；太多 = 噪音交易
    trade_count_score = 30 if trade_count < 3 else (
        100 if 5 <= trade_count <= 100 else max(100 - (trade_count - 100) * 0.5, 20))
    components['trade_quality'] = (
        win_rate * 0.3 + min(profit_factor * 15, 40) + trade_count_score * 0.3)
    
    # 4. 鲁棒性（参数敏感性）
    # 通过小幅参数扰动后回测结果的方差来衡量
    components['robustness'] = ...  # 需要在进化结束后计算
    
    # 5. 简洁性（条件数量惩罚）
    complexity_penalty = max(0, (complexity - 3) * 5)
    components['simplicity'] = max(100 - complexity_penalty, 0)
    
    # 加权总和
    weights = config.get('fitness_weights', {
        'risk_adj_return': 0.30,
        'stability': 0.25,
        'trade_quality': 0.20,
        'robustness': 0.15,
        'simplicity': 0.10,
    })
    
    total = sum(components[k] * weights[k] for k in weights)
    
    return FitnessScore(total=round(total, 2), components=components, weights=weights)
```

### 4.6 Strategy Lifecycle（策略生命周期）

**文件**：`python/services/agent/evolution/strategy_lifecycle.py`

**目的**：策略不是一次性产物。持续跟踪策略表现，检测退化，自动推荐退役或更新。

```python
class StrategyLifecycleManager:
    """策略生命周期管理器"""
    
    def register_strategy(self, strategy_id: int, backtest_result: dict, 
                          source: str, evolution_run_id: int = None):
        """注册新策略（人工创建或进化生成）"""
    
    def evaluate_decay(self, strategy_id: int) -> dict:
        """评估策略退化程度。
        
        比较最近 N 根 K 线的表现与历史回测表现：
        - 如果近 20 日信号频率显著下降 → 市场状态变化
        - 如果近 20 日模拟收益为负且持续 → 策略失效
        - 滚动窗口 Sharpe 趋势向下 → 退化预警
        """
    
    def recommend_action(self, strategy_id: int) -> str:
        """推荐动作：keep / paper_trade / re_optimize / retire"""
    
    def compare_strategies(self, strategy_ids: list[int]) -> dict:
        """多策略对比：相关性、互补性、组合建议"""
```

**退化检测逻辑**：

```python
def detect_decay(strategy_id: int, recent_window: int = 20) -> dict:
    """检测策略是否退化"""
    # 1. 获取策略定义
    # 2. 在最近 N 根 K 线上模拟信号
    # 3. 计算滚动窗口指标
    # 4. 与历史回测指标对比
    # 5. 返回退化评分 (0=健康, 1=完全失效)
    
    decay_signals = []
    
    # 信号频率下降 > 50%
    if recent_signal_count < historical_avg_signal_count * 0.5:
        decay_signals.append("信号频率显著下降")
    
    # 滚动 Sharpe < 0 持续超过 2 个窗口
    if rolling_sharpe_trend == "declining" and recent_sharpe < 0:
        decay_signals.append("滚动 Sharpe 持续为负")
    
    # 盈亏比恶化 > 30%
    if recent_profit_factor < historical_profit_factor * 0.7:
        decay_signals.append("盈亏比显著恶化")
    
    decay_score = len(decay_signals) / 3  # 0-1
    return {
        "decay_score": decay_score,
        "signals": decay_signals,
        "recommendation": "retire" if decay_score > 0.66 
                     else "re_optimize" if decay_score > 0.33 
                     else "keep"
    }
```

---

## 5. Agent 接口设计

### 5.1 StrategyEvolutionAgent

```python
class StrategyEvolutionAgent(Agent):
    """自进化策略发现 Agent。
    
    从价格数据中自动生成和进化交易策略。
    支持单品种深度优化和跨品种泛化验证。
    """
    
    name = "strategy_evolution"
    description = "自进化策略引擎：自动从价格变化中发现、进化、优化交易策略"
    
    async def run(self, query: str) -> AgentResult:
        """执行自进化策略发现。
        
        用户查询示例：
        - "为螺纹钢日线自动发现策略，进化 10 代"
        - "分析 AU 近一年的价格特征，找出最优均线策略"
        - "批量优化黑色系所有品种的策略参数"
        """
```

### 5.2 用户交互示例

**触发方式 1：Chat 界面**

```
用户：帮我为螺纹钢日线自动发现交易策略，进化 20 代，种群 50 个

Agent：
## 策略进化报告 — RB (螺纹钢) 日线

### 市场状态
- 当前状态：趋势上行（置信度 0.82）
- ADX: 28.5 | 波动率百分位: 62% | Hurst: 0.61

### 进化过程
- 代数：20 | 种群大小：50 | 总评估次数：1000
- 初始最优适应度：42.3 → 最终最优适应度：78.6 (+85.8%)
- 种群多样性：0.34（健康）

### 最优策略
**RB-动量突破-止损追踪-v3**
- 方向：做多
- 入场：ts_rank(close, 20) > 0.85 AND volume > ts_mean(volume, 20) × 1.5
- 出场：close < ts_mean(close, 10) × 0.95
- 止损：2.0x ATR | 止盈：1:2.5 风险收益比
- 仓位：单次 20%

### 回测表现
| 指标 | 样本内 (2024) | 样本外 (2025 Q1-Q2) |
|------|-------------|-------------------|
| 年化收益 | +32.5% | +24.1% |
| 最大回撤 | -8.2% | -10.5% |
| Sharpe | 1.85 | 1.42 |
| 胜率 | 48.3% | 44.1% |
| 盈亏比 | 2.8 | 2.4 |
| 交易次数 | 23 | 11 |

### 适应性分析
- 趋势上行环境：优秀（Sharpe 2.1）
- 震荡环境：一般（Sharpe 0.3）
- 高波动环境：回撤放大（-12% → 建议缩小仓位至 15%）

### 退化风险
- 当前状态：健康
- 样本外一致性：良好（OOS/IS = 0.74）

> ⚠️ 以上策略由算法自动生成，存在过拟合风险。建议先在模拟环境跟踪 2-4 周再考虑实盘。
```

**触发方式 2：定时任务**

```python
# Scheduler 集成：每周六凌晨 3:00 自动进化
# python/data_collector/scheduler.py
async def weekly_strategy_evolution():
    """周末自动运行所有活跃品种的策略进化"""
    active_varieties = await get_active_varieties()
    for variety in active_varieties[:10]:  # Top-10 活跃品种
        agent = StrategyEvolutionAgent(context)
        await agent.run(f"为 {variety.symbol} 自动进化策略：世代数=10 种群=30")
```

---

## 6. 实现路线图

### Phase 1：基础进化循环（预计 2 周）

**目标**：跑通 generate → backtest → evaluate → evolve 的最小闭环。

| 任务 | 文件 | 工作量 |
|------|------|--------|
| Market Regime Detection | `evolution/market_regime.py` | 2 天 |
| Factor Auto-Discovery（仅模板生成） | `evolution/factor_discovery.py` | 2 天 |
| Strategy Population | `evolution/strategy_population.py` | 1 天 |
| 扩展 `run_dsl_backtest` 支持 custom_columns | `services/backtest/service.py` | 1 天 |
| 简单 GA（tournament + threshold mutate） | `evolution/genetic_operators.py` | 1 天 |
| 单目标适应度 | `evolution/fitness.py` | 1 天 |
| StrategyEvolutionAgent 主流程 + 集成 | `strategy_evolution_agent.py` | 2 天 |
| Alembic 迁移 | `alembic/versions/` | 0.5 天 |
| pytest | `tests/test_strategy_evolution_agent.py` | 2 天 |

**Phase 1 交付物**：
- 从命令行/API 触发 `POST /api/agents/tasks` with `agent_type=strategy_evolution`
- 最小进化：10 代 × 30 种群 = 300 次回测，约 30 秒完成
- SSE 流式展示每代最优适应度
- 生成最优策略 DSL 并自动创建 `StrategyDB` 记录

### Phase 2：进化引擎增强（预计 2 周）

**目标**：完整遗传算法 + 多维适应度 + 样本外验证。

| 任务 | 文件 | 工作量 |
|------|------|--------|
| 遗传编程因子生成 | `evolution/factor_discovery.py`（GP 部分） | 3 天 |
| 完整遗传算子（交叉 + 多类型变异） | `evolution/genetic_operators.py` | 2 天 |
| 多维适应度评分 | `evolution/fitness.py` | 2 天 |
| 样本外 + Walk-forward 验证 | `evolution/fitness.py` | 2 天 |
| 精英保留 + 多样性维护 | `evolution/strategy_population.py` | 1 天 |
| 贝叶斯优化参数精调 | `evolution/genetic_operators.py` | 2 天 |
| pytest | 持续 | 2 天 |

**Phase 2 交付物**：
- 完整的遗传算法：选择/交叉/变异/精英保留
- 遗传编程因子生成
- 样本内外分离验证
- 参数敏感性分析

### Phase 3：生命周期与前端（预计 1 周）

**目标**：策略持续跟踪 + 前端可视化。

| 任务 | 文件 | 工作量 |
|------|------|--------|
| Strategy Lifecycle Manager | `evolution/strategy_lifecycle.py` | 2 天 |
| 退化检测 + 自动预警 | `evolution/strategy_lifecycle.py` | 1 天 |
| Scheduler 集成（周末自动进化） | `data_collector/scheduler.py` | 1 天 |
| 前端进化仪表盘 | `frontend/app/strategies/evolution/` | 2 天 |
| 前端进化报告组件 | `frontend/components/agent/EvolutionReportCard.tsx` | 1 天 |
| E2E 测试 | `tests/` | 1 天 |

---

## 7. 关键风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| **过拟合**：进化出的策略在样本外失效 | 高 | 高 | OOS 验证、walk-forward、简洁性惩罚、跨品种鲁棒性检验 |
| **计算成本**：大量回测耗时过长 | 中 | 中 | 向量化回测（每笔 < 100ms）、并行评估、缓存 K 线数据、限时截断 |
| **搜索空间爆炸**：因子组合数过大 | 中 | 中 | 因子预筛选（IC 过滤）、模板引导、种群大小限制 |
| **策略同质化**：种群收敛到相似策略 | 中 | 中 | 多样性维护（novelty score）、显式去重、因子相关性过滤 |
| **数据质量**：K 线不足导致回测不可靠 | 低 | 高 | 前置 DataCatalog 检查、最少 100 根 K 线要求 |
| **市场状态切换**：策略在新环境下失效 | 高 | 中 | Market regime 标记 + 多状态回测 + 适应性评分 |

---

## 8. 与现有系统的集成点

| 现有模块 | 集成方式 |
|----------|----------|
| `Agent` 基类 | `StrategyEvolutionAgent(Agent)` 继承，复用 `run()` / `run_stream()` / `AgentResult` |
| `AgentExecutor` | 复用任务生命周期管理、SSE 流式发射 |
| `DataCatalogService` | 数据前置检查、K 线覆盖验证 |
| `factor_engine/dsl.py` | `validate_factor_formula()` + `evaluate_factor()` 用于因子安全校验和求值 |
| `factor_engine/evaluator.py` | `evaluate_factor_performance()` 用于因子预筛选 |
| `factor_engine/data_loader.py` | `load_panel_data()` 用于因子计算 |
| `services/backtest/engine.py` | `run_backtest()` + `_eval_conditions()` 用于策略回测 |
| `services/backtest/service.py` | `run_dsl_backtest()` 作为回测入口 |
| `services/backtest/optimization_engine.py` | `optimize_strategy_params()` 用于进化后的参数精调 |
| `strategy_compiler_agent.py` | `StrategyValidator.validate()` 用于校验进化生成的 DSL |
| `lib/technical_indicators.py` | 现有指标库用于 Market Regime Detection |
| `StrategyDB` / `BacktestRunDB` | 持久化进化产物 |
| `FactorDefinitionDB` | 持久化发现的因子 |
| `routers/agents.py` | 注册 `strategy_evolution` 为新的 agent_type |
| `routers/strategies.py` | 扩展 API 支持 evolution 触发和结果查询 |

---

## 9. 扩展方向（远期）

1. **强化学习精调**：GA 产出的策略作为初始策略，用 RL（PPO/DQN）在模拟器中精调出场时机
2. **多品种策略组合**：进化产出多个不相关策略，自动构建策略组合（MDP 或风险平价）
3. **迁移学习**：在一个品种上进化出的好策略，自动适配到相关性高的品种上
4. **对抗训练**：生成对抗性的市场情景（极端波动、流动性枯竭）来测试策略鲁棒性
5. **自然语言解释**：用 LLM 将进化出的 DSL 翻译成交易员能理解的策略描述
6. **Auto-Keras 混合**：对于因子权重学习，引入轻量神经网络替代线性组合
