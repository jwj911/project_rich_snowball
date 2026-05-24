# K 线表分区与归档策略评估报告

> **评估日期**：2026-05-24  
> **评估基准**：当前 `kline_data` 单表，2,102 条记录，11 个品种  
> **目标**：为未来数据规模增长提供可落地的分区/归档技术方案  
> **结论**：当前无需立即实施分区；建议在数据量达到 100 万条时启动按周期+时间的复合分区。

---

## 一、当前数据画像

| 指标 | 数值 | 说明 |
|---|---|---|
| 总记录数 | 2,102 | 开发/测试环境，含历史回填 + Mock 数据 |
| 品种覆盖 | 11 | 主要为 AU/AG/CU/RB 等主流品种 |
| 周期分布 | 1h: 1,201 / 1d: 900 / D: 1 | 小时线和日线为主，尚无分钟级数据 |
| 时间跨度 | 2025-02-05 ~ 2026-05-14 | 约 15 个月 |
| 单条大小 | ~200 bytes | Numeric × 4 + DateTime + Integer + 元数据 |
| 表总容量 | ~420 KB | 远未达到任何性能瓶颈 |

**现状判断**：当前单表 + 现有索引（`idx_kline_lookup`、`idx_kline_contract_period_time`、`idx_kline_data_trading_date`）完全满足查询性能需求。**无需立即分区**。

---

## 二、未来规模预测

### 2.1 数据采集预期

中国期货市场约 **70 个活跃品种**，每个品种的日常 K 线生产规模：

| 周期 | 单合约日产量 | 70 品种年产量 | 3 年累计 |
|---|---|---|---|
| 分钟线 (1m) | ~240 条 | ~420 万条 | ~1,260 万条 |
| 小时线 (1h) | ~10 条 | ~17.5 万条 | ~52.5 万条 |
| 日线 (1d/D) | 1 条 | ~1.75 万条 | ~5.25 万条 |
| **合计** | — | **~439 万条/年** | **~1,317 万条** |

> 注：实际产量因品种交易时段差异（部分无夜盘）略低于理论值，但数量级不变。

### 2.2 性能拐点估算

基于 PostgreSQL 在常规 SSD + 32GB RAM 配置下的经验值：

| 数据量级 | 单表查询延迟 | 建议动作 |
|---|---|---|
| < 10 万条 | < 10 ms | 无需优化 |
| 10 ~ 100 万条 | 10 ~ 50 ms | 监控慢查询，评估索引 |
| 100 ~ 500 万条 | 50 ~ 200 ms | **启动分区** |
| 500 ~ 1,000 万条 | 200 ms ~ 1 s | 必须分区 + 归档 |
| > 1,000 万条 | > 1 s | 分区 + 归档 + 读写分离 |

**关键阈值**：**100 万条** 是启动分区的合理触发点。

---

## 三、查询模式分析

### 3.1 现有 API 查询路径

```
GET /api/klines/{symbol}?period=1d&limit=100
  └─ WHERE variety_id = ? AND period = ? ORDER BY trading_time DESC LIMIT ?

GET /api/klines/{symbol}/continuous?period=1h&limit=200
  └─ 多段拼接：WHERE variety_id = ? AND contract_id IN (...) AND period = ?

GET /api/klines/{symbol}/main?period=D&limit=50
  └─ 主力合约：WHERE variety_id = ? AND contract_id = ? AND period = ?
```

### 3.2 查询特征总结

1. **等值过滤**：`variety_id`、`period`、`contract_id`
2. **范围过滤**：`trading_time`（时间窗口）
3. **排序**：`trading_time DESC`（取最新 N 条）
4. **无跨品种聚合**：查询永远限定在单个品种内
5. **周期隔离**：前端切换周期时，不会同时查询 1m 和 1d

**分区键选择原则**：必须能裁剪（partition pruning）最常见的 `WHERE` 条件。

---

## 四、分区方案评估

PostgreSQL 10+ 支持 **Declarative Partitioning**，提供三种分区策略：`RANGE`、`LIST`、`HASH`。

### 4.1 方案 A：按时间 RANGE 分区（月度/季度）

```sql
CREATE TABLE kline_data (
    ...
) PARTITION BY RANGE (trading_time);

CREATE TABLE kline_data_2025_01 PARTITION OF kline_data
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE kline_data_2025_02 PARTITION OF kline_data
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
-- ...
```

| 维度 | 评分 | 说明 |
|---|---|---|
| 查询裁剪 | ⭐⭐⭐ | `WHERE trading_time BETWEEN x AND y` 可裁剪 |
| 数据清理 | ⭐⭐⭐⭐⭐ | 旧分区 `DETACH` 后可直接删除或归档 |
| 管理复杂度 | ⭐⭐⭐ | 需定时脚本创建新分区，或 `pg_partman` |
| 缺点 | — | 单个分区仍含所有品种和周期，分钟线分区仍会膨胀到数百万条 |

**适用场景**：以时间序列分析为主、不区分品种/周期的场景。**本项目中仅作为二级分区**。

### 4.2 方案 B：按周期 LIST 分区

```sql
CREATE TABLE kline_data (...) PARTITION BY LIST (period);

CREATE TABLE kline_data_1m PARTITION OF kline_data FOR VALUES IN ('1m');
CREATE TABLE kline_data_1h PARTITION OF kline_data FOR VALUES IN ('1h');
CREATE TABLE kline_data_1d PARTITION OF kline_data FOR VALUES IN ('1d', 'D');
```

| 维度 | 评分 | 说明 |
|---|---|---|
| 查询裁剪 | ⭐⭐⭐⭐⭐ | `WHERE period = '1m'` 直接定位到分钟线分区 |
| 数据清理 | ⭐⭐⭐ | 可按周期独立归档（如只保留 1m 最近 1 年）|
| 管理复杂度 | ⭐⭐⭐⭐ | 周期值固定，分区数量少 |
| 缺点 | — | 1m 分区内部仍需进一步拆分，否则单分区过大 |

**适用场景**：不同周期数据生命周期差异大的场景。例如：分钟线保留 6 个月，日线保留 10 年。

### 4.3 方案 C：复合分区（推荐）

PostgreSQL 10 原生不支持多级分区，但可通过 **分区表本身再分区** 实现：

```sql
-- 一级：按周期 LIST 分区
CREATE TABLE kline_data (...) PARTITION BY LIST (period);

-- 二级：分钟线再按时间 RANGE 分区
CREATE TABLE kline_data_1m PARTITION OF kline_data
    FOR VALUES IN ('1m')
    PARTITION BY RANGE (trading_time);

CREATE TABLE kline_data_1m_2025_01 PARTITION OF kline_data_1m
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

-- 小时线同理
CREATE TABLE kline_data_1h PARTITION OF kline_data
    FOR VALUES IN ('1h')
    PARTITION BY RANGE (trading_time);

-- 日线数据量小，无需再分区
CREATE TABLE kline_data_1d PARTITION OF kline_data
    FOR VALUES IN ('1d', 'D');
```

| 维度 | 评分 | 说明 |
|---|---|---|
| 查询裁剪 | ⭐⭐⭐⭐⭐ | `period='1m' AND trading_time >= '2025-01-01'` 只扫描 1 个分区 |
| 数据清理 | ⭐⭐⭐⭐⭐ | 旧月份可独立 DETACH + DROP/归档 |
| 管理复杂度 | ⭐⭐⭐ | 需维护 `period` 列表 + 定时创建时间子分区 |
| 扩展性 | ⭐⭐⭐⭐⭐ | 新增周期（如 5m、15m）只需新增一级分区 |

**推荐作为中期方案**。

### 4.4 方案 D：按品种 HASH 分区

```sql
CREATE TABLE kline_data (...) PARTITION BY HASH (variety_id);
CREATE TABLE kline_data_p0 PARTITION OF kline_data FOR VALUES WITH (MODULUS 16, REMAINDER 0);
-- ... 共 16 个分区
```

| 维度 | 评分 | 说明 |
|---|---|---|
| 查询裁剪 | ⭐⭐ | 只有 `variety_id = ?` 能裁剪；`variety_id IN (...)` 扫描多个分区 |
| 数据清理 | ⭐⭐ | 无法按时间清理，旧数据分散在所有分区 |
| 管理复杂度 | ⭐⭐⭐⭐⭐ | 分区数固定，但扩容需重分布 |
| 适用性 | ⭐⭐ | **不推荐**。品种数量少（70），HASH 带来的并发写入优势不明显。|

---

## 五、归档方案评估

### 5.1 冷数据定义

| 周期 | 热数据 | 温数据 | 冷数据（建议归档）|
|---|---|---|---|
| 分钟线 (1m) | 最近 1 个月 | 1~6 个月 | > 6 个月 |
| 小时线 (1h) | 最近 3 个月 | 3~12 个月 | > 1 年 |
| 日线 (1d/D) | 最近 1 年 | 1~5 年 | > 5 年 |

### 5.2 归档实施方式

**方式 1：分区 DETACH + 独立表保留**

```sql
-- 将 2024 年 1 月的分钟线分区变为独立表
ALTER TABLE kline_data_1m DETACH PARTITION kline_data_1m_2024_01;

-- 可导出为 Parquet / CSV，或保留为只读表
ALTER TABLE kline_data_1m_2024_01 RENAME TO kline_data_1m_2024_01_archive;
```

- **优点**：在线完成，不影响写入；保留在数据库内，可 UNION ALL 查询。
- **缺点**：仍占用存储空间。

**方式 2：导出到对象存储（S3/MinIO）**

使用 `COPY TO` 导出为 Parquet 格式：

```sql
COPY (SELECT * FROM kline_data_1m_2024_01_archive)
TO '/s3/kline-archive/1m/2024/01/data.parquet'
WITH (FORMAT 'parquet');
```

- **优点**：极大节省数据库存储；Parquet 列式存储利于分析查询。
- **缺点**：查询冷数据需回源对象存储，延迟较高。

**方式 3：表空间分离（Tablespace）**

将归档分区放到廉价存储（HDD/S3 Tablespace）：

```sql
CREATE TABLESPACE cold_storage LOCATION '/mnt/s3-tablespace';
ALTER TABLE kline_data_1m_2024_01 SET TABLESPACE cold_storage;
```

- **优点**：对应用透明，查询语法不变。
- **缺点**：PostgreSQL 15 之前表空间迁移会锁表；S3 Tablespace 需 FDW 扩展。

**推荐组合**：
- **温数据**（1m: 1~6 个月）：保留在主库分区中
- **冷数据**（1m: > 6 个月）：DETACH 为独立表 → 导出 Parquet → 删除数据库内表
- **日线**：长期保留在主库，5 年以上再考虑归档

---

## 六、迁移路径设计

### 阶段 0：当前（< 10 万条）

- **行动**：维持现状，单表 + 现有索引。
- **监控**：每月检查 `kline_data` 记录数和表大小。
- **指标**：`SELECT count(*), pg_size_pretty(pg_total_relation_size('kline_data'));`

### 阶段 1：触发点（~100 万条）

- **行动**：实施复合分区（方案 C）。
- **步骤**：
  1. 创建新分区表结构 `kline_data_new`
  2. 使用 `INSERT INTO ... SELECT ...` 迁移历史数据（可分批）
  3. 重命名表：`kline_data` → `kline_data_old`，`kline_data_new` → `kline_data`
  4. 验证索引和约束
  5. 删除 `kline_data_old`
- **停机时间**：~5~15 分钟（100 万条数据量）。

### 阶段 2：日常运维（> 100 万条）

- **自动分区创建**：使用 `pg_partman` 或自定义脚本，每月初预创建未来 3 个月的分区。
- **自动归档**：定时任务（如每月 1 日）DETACH 超过保留期的分区，导出 Parquet 后删除。

### 阶段 3：扩展（> 1,000 万条）

- **行动**：分钟线独立表或独立数据库实例。
- **理由**：分钟线占数据量 95% 以上，分离后可大幅降低主库压力。
- **架构**：日线/小时线保留在主业务库；分钟线迁移到专用时序数据库（TimescaleDB / InfluxDB / ClickHouse）。

---

## 七、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| 分区键选择不当导致查询性能未改善 | 中 | 高 | 在 staging 环境用真实查询模式压测 |
| 分区数量过多导致规划器开销增大 | 低 | 中 | 限制子分区数量（月级别 12 个/年），使用 `pg_partman` |
| 迁移期间数据不一致 | 低 | 高 | 迁移时暂停采集调度，或在线迁移（双写）|
| 归档后用户查询冷数据需求 | 中 | 低 | 保留温数据 6 个月；冷数据 Parquet 可通过单独 API 提供 |

---

## 八、结论与建议

| 维度 | 当前建议 | 触发条件 |
|---|---|---|
| **是否立即分区** | ❌ 否 | 当前 2,102 条，无需分区 |
| **分区触发阈值** | 100 万条 | 预计采集 2~3 个月分钟线后达到 |
| **推荐分区方案** | 复合分区（周期 LIST + 时间 RANGE）| 达到阈值时实施 |
| **归档策略** | 分钟线保留 6 个月，日线长期保留 | 与分区同步实施 |
| **技术栈准备** | 预研 `pg_partman` + Parquet 导出流程 | 触发前 2 周完成 |

**下一步行动**：
1. 在数据库中创建 `kline_data` 表大小监控（Prometheus 指标或定时日志）。
2. 当 `count(*)` 超过 50 万时，在 Staging 环境预演复合分区迁移。
3. 当 `count(*)` 超过 100 万时，在生产环境低峰期实施分区。

---

*报告生成时间：2026-05-24*  
*评估人：AI 后端架构评审*
