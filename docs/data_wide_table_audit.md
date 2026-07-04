# 数据宽表审计报告

**日期**：2026-07-04  
**范围**：因子评估、回测、技术分析可复用的数据宽表/面板能力  
**结论**：当前仓库尚未实现独立物理数据宽表；已有能力是 `kline_data` 原始 K 线、Tushare 扩展表、因子引擎内存面板，以及 `technical_indicators.py` 的单 DataFrame 因子计算。宽表可以设计并落地，但目前不应标记为“可被 FactorMiningAgent 和 BacktestAgent 安全使用”。

---

## 1. 当前事实

### 1.1 已有基础表

| 数据集 | 当前用途 | 关键字段 | 审计结论 |
|---|---|---|---|
| `kline_data` | 技术分析、回测、因子面板基础行情 | `variety_id`、`contract_id`、`period`、`trading_time`、`trading_date`、OHLC、`volume`、`open_interest` | 可作为宽表主源，但缺 `amount`，且当前为合约级原始 K 线 |
| `fut_daily_data` | Tushare 日/周/月扩展行情 | OHLC、`settle`、`volume`、`amount`、`open_interest`、`oi_chg` | 可补充 `amount/open_interest/settle`，但日期字段为 `trade_date`，周期口径为 `D/W/M` |
| `fut_settle` | 结算与保证金/手续费参数 | `settle`、费率、保证金率 | 可补充结算和成本字段，但 keyed by `ts_code + trade_date` |
| `fut_wsr` | 仓单日报 | `symbol`、`warehouse`、`vol`、`vol_chg` | 可聚合为品种日级 `warehouse_receipt` |
| `fut_holding` | 持仓排名 | `symbol`、`broker`、成交/多空持仓及变化 | 可聚合为 `holding_rank` 或多空集中度指标 |
| `fut_price_limits` | 涨跌停与保证金 | `ts_code`、`up_limit`、`down_limit`、`m_ratio` | 可补充 `limit_up/limit_down`，需合约映射 |
| `contract_rollovers` | 主力换月 | `variety_id`、新旧合约、`effective_date` | 是连续合约和 `data_view` 口径的必要来源 |

### 1.2 当前因子面板限制

`services/agent/factor_engine/data_loader.py` 当前只输出：

```text
open, high, low, close, volume
```

因此 `amount/open_interest/turnover_rate` 等字段尚不能通过 FactorMiningAgent 的 DSL 直接使用。本轮 C+ 已让 FactorMiningAgent 在计算前明确失败，而不是在求值阶段隐式报错。

### 1.3 当前技术指标能力

`python/lib/technical_indicators.py` 已支持大量因子函数，并在缺少 `amount` 时用 `close * volume` 近似。这适合单 DataFrame 离线计算，但还不是 Agent 可查询、可追踪血缘、可刷新校验的数据宽表。

---

## 2. 字段完整性审计

| 字段 | 当前来源建议 | 当前状态 | 处理建议 |
|---|---|---|---|
| `symbol` | `varieties.symbol` | 有 | 宽表直接冗余，避免 Agent 再 join |
| `trading_date` | `kline_data.trading_date` / `fut_daily_data.trade_date` | 有 | 统一为 date，不带时区时间 |
| `period` | `kline_data.period` / `fut_daily_data.period` | 有 | 建议统一 `1d/1w/1M` |
| `open/high/low/close` | `kline_data` 优先，缺失时可用 `fut_daily_data` | 有 | 明确 `raw_contract/main_continuous` 口径 |
| `volume` | `kline_data.volume` / `fut_daily_data.volume` | 有 | 保留原始单位 |
| `amount` | `fut_daily_data.amount`，fallback `close * volume` | 部分有 | 必须记录是否估算 |
| `open_interest` | `kline_data.open_interest` / `fut_daily_data.open_interest` | 部分有 | 优先真实值，记录来源 |
| `ret_1/ret_5/ret_20` | `close.pct_change()` | 未物化 | 宽表刷新时派生 |
| `gap` | `open / prev_close - 1` | 未物化 | 需处理换月断点 |
| `amplitude` | `(high - low) / close` | 未物化 | 除零保护 |
| `intraday_range` | `(close - open) / open` | 未物化 | 除零保护 |
| `turnover_rate` | 需持仓/流通口径 | 未具备明确口径 | 第一版建议不物化，或标记为 unavailable |
| `volume_ratio` | `volume / rolling_mean(volume, N)` | 未物化 | 建议 N=20，`min_periods=1` |
| `warehouse_receipt` | `fut_wsr` 按品种+日期聚合 | 未物化 | 聚合 `sum(vol)` |
| `holding_rank` | `fut_holding` 聚合 | 未物化 | 先输出多空持仓 Top N 汇总/净持仓 |
| `settlement` | `fut_settle.settle` / `fut_daily_data.settle` | 部分有 | 需明确合约映射 |
| `limit_up/limit_down` | `fut_price_limits` | 部分有 | 需合约映射 |
| `basis` | 现货/指数数据 | 未具备稳定来源 | 暂缓 |
| `term_structure` | 多合约曲线 | 原始合约可推导 | 需独立口径设计 |

---

## 3. 血缘与口径要求

第一版宽表建议命名为 `factor_market_daily` 或 `agent_market_panel_daily`，至少包含：

```text
data_view          raw_contract | main_continuous | main_back_adjusted | main_forward_adjusted
symbol
contract_code
trading_date
period
open, high, low, close, volume, amount, open_interest
derived fields...
source_flags       JSON/text，记录字段来源与 fallback
quality_status     good | warning | bad
created_at
updated_at
```

必要血缘规则：

- `amount` 如果来自 `close * volume`，必须在 `source_flags.amount = "estimated_close_volume"` 中标记。
- `open_interest` 如果来自 `fut_daily_data` 而不是 `kline_data`，必须标记来源。
- `settlement/limit_up/limit_down` 必须记录 `ts_code` 来源，避免品种级错配合约级字段。
- `data_view != raw_contract` 时必须关联连续合约或换月来源，不能只保留拼接后的价格。
- 缺失值处理方式必须字段级记录，不能只在刷新日志里写总览。

---

## 4. 索引与性能建议

必须索引：

```text
(symbol, trading_date)
(trading_date)
(period, symbol, trading_date)
```

如果支持多口径，必须增加：

```text
(data_view, symbol, trading_date)
```

建议唯一约束：

```text
(data_view, symbol, contract_code, period, trading_date)
```

如后续 PostgreSQL 数据量扩大，可按 `period` + 年份或 `trading_date` 范围分区；SQLite 开发环境保留普通表即可。

---

## 5. 刷新与质量门禁

宽表刷新流程建议：

1. 读取 `kline_data` 主源。
2. 按 `variety_id/symbol/trading_date/contract_code` 对齐 `fut_daily_data`、`fut_settle`、`fut_price_limits`。
3. 按品种+日期聚合 `fut_wsr`、`fut_holding`。
4. 生成派生字段。
5. 执行质量门禁。
6. 通过 upsert 写入宽表。
7. 产出刷新摘要，供 Data Catalog 和 DataQualityAgent 查询。

质量门禁：

- row count 与源 K 线对账。
- 日期范围与源 K 线对账。
- OHLC 合法性。
- `amount/open_interest/settlement/limit_up/limit_down` 空值比例。
- 派生字段空值比例。
- 抽样对账源 K 线 OHLCV。
- 最近 N 日增量刷新校验。
- `data_view` 为连续合约时检查换月断点和跳空标记。

---

## 6. 对 Agent 的影响

当前 C+ 已经避免了最危险的失败模式：

- BacktestAgent 在 K 线 `bad` 时不会进入回测引擎。
- FactorMiningAgent 遇到 `amount/open_interest/turnover_rate` 会明确提示缺字段。
- AnalysisPipelineAgent 在基础 K 线 `bad` 时会停止后续技术分析和风控。

宽表落地后建议改造：

- FactorMiningAgent 的 `PanelData` 扩展到 `amount/open_interest/settlement/limit_up/limit_down`。
- DataCatalogService 增加 `agent_market_panel_daily` 数据集 profile。
- DataQualityService 增加宽表质量检查。
- BacktestAgent 支持 `data_view` 参数，并在结果中说明使用的数据口径。

---

## 7. 审计结论

Milestone D 的审计结论是：**当前具备构建宽表的数据来源，但还没有可验收的数据宽表实现**。

建议下一步先实现最小宽表：

1. `raw_contract` 日级宽表：只做原始合约口径。
2. 字段覆盖：基础 OHLCV + `amount/open_interest` + 常用派生字段。
3. source_flags：记录 `amount` 是否估算。
4. 质量门禁：row count、OHLC、空值比例、抽样对账。
5. Data Catalog 接入：让 Agent 能发现并解释宽表可用性。

主力连续与复权口径应进入 Milestone E，不建议和第一版宽表混在同一个提交里一次完成。
