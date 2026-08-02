# K 线分区生命周期与安全演练

> 最后更新：2026-08-02（R8 工程基线）
> 状态：容量门禁、影子 DDL、隔离演练和观测已实现；活动表未切换
> 适用范围：PostgreSQL `kline_data`，SQLite 仅提供非分区摘要

## 1. 当前边界

生产读写仍使用未分区的 `kline_data`。R8 只提供只读容量判断、显式影子表规划和隔离复制
演练，不会重命名或替换活动表，也不会导出、删除或归档冷数据。

当前 ORM 契约如下：

```sql
CREATE TABLE kline_data (
    id INTEGER PRIMARY KEY,
    variety_id INTEGER NOT NULL REFERENCES varieties(id) ON DELETE CASCADE,
    contract_id INTEGER NOT NULL REFERENCES fut_contracts(id) ON DELETE CASCADE,
    period VARCHAR(10) NOT NULL,
    trading_time TIMESTAMP WITH TIME ZONE NOT NULL,
    trading_date DATE,
    open_price NUMERIC(19, 4) NOT NULL,
    high_price NUMERIC(19, 4) NOT NULL,
    low_price NUMERIC(19, 4) NOT NULL,
    close_price NUMERIC(19, 4) NOT NULL,
    volume INTEGER NOT NULL,
    open_interest INTEGER,
    created_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uix_kline_contract
        UNIQUE (variety_id, contract_id, period, trading_time)
);
```

查询索引为：

- `(contract_id)`；
- `(trading_date)`；
- `(variety_id, period, trading_time)`；
- `(contract_id, period, trading_time)`。

## 2. 容量门禁

启动生产切换规格前，必须先取得 `python/scripts/kline_storage_preflight.py` 的只读报告。固定
阈值为：

| 指标 | 阈值 | 稳定触发代码 |
|---|---:|---|
| 总行数 | 100,000,000 | `KLINE_ROW_COUNT_THRESHOLD` |
| 表与索引总大小 | 100 GiB | `KLINE_TOTAL_BYTES_THRESHOLD` |
| 分钟查询 P99 | 500 ms | `KLINE_MINUTE_QUERY_P99_THRESHOLD_MS` |

```powershell
cd python
.\.venv\Scripts\python.exe scripts\kline_storage_preflight.py `
  --report-path "$env:TEMP\r8-kline-storage.json"
```

需要合并外部只读 benchmark 证据时，显式传入 `--minute-query-p99-ms`。默认 benchmark 不再
造数；隔离环境需要 BENCH 数据时才允许使用 `benchmark_kline.py --seed`，且
`ENV=production` 会硬拒绝该参数。

报告包含方言、版本、聚合行数、容量、周期分布、时间边界、分区状态、未来月份覆盖、
`EXPLAIN` 摘要、阈值结论和独立 `trace_id`。不得包含连接凭据、Provider Token、原始
OHLCV 或 SQL 参数值。SQLite 返回基础统计及 `unsupported_for_partitioning`。

`not_required` 只表示当前证据未达到阈值，不表示已经完成生产分区。

## 3. 影子分区契约

`services/kline_partitioning.py` 生成两级 PostgreSQL 分区：

1. 父表按 `LIST (period)`；
2. 分钟组按 `RANGE (trading_time)` 创建月分区；
3. 长周期进入单独 LIST 分区；
4. 未知周期进入 DEFAULT 分区。

周期目录：

| 分组 | 周期值 |
|---|---|
| 分钟 | `1m`、`1`、`5m`、`5`、`15m`、`15`、`30m`、`30`、`1h`、`60` |
| 长周期 | `1d`、`D`、`1w`、`W`、`M` |
| 默认 | 其他未登记值 |

PostgreSQL 要求分区表的主键和唯一约束包含相关分区键。影子父表因此使用：

```sql
PRIMARY KEY (id, period, trading_time);
UNIQUE (variety_id, contract_id, period, trading_time);
```

`id` 由父表共享的 INTEGER sequence 生成。自然唯一键与现有
`ON CONFLICT DO NOTHING` 写入契约保持一致。影子 DDL 同时保留当前字段精度、时区、
`trading_date`、非空条件和两个级联外键。

## 4. 生命周期命令

命令默认只打印稳定计划，不连接数据库：

```powershell
cd python
.\.venv\Scripts\python.exe scripts\manage_kline_partitions.py `
  --shadow-table kline_data_shadow_r8
```

实际 DDL 必须同时满足 PostgreSQL、显式 `--apply`、`--confirm` 和包含独立 `shadow`
token 的安全表名：

```powershell
.\.venv\Scripts\python.exe scripts\manage_kline_partitions.py `
  --shadow-table kline_data_shadow_r8 `
  --apply `
  --confirm
```

活动表名 `kline_data`、schema-qualified 名称、非法标识符、非 PostgreSQL URL 和缺失确认
参数均被拒绝。计划创建未来 3 个月的分钟分区，并使用 `IF NOT EXISTS` 保持重复执行幂等。

## 5. 隔离迁移演练

演练也默认 dry-run：

```powershell
.\.venv\Scripts\python.exe scripts\rehearse_kline_partition.py `
  --source-table kline_data `
  --shadow-table kline_data_shadow_rehearsal
```

在隔离 PostgreSQL 中实际复制并于成功后清理：

```powershell
.\.venv\Scripts\python.exe scripts\rehearse_kline_partition.py `
  --source-table kline_data `
  --shadow-table kline_data_shadow_rehearsal `
  --apply `
  --confirm `
  --cleanup
```

演练使用 `REPEATABLE READ` 事务和 transaction-level advisory lock。复制前会为源数据已有的
分钟月份补齐范围分区，复制后验证：

- 总行数、各周期计数和最早/最晚 `trading_time`；
- 自然键重复数；
- sequence 下一值大于当前最大 `id`；
- 影子表外键及 `ON DELETE CASCADE`；
- 核心合约/周期/时间范围查询；
- `ON CONFLICT DO NOTHING`；
- `EXPLAIN (FORMAT JSON)` 只访问目标月份分区。

任一检查失败时，PostgreSQL 事务回滚本轮 DDL 和复制数据。报告只保留聚合证据、稳定检查
代码、异常类型和 `trace_id`，不会输出异常文本或原始行情。命令不包含 rename/swap 路径。

## 6. 管理员观测

管理员可调用 `GET /metrics/dashboard/kline-storage` 查看低成本摘要。PostgreSQL 使用系统
目录行数估计和容量元数据，结果在进程内缓存 60 秒；SQLite 返回精确基础行数并标记
`partitioning_supported=false`。普通用户返回 403。

Prometheus `/metrics` 不调用该容量统计，避免每次 scrape 触发高成本查询。

## 7. CI 与验证

Backend CI 在 PostgreSQL 16 中依次执行：

1. Alembic `upgrade head`；
2. R8 只读容量预检；
3. 分区 DDL、全部周期别名、DEFAULT 路由和重复 apply；
4. 影子复制一致性、冲突写入、级联外键和实际分区裁剪；
5. 成功清理与失败事务回滚；
6. 断言不存在 `kline_data_shadow_*` 表或序列；
7. 既有全量 pytest、API smoke、Ruff 和依赖审计。

本地没有 PostgreSQL 时，三个真实 PostgreSQL 用例必须明确 skip，不得以 SQLite 或 fake
结果替代远程 PostgreSQL 证据。

## 8. 后续生产切换与归档

以下内容不属于 R8，必须在达到阈值后建立新的生产规格：

- 发布窗口、负责人、备份与恢复点；
- 真实生产容量报告及可重复 benchmark；
- 影子表增量追平、短暂停写或双写策略；
- 活动表 rename/swap、权限、序列 owner 和依赖对象核对；
- 应用读写 smoke、回滚时限与旧表保留期；
- 分钟冷数据导出为 Parquet、对象存储校验、恢复演练和删除审批；
- 归档元数据、保留策略、合规要求和定期恢复抽检。

在这些条件完成前，不得执行活动表替换、旧分区 detach/drop 或冷数据删除，也不得将 R8
表述为生产已经分区。
