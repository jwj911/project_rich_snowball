# R4：DSL Transform 与 Walk-Forward 验证

> 状态：已完成
> 日期：2026-07-26
> 依赖：[`r3_raw_contract_market_panel.md`](r3_raw_contract_market_panel.md)

## 目标

R4 让策略编译、回测执行和验证报告使用同一组可审计契约：

1. 已允许的 DSL `transform` 必须有确定的执行语义；
2. 未知或参数不完整的 transform 必须在数据读取前明确拒绝；
3. walk-forward 输出必须区分完成、未运行、部分失败和稳定性判断；
4. 数据覆盖、质量状态、样本内/窗口样本外指标必须进入报告和生命周期记录。

## Transform 执行契约

实现位于 `python/services/backtest/transform_contract.py`。

| Transform | 状态 | 执行语义 | 参数约束 |
|---|---|---|---|
| `multiply_indicator2` | canonical | 右侧阈值为 `indicator2 * value` | 必须有 `indicator2`；`value` 为有限且大于 0 的数值 |
| `multiply_value` | 兼容别名 | 同 `multiply_indicator2` | 与 canonical 相同 |

策略编译器现在生成 `multiply_indicator2`。保留 `multiply_value` 仅为了执行历史策略 JSON，不能新增依赖。

`StrategyValidator`、`run_dsl_backtest()` 和 `_eval_conditions()` 共享这一契约：

- 编译时返回可读校验错误；
- 回测服务在 cache lookup 和数据读取前抛出 `TransformContractError`；
- 引擎直接调用也会拒绝未知 transform，不能退化为无信号。

可读解释与引擎使用同一个右侧表达式，例如：

```text
volume > volume_sma20 × 1.5
```

## Walk-Forward 语义

实现位于 `python/services/backtest/walk_forward.py`。

`WalkForwardConfig` 的默认值为：

```text
train_bars = 120
test_bars = 60
step_bars = 60
window_mode = expanding
min_windows = 2
```

窗口按实际已观测的日线日期建立，不按自然日估算：

- `expanding`：训练窗口从第一个可用 bar 开始扩展；
- `rolling`：训练窗口保持 `train_bars` 长度；
- 每个训练段严格早于对应测试段；
- 当前仅支持 `1d`，避免日内数据按日期截断导致边界不一致。

输出结构包含：

- `status`：`completed`、`partial` 或 `not_run`；
- `validation_status`：`stable`、`unstable`、`inconclusive` 或 `not_run`；
- 每个窗口的 IS / OOS 日期、指标和数据口径；
- OOS 收益和 Sharpe 汇总、正收益窗口比例、IS/OOS Sharpe 一致性；
- 数据覆盖、宽表质量状态和解释提示。

窗口不足、执行失败、非日线或质量提示均会写入 `reason` / `warnings`。这些情形不能表示为验证通过。

### 解释边界

当前服务评估的是**冻结 DSL 的时间窗口稳定性**。若 DSL 是在完整历史上搜索或调参得到的，结果的
`independent_oos` 固定为 `false`，不得作为逐窗口重新寻优后的独立 OOS 验收。

策略进化报告已将旧的全历史回测称为“全样本回测”，将既有单次切分称为“留出段复测”，避免误称为独立 OOS。

## 持久化与查询

`StrategyLifecycleDB.walk_forward_metrics` 为既有字段，R4 不新增 Alembic migration。

- `StrategyLifecycleManager.register_strategy()` 首次注册写入 IS、留出段和 walk-forward 报告；
- 已有生命周期记录会原子更新传入的验证指标；
- `get_lifecycle_summary()` 返回解析后的 `walk_forward_metrics`；
- `/api/evolution/lifecycles` 和 `/api/evolution/lifecycle/{strategy_id}` 已通过
  `StrategyLifecycleResponse` 返回该字段；
- `/api/strategies/{strategy_id}/backtest` 将回测结果内的 walk-forward 报告保存至
  `backtest_runs.result_json`，并同步策略生命周期。

## 数据边界

为确保窗口首尾日期包含完整日 K，`_get_kline_data()` 的日期筛选优先使用
`KlineDataDB.trading_date`；历史行缺少该字段时回退到 SQL `date(trading_time)`。

BacktestAgent、StrategyEvolutionAgent 和 walk-forward 报告都显示：

- 数据集、`data_view`、具体合约与构建 `trace_id`（适用时）；
- 覆盖起止、bar 数和质量评分；
- 宽表 `quality_statuses` 与明确 warning。

## 回归范围

- `tests/test_backtest_transform_contract.py`：canonical / legacy transform、未知 transform 与参数拒绝、编译校验；
- `tests/test_backtest_engine.py`：StrategyParser 到 DSL 回测引擎的端到端 transform 路径；
- `tests/test_walk_forward.py`：扩展/滚动窗口、窗口指标、数据不足不通过；
- `tests/test_strategy_lifecycle.py`：walk-forward 写入、更新和摘要读取；
- 既有 `test_backtest_agent.py`、`test_strategy_compiler.py`、`test_multi_condition_strategy.py`、
  `test_agent_streaming.py`：报告与 canonical compiler 输出兼容性。

## 验证记录

- SQLite 全量后端：`1026 passed, 15 skipped, 0 failed`；
- PostgreSQL：隔离数据库从空库升级至 `c0d1e2f3a4b5`，宽表 schema/rebuild、构建批次与
  日 K 首尾日期包含式筛选专项：`3 passed`；验证库已删除；
- `ruff check .`、本轮 `py_compile` 和 `git diff --check`：通过。
