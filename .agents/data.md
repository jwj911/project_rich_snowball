<!-- .agents/data.md — 数据采集、调度与历史回填 -->

## 调度器

`data_collector/scheduler.py` 使用延迟初始化 collector，避免导入期就因外部数据源失败导致应用不可启动。

### 调度任务

- 实时行情：每 60 秒（可通过 `REALTIME_REFRESH_INTERVAL_SECONDS` 调整）
- 日 K：每日 16:05
- 分钟 K：每 15 分钟，走 AkShare 分钟线 pipeline
- 品种元数据：每日 02:00
- Tushare 扩展任务：日线、结算、仓单、持仓、涨跌停、周报等，仅在 Tushare pipeline 可用时注册
- 价格预警检测：`refresh_realtime_quotes` 成功后遍历未触发预警与 `RealtimeQuoteDB.current_price` 比较

## 数据源

`DATA_SOURCE`：

- `mock`：开发默认
- `akshare`：真实行情源之一
- `tushare`：需要 `TUSHARE_TOKEN`
- `auto`：尝试真实源 fallback

非生产环境所有真实 collector 失败时可以降级 Mock；生产环境不允许降级 Mock。

数据源熔断器（`services/circuit_breaker.py`）：连续失败 5 次后冷却 10 分钟。

## PostgreSQL 与历史回填

基础设施：

```powershell
docker-compose up -d postgres redis
```

PostgreSQL 连接串：

```env
DATABASE_URL=postgresql://futures:futures123@localhost:15432/futures_community
```

迁移：

```powershell
cd python
alembic upgrade head
```

`python/tushare_pg_ingest/` 是独立于应用启动流程的历史数据回填工具。常用脚本包括：

- `ingest_daily.py`：日线/周线/月线，写入 `fut_daily_data`
- `ingest_settle.py`：结算参数
- `ingest_wsr.py`：仓单日报
- `ingest_holding.py`：持仓排名
- `ingest_price_limit.py`：涨跌停价格
- `ingest_mapping.py`：主力映射，更新 `varieties.contract_code`
- `ingest_weekly_detail.py`：周度交易统计
- `ingest_all.py`：保守总入口
- `ingest_commission_9qihuo.py`：九期网/AKShare 手续费与保证金

运行前阅读 `python/tushare_pg_ingest/README.md`。

## 后端文档目录

`python/docs/` 存放架构决策、运维手册和 API 契约文档：

- `api_error_contract.md`：统一业务错误码契约（`errors.py` 配套文档）
- `kline_partitioning.md`：K 线表 LIST+RANGE 分区策略与冷数据归档方案
- `sse_scaling_strategy.md`：SSE 单实例限制、sticky session、cookie-only 鉴权部署约束
- `observability_runbook.md`：可观测性运维手册（指标、日志、告警）
- `postgres_acceptance.md` / `postgres_backup_runbook.md`：PostgreSQL 验收与备份手册
- `../docs/archive/productdb_sunset_plan.md`：ProductDB 退场历史计划与验证记录（仅归档）
- `settings_api.md`：用户偏好设置 API 设计文档
- `kline_benchmark_20260529.md`：K 线性能基准测试记录
