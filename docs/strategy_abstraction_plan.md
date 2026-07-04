# 凌烟阁回测系统 → project_rich_snowball 功能抽象方案

> 分析日期：2026-07-04
> 源系统：`D:\Code\stock-quant\flagship_stock_strategy\凌烟阁中市值选股策略精心随机_26_v3_original`
> 目标系统：`D:\Code\project_rich_snowball`

---

## 一、凌烟阁回测系统架构

### 1.1 目录结构

```
凌烟阁中市值选股策略精心随机_26_v3_original/
├── config_凌烟阁中市值选股策略精心随机.py    # 回测配置（驱动文件）
├── 因子库/                                     # ~40 个独立因子模块
│   ├── 估值/        EP, SP, HML因子, 企业价值倍数, 捡烟蒂因子
│   ├── 成长/        ROE, EPS相关因子, 净利润单季同比, 归母净利润同比, 毛利率季度增加, 营业收入单季同比增速
│   ├── 波动/        G161, G167, G187, G189, PriceVol, 加权盈利率
│   ├── 短期反转/    Adxrpos, Ax10, CoppAtr, CRet, G135, MaDisplaced, MakV2, MtmHcm
│   ├── 规模/        Alpha95V2, G144, 成交额Mean, 成交额Std, 资金流买入占比
│   ├── 长期反转/    Ic, Mm, M日内N日新高次数, Po, PpoV1, Sroc, Trv, Wc
│   ├── 未来收益.py
│   ├── 收盘价.py
│   ├── 一级行业.py / 一级行业过滤.py
│   ├── 近期停牌天数.py / 异常涨跌停状态.py
│   ├── N日均价.py / N日最高收盘价.py / N日最低收盘价.py / N日收盘价标准差.py
│   ├── FCFFEV.py / FCFF_TTM大于0.py / CCI.py
├── 信号库/                                     # 6 个个股择时信号
│   ├── 个股择时_均线.py
│   ├── 个股择时_海龟.py
│   ├── 个股择时_布林带.py
│   ├── 个股择时_KDJ.py
│   ├── 个股择时_RSV.py
│   └── 个股择时_CCIQ.py
├── 策略库/                                     # 3 个策略模板
│   ├── 偏科生选股策略_方案三.py               # ICIR多因子加权组合
│   ├── 偏科生选股策略_方案三_polars.py         # 同上 + Polars 加速
│   └── 现金流选股策略.py                       # 行业超配选股
└── README.md
```

### 1.2 三层架构

```
┌─────────────────────────────────────────────────────┐
│                   config.py (声明式配置)              │
│   start_date, end_date, 策略列表, 资金/手续费参数     │
└────────────────────┬────────────────────────────────┘
                     │
    ┌────────────────┼────────────────┐
    ▼                ▼                ▼
┌────────┐    ┌──────────┐    ┌──────────────┐
│ 因子层  │    │  信号层   │    │   策略层      │
│ 因子库  │    │  信号库   │    │   策略库      │
│ ~40个  │    │   6个    │    │    3个       │
└───┬────┘    └────┬─────┘    └──────┬───────┘
    │              │                 │
    │   统一接口    │   统一接口      │   统一接口
    │ add_factor() │ stock_signal() │ calc_select_factor()
    │              │                 │
    ▼              ▼                 ▼
┌─────────────────────────────────────────────────────┐
│              core 框架引擎（闭源）                      │
│  数据加载 → 因子计算 → 过滤 → 排序选股 →              │
│  择时信号 → 模拟交易 → 资金曲线 → 绩效报告             │
└─────────────────────────────────────────────────────┘
```

### 1.3 核心设计模式

#### 因子层：统一契约

每个因子文件暴露以下要素：

| 要素 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `add_factor(df, param, **kwargs)` | 函数 | 核心计算逻辑，返回 `pd.DataFrame` | `df['close'].rolling(n).mean()` |
| `fin_cols` | `list[str]` | 声明需要的财务数据列 | `['R_np@xbx_ttm']` |
| `ov_cols` | `list[str]` | 声明需要的其他数据列 | `['新版申万一级行业名称']` |
| `FA_INTRO` | `dict` | 因子元数据文档 | 含直播链接、使用案例 |

配置方式（在 config 的 `factor_list` 中声明）：

```python
("因子名.子因子名", is_sort_asc, param, 权重/分组)
# 例：
("估值.EP", False, "单季", "组合1")        # EP_单季，降序排序，属于"组合1"
("长期反转.Wc", True, 20, "组合1")          # Wc_20，升序排序
("未来收益", True, 5, 50, "0930")          # 未来5日收益，滚动50周期ICIR
```

#### 信号层：统一契约

每个信号文件暴露 `stock_signal(stock_timing, stock_df) → pd.Series`，返回持仓状态序列：

```python
# 例：均线择时
def stock_signal(stock_timing, stock_df):
    ma_col = stock_timing.factor_list[0].col_name
    bias = stock_df["close"] / stock_df[ma_col] - 1
    signal = pd.Series(np.nan, index=stock_df.index)
    signal[bias > threshold] = 1    # 做多
    signal[bias < threshold] = 0    # 空仓
    return signal.ffill().fillna(0)
```

#### 策略层：因子组合艺术

策略模板接收原始 K 线数据 + 已计算好的因子列，生成**复合因子**（一个综合评分列），框架按此排序选股：

**偏科生策略**（ICIR加权组合）：
```
1. 将所有因子按配置分为5组
2. 每组内：
   a. 计算每个因子的 Rank IC（与未来收益的秩相关）
   b. 取滚动50周期的 IC / IC_std = ICIR
   c. 因子排名 × ICIR = 加权排名
   d. 同组加权排名求和 = 该组偏科生因子
3. 5组偏科生因子等权求和 = 复合因子
4. 按复合因子排序，选前 select_num 只
```

**现金流策略**（行业超配组合）：
```
1. 按 FCFFEV 因子排序得到每个股票的排名
2. 计算每个行业的 FCFFEV 均值，对行业排名
3. 按配置的 quota 分配：前N行业各取M只
```

---

## 二、project_rich_snowball 现有能力对照

### 2.1 能力矩阵

| 能力维度 | 凌烟阁 | rich_snowball | 差距评估 |
|----------|--------|---------------|----------|
| **因子 DSL 求值** | ❌ 无 | ✅ `factor_engine/dsl.py` | rich_snowball 领先 |
| **单因子绩效评估** (IC/RankIC/ICIR/分层回测) | ✅ 内置 | ✅ `factor_engine/evaluator.py` | 基本对齐 |
| **技术指标** (MA/MACD/RSI/KDJ/Boll/ATR/CCI) | ✅ 因子库 | ✅ `backtest/engine.py` `_compute_indicator` | 基本对齐 |
| **策略 DSL 编译** (自然语言→结构化策略) | ❌ | ✅ `strategy_compiler_agent.py` | rich_snowball 领先 |
| **单品种择时回测** | ✅ | ✅ `backtest/engine.py` | 基本对齐 |
| **多因子组合** (ICIR加权/行业超配) | ✅ 策略库 | **❌ 缺失** | 🔴 核心差距 |
| **声明式过滤条件** (停牌/涨跌停/价格) | ✅ `filter_list` | **❌ 缺失** | 🔴 核心差距 |
| **因子即插即用注册** (统一 add_factor) | ✅ 模块化 | **❌ 缺失** | 🟡 中等差距 |
| **行业/市值中性化** | ✅ 内置 | **❌ 缺失** | 🟡 中等差距 |
| **选股 + 择时双层信号** | ✅ | **❌ 缺失** | 🔴 架构差距 |
| **多偏移日换仓** (`offset_list`) | ✅ | **❌ 缺失** | 🟢 远期 |
| **真实交易约束** (`stay_real`) | ✅ | **❌ 缺失** | 🟢 远期 |
| **Polars 加速** (大截面计算) | ✅ | **❌ 缺失** | 🟢 远期 |
| **分钟级择时** (intraday) | ✅ 支持 1H | ❌ 仅日线 | 🟢 远期 |
| **多品种选股回测** (从 N 只中选 K 只) | ✅ 核心能力 | **❌ 缺失** | 🔴 架构差距 |

### 2.2 existing 资产的复用价值

rich_snowball 已有的以下模块可直接作为基础设施被新功能使用：

| 已有资产 | 路径 | 可被复用的能力 |
|----------|------|---------------|
| 因子 DSL 求值器 | `factor_engine/dsl.py` | 安全执行用户提供的因子表达式 |
| 面板数据加载器 | `factor_engine/data_loader.py` | 从数据库构建 `日期 × 品种` PanelData |
| 因子评估器 | `factor_engine/evaluator.py` | IC/ICIR/分层回测/多空收益/换手率 |
| 回测引擎 | `backtest/engine.py` | 单品种逐笔回测、资金曲线、绩效指标 |
| 回测服务 | `backtest/service.py` | 将 engine 封装为服务调用 |
| DSL 适配器 | `backtest/dsl_adapter.py` | 将策略 DSL 转换为 engine 可执行的条件 |
| 策略编译器 | `strategy_compiler_agent.py` | 自然语言→结构化策略 DSL |
| 数据库模型 | `models.py` | KlineDataDB、VarietyDB 等数据模型 |

---

## 三、建议抽象的功能（按优先级）

### 3.1 P0：核心价值，应立即落地

#### P0-1：多因子组合框架 `factor_engine/compositor.py`

**目标**：填补从"单因子评估"到"完整选股策略"的空白。

**抽象来源**：
- `策略库/偏科生选股策略_方案三.py` — ICIR 加权组合
- `策略库/现金流选股策略.py` — 行业超配组合

**设计方案**：

```python
# factor_engine/compositor.py

@dataclass
class CompositeConfig:
    """多因子组合配置"""
    factors: list[FactorSpec]           # 因子列表（名+排序方向+分组）
    method: Literal["icir_weighted", "equal_weight", "industry_quota"]
    select_num: int                      # 选股数量
    future_return: FutureReturnSpec      # 用于计算 ICIR 的未来收益配置

class FactorCompositor:
    """将多个因子组合为复合评分"""
    
    def compute_composite_score(
        self, panel: PanelData, config: CompositeConfig
    ) -> CompositeScoreResult:
        ...
        # 1. 计算各因子的 Rank ICIR
        # 2. 按 ICIR 对各因子排名加权
        # 3. 聚合为复合评分
        # 4. 返回排序结果 + ICIR 明细
```

**核心算法（偏科生策略的精华）**：

```
复合因子 = Σ_groups [ Σ_factors_in_group (rank_pct(factor) × ICIR(factor)) ]
```

其中 `ICIR = rolling_mean(IC, 50) / rolling_std(IC, 50)`，对未来收益做 shift 以避免未来函数。

**集成路径**：
1. 复用 `dsl.py` 的 `PanelData` 和 `evaluate_factor` 进行单因子求值
2. 复用 `evaluator.py` 的 IC 计算逻辑
3. 新增组合层逻辑
4. 新增 `CompositeScoreResult` 数据类
5. 在 `backtest/engine.py` 中增加 `run_selection_backtest()` 入口

#### P0-2：声明式过滤条件 DSL `factor_engine/filters.py`

**目标**：提供统一的股票过滤机制，支撑停牌/涨跌停/价格/行业等过滤需求。

**抽象来源**：
- `config.py` 中的 `filter_list` 机制
- `因子库/一级行业过滤.py`、`因子库/近期停牌天数.py`、`因子库/异常涨跌停状态.py`

**设计方案**：

```python
# factor_engine/filters.py

@dataclass
class FilterCondition:
    """单个过滤条件"""
    field: str                           # 因子/字段名，如 "收盘价"、"近期停牌天数"
    params: Any                          # 因子参数
    expression: str                      # 表达式，如 "val:==0", "val:<20", "pct:>=0.05"
    is_and: bool = True                  # True=AND, False=OR
    
class FilterPipeline:
    """过滤流水线"""
    
    def apply(
        self, df: pd.DataFrame, conditions: list[FilterCondition]
    ) -> pd.DataFrame:
        """
        返回过滤后的 DataFrame。
        支持的表达式语法：
          - val:==X    值等于 X
          - val:>X     值大于 X
          - val:<X     值小于 X
          - pct:>=X    在截面内的分位数 >= X
          - pct:<=X    在截面内的分位数 <= X
        """
```

**集成路径**：
1. 在 `backtest/engine.py` 回测循环的选股步骤之前插入过滤
2. 集成到 `BacktestConfig` 中作为 `filter_list` 字段
3. 支持多条件 AND/OR 组合

---

### 3.2 P1：中期增强

#### P1-1：因子注册表 `factor_engine/registry.py`

**目标**：提供因子按类别的统一注册、发现、元数据查询能力。

**抽象来源**：凌烟阁因子库的模块组织方式 + `FA_INTRO` 元数据模式。

**设计方案**：

```python
# factor_engine/registry.py

@dataclass
class FactorDefinition:
    name: str                            # 因子名，如 "EP"
    category: str                        # 类别：估值/成长/波动/短期反转/长期反转/规模
    description: str                     # 含义说明
    params_schema: list[ParamSpec]       # 参数 schema
    requires_fin_data: list[str]         # 需要的财务数据列
    requires_ov_data: list[str]          # 需要的其他数据列
    compute_fn: Callable                 # 计算函数引用

class FactorRegistry:
    """因子注册中心"""
    
    def register(self, definition: FactorDefinition): ...
    def get(self, name: str) -> FactorDefinition: ...
    def list_by_category(self, category: str) -> list[FactorDefinition]: ...
    def discover_from_directory(self, path: Path): ...  # 自动扫描加载
```

**与现有 `factor_definitions` 表的衔接**：已有的数据库表可存储元数据，`FactorRegistry` 作为运行时缓存，提供编程访问接口。

#### P1-2：因子中性化 `factor_engine/neutralization.py`

**目标**：去除行业/市值等系统性偏差的影响。

**抽象来源**：凌烟阁 `core.market_essentials.factor_neutralization` + 现金流策略中的使用模式。

**设计方案**：

```python
# factor_engine/neutralization.py

def neutralize_factor(
    df: pd.DataFrame,
    factor_col: str,
    by: list[str],                       # 中性化的维度，如 ["industry", "market_cap"]
    method: Literal["residual", "demean"] = "residual",
) -> pd.Series:
    """
    对因子值做截面中性化。
    residual 方法：factor ~ industry_dummies + log(market_cap)，取残差
    demean 方法：因子值减去行业均值
    """
```

#### P1-3：评测指标补充 `backtest/metrics.py`

**目标**：在现有 `_calculate_metrics` 基础上增加更丰富的绩效指标。

**抽象来源**：凌烟阁回测框架的标准评测输出。

**设计方案**：

```python
# backtest/metrics.py

@dataclass
class EnhancedBacktestMetrics:
    # 现有指标
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    sharpe: float
    trade_count: int
    score: int
    
    # 新增指标
    information_ratio: float | None       # 信息比率（相对基准的超额收益/跟踪误差）
    excess_return_pct: float | None       # 超额收益（相对基准）
    turnover_rate: float | None           # 年化换手率
    calmar_ratio: float | None            # 年化收益/最大回撤
    sortino_ratio: float | None           # 下行风险调整收益
    quantile_returns: list[float]         # 分层回测各分位收益
    ic_decay: list[float]                 # IC 衰减曲线（各提前期的 IC）
    monthly_returns: list[dict]           # 月度收益明细
    
    # 选股回测特有
    avg_hold_stocks: float | None         # 平均持仓数量
    selection_alpha: float | None         # 选股超额 alpha
```

---

### 3.3 P2：远期架构升级

#### P2-1：选股 + 择时双层信号 `backtest/selection_engine.py`

**目标**：实现"先选股、再择时"的完整投资决策链。

**架构设计**：

```
                    ┌─────────────┐
                    │  多品种数据   │
                    │ (PanelData) │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ 因子计算  │ │ 过滤条件  │ │ 择时信号  │
        │ (因子库)  │ │ (filter) │ │ (signal) │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             ▼            ▼            │
        ┌──────────────────────┐       │
        │   多因子组合评分       │       │
        │   (compositor)       │       │
        └──────────┬───────────┘       │
                   │                   │
                   ▼                   ▼
              ┌────────────────────────────┐
              │     选股引擎               │
              │  按复合评分排序，选 Top N    │
              └────────────┬───────────────┘
                           │
                           ▼
              ┌────────────────────────────┐
              │     仓位管理                │
              │  择时信号 × 基础仓位 = 实际仓位│
              └────────────┬───────────────┘
                           │
                           ▼
              ┌────────────────────────────┐
              │     模拟交易引擎             │
              │  逐日/逐分钟撮合 + 资金管理   │
              └────────────────────────────┘
```

**凌烟阁对应**：
- `stock_timing_list` 中的 `weight` 决定择时信号对仓位的影响权重
- 多个择时信号可取加权平均：`最终仓位 = Σ(信号_i × 权重_i)`
- `stock_timing_order_price` 控制择时成交价的模拟精度

#### P2-2：多偏移日换仓

**目标**：分散换仓冲击，更接近实盘操作。

**凌烟阁对应**：`offset_list: [0, 1, 2, 3, 4]` — 将总资金分为5份，在连续5个交易日各换1/5。

```python
@dataclass
class RebalanceConfig:
    hold_period: str                     # 持仓周期 "W" / "5D"
    offset_list: list[int]               # 偏移日列表
    select_num: int                      # 选股数量
    rebalance_time: Literal["open", "close"]  # 换仓时点
```

#### P2-3：真实交易约束

**目标**：模拟停牌无法买入、涨停买不到、跌停卖不出的真实交易限制。

**凌烟阁对应**：`stay_real = True` 时的行为：
- 换仓日停牌的股票不参与选股
- 涨停股票在买入列表中排除
- 跌停持仓挂单直至成交（不限天数）

#### P2-4：分钟级数据支持

**目标**：支持 1H 等分钟级择时信号的回测。

**凌烟阁对应**：`period: "1H"` + `stock_timing_order_price = 5`（延迟5分钟成交模拟）。

---

## 四、实施路线图

```
Week 1-2 ─── P0-1 多因子组合框架 ─────────────────────────┐
            │  - compositor.py                             │
            │  - 集成到 backtest/engine                     │
            │  - 偏科生策略 + 现金流策略模板                  │
            │                                               │
Week 2-3 ─── P0-2 过滤条件 DSL ────────────────────────────┤
            │  - filters.py                                │
            │  - 集成到 BacktestConfig                      │
            │  - 常用过滤条件预制                            │
            │                                               │
Week 3-4 ─── P1-1 因子注册表 ───────────────────────────────┤
            │  - registry.py                               │
            │  - 自动发现因子                                │
            │  - 与 factor_definitions 表对齐               │
            │                                               │
Week 4-5 ─── P1-2 中性化 + P1-3 评测指标补充 ───────────────┤
            │  - neutralization.py                          │
            │  - metrics.py (增强版)                        │
            │                                               │
Week 6+  ─── P2 远期功能（按需排期）────────────────────────┘
```

---

## 五、讨论要点

在进入实施前，建议先就以下问题达成共识：

1. **品种域差异**：凌烟阁是股票多因子选股系统，rich_snowball 当前是期货系统。多因子组合框架是否先限定在期货品种上，还是同时考虑股票扩展？两者的数据模型（`VarietyDB` vs `StockDB`）和可用的因子类别差异较大。

2. **因子注册表的实现方式**：是像凌烟阁那样用 Python 文件（每因子一个文件 + 自动扫描），还是用数据库表（`factor_definitions`）为主 + Python 实现为辅？前者对量化研究员友好（写 Python 即可），后者对 UI 展示和搜索更友好。

3. **回测引擎升级策略**：是渐进式增强现有 `backtest/engine.py`（保持向后兼容），还是新建一个 `backtest/engine_v2.py` 做全新设计？建议渐进式，因为现有引擎的单品种回测已经稳定且有测试覆盖。

4. **与 Agent 系统的集成深度**：P0 的功能是否需要对用户透明（通过 Agent 自然语言触发），还是先作为 Python API 可用、Agent 集成作为后续迭代？建议先 API 可用 + 基础 Agent 触发，保证 MVP 速度。
