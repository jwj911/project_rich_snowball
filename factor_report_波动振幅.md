# 期货Agent系统 — 波动振幅类因子精选报告

> 数据来源：`factor_screening_top100.csv` / `factor_screening_top100.json`
> 筛选类别：**波动振幅**
> 适配目标：期货单品种时序信号（多空判断）
> 生成时间：2026-07-05

---

## 一、筛选概览

| 指标 | 阈值/要求 |
|------|----------|
| Q | ≥ 0.85（优先） |
| \|test_rankicir\| | ≥ 0.45（优先，允许放宽至 0.42） |
| monotonicity | 接近 ±1.0（方向稳定） |
| 公式复杂度 | 排除 >5 层嵌套 |
| 重复性 | 排除结构雷同因子 |

**波动振幅类别原始因子数**：7 个  
**最终精选因子数**：**5 个**（排除 2 个高度重复项）

> 排除说明：`AM_ts_regression_beta_amplitude_ret_05be75b2`（rank=35）与 `AM_ts_regression_beta_amplitude_ret_581e00f9`（rank=29）公式结构完全雷同（均为振幅-收益回归beta），仅参数窗口可能存在差异，保留Q更高者（rank=29）。

---

## 二、精选因子总览表

| 序号 | 因子名称 | Q | \|test_rankicir\| | monotonicity | ls_sharpe | 核心逻辑类型 | 信号方向 |
|:---:|---------|:---:|:---:|:---:|:---:|:---|:---:|
| 1 | AM_ema_ts_dema_delta_8dc6d97c | **0.8826** | **0.4554** | **1.0** | 1.5643 | 双均线动量差 | 正→多 |
| 2 | AM_ts_regression_beta_amplitude_ret_581e00f9 | **0.8912** | 0.4428 | **-1.0** | -1.3982 | 振幅-收益回归beta | 正→空 |
| 3 | AM_ts_regression_beta_intraday_rang_b4142f62 | **0.8790** | **0.4525** | -0.9 | -1.4432 | 日内区间-收益回归beta | 正→空 |
| 4 | AM_ts_regression_beta_neg_amplitude_e0ddc0c0 | 0.8659 | 0.4365 | **0.9** | **1.5689** | 负振幅-收益回归beta | 正→多 |
| 5 | AM_div_ts_pct_change_intraday_range_7dfa319a | **0.8811** | 0.4224 | **-1.0** | -1.1462 | 波动效率比率 | 正→空 |

---

## 三、因子详解

### 因子 1：AM_ema_ts_dema_delta — 振幅动量差（Volatility Momentum Delta）

#### 因子逻辑
计算日内振幅 `amplitude = (high - low) / pre_close` 的 **EMA** 与 **DEMA**（Double EMA）之差。当振幅的短期动量加速（EMA 上穿 DEMA），意味着市场波动正在放大，通常伴随趋势突破；当动量减速（EMA 下穿 DEMA），则预示波动收敛、可能面临变盘。

在期货时序应用中，该因子直接衡量**波动率自身的动量方向**，是波动率突破策略的核心构件。

#### A股字段 → 期货字段映射

| A股字段 | 期货字段 | 说明 |
|---------|---------|------|
| 最高价_复权 | `high_price` | 当日最高价 |
| 最低价_复权 | `low_price` | 当日最低价 |
| 前收盘价 | `pre_close` | 前一日收盘价 |

#### 评分指标

| 指标 | 数值 | 解读 |
|------|------|------|
| Q | **0.8826** | 高质量，超过 0.85 阈值 |
| test_rankicir | **+0.4554** | OOS 稳健，正方向显著 |
| monotonicity | **1.0** | 完美单调递增，方向极其稳定 |
| ls_sharpe | 1.5643 | 多空组合夏普比率优秀 |

#### 期货适配 Pandas 表达式

```python
import numpy as np
import pandas as pd

# 1. 计算日内振幅（前收盘价标准化）
amplitude = (df['high_price'] - df['low_price']) / df['pre_close']

# 2. 计算振幅的 EMA（指数移动平均）
ema_amp = amplitude.ewm(span=12, adjust=False).mean()

# 3. 计算振幅的 DEMA（双指数移动平均）
# DEMA = 2 * EMA - EMA(EMA)
ema_of_ema = ema_amp.ewm(span=12, adjust=False).mean()
dema_amp = 2 * ema_amp - ema_of_ema

# 4. 因子值 = EMA - DEMA（衡量振幅动量加速/减速）
df['factor_vol_momentum_delta'] = ema_amp - dema_amp

# 5. 信号方向（monotonicity=+1.0）
#  factor > 0 → 振幅动量加速 → 多头信号（趋势强化）
#  factor < 0 → 振幅动量减速 → 空头信号或观望（波动收敛）
```

#### 交易含义与时序信号

- **多头信号**：`factor_vol_momentum_delta > 0` 且持续扩大 → 波动率动量向上，突破行情概率高，适合趋势跟踪
- **空头信号**：`factor_vol_momentum_delta < 0` 且持续走低 → 波动率动量向下，市场进入收敛整理，适合区间做空或观望
- **注意事项**：在期货高杠杆环境下，波动率放大通常预示方向选择，需结合价格趋势方向确认

---

### 因子 2：AM_ts_regression_beta_amplitude_ret — 振幅弹性（Amplitude Beta）

#### 因子逻辑
在滚动时序窗口（如 20 日）内，用**日内振幅**对**日收益率**做线性回归，取 **beta 系数**：

```
ret = alpha + beta * amplitude + epsilon
```

该 beta 衡量"单位振幅带来的收益变化"，即振幅的**弹性/质量**。高 beta 意味着同样的波动能产生更大收益，属于"高效波动"；低 beta 意味着波动与收益脱节，属于"无效震荡"。

A 股截面因子中该因子 monotonicity=-1.0，说明**高 beta 不可持续**，往往预示后续收益回落（过度波动后的均值回归）。

#### A股字段 → 期货字段映射

| A股字段 | 期货字段 | 说明 |
|---------|---------|------|
| 最高价_复权 | `high_price` | 当日最高价 |
| 最低价_复权 | `low_price` | 当日最低价 |
| 收盘价_复权 | `close_price` | 当日收盘价 |
| 前收盘价 | `pre_close` | 前一日收盘价 |

#### 评分指标

| 指标 | 数值 | 解读 |
|------|------|------|
| Q | **0.8912** | 极高信度 |
| test_rankicir | -0.4428 | OOS 稳定，接近 0.45 阈值 |
| monotonicity | **-1.0** | 完美单调递减，方向稳定 |
| ls_sharpe | -1.3982 | 多空组合表现良好 |

#### 期货适配 Pandas 表达式

```python
# 1. 计算日内振幅（前收盘价标准化）
amplitude = (df['high_price'] - df['low_price']) / df['pre_close']

# 2. 计算日收益率
ret = df['close_price'] / df['pre_close'] - 1

# 3. 滚动窗口回归 beta（cov(x,y) / var(x)）
window = 20
cov = amplitude.rolling(window).cov(ret)
var = amplitude.rolling(window).var()
df['factor_amplitude_beta'] = cov / var

# 4. 处理极端值
df['factor_amplitude_beta'] = df['factor_amplitude_beta'].replace([np.inf, -np.inf], np.nan)
df['factor_amplitude_beta'] = df['factor_amplitude_beta'].clip(-5, 5)  # 限制beta范围

# 5. 信号方向（monotonicity=-1.0）
#  factor > 0（高弹性）→ 过度波动 → 空头信号（均值回归）
#  factor < 0（负弹性）→ 反向波动 → 多头信号（反向择时）
```

#### 交易含义与时序信号

- **空头信号**：`factor_amplitude_beta > 0` 且绝对值较大 → 振幅与收益正相关（波动放大伴随上涨），但不可持续，适合反手做空或止盈
- **多头信号**：`factor_amplitude_beta < 0` → 振幅与收益负相关（高波动伴随下跌），后续可能反转，适合抄底做多
- **期货特化**：在期货中，该因子特别适合**波动率均值回归策略**——当波动-收益弹性过高时，押注波动回落

---

### 因子 3：AM_ts_regression_beta_intraday_rang — 日内区间弹性（Intraday Range Beta）

#### 因子逻辑
与因子 2 类似，但用**日内区间** `intraday_range = (high - low) / close`（以**当日收盘价**标准化，而非前收盘价）对收益率做回归 beta。当日收盘价标准化更能反映**实时波动效率**，而非隔日跳空的影响。

该因子衡量当日实时波动与当日收益的关系。当日内区间很大但收盘收益很小时，beta 趋近于 0，说明是"无序震荡"；当区间与收益同步放大时，beta 升高，说明是"定向波动"。

#### A股字段 → 期货字段映射

| A股字段 | 期货字段 | 说明 |
|---------|---------|------|
| 最高价_复权 | `high_price` | 当日最高价 |
| 最低价_复权 | `low_price` | 当日最低价 |
| 收盘价_复权 | `close_price` | 当日收盘价 |

#### 评分指标

| 指标 | 数值 | 解读 |
|------|------|------|
| Q | **0.8790** | 高质量 |
| test_rankicir | **-0.4525** | 超过 0.45 阈值，OOS 稳健 |
| monotonicity | -0.9 | 单调递减，方向稳定 |
| ls_sharpe | -1.4432 | 多空夏普优秀 |

#### 期货适配 Pandas 表达式

```python
# 1. 计算日内区间（当日收盘价标准化）
intraday_range = (df['high_price'] - df['low_price']) / df['close_price']

# 2. 计算日收益率（也可用 close/pre_close - 1）
ret = df['close_price'].pct_change()

# 3. 滚动窗口回归 beta
window = 20
cov = intraday_range.rolling(window).cov(ret)
var = intraday_range.rolling(window).var()
df['factor_intraday_range_beta'] = cov / var

# 4. 处理极端值
df['factor_intraday_range_beta'] = df['factor_intraday_range_beta'].replace([np.inf, -np.inf], np.nan)
df['factor_intraday_range_beta'] = df['factor_intraday_range_beta'].clip(-5, 5)

# 5. 信号方向（monotonicity=-0.9）
#  factor > 0（高区间弹性）→ 实时波动不可持续 → 空头信号
#  factor < 0（负区间弹性）→ 反向波动 → 多头信号
```

#### 交易含义与时序信号

- **空头信号**：`factor_intraday_range_beta > 0` 且偏高 → 日内波动与收益同步放大，但 A 股经验表明这种同步不可持续，适合做空或反向操作
- **多头信号**：`factor_intraday_range_beta < 0` → 日内波动与收益反向，可能预示洗盘或底部震荡，后续可能反转向上
- **与因子 2 的区别**：因子 2 用 `pre_close` 标准化，受隔夜跳空影响大；因子 3 用 `close` 标准化，更反映当日实时博弈，适合**日内或短周期CTA策略**

---

### 因子 4：AM_ts_regression_beta_neg_amplitude — 负振幅弹性（Negative Amplitude Beta）

#### 因子逻辑
将振幅取负后 `neg_amplitude = -(high - low) / pre_close`，再对收益率做回归 beta。本质是因子 2 的"镜像"版本，但由于回归变量取负，beta 的经济含义发生反转。

monotonicity=+0.9，说明**正 beta 值对应未来正收益**。这意味着：当负振幅（即波动率的反向代理）对收益有正向解释力时，市场处于"低波动稳态"，后续趋势延续概率高。该因子捕捉的是**"低波动后的趋势延续"**或**"波动压缩后的突破"**。

#### A股字段 → 期货字段映射

| A股字段 | 期货字段 | 说明 |
|---------|---------|------|
| 最高价_复权 | `high_price` | 当日最高价 |
| 最低价_复权 | `low_price` | 当日最低价 |
| 收盘价_复权 | `close_price` | 当日收盘价 |
| 前收盘价 | `pre_close` | 前一日收盘价 |

#### 评分指标

| 指标 | 数值 | 解读 |
|------|------|------|
| Q | 0.8659 | 超过 0.85 阈值 |
| test_rankicir | 0.4365 | 接近 0.45，OOS 表现良好 |
| monotonicity | **0.9** | 单调递增，方向稳定（正方向） |
| ls_sharpe | **1.5689** | 多空夏普最高，策略表现最优 |

> **亮点**：该因子 ls_sharpe=1.5689 是全部 5 个精选因子中最高的，说明其多空区分能力极强。

#### 期货适配 Pandas 表达式

```python
# 1. 计算负振幅（前收盘价标准化）
neg_amplitude = -(df['high_price'] - df['low_price']) / df['pre_close']

# 2. 计算日收益率
ret = df['close_price'] / df['pre_close'] - 1

# 3. 滚动窗口回归 beta
window = 20
cov = neg_amplitude.rolling(window).cov(ret)
var = neg_amplitude.rolling(window).var()
df['factor_neg_amplitude_beta'] = cov / var

# 4. 处理极端值
df['factor_neg_amplitude_beta'] = df['factor_neg_amplitude_beta'].replace([np.inf, -np.inf], np.nan)
df['factor_neg_amplitude_beta'] = df['factor_neg_amplitude_beta'].clip(-5, 5)

# 5. 信号方向（monotonicity=+0.9）
#  factor > 0（负振幅正向解释收益）→ 低波动稳态 → 多头信号（趋势延续）
#  factor < 0 → 高波动失控 → 空头信号或观望
```

#### 交易含义与时序信号

- **多头信号**：`factor_neg_amplitude_beta > 0` → 负振幅（即低振幅代理）对收益有正向解释，市场处于低波动稳态，趋势延续概率高，适合**趋势跟踪加仓**
- **空头信号**：`factor_neg_amplitude_beta < 0` → 负振幅对收益负向解释，波动放大伴随收益恶化，适合**减仓或做空**
- **策略组合**：该因子与因子 2（振幅弹性）方向天然相反（mono 分别为 +0.9 和 -1.0），可组成**波动率多空配对**：因子 4 做多低波动、因子 2 做空高波动，形成完整的波动率曲面策略

---

### 因子 5：AM_div_ts_pct_change_intraday_range — 波动效率比（Volatility Efficiency Ratio）

#### 因子逻辑
计算**日收益率**除以**日内区间**的比率，衡量"单位日内波动所转化的价格变化效率"。

- 比率高 → 波动高度定向（趋势性强），少量波动就能产生大收益
- 比率低 → 波动无效（震荡市），大量波动仅产生微小收益
- 比率为负 → 波动与收益反向（洗盘或假突破）

该因子本质是**Kaufman 效率比率的变体**，但用日内区间替代真实波幅（TR），更聚焦于当日博弈的"纯度"。

monotonicity=-1.0 说明**高效率比率不可持续**——昨日趋势性太强，今日容易反转或回调。这符合"趋势耗尽"的市场微观结构假说。

#### A股字段 → 期货字段映射

| A股字段 | 期货字段 | 说明 |
|---------|---------|------|
| 最高价_复权 | `high_price` | 当日最高价 |
| 最低价_复权 | `low_price` | 当日最低价 |
| 收盘价_复权 | `close_price` | 当日收盘价 |

#### 评分指标

| 指标 | 数值 | 解读 |
|------|------|------|
| Q | **0.8811** | 高质量 |
| test_rankicir | -0.4224 | 接近 0.45，OOS 尚可 |
| monotonicity | **-1.0** | 完美单调递减 |
| ls_sharpe | -1.1462 | 多空组合表现良好 |

#### 期货适配 Pandas 表达式

```python
# 1. 计算日内区间（当日收盘价标准化）
intraday_range = (df['high_price'] - df['low_price']) / df['close_price']

# 2. 计算日收益率
pct_change = df['close_price'].pct_change()

# 3. 波动效率比 = 收益率 / 日内区间
df['factor_vol_efficiency'] = pct_change / intraday_range

# 4. 处理除零和极端值
df['factor_vol_efficiency'] = df['factor_vol_efficiency'].replace([np.inf, -np.inf], np.nan)
df['factor_vol_efficiency'] = df['factor_vol_efficiency'].clip(-2, 2)  # 限制在合理范围

# 5. 可选：对效率比做平滑以减少噪声
df['factor_vol_efficiency_smooth'] = df['factor_vol_efficiency'].ewm(span=3, adjust=False).mean()

# 6. 信号方向（monotonicity=-1.0）
#  factor > 0（高效率）→ 趋势过度延伸 → 空头信号（反转）
#  factor < 0（负效率）→ 反向波动或低效震荡 → 多头信号（均值回归）
```

#### 交易含义与时序信号

- **空头信号**：`factor_vol_efficiency > 0.5` → 昨日波动效率极高，趋势可能过度延伸，适合**反手做空或止盈**（趋势耗尽策略）
- **多头信号**：`factor_vol_efficiency < -0.3` → 昨日波动与收益反向，可能是假突破或洗盘，后续有修复性上涨，适合**抄底做多**
- **中性区间**：`factor_vol_efficiency` 在 -0.3 ~ 0.5 之间 → 市场处于正常波动状态，无明确信号
- **期货特化**：该因子在**日内高频**和**短周期CTA**中效果最佳，因为日内区间的信息在 T+1 之前就会衰减

---

## 四、因子关联与组合策略建议

### 4.1 因子方向矩阵

| 因子 | mono | 正信号含义 | 策略类型 |
|------|:----:|----------|---------|
| 振幅动量差 | **+1.0** | 波动加速 → 多 | 趋势突破 |
| 振幅弹性 | **-1.0** | 高弹性不可持续 → 空 | 波动率均值回归 |
| 日内区间弹性 | **-0.9** | 实时高弹性不可持续 → 空 | 日内反转/短周期CTA |
| 负振幅弹性 | **+0.9** | 低波动稳态 → 多 | 趋势延续/低波动做多 |
| 波动效率比 | **-1.0** | 高效率不可持续 → 空 | 趋势耗尽/反转 |

### 4.2 多空配对组合

#### 组合 A：波动率曲面多空（Volatility Surface Long-Short）
- **做多**：因子 4（负振幅弹性 > 0）+ 因子 1（振幅动量差 > 0）
  → 低波动稳态 + 波动开始加速 = 趋势启动初期
- **做空**：因子 2（振幅弹性 > 0）+ 因子 5（波动效率比 > 0.5）
  → 高弹性不可持续 + 趋势过度延伸 = 顶部反转

#### 组合 B：日内CTA短周期（Intraday CTA）
- **做多**：因子 3（日内区间弹性 < 0）+ 因子 4（负振幅弹性 > 0）
  → 实时波动反向 + 低波动稳态 = 日内洗盘后做多
- **做空**：因子 3（日内区间弹性 > 0）+ 因子 5（波动效率比 > 0.5）
  → 实时高弹性 + 效率过度 = 日内假突破做空

#### 组合 C：三因子投票（3-Factor Voting）
```python
# 方向投票（+1=多, -1=空, 0=观望）
signal = 0
if df['factor_vol_momentum_delta'] > 0:      signal += 1   # 因子1
if df['factor_amplitude_beta'] > 0:          signal -= 1   # 因子2
if df['factor_neg_amplitude_beta'] > 0:      signal += 1   # 因子4
if df['factor_vol_efficiency'] > 0.5:        signal -= 1   # 因子5

# 最终信号
#  signal >= 2  → 强烈做多
#  signal <= -2 → 强烈做空
#  -1 ~ 1       → 观望或轻仓
```

### 4.3 参数调优建议

| 因子 | 默认窗口 | 期货调优建议 |
|------|---------|------------|
| 因子 1 EMA span | 12 | 期货可尝试 5~10（反应更快）或 20~30（过滤噪音） |
| 因子 2 回归窗口 | 20 | 期货短线 10~15，中线 20~30 |
| 因子 3 回归窗口 | 20 | 日内与因子 2 相同，但可缩短至 5~10 日 |
| 因子 4 回归窗口 | 20 | 与因子 2 同步调整，保持配对一致性 |
| 因子 5 效率阈值 | 0.5 / -0.3 | 高波动品种（如原油、股指）阈值放宽；低波动品种（如国债）收紧 |

---

## 五、风险提示与局限

1. **公式推断局限**：原始数据中 `formula` 字段为空，本报告所有 pandas 表达式基于因子名称语义推断，实际部署前建议与 A 股原始代码（code_hash）对照验证。

2. **A股→期货适配**：A 股因子为截面选股设计（rank IC），适配到期货时序后，预测目标从"横截面相对收益"变为"单品种绝对方向"，需重新用期货历史数据回测验证 IC 和夏普比率。

3. **品种差异**：不同期货品种（股指、商品、债券）的波动率特征差异极大，建议按品种分组训练参数，不要全品种统一阈值。

4. **过拟合风险**：自动挖掘因子存在数据挖掘偏误（data mining bias），建议用期货 OOS 数据（至少 1 年）验证后再实盘。

5. **杠杆风险**：波动率因子在高杠杆期货中放大效应显著，建议搭配止损模块（如 ATR 止损）使用。

---

## 六、附录：被排除因子说明

| 因子名称 | 排除原因 |
|---------|---------|
| `AM_ts_regression_beta_amplitude_ret_05be75b2` | 与 rank=29 因子结构完全雷同（同为振幅-收益回归beta），保留 Q 更高者 |
| `AM_ts_regression_beta_ret_20_intrad_a93226c2` | Q=0.8600 较低，\|test_rankicir\|=0.4007 显著低于 0.45 阈值，且与因子 3 同属日内区间回归类，信息量冗余 |

---

> 本报告由量化因子研究员生成，供期货Agent系统策略开发参考。  
> 建议在 `python/services/agent/factor_engine/` 中实现对应因子计算模块，并接入回测引擎验证。
