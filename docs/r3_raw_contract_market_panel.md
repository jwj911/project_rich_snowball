# R3：raw_contract 日频研究宽表

> 实施日期：2026-07-24 至 2026-07-25
> 状态：R3 前两项已完成
> 关联计划：[后续迭代计划 R3](iteration_plan_20260724_follow_up.md)

## 范围

本批只实现合约原始口径的 `raw_contract` 日频研究宽表，不实现主力连续、前复权、
后复权或换月拼接。连续合约的价格语义和换月血缘将在 R3 后续子项中单独处理。

## 数据模型

新增 `agent_market_panel_daily`：

- 业务唯一键：`(data_view, variety_id, contract_id, period, trading_date)`；
- 第一版固定 `data_view=raw_contract`、`period=1d`；
- 保留 `symbol`、`contract_code`、OHLCV、`amount`、`open_interest` 和
  `settlement`；
- 物化 `ret_1/5/20`、`gap`、`amplitude`、`intraday_range` 和
  `volume_ratio_20`；
- `source_flags` 逐字段记录 `kline_data`、`fut_daily_data` 或估算来源；
- `quality_status` 标记 `good/warning/bad`。

## 构建规则

`services.market_panel.rebuild_raw_contract_daily_panel()`：

1. 以 `kline_data` 的 `1d/D` 合约级 K 线作为 OHLCV 主源；
2. 用匹配的 `fut_daily_data(ts_code, D, trade_date)` 补充成交额、持仓和结算价；
3. 当 `amount` 缺失时使用 `close * volume`，并写入
   `source_flags.amount=estimated_close_volume`；
4. 指定日期范围重建时仍读取该合约完整历史，以保证收益率和 20 日成交量比与全量
   重建一致；
5. 在同一事务内先删除目标范围旧行、再使用 `ON CONFLICT DO UPDATE` 写入，因而
   可重跑且不会遗留已删除源 K 线对应的宽表行。

## 批次、重试与质量快照

`run_raw_contract_daily_panel_build()` 在原始重建函数外提供构建编排：

- 每次尝试均写入既有的 `data_ingestion_runs`，使用
  `job_name=rebuild_agent_market_panel_daily`、`source=market_panel`；
- 同一个构建请求的全部尝试共享一个 `trace_id`，便于独立诊断；
- 成功记录保存物化写入与删除计数，以及只含状态、分数、覆盖范围和 issue code 的质量快照；
- 失败记录只保留 `trace_id`、异常类型、尝试次数和下一次退避时间，不记录原始行情、
  Provider Token 或异常原文；
- 仅 `ConnectionError`、`TimeoutError` 和 SQLAlchemy `OperationalError` 重试，退避
  间隔为 `retry_delay_seconds * 2^(attempt - 1)`；确定性数据错误立即失败；
- 每次尝试在保存点中运行。`--dry-run` 会回滚保存点，既不物化宽表，也不创建批次记录。

调度触发暂不在本批固定。它必须在具体合约日线和补充日线均完成后运行，后续与连续/
复权视图的构建顺序一并设计，避免产生不完整的自动化口径。

## 运行

```powershell
cd python
.venv\Scripts\python.exe scripts\rebuild_raw_contract_panel.py --symbol RB
.venv\Scripts\python.exe scripts\rebuild_raw_contract_panel.py --start-date 2026-01-01 --dry-run
.venv\Scripts\python.exe scripts\rebuild_raw_contract_panel.py --symbol RB --max-attempts 3 --retry-delay-seconds 1
```

构建成功时脚本输出统计、质量快照与 `run_id`。最终失败时仅输出
`error`、`error_type` 与 `trace_id`，并返回非零退出码。

## Agent 接入

- `DataCatalogService` 已登记 `agent_market_panel_daily`，提供字段、行数、日期和
  品种覆盖；
- `get_symbol_data_coverage()` 已返回该数据集覆盖；
- `DataQualityService.check_market_panel()` 检查空表、`bad` 与 `warning` 行数；
- DataAgent 可通过白名单 `query_database` 查询本表；私有数据 owner policy 不适用于
  该公共市场数据集；
- FactorMiningAgent 与 BacktestAgent 暂不直接消费本表，避免在未定义
  `data_view` 选择规则前改变既有回测语义。

## 验证

- SQLite：构建、字段血缘、派生字段、幂等重建、陈旧行清理、批次快照、可恢复重试、
  失败脱敏和脚本 dry-run；
- PostgreSQL：空库 Alembic 迁移至 `a1c2d3e4f5a6`，唯一键、重复构建与批次快照回归；
- 定向回归：SQLite `17 passed`，PostgreSQL `2 passed`；
- PostgreSQL 模式全量后端：`1017 passed, 1 skipped, 0 failed`；全仓库 Ruff 通过。

## 后续边界

R3 后续子项依次处理：

1. 主力连续与复权视图及换月血缘；
2. FactorMiningAgent、BacktestAgent 的显式 `data_view` 参数和消费侧实现。
