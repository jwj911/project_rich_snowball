# 自进化策略 Agent — 架构设计文档

> **状态**：Phase 1-3 已完成 ✅ | **日期**：2026-07-05 | **作者**：AI Agent

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
│   ├── factor_discovery.py        # 因子自动发现（模板 + 遗传编程）
│   ├── strategy_population.py     # 策略种群管理
│   ├── genetic_operators.py       # 选择/交叉/变异算子
│   ├── fitness.py                 # 多维适应度评分（标量 + NSGA-II Pareto）
│   ├── bayesian_optimizer.py      # 贝叶斯优化参数精调（sklearn GP + EI）
│   └── strategy_lifecycle.py      # 策略生命周期跟踪（✅ Phase 3）
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
    │         ├─ 模板生成：预设因子模板 + 参数采样 → 约 80 个
    │         ├─ 遗传编程（可选）：随机表达式树 + 交叉/变异进化 → 50-100 个
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
    │    │      compute_fitness() (标量加权) 或 compute_pareto_fitness() (NSGA-II)
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
    │    ├─ 贝叶斯优化参数精调（可选）
    │    └─ Walk-forward 分析（✅ Phase 3 — DB 字段 + schema 已就绪，Walk-forward 分析逻辑待后续补充）
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
GP_TERMINALS = ['open', 'high', 'low', 'close', 'volume']

GP_UNARY_TS = [
    # (函数名, 候选窗口参数) — 14 个一元时间序列函数
    ("ts_delay",  [1, 3, 5, 10, 20, 60]),
    ("ts_delta",  [3, 5, 10, 20, 60]),
    ("ts_mean",   [3, 5, 10, 20, 60, 120]),
    ("ts_std",    [5, 10, 20, 60]),
    ("ts_rank",   [5, 10, 20, 60]),
    ("ts_zscore", [5, 10, 20, 60]),
    ("ts_max",    [5, 10, 20, 60, 120]),
    ("ts_min",    [5, 10, 20, 60, 120]),
    ("ts_skew",   [10, 20, 60]),
    ("ts_kurt",   [10, 20, 60]),
    ("ts_rank_pct", [5, 10, 20, 60]),
    ("ts_mad",    [5, 10, 20, 60]),
    ("ts_sum",    [5, 10, 20]),
    ("ts_median", [5, 10, 20, 60]),
]

GP_UNARY_NOPARAM = ["abs", "log", "sqrt", "sign", "rank", "zscore"]

GP_BINARY_TS = [
    ("ts_corr", [10, 20, 60]),
    ("ts_cov",  [10, 20, 60]),
    ("ts_regression_beta", [20, 60]),
]

GP_ARITHMETIC = ["+", "-", "*", "/"]

def generate_random_factor(max_depth: int = 3) -> str:
    """随机生成一棵表达式树，返回合法因子公式。
    
    depth=1: 终结符 或 简单一元函数调用
    depth=2: 一元嵌套 或 二元运算
    depth=3: 复杂嵌套表达式
    """

def crossover_factor_formula(formula_a: str, formula_b: str) -> str | None:
    """因子公式交叉：交换两个公式中的数值参数。"""

def mutate_factor_formula(formula: str, mutation_strength: float = 0.3) -> str | None:
    """因子公式变异，四种类型：
    - param: 窗口参数微调（±比例步长）
    - function: 一元函数名替换
    - terminal: 终结符替换
    - wrap_unary: 添加/移除一元包装
    """

def evolve_factor_pool(
    template_factors, n_gp=80, gp_generations=3,
    population_size=40, crossover_rate=0.7, mutation_rate=0.3,
) -> list[FactorCandidate]:
    """GP 进化合并：随机生成 → 选择 → 交叉 → 变异 × N 代 → 与模板因子去重合并"""
```

**因子筛选流水线**：

```
模板生成：14 个模板 × 参数组合 → 约 80 个候选因子
    ↓
[可选] GP 生成：随机表达式树 + 交叉/变异进化 × 3 代 → 50-100 个
    ↓
模板 + GP 合并去重
    ↓
validate_factor_formula() 安全校验（在生成阶段已校验）
    ↓
load_panel_data() 加载面板数据
    ↓
evaluate_factor() 求值
    ↓
evaluate_factor_performance() — IC / Rank IC
    ↓
过滤：|Rank IC| > 0.02（多品种模式）
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
    uid: str                         # 唯一标识
    entry_conditions: list[dict]     # 入场条件（DSL format）
    entry_logic: str                 # and | or
    exit_conditions: list[dict]      # 出场条件
    exit_logic: str                  # and | or
    risk: dict                       # 风控参数
    direction: str                   # long | short
    timeframe: str                   # 周期
    source_factors: list[str]        # 来源因子公式列表
    generation: int = 0              # 所属代数
    parent_uids: list[str] = []      # 谱系追踪
    fitness: float | None = None     # 适应度评分
    fitness_components: dict = {}    # 各维度得分
    backtest_result: dict | None = None

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

**策略编码**（基因型，直接存储在 StrategyIndividual 字段中）：

```
Entry Conditions (DSL-compatible):
[
  {"indicator": "factor_custom:<md5hash>", "operator": "greater_than", "value": 0.5},
  {"indicator": "factor_custom:<md5hash>", "operator": "less_than", "value": -0.3}
]

↓ StrategyIndividual.to_dsl() ↓

Phenotype (Strategy DSL):
{
  "name": "auto-evolved-strategy-abc123",
  "universe": ["RB"],
  "timeframe": "1d",
  "direction": "long",
  "entry": {
    "conditions": [
      {"indicator": "factor_custom:abc123def456", "operator": "greater_than", "value": 0.5}
    ],
    "logic": "and"
  },
  "exit": {
    "conditions": [
      {"indicator": "close", "operator": "cross_below", "indicator2": "sma10"}
    ],
    "logic": "and"
  },
  "risk": {
    "stop_loss": {"type": "atr_multiple", "value": 2.0},
    "take_profit": {"type": "risk_reward_ratio", "value": 2.0},
    "position_size": {"type": "fixed_lots", "value": 1}
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
def tournament_select(
    population: list[StrategyIndividual],
    tournament_size: int = 3,
) -> StrategyIndividual:
    """锦标赛选择：随机选 k 个，返回适应度最高的"""
    k = min(tournament_size, len(population))
    contestants = random.sample(population, k)
    return max(contestants, key=lambda ind: ind.fitness or -float('inf'))
```

#### 交叉算子

```python
def crossover(
    parent_a: StrategyIndividual,
    parent_b: StrategyIndividual,
) -> tuple[StrategyIndividual, StrategyIndividual]:
    """策略交叉：随机选择交叉点交换基因。
    
    四种交叉点（等概率）：
    - entry: 交换一个入场条件
    - exit: 交换一个出场条件
    - risk: 交换全部风控参数
    - logic: 交换逻辑门 (AND ↔ OR)
    """
```

#### 变异算子

```python
# 复合变异：按概率随机选择一种变异类型
# 有 factor_pool 时的概率分布：
#   35% — mutate_threshold (阈值微调)
#   25% — mutate_swap_factor (替换因子)
#   10% — mutate_add_condition (新增条件)
#   10% — mutate_remove_condition (删除条件)
#   10% — mutate_logic_switch (AND ↔ OR)
#   10% — mutate_adjust_risk (风控参数调整)
# 无 factor_pool 时：仅 threshold + logic_switch（Phase 1 兼容）

def mutate(
    individual: StrategyIndividual,
    mutation_strength: float = 0.15,
    factor_pool: list[FactorCandidate] | None = None,
) -> StrategyIndividual:
    """复合变异：随机选择一种变异类型执行。"""
```

#### 世代推进

```python
def next_generation(
    population: list[StrategyIndividual],
    elite_count: int = 5,
    mutation_rate: float = 0.3,
    mutation_strength: float = 0.15,
    crossover_rate: float = 0.7,
    factor_pool: list[FactorCandidate] | None = None,
    diversity_threshold: float = 0.35,
    fresh_blood_count: int = 3,
) -> list[StrategyIndividual]:
    """产生下一代种群。
    
    流程：
    1. 精英保留（Top-N 直接进入下一代）
    2. 剩余填充：选择两个父本 → 交叉(70%概率) → 变异(30%概率)
    3. 去重检查 + 多样性不足时注入新鲜血液
    """
```

### 4.5 Multi-Dimensional Fitness（多维适应度）

**文件**：`python/services/agent/evolution/fitness.py`

**目的**：防止单指标（如总收益）导致的过拟合。综合多维度评估策略质量。支持两种模式：标量加权（默认）和 NSGA-II Pareto 多目标排序（可选）。

#### A. 标量加权模式（`compute_fitness`）

```python
@dataclass
class FitnessScore:
    total: float                    # 综合评分 0-100
    components: dict[str, float]    # 各维度得分
    weights: dict[str, float]       # 各维度权重

_DEFAULT_WEIGHTS = {
    "sharpe":           0.30,  # Sharpe 比率
    "return_drawdown":  0.25,  # 收益回撤比（Calmar-like）
    "win_rate":         0.10,  # 胜率
    "profit_factor":    0.10,  # 盈亏比
    "trade_quality":    0.10,  # 交易数量合理性
    "simplicity":       0.15,  # 简洁性（条件数惩罚）
}

def compute_fitness(
    backtest_result: dict,
    condition_count: int = 1,
    weights: dict | None = None,
) -> FitnessScore:
    """标量加权适应度。
    
    各维度映射函数：
    - _sharpe_score(): 0→25, 1.5→75, 2.0→90, 3.0→100
    - _return_drawdown_score(): Calmar > 3 → 100
    - _win_rate_score(): 30%→30, 55%→80, 70%+→100
    - _profit_factor_score(): 1.0→20, 2.0→75, 3.0+→100
    - _trade_count_score(): <3→20, 5-30→100, >60→~50
    - _simplicity_score(): 1-2→100, 4→65, 6+→~15
    """
```

#### B. OOS 一致性模式（`compute_fitness_with_oos`）

```python
def compute_fitness_with_oos(
    is_backtest_result: dict,
    oos_backtest_result: dict | None,
    condition_count: int = 1,
    weights: dict | None = None,
    oos_consistency_weight: float = 0.25,
) -> FitnessScore:
    """在 IS 标量适应度的基础上，用 OOS Sharpe 一致性调整 stability 维度。
    
    stability = max(0, min(100, (oos_sharpe / is_sharpe) × 100))
    当 OOS 表现严重退化时，stability 分数被大幅压低。
    """
```

#### C. NSGA-II Pareto 模式（`compute_pareto_fitness`）— Phase 2B

```python
@dataclass
class ParetoFront:
    rank: int               # Pareto 层级（0=前沿）
    crowding_distance: float  # 拥挤距离

def _extract_multi_objectives(backtest_result: dict, condition_count: int) -> np.ndarray:
    """提取 6 维目标向量（均最大化）：
    [Sharpe, Calmar, WinRate, ProfitFactor, Simplicity, TradeQuality]
    """

def non_dominated_sort(objectives: list[np.ndarray]) -> list[int]:
    """NSGA-II 非支配排序。O(n²) 支配关系计算 → 迭代前沿构建。
    返回每个个体的 Pareto 层级（0=第1前沿，1=第2前沿，...）。
    """

def crowding_distance(
    objectives: list[np.ndarray], front_indices: list[int],
) -> dict[int, float]:
    """拥挤距离：各维度上相邻个体距离之和，边界点 = ∞。
    距离越大 → 个体越稀疏 → 被选中的概率越高。
    """

def pareto_selection(
    population, objectives: list[np.ndarray], n_select: int,
) -> list[int]:
    """NSGA-II 选择：按 Pareto 层级 → 拥挤距离选出 n_select 个个体。"""

def compute_pareto_fitness(
    backtest_results: list[dict], condition_counts: list[int],
) -> list[FitnessScore]:
    """基于 Pareto 排名的适应度：
    total = 100 - rank×20 + min(crowding_distance×5, 10)
    - 前沿个体（rank=0）: 100-110
    - 第二前沿（rank=1）: 80-90
    """
```

### 4.6 Bayesian Optimization（贝叶斯优化参数精调）— Phase 2B

**文件**：`python/services/agent/evolution/bayesian_optimizer.py`

**目的**：在 GA 产出最优策略后，对其连续参数（止损倍数、止盈倍数、仓位、因子阈值）进行贝叶斯优化精调，用更少的评估次数找到更优的参数组合。

**与网格搜索的区别**：网格搜索暴力枚举离散参数空间；贝叶斯优化使用 GP 建模目标函数，通过 Expected Improvement 智能采样，30-50 次迭代即可收敛。

```python
@dataclass
class BOParams:
    """贝叶斯优化参数向量，支持归一化编码。"""
    stop_loss_atr: float = 2.0
    take_profit_rr: float = 2.0
    position_size_pct: float = 0.2
    thresholds: list[float] = [0.5]

    def to_normalized(self) -> np.ndarray:
        """转换为 [0,1]^5 归一化向量。"""

class BayesianOptimizer:
    """贝叶斯优化器。
    
    GP 核 = ConstantKernel × RBF + Matern(nu=2.5) + WhiteKernel
    采集函数 = Expected Improvement (EI)
    """
    
    def __init__(
        self, n_dim=5, n_initial=10, n_iterations=30,
        exploration_xi=0.01, random_state=42,
    ):
        ...
    
    def optimize(self, objective_fn) -> tuple[np.ndarray, float, list[dict]]:
        """运行 BO：初始 LHS 采样 → 迭代 GP 拟合 + EI 最大化。"""

def _expected_improvement(x, gp, y_best, xi=0.01) -> float:
    """EI(x) = (μ - y_best - ξ)·Φ(Z) + σ·φ(Z), Z = (μ - y_best - ξ)/σ"""

def optimize_strategy_params_bayesian(
    backtest_fn,          # callable(params: dict) -> float
    initial_params: dict, # 初始参数字典
    n_iterations: int = 30,
    n_initial: int = 10,
) -> tuple[dict, float, list[dict]]:
    """策略参数贝叶斯优化高级封装。
    
    Returns: (最优参数字典, 最优适应度, 优化历史)
    """
```

**Agent 集成**：在进化完成 + OOS 验证后，如果 `use_bayesian_optimization=True`，自动对最优个体执行 BO 精调，优化完成后用新参数重新回测并更新报告。

### 4.7 Strategy Lifecycle（策略生命周期）— ✅ Phase 3

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
    
    async def run_stream(self, query: str) -> AsyncIterator[dict]:
        """流式执行进化过程，SSE 推送每代进度。"""
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

### Phase 1：基础进化循环 ✅ 已完成

**目标**：跑通 generate → backtest → evaluate → evolve 的最小闭环。

| 任务 | 文件 | 状态 |
|------|------|------|
| Market Regime Detection | `evolution/market_regime.py` | ✅ 完成 |
| Factor Auto-Discovery（仅模板生成） | `evolution/factor_discovery.py` | ✅ 完成 |
| Strategy Population | `evolution/strategy_population.py` | ✅ 完成 |
| 扩展 `run_dsl_backtest` 支持 custom_columns | `services/backtest/service.py` | ✅ 完成 |
| 简单 GA（tournament + threshold mutate） | `evolution/genetic_operators.py` | ✅ 完成 |
| 单目标适应度 | `evolution/fitness.py` | ✅ 完成 |
| StrategyEvolutionAgent 主流程 + 集成 | `strategy_evolution_agent.py` | ✅ 完成 |
| Alembic 迁移 | `alembic/versions/` | ✅ 完成（Phase 3 统一迁移 `0cdaf00da990`） |
| pytest | `tests/test_strategy_evolution_agent.py` | ✅ 39 个测试全部通过 |

**Phase 1 交付物**（全部已完成）：
- ✅ 从命令行/API 触发 `POST /api/agents/tasks` with `agent_type=strategy_evolution`
- ✅ 最小进化：10 代 × 40 种群 = 400 次回测，约 30 秒完成
- ✅ SSE 流式展示每代最优适应度
- ✅ 生成最优策略 DSL 并自动创建 `StrategyDB` 记录
- ✅ `routers/agents.py` 已注册 `strategy_evolution` agent_type

### Phase 2A：进化引擎增强（Sprint 2A） ✅ 已完成

**目标**：完整遗传算法（交叉 + 多类型变异）+ 样本外验证 + 多样性维护。

| 任务 | 文件 | 状态 |
|------|------|------|
| 日期区间 K 线数据访问（OOS 基础依赖） | `services/agent/data_tools.py`, `services/backtest/service.py`, `services/backtest/optimization_engine.py` | ✅ 完成 |
| 交叉算子 | `evolution/genetic_operators.py` — `crossover()` | ✅ 完成 |
| 多类型变异（swap/add/remove/risk） | `evolution/genetic_operators.py` — `mutate_swap_factor()`, `mutate_add_condition()`, `mutate_remove_condition()`, `mutate_adjust_risk()` | ✅ 完成 |
| 样本外 (OOS) 验证 | `evolution/fitness.py` — `compute_fitness_with_oos()`, `split_train_test_dates()` | ✅ 完成 |
| 去重 + 适应度共享 + 新鲜血液注入 | `evolution/strategy_population.py` — `deduplicate_population()`, `apply_fitness_sharing()`, `inject_fresh_blood()` | ✅ 完成 |
| 更新 `next_generation()` 集成交叉 + 多样性维护 | `evolution/genetic_operators.py` | ✅ 完成 |
| pytest（新增 22 个测试） | `tests/test_strategy_evolution_agent.py` | ✅ 61 个测试全部通过 |

**Phase 2A 交付物**：
- ✅ `_get_kline_data()` / `run_dsl_backtest()` / `optimize_strategy_params()` 支持 `start_date` / `end_date`，完全向后兼容
- ✅ 交叉算子支持 4 种交叉点（入场条件 / 出场条件 / 风控参数 / 逻辑门）
- ✅ 6 种变异类型（threshold / swap_factor / add_condition / remove_condition / logic_switch / adjust_risk）
- ✅ OOS 验证：进化完成后自动在 OOS 数据上评估最佳策略，报告展示 IS/OOS 对比
- ✅ 多样性维护：去重 + 适应度共享 + 多样性不足时自动注入新鲜个体
- ✅ 61 个测试（Phase 1 的 39 个 + 新增 22 个），全部通过

**关键实现细节**：
- `mutate()` 接受 `factor_pool` 参数 — 有因子池时使用丰富变异类型，无因子池时回退到 Phase 1 行为
- `next_generation()` 新增 `crossover_rate`（默认 0.7）和 `diversity_threshold`（默认 0.35）参数
- OOS 通过 `_DEFAULT_EVOLUTION_CONFIG["oos_split_ratio"]`（默认 0.3）配置；设为 0 可禁用
- 多样性维护仅在提供 `factor_pool` 时激活（无因子池时静默跳过，保持种群大小不变）

### Phase 2B：GP 因子生成 + Pareto 适应度 + 贝叶斯优化 ✅ 已完成

**目标**：遗传编程因子生成 + 多目标 Pareto 优化 + 参数精调。

| 任务 | 文件 | 状态 |
|------|------|------|
| 遗传编程因子生成（随机生成 + 交叉/变异 + 进化合并） | `evolution/factor_discovery.py` | ✅ 完成 |
| Pareto 多目标适应度（NSGA-II 风格非支配排序 + 拥挤距离选择） | `evolution/fitness.py` | ✅ 完成 |
| 贝叶斯优化参数精调（sklearn GP + Expected Improvement） | `evolution/bayesian_optimizer.py`（新文件） | ✅ 完成 |
| Agent 主流程集成（配置开关 + 报告） | `strategy_evolution_agent.py` | ✅ 完成 |
| pytest（新增 26 个测试） | `tests/test_strategy_evolution_agent.py` | ✅ 87 个测试全部通过 |

**Phase 2B 交付物**：
- ✅ 遗传编程因子生成：`generate_random_factor()` 表达式树随机生成（3 层深度）、`crossover_factor_formula()` 参数交换交叉、`mutate_factor_formula()` 4 种变异（param/function/terminal/wrap_unary）、`evolve_factor_pool()` GP 种群进化与模板合并
- ✅ NSGA-II Pareto 多目标适应度：`non_dominated_sort()` 非支配排序、`crowding_distance()` 拥挤距离、`pareto_selection()` 层级+距离选择、`compute_pareto_fitness()` 6 维目标评分（Sharpe/Calmar/WinRate/ProfitFactor/Simplicity/TradeQuality）
- ✅ 贝叶斯优化：`BayesianOptimizer` 类（sklearn GP + RBF×Matern×WhiteKernel + EI 采集函数）、`optimize_strategy_params_bayesian()` 高级封装
- ✅ Agent 主流程集成：`_evaluate_population()` 支持 `use_pareto_fitness` 调度、OOS 验证后可选 BO 精调、报告含 BO 结果
- ✅ 所有 Phase 2B 功能默认关闭（`use_gp_factors`/`use_pareto_fitness`/`use_bayesian_optimization`），完全向后兼容
- ✅ 87 个测试（Phase 2A 的 61 个 + 新增 26 个），全部通过

**关键实现细节**：
- GP 因子生成通过 `use_gp_factors=True` 启用，`gp_n_generate`（默认 80）控制初始生成量，`gp_generations`（默认 3）控制进化代数
- `non_dominated_sort()` 使用 O(n²) 支配关系比较 + 迭代前沿构建；`pareto_selection()` 按 rank → crowding_distance 优先级选择
- BO 的 GP 核 = ConstantKernel × RBF + Matern(nu=2.5) + WhiteKernel，采集函数 = Expected Improvement；默认 30 次迭代
- `optimize_strategy_params_bayesian()` 封装为高阶函数，接受 `backtest_fn(params) -> float` 签名，与现有回测引擎解耦
- Phase 2B 所有配置默认关闭，启用后对 Agent 主流程的性能影响：GP 增加 ~30% 因子发现时间，Pareto 适应度基本无额外开销，BO 增加 30-50 次额外回测

### Phase 3：生命周期与前端（预计 1 周）✅ 完成

**目标**：策略持续跟踪 + 前端可视化。

| 任务 | 文件 | 状态 |
|------|------|------|
| Strategy Lifecycle Manager（注册/衰减评估/行动推荐/对比/摘要） | `evolution/strategy_lifecycle.py` | ✅ 完成 |
| 退化检测 + 自动预警 | `evolution/strategy_lifecycle.py` — `detect_decay()`, `evaluate_decay()` | ✅ 完成 |
| Scheduler 集成（周末自动进化） | `data_collector/scheduler.py` + `job_registry.py` | ✅ 完成 |
| 数据库模型 + Alembic 迁移 | `models.py` + `alembic/versions/0cdaf00da990_*.py` | ✅ 完成 |
| 进化 API 路由 | `routers/evolution.py` | ✅ 完成 |
| 前端进化仪表盘 | `frontend/app/strategies/evolution/` | ✅ 完成 |
| 前端进化报告组件 | `frontend/components/agent/EvolutionReportCard.tsx` | ✅ 完成 |
| 前端 Chat 模式扩展 | `frontend/app/chat/page.tsx` — strategy_evolution ModeKey | ✅ 完成 |
| 前端 API Client 层 | `frontend/lib/api/evolution.ts`, `frontend/lib/api/types.ts` | ✅ 完成 |
| Agent 持久化集成 | `strategy_evolution_agent.py` — persist_to_db 配置 + 自动保存 | ✅ 完成 |
| 单元测试（生命周期） | `tests/test_strategy_lifecycle.py` — 20 个测试 | ✅ 完成 |
| 单元测试（DB 模型） | `tests/test_evolution_db_models.py` — 12 个测试 | ✅ 完成 |
| 集成测试（API 路由） | `tests/test_evolution_router.py` — 8 个测试 | ✅ 完成 |

---

## 6.1 实际完成进度

| 阶段 | 状态 | 测试数 | 日期 |
|------|------|--------|------|
| Phase 1 | ✅ 完成 | 39 | 2026-07-04 |
| Phase 2A | ✅ 完成 | 61 (+22) | 2026-07-05 |
| Phase 2B | ✅ 完成 | 87 (+26) | 2026-07-05 |
| Phase 3 | ✅ 完成 | 119 (+32) | 2026-07-05 |

**Phase 3 交付物详情**：

### 数据库层
- ✅ 3 个新 ORM 模型：`StrategyEvolutionRunDB`（进化运行记录）、`StrategyGenerationDB`（代际快照）、`StrategyLifecycleDB`（生命周期追踪）
- ✅ Alembic 迁移：`0cdaf00da990_add_strategy_evolution_lifecycle_tables.py`
- ✅ `StrategyDB` 新增 `lifecycle` relationship（1:1）
- ✅ `UserDB` 新增 `evolution_runs` relationship（1:N）

### 生命周期管理器 (`strategy_lifecycle.py`)
- ✅ `register_strategy()` — 注册策略生命周期，记录 IS/OOS 基准指标
- ✅ `evaluate_decay()` — 4 维度加权衰减评估（Sharpe 40% + 盈亏比 25% + 胜率 15% + 交易频率 20%）
- ✅ `detect_decay()` — 详细回测历史趋势分析（信号频率/滚动 Sharpe/盈亏比趋势）
- ✅ `recommend_action()` — 4 级衰减决策：keep(<20) / paper_trade(20-40) / re_optimize(40-70) / retire(70+)
- ✅ `compare_strategies()` — 多策略按衰减分排名对比
- ✅ `get_lifecycle_summary()` — 前端摘要数据（含 IS/OOS 指标 JSON 解析）

### Agent 集成
- ✅ `_DEFAULT_EVOLUTION_CONFIG` 新增 `persist_to_db`（默认 True）
- ✅ 进化完成后自动：保存最优策略到 `StrategyDB` → 创建 `StrategyEvolutionRunDB` → 保存每代 `StrategyGenerationDB` → 注册 `StrategyLifecycleDB`
- ✅ 进化失败时创建 `failed` 状态的 `StrategyEvolutionRunDB` 记录

### 调度器
- ✅ `weekly_strategy_evolution()` — 周六凌晨自动进化活跃品种（轻量配置：pop=20, gens=5）
- ✅ `build_weekly_evolution_job()` — 独立于 `build_job_configs` 的注册函数
- ✅ 通过 `ENABLE_WEEKLY_EVOLUTION` 环境变量控制（默认开启）

### API 路由 (`/api/evolution`)
- ✅ `GET /runs` — 进化运行历史（分页 + symbol/status 过滤）
- ✅ `GET /runs/{id}` — 单次运行详情 + 代际快照列表
- ✅ `GET /lifecycles` — 用户策略生命周期列表
- ✅ `GET /lifecycle/{id}` — 单个策略生命周期详情
- ✅ `POST /evaluate-decay` — 触发衰减评估
- ✅ `POST /compare` — 多策略生命周期对比

### 前端
- ✅ `/strategies/evolution` 页面：进化历史 Tab（RunCard 卡片列表）+ 策略生命周期 Tab（状态徽章/衰减评分/批量对比）
- ✅ `EvolutionReportCard.tsx`：进化报告卡片（摘要指标 + 可折叠完整报告）
- ✅ Chat 页面 `ModeKey` 扩展：`strategy_evolution` 模式 + GitBranch 图标 + 快捷提示词
- ✅ 前端 API Client：`evolution.ts` + TypeScript 类型定义

### 测试
- ✅ 32 个新测试 + 87 个已有测试 = 119 个测试全部通过
- ✅ `test_strategy_lifecycle.py`：注册/衰减评估/行动推荐/检测/对比/摘要（20 用例）
- ✅ `test_evolution_db_models.py`：CRUD/关系/CASCADE/唯一约束（12 用例）
- ✅ `test_evolution_router.py`：路由集成测试（8 用例）
- ✅ `test_strategy_evolution_agent.py`：87 个已有测试保持通过（无回归）

### 延期至后续迭代
- ⏳ Walk-forward 分析引擎实现（DB 字段 + Schema 已预留，分析逻辑待后补）
- ⏳ 前端 Dashboard 实时 SSE 流式进化进度（后端 Agent 层 SSE 已支持）

### 配置参数速查（当前版本）

```python
_DEFAULT_EVOLUTION_CONFIG = {
    # Phase 1 基础配置
    "population_size": 40,
    "generations": 10,
    "elite_count": 5,
    "mutation_rate": 0.3,
    "mutation_strength": 0.15,
    "factor_top_n": 15,
    "factor_min_abs_rank_ic": 0.02,
    # Phase 2A 新增
    "crossover_rate": 0.7,       # 交叉概率
    "oos_split_ratio": 0.3,      # OOS 验证数据占比（0=禁用）
    # Phase 2B 新增
    "use_gp_factors": False,     # 启用 GP 因子生成
    "gp_n_generate": 80,         # GP 初始因子数量
    "gp_generations": 3,         # GP 进化代数
    "use_pareto_fitness": False, # 启用 NSGA-II Pareto 适应度
    "use_bayesian_optimization": False,  # 启用贝叶斯优化
    "bo_iterations": 30,         # BO 迭代次数
    "bo_initial_samples": 10,    # BO 初始采样数
    # Phase 3 新增
    "persist_to_db": True,       # 进化结果持久化到数据库
}
```

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
| `services/backtest/optimization_engine.py` | `optimize_strategy_params()`（网格搜索）+ 贝叶斯优化作为补充 |
| `evolution/bayesian_optimizer.py` | `optimize_strategy_params_bayesian()` — sklearn GP + EI 贝叶斯优化 |
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
