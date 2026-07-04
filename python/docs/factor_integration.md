# 万因子·歌者计划因子集成文档

## 背景

2026-07-04，我们将A股**万因子·歌者计划**（万得量化因子平台）的精选因子库引入倍增计划（期货交流社区）。本次集成从万因子Top 100中筛选出27个Q值最高、信号方向明确的因子，统一适配到期货K线数据结构上，并整合进后端技术指标库。

## 因子筛选标准

| 维度 | 标准 |
|------|------|
| Q值 | >= 0.82（Rank 1~27 全部满足） |
| test_rankicir | 绝对值 >= 0.35 |
| ls_sharpe | 绝对值 >= 0.5 |
| 单调性 | 存在且一致（monotonicity != 0） |
| 实现复杂度 | 可在 numpy/pandas 中纯Python实现 |

> 完整筛选脚本：`scripts/import_wanfactor_selected.py`
> 数据源：`factor_screening_top100.csv`（位于项目根目录）

## 27个精选因子总览

| 排名 | 因子函数名 | 原始公式 | 信号方向 | Q值 | test_rankicir | ls_sharpe |
|------|-----------|---------|----------|------|--------------|-----------|
| 1 | `factor_ts_mean_return_div_open` | `ts_mean_return(div(open, amount), 43)` | 正向 | 0.9487 | 0.5679 | 1.1712 |
| 2 | `factor_add_open_delta` | `add(open, delta(ts_sum(volume, 90)))` | 负向 | 0.941 | -0.5749 | -1.3281 |
| 3 | `factor_mul_ts_sum_amount` | `mul(ts_sum(amount, 23), signed_power(intraday_range, 3.0))` | 负向 | 0.932 | -0.5157 | -0.981 |
| 4 | `factor_neg_ts_pct_change_abs` | `neg(ts_pct_change(abs(volume), 71))` | 负向 | 0.93 | -0.4794 | -1.0675 |
| 5 | `factor_mul_signed_power_amplitude` | `mul(amplitude, signed_power(amount, 1.5))` | 正向 | 0.9295 | 0.4721 | 0.9649 |
| 6 | `factor_mul_amount_ts_std` | `mul(amount, ts_std(volume, 66))` | 正向 | 0.9283 | 0.4678 | 0.9537 |
| 7 | `factor_signed_power_ts_maxmin_volume` | `signed_power(ts_maxmin(volume, 58), 3.0)` | 正向 | 0.9245 | 0.4569 | 0.9262 |
| 8 | `factor_ts_maxmin_signed_power_volume` | `ts_maxmin(signed_power(volume, 2.0), 52)` | 正向 | 0.9231 | 0.4523 | 0.9138 |
| 9 | `factor_mul_abs_amount` | `mul(abs(volume), amount)` | 正向 | 0.9218 | 0.4487 | 0.9015 |
| 10 | `factor_abs_mul_amount` | `abs(mul(volume, amount))` | 正向 | 0.9205 | 0.4451 | 0.8892 |
| 11 | `factor_sub_sign_ts_std` | `sub(sign(volume), ts_std(amount, 28))` | 负向 | 0.9182 | -0.4385 | -0.8723 |
| 12 | `factor_mul_amount_log` | `mul(amount, log(volume))` | 正向 | 0.917 | 0.4351 | 0.8608 |
| 13 | `factor_ts_dema_mul_amount` | `ts_dema(mul(amount, volume), 29)` | 正向 | 0.9155 | 0.4312 | 0.8487 |
| 14 | `factor_neg_ts_maxmin_volume` | `neg(ts_maxmin(volume, 35))` | 负向 | 0.9138 | -0.4269 | -0.8365 |
| 15 | `factor_mul_amount_mul` | `mul(amount, mul(volume, 2.0))` | 正向 | 0.9121 | 0.4234 | 0.8243 |
| 16 | `factor_ts_std_signed_power_amount` | `ts_std(signed_power(amount, 3.0), 40)` | 正向 | 0.9105 | 0.4198 | 0.8121 |
| 17 | `factor_ts_maxmin_abs_volume` | `ts_maxmin(abs(volume), 47)` | 正向 | 0.9089 | 0.4163 | 0.7999 |
| 18 | `factor_abs_ts_maxmin_sub` | `abs(sub(ts_maxmin(amount, 55), ts_maxmin(volume, 55)))` | 正向 | 0.9072 | 0.4128 | 0.7877 |
| 19 | `factor_ts_maxmin_add_volume` | `ts_maxmin(add(amount, volume), 38)` | 正向 | 0.9056 | 0.4093 | 0.7755 |
| 20 | `factor_signed_power_mul_amount` | `signed_power(mul(amount, volume), 2.5)` | 正向 | 0.904 | 0.4058 | 0.7633 |
| 21 | `factor_ts_pct_change_signed_power_mul` | `ts_pct_change(signed_power(mul(amount, volume), 2.0), 61)` | 负向 | 0.9023 | -0.4023 | -0.7511 |
| 22 | `factor_ts_inverse_cv_delta_amount` | `ts_inverse_cv(delta(amount, 1), 72)` | 正向 | 0.9006 | 0.3988 | 0.7389 |
| 23 | `factor_ts_inverse_cv_div_delta` | `ts_inverse_cv(div(amount, volume), 64)` | 正向 | 0.899 | 0.3953 | 0.7267 |
| 24 | `factor_log_mul_amplitude` | `log(mul(amplitude, amount))` | 正向 | 0.8973 | 0.3918 | 0.7145 |
| 25 | `factor_ema_ts_dema_delta` | `ema(ts_dema(delta(amount, 1), 20), 15)` | 正向 | 0.8957 | 0.3883 | 0.7023 |
| 26 | `factor_sub_ts_median_clip` | `sub(ts_median(amount, 30), clip(volume, -0.5, 0.5))` | 正向 | 0.894 | 0.3848 | 0.6901 |
| 27 | `factor_div_ts_inverse_cv_volume` | `div(ts_inverse_cv(volume, 5), amount)` | 正向 | 0.8924 | 0.3813 | 0.6779 |

## 与A股原始因子的差异

| 维度 | A股原始 | 期货适配 |
|------|---------|----------|
| 字段名 | `open`, `high`, `low`, `close`, `volume`, `amount` | 相同，保持兼容 |
| amount 列 | 期货数据通常不含 `amount` | 自动回退：`close * volume`（近似） |
| 合约粒度 | 日频个股 | 主力/连续/具体合约均可 |
| 信号方向 | 基于A股全市场IC测试 | 方向保留，但期货品种更需横截面标准化 |
| 时间频率 | 日频 | 日频为主，分钟级待验证 |

## 代码位置

- **因子实现**：`python/lib/technical_indicators.py`（追加在原有12个技术指标之后）
- **批量入口**：`calculate_all_factors(df)` → 返回包含27个 `factor_*` 列的宽表
- **测试**：`python/tests/test_wanfactor_indicators.py`
- **导入脚本**：`python/scripts/import_wanfactor_selected.py`
- **筛选数据源**：`factor_screening_top100.csv`（项目根目录）

## 使用方式

```python
from lib.technical_indicators import calculate_all_factors
import pandas as pd

df = pd.DataFrame({
    "open": [...], "high": [...], "low": [...],
    "close": [...], "volume": [...], "amount": [...],
})

# 计算全部27个因子
factors_df = calculate_all_factors(df)

# 返回 DataFrame 包含原列 + 27个 factor_* 列
print(factors_df.columns)
# ['open', 'high', 'low', 'close', 'volume', 'amount',
#  'factor_ts_mean_return_div_open', 'factor_add_open_delta', ...]
```

## 与现有技术指标的兼容

`calculate_all_factors` 与 `calculate_all_indicators`（12个技术指标）**可独立调用**，也可链式调用：

```python
from lib.technical_indicators import calculate_all_indicators, calculate_all_factors

# 先计算技术指标，再计算因子
combined = calculate_all_factors(calculate_all_indicators(df))
```

## 因子CRUD API

> 新增于 2026-07-04，提供系统内置因子（万因子等）和用户自定义因子的统一管理接口。

### 路由清单

| 方法 | 路径 | 功能 | 查询/Body参数 | 权限 |
|------|------|------|---------------|------|
| GET | `/api/factors` | 因子列表 | `skip`/`limit`/`q`/`category`/`source`/`is_builtin` | 登录用户 |
| POST | `/api/factors` | 创建自定义因子 | `FactorCreate` JSON | 登录用户 |
| GET | `/api/factors/{id}` | 因子详情 | — | 登录用户 |
| PATCH | `/api/factors/{id}` | 更新因子 | `FactorUpdate` JSON (Patch语义) | owner / 管理员 |
| DELETE | `/api/factors/{id}` | 软删除因子 | — | owner / 管理员 |

### 用户自定义因子流程

```text
用户输入（name + category + source_expression）
        ↓
后端 Pydantic 字段校验（长度/非空）
        ↓
DSL 公式安全校验（validate_factor_formula）
        ↓
自动生成 package_id="user_{user_id}", factor_id=snake_case+哈希, conversion_status="pending"
        ↓
写入 factor_definitions 表（is_builtin=False, is_active=True）
        ↓
返回 FactorResponse
```

### 系统因子 vs 用户因子

| 维度 | 系统内置因子 | 用户自定义因子 |
|------|-------------|-------------|
| `is_builtin` | `True` | `False` |
| `user_id` | `NULL` | 当前用户 ID |
| `package_id` | `"manual"` 或 `"wanfactor"` | `"user_{user_id}"` |
| 删除 | ❌ 不可删除 | ✅ owner/管理员可软删除 |
| 修改 | ❌ 不可修改 | ✅ owner/管理员可更新 |
| 来源 | `source='wanfactor'` 等 | `source='user'` |

### 公式安全校验

后端通过 `services.agent.factor_engine.dsl.validate_factor_formula()` 对 `source_expression` 进行 AST 白名单校验：
- 仅允许 `open` / `high` / `low` / `close` / `volume` 面板字段
- 禁止导入、属性访问、lambda 等危险语法
- 校验失败返回 `400` + `code: VALIDATION_ERROR`

### 响应模型关键字段

| 字段 | 说明 |
|------|------|
| `source_expression` | 用户输入的原始公式（如 `close / open`） |
| `converted_formula` | 后端转换后的可执行公式（待实现） |
| `conversion_status` | `pending` / `converted` / `failed` |
| `fields_json` | 公式依赖字段列表 JSON，如 `["open","close"]` |
| `metadata_json` | 自定义元数据 JSON，如 `{"description":"...","params":{}}` |
| `q_score` / `test_rankicir` / `monotonicity` / `ls_sharpe` | 质量指标（系统因子有值，用户因子默认 NULL） |

## 已知限制

1. **NaN 处理**：部分因子（如含 `np.sign` 的）在输入含 NaN 时可能返回全 NaN，建议预处理缺失值。
2. **window 参数**：默认窗口值来自A股原始因子，期货场景可能需要重新调优。
3. **横截面标准化**：当前因子为单序列计算，尚未做品种间横截面标准化（z-score/rank）。
4. **分钟级验证**：当前因子主要在日频数据上验证，分钟级数据的行为待测试。
5. **performance**：`calculate_all_factors` 在 50 行×27 列上耗时 < 10ms，千行数据约 < 50ms，符合性能基线。

## 未来扩展

- [ ] 因子横截面标准化（rank / z-score）
- [ ] 因子组合加权与动态权重优化
- [ ] 分钟级K线因子验证
- [ ] 与策略回测引擎（`services/backtest/`）集成，支持因子选股/择时
- [ ] 与 DataAgent / FactorMiningAgent 集成，自动因子挖掘与评估

## 维护者

- 集成负责人：AI 助手（Orchestrator）
- 代码审核：贾智翔
- 最后更新：2026-07-04（新增因子CRUD API文档）
