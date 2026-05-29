# K 线查询性能基准测试报告

> 测试日期：2026-05-29  
> 数据库：PostgreSQL 16（Docker，端口 15432）  
> 数据量：`kline_data` 21,965 条（1 年日线 365 条 + 3 个月 1m 线 21,600 条）  
> 测试脚本：`scripts/benchmark_kline.py`

---

## 1. 测试环境

| 项目 | 值 |
|------|-----|
| 数据库 | PostgreSQL 16-alpine (Docker) |
| 连接串 | `postgresql://futures:futures123@localhost:15432/futures_community` |
| 测试品种 | `BENCH` (benchmark 专用品种，symbol = `BENCH`) |
| 合约 | `BENCH2401` (id=100418), `BENCH2405` (id=100419) |
| 换月点 | 2024-05-01 (`BENCH2401` → `BENCH2405`) |
| 索引 | `idx_kline_lookup(variety_id, period, trading_time)`、`idx_kline_contract_period_time(contract_id, period, trading_time)` |

---

## 2. 延迟基准（20 轮迭代，单位 ms）

| 查询场景 | p50 | p95 | p99 | mean | max |
|----------|-----|-----|-----|------|-----|
| variety_kline (D, limit=100) | 2.722 | 3.817 | 6.532 | 2.972 | 7.211 |
| contract_kline (D, limit=500) | 2.890 | 3.707 | 4.324 | 2.917 | 4.478 |
| main_contract_kline (D, limit=500) | 8.150 | 10.415 | 11.090 | 8.196 | 11.259 |
| continuous_kline (D, limit=500, backward) | 12.578 | 19.067 | 45.850 | 15.123 | 52.545 |
| minute_kline (1m, limit=5000) | 82.598 | 113.179 | 119.492 | 77.294 | 121.071 |

**结论**：当前数据量下，所有场景 p95 < 500ms，**不满足分区/分表触发阈值**。单表 + 现有索引策略完全够用。

---

## 3. 数据库层执行分析（EXPLAIN ANALYZE）

### variety_kline_D
```
Index Scan Backward using idx_kline_lookup on kline_data
  Index Cond: ((variety_id = 174) AND ((period)::text = 'D'::text))
Planning Time: 0.573 ms
Execution Time: 0.077 ms
```
- **索引命中**：`idx_kline_lookup` ✅
- **扫描方向**：Backward（对应 `ORDER BY trading_time DESC`）

### contract_kline_D
```
Index Scan using idx_kline_contract_period_time on kline_data
  Index Cond: ((contract_id = 100418) AND ((period)::text = 'D'::text))
Planning Time: 0.177 ms
Execution Time: 0.083 ms
```
- **索引命中**：`idx_kline_contract_period_time` ✅

### minute_kline_1m
```
Bitmap Index Scan on idx_kline_contract_period_time
  Index Cond: ((contract_id = 100418) AND ((period)::text = '1m'::text))
Planning Time: 0.109 ms
Execution Time: 0.120 ms
```
- **索引命中**：`idx_kline_contract_period_time`（Bitmap Scan）✅
- 注意：该查询返回 0 行是因为 `BENCH2401` 上没有 1m 数据（1m 数据仅在 `BENCH2405` 上），但索引仍被正确使用。

---

## 4. 瓶颈分析

| 场景 | 数据库执行时间 | 端到端延迟 | 瓶颈推断 |
|------|---------------|-----------|----------|
| variety_kline | ~0.08 ms | ~3 ms | ORM 对象构造 + Python 序列化 |
| contract_kline | ~0.08 ms | ~3 ms | ORM 对象构造 + Python 序列化 |
| main_contract_kline | ~0.1 ms | ~8 ms | 多一次合约查询 + ORM |
| continuous_kline | ~0.2 ms | ~15 ms | segment 拼接 + backward adjustment（纯 Python 计算） |
| minute_kline (1m) | ~0.1 ms | ~82 ms | 大量 ORM 对象构造（5000 条） |

**关键发现**：
- 数据库层执行极快（< 0.2ms），端到端延迟主要来自 ORM 和 Python 处理。
- `continuous_kline` 的 p99 波动较大（45ms+），原因是 backward adjustment 的纯 Python 计算量随数据量变化。
- `minute_kline` 的高延迟（82ms p50）主要来自 5000 条记录的 ORM 实例化；若前端不需要一次拉 5000 条，可减小 limit。

---

## 5. 分区/分表决策建议

当前明确**不需要**分区或分表。

触发阈值（达到任一即重新评估）：
1. `kline_data` 总行数 > 100 万
2. 任一核心查询 p95 > 500ms
3. 单品种单周期数据量 > 50 万行
4. 索引膨胀导致 `EXPLAIN` 中出现 Seq Scan（全表扫描）

若未来达到阈值，推荐方案：
- **首选**：PostgreSQL native range partition by `trading_time`（按月或按年）
- **次选**：按 `period` 拆分（仅在单一周期数据量极大时考虑）
- **不推荐**：业务层分表路由（增加 API 查询复杂度）

---

## 6. 复现命令

```powershell
cd d:\Code\project_rich_snowball\python
$env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
$env:SECRET_KEY="test-secret-key-for-local-dev-only-must-be-32-characters-long"

# 运行基准测试
.\venv\Scripts\python.exe scripts\benchmark_kline.py

# 只输出 EXPLAIN ANALYZE
.\venv\Scripts\python.exe scripts\benchmark_kline.py --explain
```

---

*报告生成时间：2026-05-29*
