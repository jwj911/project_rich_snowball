# data_collector 审查与修复记录

日期：2026-05-05

## 审查范围

本次审查覆盖 `python/data_collector` 下的采集链路文件：

- `base.py`
- `tushare_collector.py`
- `akshare_collector.py`
- `mock_collector.py`
- `file_collector.py`
- `adapters.py`
- `cleaner.py`
- `pipeline.py`
- `scheduler.py`
- `upsert.py`
- `init_varieties.py`

重点检查文件之间的接口契约是否一致：Collector 原始数据、Adapter 标准字段、Cleaner 校验、Pipeline 统计与过滤、Upsert 数据库写入、Scheduler 数据源选择与定时任务。

参考 Tushare 文档包括用户提供的：

- `fut_basic`
- `ft_mins`
- `fut_daily`
- `fut_weekly_monthly`
- `fut_mapping`
- `fut_settle`
- `fut_wsr`
- `fut_holding`
- `fut_weekly_detail`
- `ft_limit`

## 发现并修复的问题

### 1. Tushare 接口调用不够贴合官方接口

原问题：

- 分钟线、周线、月线曾混用 `pro_bar` 语义，和当前 Tushare 文档中的期货专用接口不完全一致。
- 分钟线应使用具体合约代码，例如 `AU2506.SHF`，而不是主力连续代码 `AU.SHF`。
- `fut_weekly_detail` 的入参应为 `start_week/end_week`，不是普通日期字段。
- 涨跌停接口 `ft_limit` 未接入。

修复：

- `tushare_collector.py`
  - 分钟线改为 `pro.ft_mins(...)`。
  - 日线改为 `pro.fut_daily(...)`。
  - 周/月线改为 `pro.fut_weekly_monthly(...)`。
  - 合约基础信息接入 `pro.fut_basic(...)`。
  - 主力映射接入 `pro.fut_mapping(...)`。
  - 涨跌停接入 `pro.ft_limit(...)`。
  - `ZCE` 自动转换为 Tushare 需要的 `CZCE`。
  - `fut_weekly_detail` 自动把 `YYYYMMDD` 转为 `YYYYWW` 后传 `start_week/end_week`。

### 2. Tushare 主源与 AkShare 备源的调度关系不完整

原问题：

- `DATA_SOURCE=tushare` 时，Tushare token 或依赖不可用会导致调度器导入失败。
- Tushare 单品种拉取失败时没有自然回退 AkShare。

修复：

- `scheduler.py`
  - 新增 `_MappedFallbackCollector`。
  - `DATA_SOURCE=tushare` 时优先 Tushare，初始化失败或运行失败会尝试 AkShare。
  - Tushare 扩展任务只在 Tushare 初始化成功时注册。

### 3. Adapter 与 Cleaner 字段契约不完整

原问题：

- AkShare/Tushare 字段存在原始字段和内部字段混用风险。
- K 线时间字段只兼容部分名称，周/月线 `end_date` 可能无法入库。
- 实时 bid/ask 字段被 adapter 解析后没有被 cleaner/upsert 保留。

修复：

- `adapters.py`
  - 统一输出内部字段：`current_price/open_price/high/low/volume/open_interest` 等。
  - K 线兼容 `trade_time`、`trade_date`、`end_date`。
  - 新增 `map_tushare_ft_limit`。
- `cleaner.py`
  - 重写实时与 K 线清洗逻辑。
  - 校验 K 线 `period/trading_time/volume` 必填。
  - 保留 `bid1/ask1`。
- `upsert.py`
  - `upsert_realtime` 写入并更新 `bid1/ask1`。

### 4. Mock 数据偶发生成非法 OHLC

原问题：

- `mock_collector.fetch_realtime()` 先随机生成 open/high/low，可能出现 open 高于 high 或 open 低于 low，导致 cleaner 随机丢弃 mock 行情。

修复：

- `mock_collector.py`
  - high 基于 `max(open, close)` 生成。
  - low 基于 `min(open, close)` 生成。

验证结果：连续 500 条 mock 实时行情清洗失败数为 0。

### 5. Pipeline 扩展表写入缺少必填字段过滤

原问题：

- 扩展接口返回缺字段时，可能把 `trade_date=None`、`ts_code=None` 等写入非空列。
- `run_fut_daily()` 用 `ts_code.split(".")[0]` 查品种，遇到 `AU2506.SHF` 会得到 `AU2506`，无法匹配 `VarietyDB.symbol=AU`。
- skip 统计会覆盖已经累计的跳过数量。

修复：

- `pipeline.py`
  - 新增 `_symbol_from_ts_code()`，从 `AU2506.SHF` 正确提取 `AU`。
  - `fut_daily/fut_settle/fut_weekly_detail/fut_wsr/fut_holding/ft_limit` 写入前过滤关键字段。
  - 修复 skipped 统计覆盖问题。

### 6. 部分 Upsert 与模型约束不匹配

原问题：

- `fut_weekly_detail`、`fut_wsr`、`fut_holding` 模型中没有唯一约束，不能安全使用 SQLite `ON CONFLICT`。
- `ft_limit` 已有模型但未接入 upsert。

修复：

- `upsert.py`
  - 对没有唯一约束的扩展表改为查询去重后插入。
  - 新增 `upsert_fut_price_limit_bulk()`，使用 `FutPriceLimitDB` 的唯一约束做 upsert。

### 7. init_varieties 初始化脚本与数据库配置冲突

原问题：

- `init_varieties.py` 自己创建 engine，并且无条件传 `check_same_thread=False`，切 PostgreSQL 时会冲突。
- 文件内容存在明显编码损坏，品种中文不可读。

修复：

- `init_varieties.py`
  - 改为复用 `models.SessionLocal`。
  - 恢复中文品种名与分类。
  - 已存在品种会更新基础字段，缺失品种会创建。

## 验证

已执行：

```bash
SECRET_KEY=test-secret-key python -m py_compile python/data_collector/*.py
```

额外验证：

- Mock 实时行情连续 500 条通过 adapter + cleaner。
- 使用 stub Tushare client 验证：
  - `ft_mins` 参数为具体合约，如 `AU2506.SHF`。
  - `fut_basic("ZCE")` 实际传参为 `exchange="CZCE"`。
  - `fut_weekly_detail("20260501", "20260505")` 实际传参为 `start_week="202618", end_week="202619"`。
  - `ft_limit` 可返回并映射涨跌停字段。
- 使用 stub 依赖验证 `scheduler.py` 在 `DATA_SOURCE=tushare` 时可构建 Tushare 主源和扩展 pipeline。

## 未执行项

未执行真实 Tushare/AkShare 网络调用，原因：

- 当前环境缺少真实 token 与完整运行依赖。
- 外部接口调用需要网络与 Tushare 权限积分。

建议在具备真实环境后执行一次小范围联调：

```bash
cd python
SECRET_KEY=test-secret-key DATA_SOURCE=tushare TUSHARE_TOKEN=<真实token> ENABLE_SCHEDULER=0 python -c "from data_collector.tushare_collector import TushareCollector; c=TushareCollector(); print(c.fetch_kline('AU2506', '1m', 3))"
```

