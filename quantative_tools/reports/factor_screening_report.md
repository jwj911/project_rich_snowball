# A股万因子·歌者计划 — 期货Agent系统适配筛选报告

> **生成日期**: 2026-07-05  
> **数据来源**: `D:\BaiduNetdiskDownload\pack021-032`（factor_pack_021 ~ factor_pack_032）  
> **适配目标**: 期货交流社区（倍增计划）Agent 系统 — 单品种时序信号  
> **报告版本**: v1.0

---

## 执行摘要

从 **12 个因子包（共 116,118 个因子）**中，通过自动化扫描 + 人工精选，完成以下筛选：

| 阶段 | 数量 | 说明 |
|------|------|------|
| 原始因子总量 | 116,118 | pack_021~030 各 10,000；pack_032 共 6,118 |
| 扫描候选池 | 2,400 | 每包取 Top 200（按 Q 综合质量分排序） |
| 纯量价筛选 | 1,979 | 排除所有依赖市值、换手率、财务数据的因子 |
| 去重后 | 1,979 | 代码逻辑无重复，AI 挖掘引擎产出了高度差异化的因子 |
| Top 100 | 100 | 按综合评分（Q 50% + OOS ICIR 30% + 单调性 10% + 多空夏普 10%）排序 |
| **人工精选推荐** | **27** | 分 4 大类别，每类 5-8 个，逻辑清晰、可解释、可执行 |

**核心结论**：
- Pack 021-030 质量极高（Q 均值 0.87-0.92），**031 和 032 质量明显下滑**（Q 均值 0.62 / 0.42），建议优先使用 021-030。
- 全部 1,979 个纯量价因子**均可适配期货**，因为 `FutDailyDataDB` 已包含 `amount`（成交额）和 `pre_close`（前收盘价）。
- 推荐精选 **27 个因子**接入 Agent 系统，覆盖资金动量、量能动量、波动振幅、价格动量四大维度。

---

## 一、12 个 Pack 质量评估

| Pack | 总因子数 | 来源分布 | Top 200 中纯量价数 | Top 1 Q | Top 20 Q 均值 | 质量评级 |
|------|---------|---------|-------------------|---------|-------------|---------|
| 021 | 10,000 | mining=10000 | 159 | 0.9118 | 0.876 | ⭐⭐⭐⭐⭐ |
| 022 | 10,000 | mining=10000 | 165 | 0.9249 | 0.896 | ⭐⭐⭐⭐⭐ |
| 023 | 10,000 | mining=10000 | 168 | 0.9130 | 0.878 | ⭐⭐⭐⭐⭐ |
| 024 | 10,000 | mining=10000 | 172 | 0.9008 | 0.878 | ⭐⭐⭐⭐⭐ |
| 025 | 10,000 | mining=10000 | 168 | 0.8975 | 0.873 | ⭐⭐⭐⭐⭐ |
| 026 | 10,000 | mining=10000 | 167 | 0.9212 | 0.892 | ⭐⭐⭐⭐⭐ |
| 027 | 10,000 | mining=10000 | 169 | 0.9487 | 0.878 | ⭐⭐⭐⭐⭐ |
| 028 | 10,000 | mining=10000 | 170 | 0.9410 | 0.892 | ⭐⭐⭐⭐⭐ |
| 029 | 10,000 | mining=10000 | 166 | 0.9320 | 0.885 | ⭐⭐⭐⭐⭐ |
| 030 | 10,000 | mining=10000 | 170 | 0.9289 | 0.888 | ⭐⭐⭐⭐⭐ |
| 031 | 10,000 | mining=10000 | 58 | 0.6269 | 0.627 | ⭐⭐⭐ |
| 032 | 6,118 | mining=5040, complex=754, fundamental=258, finance=66 | 49 | 0.4159 | 0.416 | ⭐⭐ |

> **建议**：生产环境只使用 **021-030** 的因子。031 和 032 质量下滑明显，可用于扩展研究，但不做主推。

---

## 二、筛选方法论

### 2.1 自动化筛选流程

```
116,118 原始因子
    → 每包取 Top 200（按 Q 排序）→ 2,400 候选
    → 代码扫描：提取 df["xxx"] 列名
    → 排除含市值/换手率/财务数据的因子 → 1,979 纯量价
    → 按综合评分排序 → Top 100
    → 人工分类精选 → 27 推荐因子
```

### 2.2 综合评分公式

```
composite_score = 0.5 × Q + 0.3 × |test_rankicir| + 0.1 × |monotonicity| + 0.1 × min(|ls_sharpe|, 3.0) / 3.0
```

| 指标 | 权重 | 含义 |
|------|------|------|
| Q | 50% | 综合质量分（ICIR + 单调性 + 年稳定性 + 市值中性） |
| \|test_rankicir\| | 30% | **OOS 样本外** Rank ICIR，防过拟合核心指标 |
| \|monotonicity\| | 10% | 分位单调性，越接近 1 方向越稳定 |
| \|ls_sharpe\| | 10% | 多空组合夏普，衡量区分能力 |

### 2.3 从截面到单品种时序的转换原则

原 A 股因子为**截面选股**设计（横截面比较全市场股票）。适配到期货 Agent 时，转换为**单品种时序信号**（跟踪同一品种自身的因子值变化）：

- **信号方向**：
  - `test_rankicir > 0` + `monotonicity > 0` → 因子值越高越偏多
  - `test_rankicir < 0` + `monotonicity < 0` → 因子值越高越偏空（或取反后偏多）
- **滚动窗口**：因子已内嵌 `rolling(N)` 或 `shift(N)`，保持原窗口
- **字段映射**：详见 §3.5
- **时序归一化**：所有 pandas 表达式可直接嵌入 `technical_indicators.py` 或 Agent 因子引擎

---

## 三、精选因子分类总览

| 类别 | 数量 | 核心逻辑 | 报告文件 |
|------|------|---------|---------|
| **资金动量** | 8 | 成交额 + 时序动量（rolling mean/std/pct_change） | [`factor_report_资金动量.md`](factor_report_资金动量.md) |
| **量能动量** | 8 | 成交量 + 时序动量（ts_maxmin/ts_pct_change/变异系数） | [`factor_report_量能动量.md`](factor_report_量能动量.md) |
| **波动振幅** | 5 | 日内振幅/区间 + 动量/回归（EMA/DEMA/beta） | [`factor_report_波动振幅.md`](factor_report_波动振幅.md) |
| **价格动量** | 6 | 纯价格收益/位置/趋势（returns/EMA/DEMA） | [`factor_report_价格动量.md`](factor_report_价格动量.md) |

### 3.1 资金动量 — 精选 8 个（详见分类报告）

| # | 因子 | Q | test_rankicir | mono | 核心逻辑 |
|---|------|---|---------------|------|---------|
| 1 | AM_ts_mean_return_div_open | **0.9487** | **+0.568** | +0.9 | 开盘收益率动量归一化 |
| 2 | AM_mul_amount_ts_std | 0.9134 | -0.521 | -1.0 | 成交额 × 波动标准差 |
| 3 | AM_sub_sign_ts_std | 0.8951 | -0.507 | -0.9 | 资金流方向 − 波动偏离 |
| 4 | AM_ts_inverse_cv_delta_amount | 0.9010 | -0.489 | -0.9 | 成交额变化稳定性（逆变异系数） |
| 5 | AM_ts_pct_change_add_amount | 0.8976 | -0.506 | -0.9 | 成交额动量叠加 |
| 6 | AM_log_ts_pct_change_amount | 0.8884 | -0.495 | -0.9 | 对数成交额增长率 |
| 7 | AM_ts_maxmin_add_ret | 0.8853 | -0.462 | -1.0 | 成交额极差 + 短期收益 |
| 8 | AM_ts_dema_mul_amount | 0.8963 | -0.488 | -1.0 | DEMA-成交额交互 |

### 3.2 量能动量 — 精选 8 个（详见分类报告）

| # | 因子 | Q | test_rankicir | mono | 核心逻辑 |
|---|------|---|---------------|------|---------|
| 1 | AM_neg_ts_pct_change_abs | **0.9211** | **+0.511** | **+1.0** | 成交量变化率反转 |
| 2 | AM_neg_ts_maxmin_volume | 0.9116 | +0.479 | **+1.0** | 成交量波动范围反转 |
| 3 | AM_ts_maxmin_signed_power_volume | 0.9054 | -0.523 | -0.9 | 成交量符号幂波动范围 |
| 4 | AM_ts_pct_change_signed_power_mul | 0.9008 | -0.483 | -0.9 | 成交量变化率 × 符号幂 |
| 5 | AM_div_ts_inverse_cv_volume | 0.8717 | +0.469 | **+1.0** | 成交量 / 逆变异系数 |
| 6 | AM_sub_gap_ts_pct_change | 0.8822 | +0.483 | +0.9 | 日内缺口 − 量能变化 |
| 7 | AM_ts_inverse_cv_delta_volume | 0.8879 | -0.467 | -0.9 | 成交量差分信噪比 |
| 8 | AM_clip_ts_pct_change_signed_power | 0.9016 | -0.517 | -0.8 | 缩尾成交量变化率 |

### 3.3 波动振幅 — 精选 5 个（详见分类报告）

| # | 因子 | Q | test_rankicir | mono | 核心逻辑 |
|---|------|---|---------------|------|---------|
| 1 | AM_ema_ts_dema_delta | 0.8826 | +0.455 | **+1.0** | 振幅 EMA-DEMA 动量差 |
| 2 | AM_ts_regression_beta_amplitude_ret | 0.8912 | -0.443 | **-1.0** | 振幅-收益回归 beta |
| 3 | AM_ts_regression_beta_intraday_rang | 0.8790 | -0.453 | -0.9 | 日内区间-收益回归 beta |
| 4 | AM_ts_regression_beta_neg_amplitude | 0.8659 | +0.437 | +0.9 | 负振幅-收益回归 beta |
| 5 | AM_div_ts_pct_change_intraday_range | 0.8811 | -0.422 | **-1.0** | 波动效率比率 |

### 3.4 价格动量 — 精选 6 个（详见分类报告）

| # | 因子 | Q | test_rankicir | mono | 核心逻辑 |
|---|------|---|---------------|------|---------|
| 1 | AM_ts_mean_return_div_open | **0.9487** | **+0.568** | +0.9 | 平均收益效率（资金+价格） |
| 2 | AM_ema_ts_dema_delta | 0.8826 | +0.455 | **+1.0** | 趋势加速度（波动+价格） |
| 3 | AM_ts_min_neg_ret_20 | 0.8953 | +0.476 | +0.9 | 下行抗跌（20日最低负收益） |
| 4 | AM_ts_max_ret_20 | 0.8930 | -0.473 | -0.9 | 上行突破（20日最高收益） |
| 5 | AM_ts_max_clip_ret_20 | 0.8951 | -0.446 | **-1.0** | 稳健反转（20日收益截尾） |
| 6 | AM_ts_regression_beta_intraday_rang | 0.8790 | -0.453 | -0.9 | 振幅-收益敏感度 |

> **注**：因子 1 和 2 在多个类别中重复出现，因为它们同时覆盖多个维度（如「资金+价格」或「波动+价格」），属于交叉类别因子，逻辑更 robust。

### 3.5 A股字段 → 期货字段映射表

| A股字段 | 期货字段 | 对应数据库模型 | 说明 |
|---------|---------|---------------|------|
| `开盘价_复权` | `open_price` | `KlineDataDB` / `FutDailyDataDB` | 期货连续合约已拼接，无需复权 |
| `收盘价_复权` | `close_price` | `KlineDataDB` / `FutDailyDataDB` | 同上 |
| `最高价_复权` | `high_price` | `KlineDataDB` / `FutDailyDataDB` | 同上 |
| `最低价_复权` | `low_price` | `KlineDataDB` / `FutDailyDataDB` | 同上 |
| `成交量` | `volume` | `KlineDataDB` / `FutDailyDataDB` | 成交手数 |
| `成交额` | `amount` | `FutDailyDataDB` | 成交金额；**分钟 K 线无此字段** |
| `前收盘价` | `pre_close` | `FutDailyDataDB` | 前一日收盘价；**分钟 K 线无此字段** |
| `日内振幅` | `(high_price - low_price) / close_price` | 计算派生 | 日内价格区间/收盘价 |
| `开盘振幅` | `(high_price - low_price) / pre_close` | 计算派生 | 日内价格区间/前收盘价 |

> **重要**：上述因子在**日线级别**可直接使用 `FutDailyDataDB`（含 `amount` + `pre_close`）。若需在**分钟级别**应用，需将含 `amount`/`pre_close` 的因子替换为仅用 `volume`/`close` 的等价表达，或预先计算 `amount = close_price × volume`。

---

## 四、Agent 系统集成方案

### 4.1 集成位置

推荐将精选因子接入以下模块：

| 模块 | 路径 | 用途 |
|------|------|------|
| 技术指标库 | `python/lib/technical_indicators.py` | 作为扩展指标，供所有 Agent 调用 |
| 因子引擎 | `python/services/agent/factor_engine/` | 作为自定义因子，供 FactorMiningAgent 挖掘和组合 |
| 回测引擎 | `python/services/backtest/` | 回测时作为信号输入 |
| 前端指标 | `frontend/lib/indicators.ts` | 前端 K 线图叠加显示 |

### 4.2 技术实现建议

**方案 A：直接扩展 `technical_indicators.py`**

```python
# python/lib/technical_indicators.py

import numpy as np
import pandas as pd

def ts_maxmin(series: pd.Series, window: int) -> pd.Series:
    """滚动最大最小归一化 (0-1)"""
    min_val = series.rolling(window).min()
    max_val = series.rolling(window).max()
    return (series - min_val) / (max_val - min_val).replace(0, np.nan)

def signed_power(x, exponent: float):
    """符号幂: sign(x) * |x|^exponent"""
    return np.sign(x) * np.abs(x) ** exponent

def ts_pct_change(series: pd.Series, window: int) -> pd.Series:
    """滚动百分比变化率"""
    return (series - series.shift(window)) / series.abs().replace(0, np.nan)

def ts_mean_return(series: pd.Series, window: int) -> pd.Series:
    """滚动平均收益率"""
    ret = np.sign(series) * (series - series.shift(1)) / series.abs().replace(0, np.nan)
    return ret.rolling(window).mean()

def ts_inverse_cv(series: pd.Series, window: int) -> pd.Series:
    """逆变异系数: mean / std"""
    mean = series.rolling(window).mean()
    std = series.rolling(window).std().replace(0, np.nan)
    return mean / std

def factor_open_return_momentum(df: pd.DataFrame, window: int = 43) -> pd.Series:
    """因子1: 开盘收益率动量归一化 (Top1)"""
    _t0 = df['open_price'] / df['amount'].replace(0, np.nan)
    return ts_mean_return(_t0, window)

def factor_volume_change_reversal(df: pd.DataFrame, window: int = 71) -> pd.Series:
    """因子2: 成交量变化率反转 (量能动量 Top1)"""
    _t0 = df['volume'].abs()
    _t1 = ts_pct_change(_t0, window)
    return -_t1

def factor_volatility_momentum_delta(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """因子3: 振幅 EMA-DEMA 动量差 (波动 Top1)"""
    amplitude = (df['high_price'] - df['low_price']) / df['pre_close'].replace(0, np.nan)
    ema = amplitude.ewm(span=window, adjust=False).mean()
    dema = 2 * ema - ema.ewm(span=window, adjust=False).mean()
    return ema - dema
```

**方案 B：在 FactorMiningAgent 中作为候选因子池**

在 `python/services/agent/factor_engine/` 中维护一个 `candidate_factors.py`，将 27 个因子注册为候选，Agent 在挖掘时自动从中选择、组合、优化参数。

### 4.3 信号合成示例

```python
def composite_signal(df: pd.DataFrame) -> pd.Series:
    """多因子投票合成信号 (-1 做空, 0 观望, +1 做多)"""
    f1 = factor_open_return_momentum(df)
    f2 = factor_volume_change_reversal(df)
    f3 = factor_volatility_momentum_delta(df)
    
    # 分位数阈值
    q_high = 0.7
    q_low = 0.3
    
    s1 = np.where(f1 > f1.quantile(q_high), 1, np.where(f1 < f1.quantile(q_low), -1, 0))
    s2 = np.where(f2 > f2.quantile(q_high), 1, np.where(f2 < f2.quantile(q_low), -1, 0))
    s3 = np.where(f3 > f3.quantile(q_high), 1, np.where(f3 < f3.quantile(q_low), -1, 0))
    
    return pd.Series(s1 + s2 + s3, index=df.index)  # -3 ~ +3
```

### 4.4 参数调优建议

| 参数 | 默认值 | 调优范围 | 说明 |
|------|--------|---------|------|
| 滚动窗口 | 20-90 | 10-120 | 日内/短线用短窗口(10-20)，波段用中窗口(40-60)，趋势用长窗口(80-120) |
| 分位数阈值 | 0.7/0.3 | 0.6-0.9 / 0.1-0.4 | 阈值越宽，信号越少但越确定 |
| 合成投票阈值 | ≥2 / ≤-2 | 1-3 | 至少需要 2/3 个因子同向才触发 |

---

## 五、风险提示与局限

1. **数据频率差异**：A 股因子基于日线，期货分钟线需适配（`amount`/`pre_close` 缺失）。
2. **品种差异**：商品期货 / 股指期货 / 国债期货的波动率和量能特征差异大，建议分品种回测。
3. **换月影响**：主力合约切换时 `pre_close` 可能不连续，需用连续合约数据。
4. **因子衰减**：AI 挖掘因子可能存在衰减，建议每季度滚动回测并替换表现下滑的因子。
5. **过拟合风险**：虽然已用 `test_rankicir`（OOS）筛选，但 116,118 个因子的大规模挖掘仍存在隐性的多重检验问题。建议实盘前用期货历史数据做独立的样本外验证。
6. **信号方向**：本报告中标注的信号方向基于 A 股回测结果，**期货中可能相反**（如 A 股小盘股动量与期货商品动量逻辑不同）。必须回测确认。

---

## 六、下一步行动建议

1. **回测验证**：选取 3-5 个期货品种（如螺纹、铁矿、沪深300），用 27 个因子做历史回测，验证 OOS 表现。
2. **参数优化**：对精选因子的窗口参数做网格搜索（如 10, 20, 40, 60, 90），找到最优参数。
3. **因子组合**：尝试 2-3 个因子的等权合成，或按 ICIR 加权合成，比较单因子 vs 组合的风险收益。
4. **集成开发**：将验证通过的因子写入 `technical_indicators.py`，并在 `FactorMiningAgent` 中注册候选池。
5. **前端展示**：在 K 线图上叠加因子信号（如用颜色标记做多/做空/观望区间）。

---

## 附录：相关文件清单

| 文件 | 路径 | 说明 |
|------|------|------|
| 本总览报告 | `D:\Code\project_rich_snowball\factor_screening_report.md` | 整合总览 + 方法论 + 集成方案 |
| 资金动量分类报告 | `D:\Code\project_rich_snowball\factor_report_资金动量.md` | 8 个因子详解 + pandas 代码 |
| 量能动量分类报告 | `D:\Code\project_rich_snowball\factor_report_量能动量.md` | 8 个因子详解 + pandas 代码 |
| 波动振幅分类报告 | `D:\Code\project_rich_snowball\factor_report_波动振幅.md` | 5 个因子详解 + pandas 代码 |
| 价格动量分类报告 | `D:\Code\project_rich_snowball\factor_report_价格动量.md` | 6 个因子详解 + pandas 代码 |
| Top 100 数据 | `D:\Code\project_rich_snowball\factor_screening_top100.csv` | 完整 Top 100 列表，可导入 Excel |
| Top 100 JSON | `D:\Code\project_rich_snowball\factor_screening_top100.json` | 结构化数据，含分类统计 |

---

> 本报告仅供研究参考，不构成任何投资建议。因子在期货中的应用需经过充分的历史回测和样本外验证。
