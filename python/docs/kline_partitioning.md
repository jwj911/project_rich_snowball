# K 线表分区策略文档

> 制定日期：2026-06-05  
> 状态：规划阶段（先文档后代码）  
> 适用范围：`kline_data` 表（日线/周线/月线/分钟线历史数据）

---

## 1. 当前状况

### 1.1 表结构

```sql
CREATE TABLE kline_data (
    id SERIAL PRIMARY KEY,
    variety_id INTEGER NOT NULL,
    contract_id INTEGER,
    period VARCHAR(10) NOT NULL,  -- 'D', 'W', 'M', '1min', '5min', '15min', '30min', '60min'
    trading_time TIMESTAMP NOT NULL,
    open_price DECIMAL(18, 6),
    high_price DECIMAL(18, 6),
    low_price DECIMAL(18, 6),
    close_price DECIMAL(18, 6),
    volume BIGINT,
    open_interest BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(variety_id, contract_id, period, trading_time)
);
```

### 1.2 数据量估算

| 品种数 | 合约数/品种 | 周期 | 条数/合约/年 | 年增量估算 |
|--------|------------|------|-------------|-----------|
| ~80 | 12（主力+连续+月度） | 日线 | ~250 | 24万 |
| ~80 | 12 | 分钟线（1min） | ~25万 | 2.4亿 |

当前阶段（上线初期）：
- 日线级数据：数十万条，无性能压力
- 分钟级数据：千万级，查询已开始需要索引优化

### 1.3 当前索引

- `idx_kline_variety_period_time`：(variety_id, period, trading_time)
- `idx_kline_contract_period_time`：(contract_id, period, trading_time)

---

## 2. 分区方案

### 2.1 方案：按 period + trading_time 组合分区（推荐）

**理由**：
- 查询模式 95% 以上按 `variety_id + period + [time_range]` 进行
- 不同 period 的数据特征差异大（日线 vs 分钟线量差 1000 倍）
- 天然支持按时间范围清理/归档冷数据

**PostgreSQL 实现**：

```sql
-- 创建分区表（替换现有 kline_data）
CREATE TABLE kline_data (
    id BIGSERIAL,
    variety_id INTEGER NOT NULL,
    contract_id INTEGER,
    period VARCHAR(10) NOT NULL,
    trading_time TIMESTAMP NOT NULL,
    open_price DECIMAL(18, 6),
    high_price DECIMAL(18, 6),
    low_price DECIMAL(18, 6),
    close_price DECIMAL(18, 6),
    volume BIGINT,
    open_interest BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (id, period, trading_time)
) PARTITION BY LIST (period);

-- 按周期创建子分区
CREATE TABLE kline_data_daily PARTITION OF kline_data
    FOR VALUES IN ('D', 'W', 'M');

CREATE TABLE kline_data_minute PARTITION OF kline_data
    FOR VALUES IN ('1min', '5min', '15min', '30min', '60min');

-- 子分区再按时间范围分区（仅对分钟线，因为数据量最大）
CREATE TABLE kline_data_minute_y2025m06 PARTITION OF kline_data_minute
    FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');
-- ... 每月自动创建新分区
```

**SQLite 兼容说明**：
- SQLite 不支持原生表分区
- 开发/测试环境继续使用单表 + 索引策略
- 生产环境（PostgreSQL）启用分区

### 2.2 分区键选择分析

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| period LIST + time RANGE | 查询裁剪效果好；分钟线按月可独立归档 | 需要维护分区创建脚本 | **推荐** |
| 仅 time RANGE | 实现简单；归档方便 | 分钟线和日线混在同一分区，查询裁剪差 | 次选 |
| variety_id HASH | 写入分布均匀 | 时间范围查询需扫描全部分区；归档困难 | 不推荐 |

---

## 3. 冷数据归档策略

### 3.1 归档规则

| 数据类型 | 热数据保留期 | 归档后存储 | 触发条件 |
|----------|-------------|-----------|---------|
| 分钟线 | 12 个月 | 压缩 Parquet / 对象存储 | 分区创建满 13 个月时 |
| 日线 | 永久保留 | 主库保留 | 不归档 |
| 周线/月线 | 永久保留 | 主库保留 | 不归档 |

### 3.2 归档流程

```python
# 伪代码：每月 1 日由 scheduler 触发
def archive_old_minute_kline():
    cutoff = now() - timedelta(days=365)
    # 1. 导出目标分区数据到 Parquet（按 variety 分片）
    # 2. 上传至对象存储（S3/MinIO）
    # 3. 删除/分离旧分区
    # 4. 记录归档元数据到 archive_log 表
```

---

## 4. 实施时机与阈值

### 4.1 触发条件（满足任一即启动实施）

- [ ] `kline_data` 总行数 > 1 亿
- [ ] 分钟线查询 P99 延迟 > 500ms
- [ ] 磁盘占用 > 100GB（仅 kline 相关表）
- [ ] 需要支持按时间范围快速清理数据（合规要求）

### 4.2 实施步骤

1. **Schema 准备**：创建分区表结构，验证与 SQLAlchemy 模型兼容
2. **数据迁移**：使用 `pg_dump` + `INSERT INTO ... SELECT` 或 `ALTER TABLE ... ATTACH PARTITION`
3. **应用适配**：`models.py` 中 KlineDataDB 无需改动（SQLAlchemy 2.0 自动识别分区表）
4. **自动化脚本**：添加 `scripts/create_kline_partition.py`，每月自动创建未来 3 个月的分区
5. **监控**：在 `metrics_dashboard.py` 中增加 kline 表大小、分区数指标

---

## 5. 替代方案（轻量级）

若短期内不满足分区触发条件，可先执行以下优化：

1. **复合索引优化**：确保 `(variety_id, period, trading_time)` 索引存在且被使用
2. **查询时间范围限制**：API 层限制单次查询最大时间跨度（如分钟线最多查 7 天）
3. **应用层缓存**：热品种最近 1 小时分钟线缓存在 Redis
4. **定期 VACUUM ANALYZE**：确保 PostgreSQL 查询计划准确

---

## 6. 验收清单

- [x] 分区方案文档已产出
- [ ] 分区 Schema 脚本已创建（待实施）
- [ ] 自动分区创建脚本已创建（待实施）
- [ ] 数据迁移方案已验证（待实施）
- [ ] 监控指标已补充（待实施）

---

*最后更新：2026-06-05*
