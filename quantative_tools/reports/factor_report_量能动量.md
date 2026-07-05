# 期货Agent系统适配报告：量能动量因子精选

**报告生成日期**：2026-07-05

**数据源**：`factor_screening_top100.csv` / `.json`（A股纯量价因子Top100）

**筛选类别**：量能动量

**筛选标准**：
- Q ≥ 0.85 且 |test_rankicir| ≥ 0.45（高质量 + OOS稳健）
- |monotonicity| 尽可能接近 1（方向稳定）
- 优先选择单字段或双字段因子（逻辑清晰、可解释性强）
- 排除公式结构高度雷同的因子
- 要求具备明确的期货交易含义（可转化为单品种时序多空信号）

---

## 一、筛选说明

原始Top100数据集中共有 **28** 个类别为「量能动量」的因子，
全部满足 Q ≥ 0.85 且 |test_rankicir| ≥ 0.45 的硬性门槛。
本报告从中精选出 **8** 个最具代表性、逻辑最清晰、交易含义最明确的因子，
适配到期货Agent系统作为单品种时序信号使用。

> **注意**：以下因子逻辑基于因子命名规则（DSL语义）推断，
> 实际部署时建议通过历史回测验证信号有效性，并调整窗口参数。

---

## 二、精选因子详情

### 1. `AM_neg_ts_pct_change_abs_ee1bb069`

#### 因子逻辑
成交量滚动变化率绝对值的反转因子。先计算滚动窗口（默认20日）内成交量的百分比变化，取绝对值后取负号。高成交量异动（放量/缩量）产生低因子值，预示后续价格可能反转。

#### 交易含义
成交量是价格变动的"燃料"。当成交量短期变化率异常放大时，往往意味着市场参与者情绪达到极端（恐慌或贪婪），后续易出现均值回归。该因子捕捉"能量耗尽"后的反转机会。因子值越低（负得越多），做空信号越强；因子值越高（接近0），做多信号越强。

#### A股字段 → 期货字段映射
- `成交量` → `volume`

#### 评分指标
| 指标 | 数值 |
|------|------|
| **Q** | 0.9211 |
| **test_rankicir** | +0.5111 |
| **monotonicity** | +1.00 |
| **ls_sharpe** | +1.1636 |
| **composite_score** | 0.7527 |

#### 期货适配 pandas 表达式
```python
window = 20
vol_pct = df['volume'].pct_change(periods=window)
df['factor_neg_vol_pct'] = -vol_pct.abs()
```

---

### 2. `AM_neg_ts_maxmin_volume_b4c7097f`

#### 因子逻辑
成交量滚动波动范围的反转因子。计算滚动窗口内成交量最大值与最小值之差（波动范围），取负号。成交量波动范围越大，因子值越低。

#### 交易含义
成交量波动范围反映了多空双方的博弈强度。当博弈进入白热化（成交量波动区间极大），往往意味着短期趋势即将耗尽，后续价格向反向运动。该因子值越低，反转做空信号越强；因子值越高（接近0），趋势延续或做多信号越强。

#### A股字段 → 期货字段映射
- `成交量` → `volume`

#### 评分指标
| 指标 | 数值 |
|------|------|
| **Q** | 0.9116 |
| **test_rankicir** | +0.4789 |
| **monotonicity** | +1.00 |
| **ls_sharpe** | +1.1290 |
| **composite_score** | 0.7371 |

#### 期货适配 pandas 表达式
```python
window = 20
vol_range = df['volume'].rolling(window=window).max() - df['volume'].rolling(window=window).min()
df['factor_neg_vol_range'] = -vol_range
```

---

### 3. `AM_ts_maxmin_signed_power_volume_8af03928`

#### 因子逻辑
成交量符号幂变换后的滚动波动范围因子。先对成交量进行 signed_power 变换（sign(x) * |x|^0.5，压缩长尾），再计算滚动窗口内的最大值与最小值之差。

#### 交易含义
成交量的平方根变换能够降低极端大额成交的权重，突出中等成交量区间的信息。该因子衡量"有效成交量波动"，高值表示资金在不同价位持续换手，市场存在方向性分歧；低值表示交投一致。因子值高时，结合价格趋势可判断突破有效性。

#### A股字段 → 期货字段映射
- `成交量` → `volume`

#### 评分指标
| 指标 | 数值 |
|------|------|
| **Q** | 0.9054 |
| **test_rankicir** | -0.5232 |
| **monotonicity** | -0.90 |
| **ls_sharpe** | -1.3770 |
| **composite_score** | 0.7456 |

#### 期货适配 pandas 表达式
```python
window = 20
# signed_power: sign(x) * abs(x)^0.5，volume>0 时等价于 sqrt(volume)
signed_power = df['volume'].pow(0.5)
df['factor_vol_signed_power_range'] = (
    signed_power.rolling(window=window).max() - signed_power.rolling(window=window).min()
)
```

---

### 4. `AM_ts_pct_change_signed_power_mul_6e2207c0`

#### 因子逻辑
成交量变化率与成交量符号幂的乘积因子。将成交量的滚动百分比变化与成交量的 signed_power（平方根）相乘，放大变化率的方向性信息。

#### 交易含义
该因子是"量价耦合"的纯量能版本。当成交量快速放大（高pct_change）且本身已处于高位（高signed_power）时，乘积产生极端值，往往对应着趋势的加速或顶部。正因子值表示放量上涨动能，负值表示放量下跌动能。

#### A股字段 → 期货字段映射
- `成交量` → `volume`

#### 评分指标
| 指标 | 数值 |
|------|------|
| **Q** | 0.9008 |
| **test_rankicir** | -0.4826 |
| **monotonicity** | -0.90 |
| **ls_sharpe** | -1.1245 |
| **composite_score** | 0.7227 |

#### 期货适配 pandas 表达式
```python
window = 20
vol_pct = df['volume'].pct_change(periods=window)
signed_power = df['volume'].pow(0.5)
df['factor_vol_pct_x_power'] = vol_pct * signed_power
```

---

### 5. `AM_div_ts_inverse_cv_volume_d69faf0f`

#### 因子逻辑
成交量与逆变异系数之比。逆变异系数（inverse_cv）= 均值/标准差，反映序列的"信噪比"。该因子 = volume / (mean(volume)/std(volume)) = volume * std(volume) / mean(volume)。

#### 交易含义
该因子衡量"成交量相对于其自身稳定性的倍数"。当成交量放大且历史波动较大（分母小）时，因子值飙升，表明资金以异常不稳定的方式涌入；当成交量放大但历史波动小（分母大）时，因子值温和，表明资金有序流入。高值常对应极端行情启动点。

#### A股字段 → 期货字段映射
- `成交量` → `volume`
- `成交额` → `amount`

#### 评分指标
| 指标 | 数值 |
|------|------|
| **Q** | 0.8717 |
| **test_rankicir** | +0.4689 |
| **monotonicity** | +1.00 |
| **ls_sharpe** | +1.5230 |
| **composite_score** | 0.7273 |

#### 期货适配 pandas 表达式
```python
window = 20
inv_cv = df['volume'].rolling(window=window).mean() / df['volume'].rolling(window=window).std()
df['factor_vol_div_inv_cv'] = df['volume'] / inv_cv
# 等价于: df['volume'] * df['volume'].rolling(window=window).std() / df['volume'].rolling(window=window).mean()
```

---

### 6. `AM_sub_gap_ts_pct_change_9572d239`

#### 因子逻辑
日内价格缺口与成交量变化率之差。gap = 收盘价 - 开盘价（日内涨跌），减去成交量的滚动百分比变化。捕捉价格变动与量能变化的偏离度。

#### 交易含义
经典的价量背离信号。当价格大幅跳空（gap大）但成交量变化率不匹配（pct_change小）时，表明价格运动缺乏量能支撑，为假突破或反转信号。因子值高表示"价涨量缩"或"价跌量缩"的背离；因子值低表示价量同步。

#### A股字段 → 期货字段映射
- `开盘价_复权` → `open_price`
- `成交量` → `volume`
- `收盘价_复权` → `close_price`

#### 评分指标
| 指标 | 数值 |
|------|------|
| **Q** | 0.8822 |
| **test_rankicir** | +0.4825 |
| **monotonicity** | +0.90 |
| **ls_sharpe** | +0.9063 |
| **composite_score** | 0.7061 |

#### 期货适配 pandas 表达式
```python
window = 20
gap = df['close_price'] - df['open_price']
vol_pct = df['volume'].pct_change(periods=window)
df['factor_gap_minus_vol_pct'] = gap - vol_pct
```

---

### 7. `AM_ts_inverse_cv_delta_volume_e7a5680e`

#### 因子逻辑
成交量一阶差分的逆变异系数。对成交量做差分（今日-昨日），计算滚动窗口内差分序列的均值与标准差之比（mean/std）。

#### 交易含义
该因子衡量"成交量变化率的趋势性"。高值表示成交量在过去N天内呈现一致的增长或减少（趋势性强），预示价格趋势可能延续；低值表示成交量变化杂乱无章（噪声大），趋势可靠性低。

#### A股字段 → 期货字段映射
- `成交量` → `volume`

#### 评分指标
| 指标 | 数值 |
|------|------|
| **Q** | 0.8879 |
| **test_rankicir** | -0.4671 |
| **monotonicity** | -0.90 |
| **ls_sharpe** | -1.0520 |
| **composite_score** | 0.7092 |

#### 期货适配 pandas 表达式
```python
window = 20
delta_vol = df['volume'].diff()
inv_cv = delta_vol.rolling(window=window).mean() / delta_vol.rolling(window=window).std()
df['factor_inv_cv_delta_vol'] = inv_cv
```

---

### 8. `AM_clip_ts_pct_change_signed_power_9e766938`

#### 因子逻辑
成交量符号幂变换后变化率的截断因子。先对成交量做 signed_power（平方根），计算百分比变化，再进行缩尾截断（去除极端异常值），保留稳健信号。

#### 交易含义
成交量数据中常包含极端异常值（如大单突击、系统错误），会扭曲pct_change计算。通过平方根压缩和缩尾截断，该因子只保留稳健的中等强度量能变化信号。因子值高表示稳健放量，因子值低表示稳健缩量。

#### A股字段 → 期货字段映射
- `成交量` → `volume`

#### 评分指标
| 指标 | 数值 |
|------|------|
| **Q** | 0.9016 |
| **test_rankicir** | -0.5174 |
| **monotonicity** | -0.80 |
| **ls_sharpe** | -0.6078 |
| **composite_score** | 0.7063 |

#### 期货适配 pandas 表达式
```python
window = 20
signed_power = df['volume'].pow(0.5)
pct = signed_power.pct_change(periods=window)
# 滚动缩尾：截断到 [5%, 95%] 分位数
q_low = pct.rolling(window=window).quantile(0.05)
q_high = pct.rolling(window=window).quantile(0.95)
df['factor_clip_vol_pct'] = pct.clip(lower=q_low, upper=q_high)
```

---

## 三、使用建议与注意事项

### 1. 窗口参数
- 上述表达式默认使用 `window = 20`（对应交易日），
  在期货Agent中建议根据品种波动特征调整：
  - 高波动品种（如原油、铜）：`window = 10`
  - 中低波动品种（如玉米、白糖）：`window = 20~30`

### 2. 信号方向
- 每个因子的 `monotonicity` 已标注方向：
  - `monotonicity = +1.0`：因子值越高 → 未来收益越高（正相关）
  - `monotonicity = -1.0`：因子值越低 → 未来收益越高（负相关，即做空信号）
- 在期货Agent中，可将因子值与其滚动分位数对比，生成多空信号：
  - 因子值 > 80%分位数 → 按 monotonicity 方向做多/做空
  - 因子值 < 20%分位数 → 反向操作

### 3. 组合使用
- 8个因子可分为两类：
  - **反转类**（#1、#2、#5）：高值/低值预示价格反转
  - **趋势/动量类**（#3、#4、#6、#7、#8）：高值/低值预示趋势延续
- 建议采用等权或ICIR加权合成复合信号，降低单一因子噪声。

### 4. 数据预处理
- 成交量字段需使用对应合约的实际成交量，连续合约需进行复权处理。
- 对于主力合约切换日，建议剔除或平滑该日成交量，避免换月导致的量异常。
- 所有因子计算前应进行 `dropna()` 处理，避免前向泄露。

### 5. 风险控制
- 量能因子在极端行情（如涨停/跌停、流动性枯竭）下可能失效，
  建议结合 `amount`（成交额）过滤低流动性品种。
- 建议设置因子值的绝对上下限（如 ±3σ），防止异常值导致仓位失控。

---

**报告结束**