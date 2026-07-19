# 迭代文档：甲醇主力合约数据与时间格式修复

> **历史归档（2026-07-19）**：本文件记录 2026-07-05 的一次性修复验收，不再作为当前迭代入口。当前状态请查看 [`../iteration_plan_20260718_project_audit.md`](../iteration_plan_20260718_project_audit.md)。
>
> **迭代编号**: 2026-07-05-fix
> **日期**: 2026-07-05
> **关联问题**: K 线时间轴格式混乱、甲醇主力合约数据与页面顶部不一致

---

## 1. 问题描述

用户以甲醇主力合约（MA）为例，发现两个显式问题：

1. **K 线数据显示与页面顶部行情数据不一致**：截图中 K 线最新价约 2300-2400，而页面顶部显示的收盘价为 2377，两者虽处于同一数量级但数据时间序列不一致。
2. **K 线时间轴格式混乱**：最下方时间轴显示为 `9月 → 2023年 → 4月 → 7月 → 9月 → 12日` 等跳脱格式，不符合中文阅读习惯 `YYYY-MM-DD`。
3. **交易信息面板异常**：合约代码显示为 `MA2500`（非正常月份），交易日期显示为 `--`。

---

## 2. 根因分析

### 2.1 K 线时间格式问题

`lightweight-charts` v5 默认使用浏览器 locale 格式化时间刻度，导致中文环境下显示为"9月"、"2023年"等语义化但不统一的格式。前端未配置 `timeScale.tickMarkFormatter` 和 `localization.timeFormatter` 自定义格式。

**文件**: `frontend/hooks/useKlineChart.ts`, `frontend/components/kline/CrosshairTooltip.tsx`

### 2.2 K 线数据与顶部不一致

后端 `python/services/continuous_kline.py` 中 `get_fut_daily_main_kline` 函数使用：
```python
q.order_by(FutMainDailyDataDB.trade_date.asc()).limit(limit).all()
```

当数据表中有超过 500 条历史记录时，`asc` 升序 + `limit` 返回**最早的 500 条**（如 2011-2023 年数据），而不是最新的 500 条。页面顶部 API 使用 `order_by(...desc()).first()` 取最新一条，两者时间窗口完全不重叠。

**文件**: `python/services/continuous_kline.py`（3 处排序逻辑）

### 2.3 合约代码 `MA2500` 与交易日期 `--`

`data_collector/init_varieties.py` 在应用每次启动时**无条件覆盖** `varieties.contract_code` 为硬编码默认值（如 `MA2506`），把 `fut_mapping` 采集任务已更新的主力合约代码回滚到过期值。

数据库审计发现：
- `varieties.contract_code` 全部为 `MA2506`、`AU2506` 等**已过期合约**（2025 年 6 月已到期）
- `fut_contracts` 最新合约实际为 `MA2706.ZCE`、`AU2706.SHF` 等
- `fut_mapping` 更新被 `init_varieties` 覆盖，导致 `contract_code` 始终指向过期合约
- 当过期合约在 `fut_main_daily_data` 中没有数据时，交易日期字段为空，显示 `--`

此外，`fut_mapping` 采集任务未对合约月份做合法性校验，可能写入月份为 `00` 的异常合约代码（如 `MA2500`）。

**文件**: `python/data_collector/init_varieties.py`, `python/data_collector/pipeline_tasks/fut_mapping_task.py`, `python/tushare_pg_ingest/ingest_mapping.py`

---

## 3. 修复内容

### 3.1 前端时间格式修复

| 文件 | 修改 |
|------|------|
| `frontend/hooks/useKlineChart.ts` | 新增 `timeScale.tickMarkFormatter` 和 `localization.timeFormatter`，统一格式化为 `YYYY-MM-DD`（按 tickMarkType 层级：年份 `YYYY`，月份 `YYYY-MM`，日期 `YYYY-MM-DD`） |
| `frontend/components/kline/CrosshairTooltip.tsx` | 十字线悬浮时间格式化为 `YYYY-MM-DD`，提取 `formatKlineDate` 辅助函数 |

### 3.2 后端 K 线排序修复

| 文件 | 修改 |
|------|------|
| `python/services/continuous_kline.py` | `get_fut_daily_main_kline` 和 `get_fut_daily_contract_kline` 中 `asc().limit()` → `desc().limit().reverse()`（3 处），确保返回**最新 500 条**并保持时间升序 |

### 3.3 合约映射校验与初始化保护

| 文件 | 修改 |
|------|------|
| `python/data_collector/pipeline_tasks/fut_mapping_task.py` | 新增 `_is_valid_contract_month()` 校验，过滤月份为 `00` 的无效合约代码 |
| `python/tushare_pg_ingest/ingest_mapping.py` | 同样增加月份合法性校验，防止 `MA2500` 写入数据库 |
| `python/data_collector/init_varieties.py` | 初始化已有品种时**不再覆盖** `contract_code`，保留 `fut_mapping` 已更新的主力合约代码 |

### 3.4 数据库修复脚本

| 文件 | 说明 |
|------|------|
| `python/scripts/fix_varieties_contract_code.py` | 一次性修复脚本：将 `varieties.contract_code` 批量更新为 `fut_contracts` 中最新 `NORMAL` 类型合约。运行方式：`cd python && .venv\Scripts\python.exe scripts/fix_varieties_contract_code.py` |

---

## 4. 数据库修复操作记录

**执行时间**: 2026-07-05 08:40:06 UTC

**修复结果**:
- 总品种数: 181
- 已更新: 95（核心品种全部更新到最新合约）
- 已跳过: 0
- 失败: 86（连续合约品种如 `AUL`、`IFL`、`MAL` 等，以及测试/废弃品种，无 `NORMAL` 类型具体合约）

**核心品种更新示例**:

| 品种 | 旧合约 | 新合约 | 说明 |
|------|--------|--------|------|
| MA | MA2506 | MA2706 | 甲醇（已过期 → 2027年6月） |
| AU | AU2506 | AU2706 | 黄金（已过期 → 2027年6月） |
| RB | RB2506 | RB2706 | 螺纹钢 |
| I | I2506 | I2706 | 铁矿石 |
| SC | SC2506 | SC2906 | 原油（2029年6月，INE 远期） |
| M | M2506 | M2705 | 豆粕 |
| C | C2506 | C2705 | 玉米 |
| CF | CF2506 | CF2705 | 棉花 |

---

## 5. 验证结果

### 前端
- `tsc --noEmit` ✅ 通过（0 错误）
- `npm run lint` ✅ 通过（0 警告/错误）
- `npm run test`：32 通过，1 预先存在的硬编码测试失败（非本次修改引入）

### 后端
- `pytest tests/test_kline_service.py`：7 项全部通过 ✅
- `pytest tests/test_pipeline_rollover.py`：2 项全部通过 ✅
- `pytest tests/test_data_catalog.py`：4 项全部通过 ✅
- `ruff check`：所有修改文件通过 ✅

### 数据库验证
- `varieties.contract_code` 已更新为 `MA2706`、`AU2706` 等最新合约 ✅
- `fut_main_daily_data` 最新记录日期为 `2026-07-03` ✅

---

## 6. 仍需关注的事项

1. **连续合约品种（`L` 后缀）**：`AUL`、`IFL`、`MAL` 等 86 个连续合约品种无 `NORMAL` 类型具体合约，数据入库逻辑需要确认。这些品种在 `fut_contracts` 中仅有 `CONTINUOUS` 和 `MAIN` 类型记录。

2. **股指期货品种**：`IF`、`IH`、`IC`、`IM` 等更新到了 `IFL1`、`IH2612` 等，其中 `IFL1` 是连续合约而非具体交割合约。建议后续检查 `fut_contracts` 中股指期货的 `contract_type` 标记是否准确。

3. **启动后仍需验证**：`init_varieties` 已修复为不再覆盖 `contract_code`，但重启后端后建议再次确认 `varieties` 表未被回滚。

4. **Tushare 数据质量**：`fut_mapping` 返回的合约代码中偶见月份为 `00` 的异常数据，已增加过滤，但建议监控数据质量报告。

---

## 7. 变更文件清单

```
frontend/hooks/useKlineChart.ts                    (+12/-1)
frontend/components/kline/CrosshairTooltip.tsx       (+11/-3)
python/data_collector/init_varieties.py              (+4/-1)
python/data_collector/pipeline_tasks/fut_mapping_task.py (+18/-0)
python/services/continuous_kline.py                (+23/-8)
python/tushare_pg_ingest/ingest_mapping.py           (+24/-0)
python/scripts/fix_varieties_contract_code.py        (新增)
```

---

## 8. 修复后检查清单

- [x] K 线时间轴显示 `YYYY-MM-DD` 格式
- [x] 十字线悬浮时间显示 `YYYY-MM-DD` 格式
- [x] K 线 API 返回最新 500 条数据（而非最早的 500 条）
- [x] `varieties.contract_code` 已更新为最新主力合约
- [x] `init_varieties` 不再覆盖已有的 `contract_code`
- [x] `fut_mapping` 任务过滤月份为 `00` 的异常合约
- [x] 前端类型检查通过
- [x] 后端 Ruff 检查通过
- [x] 后端测试通过
- [ ] 重启后端后再次确认 `varieties.contract_code` 未被回滚（建议下次重启时验证）
