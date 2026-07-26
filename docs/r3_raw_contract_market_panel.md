# R3：多视图日频研究宽表

> 实施日期：2026-07-24 至 2026-07-26
> 状态：R3.1 至 R3.6 已完成
> 关联计划：[后续迭代计划 R3](iteration_plan_20260724_follow_up.md)

## 范围

本批实现以下日频研究视图：

- `raw_contract`：具体合约原始 OHLCV；
- `main_continuous`：按 `contract_rollovers` 选择实际主力合约的连续价格；
- `main_back_adjusted`：沿用既有连续 K 线的加性 backward 算法，较早主力段减去后续换月价差；
- `main_forward_adjusted`：加性 forward 口径，较新主力段减去已发生的换月价差。

既有 `/continuous` 产品 API 的日频行为不在本批改变。研究宽表独立物化，避免改动历史
产品读路径。

## 数据模型

新增 `agent_market_panel_daily`：

- 业务唯一键：`(data_view, variety_id, contract_id, period, trading_date)`；
- `period` 当前固定为 `1d`，`data_view` 为上述四种视图之一；
- 保留 `symbol`、`contract_code`、OHLCV、`amount`、`open_interest` 和
  `settlement`；
- 物化 `ret_1/5/20`、`gap`、`amplitude`、`intraday_range` 和
  `volume_ratio_20`；
- `source_flags` 逐字段记录 `kline_data`、`fut_daily_data` 或估算来源；
- `rollover_id`、`adjustment_value`、`adjustment_method`、`lineage_json` 和
  `build_trace_id` 记录换月、复权和构建血缘；
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

`rebuild_main_daily_panel_view()` 从 `raw_contract` 选择换月链上每日应使用的合约，
并为连续/复权行写入实际 `contract_id`、生效 `rollover_id`、累计调整值和应用过的
换月 ID 列表。`run_market_panel_daily_build()` 按 `raw_contract -> 派生视图` 的依赖顺序
物化所有请求视图，同一次构建共享 `trace_id`。

## 批次、重试与质量快照

`run_market_panel_daily_build()` 在重建函数外提供多视图构建编排；
`run_raw_contract_daily_panel_build()` 保持为向后兼容的 raw-only 包装器：

- 每次尝试均写入既有的 `data_ingestion_runs`，使用
  `job_name=rebuild_agent_market_panel_daily`、`source=market_panel`；
- 同一个构建请求的全部尝试共享一个 `trace_id`，便于独立诊断；
- 成功记录保存汇总和按视图的物化统计，以及只含状态、分数、覆盖范围和 issue code 的质量快照；
- 失败记录只保留 `trace_id`、异常类型、尝试次数和下一次退避时间，不记录原始行情、
  Provider Token 或异常原文；
- 仅 `ConnectionError`、`TimeoutError` 和 SQLAlchemy `OperationalError` 重试，退避
  间隔为 `retry_delay_seconds * 2^(attempt - 1)`；确定性数据错误立即失败；
- 每次尝试在保存点中运行。`--dry-run` 会回滚保存点，既不物化宽表，也不创建批次记录。

## 质量、目录与 Agent

- `DataCatalogService` 和 `DataQualityService.check_market_panel()` 均可按
  `data_view + period` 查询；
- 连续/复权视图额外检查日期覆盖、OHLC 合法性、构建/调整血缘、非正复权价格和
  换月行与 `rollover_id` 的对应关系；
- DataQualityAgent 可从“连续”“前复权”“后复权”等查询意图选择相应视图；
- FactorMiningAgent 和 BacktestAgent 仅在查询显式指定 `data_view` 时读取宽表，
  未指定时保留历史 `kline_data` 路径；
- `raw_contract` 消费必须明确 `contract_code`，避免混用不同到期月；
- 因子和回测输出记录数据集、视图、合约、质量预检、时间窗口和构建 trace。

## Worker 调度

`worker.py` 以 `start_scheduler(include_market_panel=True)` 注册宽表任务；API 进程即使启用
本地兼容 scheduler 也不会注册该任务。`market_panel_daily` 在 Asia/Shanghai `16:18` 运行，
晚于日 K（16:05）、具体合约日线（16:10）、主力日线（16:12）和结算（16:15）。

任务每次至少重建最近 20 个交易日；若上一成功批次之后新录入的 `contract_rollovers`
包含更早的 `effective_date`，窗口向前扩展至最早受影响日。任务使用
`max_instances=1`、`coalesce=True`，并复用既有构建批次、结构化日志和 Prometheus
`data_collection_*` 指标。

## 运行

```powershell
cd python
.venv\Scripts\python.exe scripts\rebuild_raw_contract_panel.py --symbol RB
.venv\Scripts\python.exe scripts\rebuild_raw_contract_panel.py --start-date 2026-01-01 --dry-run
.venv\Scripts\python.exe scripts\rebuild_raw_contract_panel.py --symbol RB --max-attempts 3 --retry-delay-seconds 1
.venv\Scripts\python.exe scripts\rebuild_market_panel.py --symbol RB
.venv\Scripts\python.exe scripts\rebuild_market_panel.py --symbol RB --data-view main_back_adjusted --dry-run
```

构建成功时脚本输出统计、质量快照与 `run_id`。最终失败时仅输出
`error`、`error_type` 与 `trace_id`，并返回非零退出码。

## 验证

- SQLite：原始/连续/前后复权口径、换月血缘、幂等重建、批次快照、失败脱敏、
  CLI dry-run、Agent 数据选择和 worker 预热窗口；
- PostgreSQL：一次性空库已完整升级到 `c0d1e2f3a4b5`；宽表 DDL、血缘列/外键/索引、
  原始重建与数据选择专项回归 `5 passed`，测试库已删除；
- SQLite 全量后端回归：`1015 passed, 14 skipped, 0 failed`；全仓 Ruff 和本轮 Python 编译通过。

## 后续边界

R3 与 R4 均已收口。R4 的 DSL transform 契约、未知 transform 显式拒绝和
walk-forward 计算/持久化/报告见
[`r4_dsl_walk_forward_validation.md`](r4_dsl_walk_forward_validation.md)。

下一项为 R5：前端质量与观测趋势。
