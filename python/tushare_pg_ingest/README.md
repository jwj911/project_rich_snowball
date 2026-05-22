# Tushare → PostgreSQL 历史数据回填脚本

本目录包含独立于应用启动流程的历史数据灌库工具，用于从 **Tushare Pro**（以及部分 **AKShare** 辅助接口）拉取国内期货数据，并写入 PostgreSQL（开发环境可降级 SQLite）。

脚本会读取项目根目录 `.env` 中的以下变量：

| 变量 | 必需 | 说明 |
|------|------|------|
| `TUSHARE_TOKEN` | 是 | Tushare Pro API Token |
| `DATABASE_URL` | 是 | 默认要求 PostgreSQL，如 `postgresql://futures:futures123@localhost:15432/futures_community` |
| `SECRET_KEY` | 是 | 仅用于初始化 `config.py` 不报错 |

---

## 目录

1. [前置准备](#前置准备)
2. [执行顺序建议](#执行顺序建议)
3. [脚本速查表](#脚本速查表)
4. [各脚本详解](#各脚本详解)
   - [ingest_basic.py](#ingest_basicpy) — 品种基础元数据
   - [ingest_contracts.py](#ingest_contractspy) — 合约明细
   - [ingest_daily.py](#ingest_dailypy) — 日线 / 周线 / 月线
   - [ingest_settle.py](#ingest_settlepy) — 结算参数
   - [ingest_wsr.py](#ingest_wsrpy) — 仓单日报
   - [ingest_holding.py](#ingest_holdingpy) — 持仓排名
   - [ingest_price_limit.py](#ingest_price_limitpy) — 涨跌停价格
   - [ingest_mapping.py](#ingest_mappingpy) — 主力合约映射
   - [ingest_weekly_detail.py](#ingest_weekly_detailpy) — 周线/月线行情
   - [ingest_commission_9qihuo.py](#ingest_commission_9qihuopy) — 九期网手续费与保证金
   - [ingest_all.py](#ingest_allpy) — 保守总入口
   - [verify_fut_daily.py](#verify_fut_dailypy) — 数据质量验证
   - [check_dupes.py](#check_dupespy) — 重复行检查
   - [delete_fut_daily_period.py](#delete_fut_daily_periodpy) — 按 period 删除数据
5. [通用参数](#通用参数)
6. [Tushare 接口速查与权限说明](#tushare-接口速查与权限说明)
7. [常见问题](#常见问题)

---

## 前置准备

```powershell
# 1. 确保 PostgreSQL 已启动（docker-compose 或本地）
cd D:\Code\project_rich_snowball
docker-compose up -d postgres

# 2. 设置环境变量并执行迁移
cd D:\Code\project_rich_snowball\python
$env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
$env:ENABLE_SCHEDULER="0"
alembic upgrade head

# 3. 确认 .env 中有 TUSHARE_TOKEN
# 若无，先申请：https://tushare.pro/register
```

---

## 执行顺序建议

首次灌库建议按以下顺序执行，避免下游脚本因依赖表为空而跳过：

```text
1. ingest_basic.py       → 填充/刷新 varieties 表基础字段
2. ingest_contracts.py   → 填充 fut_contracts 表（ingest_daily.py 会依赖此表）
3. ingest_mapping.py     → 更新 varieties.contract_code（主力合约代码）
4. ingest_daily.py       → 日线 / 周线 / 月线 K 线（核心数据）
5. ingest_settle.py      → 结算参数（可选）
6. ingest_wsr.py         → 仓单日报（可选）
7. ingest_holding.py     → 持仓排名（可选）
8. ingest_price_limit.py → 涨跌停价格（可选）
9. ingest_weekly_detail.py → 周线/月线行情（可选）
```

> 快捷方式：执行 `ingest_all.py` 可一次性按上述顺序跑完全部默认步骤（见下方）。

---

## 脚本速查表

| 脚本 | 数据源 | 目标表 | 核心参数 |
|------|--------|--------|----------|
| `ingest_basic.py` | Tushare `fut_basic` | `varieties` | `--exchanges`, `--fut-type`, `--insert-missing` |
| `ingest_contracts.py` | Tushare `fut_basic` | `fut_contracts` | `--exchanges`, `--fut-type` |
| `ingest_daily.py` | Tushare `fut_daily` / `fut_weekly_monthly` | `fut_daily_data` | `--symbols`, `--period`, `--contract-type`, `--ts-codes` |
| `ingest_settle.py` | Tushare `fut_settle` | `fut_settle` | `--date`, `--exchanges`, `--ts-code` |
| `ingest_wsr.py` | Tushare `fut_wsr` | `fut_wsr` | `--date`, `--symbols` |
| `ingest_holding.py` | Tushare `fut_holding` | `fut_holding` | `--date`, `--symbols`, `--exchanges` |
| `ingest_price_limit.py` | Tushare `ft_limit` | `fut_price_limits` | `--date`, `--symbols` |
| `ingest_mapping.py` | Tushare `fut_mapping` | `varieties` | `--date` |
| `ingest_weekly_detail.py` | Tushare `fut_weekly_monthly` | `fut_daily_data` | `--freq`, `--start-date`, `--end-date`, `--symbols` |
| `ingest_commission_9qihuo.py` | AKShare `futures_comm_info` | `fut_trade_fee` / `varieties` | `--exchange`, `--save-db`, `--update-varieties` |
| `ingest_all.py` | 组合调用上述脚本 | 多个表 | `--start-date`, `--end-date`, `--skip-*` |
| `verify_fut_daily.py` | 本地库 + Tushare 抽检 | 验证报告 | `--expected-days`, `--spot-check` |
| `check_dupes.py` | 本地库 | 重复报告 | `--limit` |

---

## 各脚本详解

### ingest_basic.py

**用途**：从 Tushare `fut_basic` 拉取期货品种基础信息，更新本地 `varieties` 表。  
**注意**：默认 `fut_type=2`，仅拉取**主力/连续合约**品种条目，用于快速建立品种列表；如需全部合约请改 `--fut-type=1`。

```powershell
# 更新全部交易所的主力/连续合约品种信息
python tushare_pg_ingest\ingest_basic.py --insert-missing

# 仅更新上期所，并插入本地缺失的品种
python tushare_pg_ingest\ingest_basic.py --exchanges SHFE --insert-missing

# 查看效果但不写入
python tushare_pg_ingest\ingest_basic.py --dry-run
```

### ingest_contracts.py

**用途**：从 Tushare `fut_basic` 拉取全部合约元数据，写入 `fut_contracts` 表。  
**说明**：这是 `ingest_daily.py` 的**前置依赖**——当 `ingest_daily.py` 使用 `--symbols` / `--exchanges` / `--contract-type` 参数时，它会查询 `fut_contracts` 表来发现需要拉取的具体合约代码。

```powershell
# 拉取全部交易所的全部合约
python tushare_pg_ingest\ingest_contracts.py

# 仅拉取上期所主力/连续合约（fut_type=2）
python tushare_pg_ingest\ingest_contracts.py --exchanges SHFE --fut-type 2
```

### ingest_daily.py

**用途**：从 Tushare `fut_daily`（日线）或 `fut_weekly_monthly`（周线/月线）拉取行情数据，写入 `fut_daily_data`。

**两种查询模式**：

1. **合约发现模式**（推荐）：通过 `--symbols` / `--exchanges` / `--contract-type` 从 `fut_contracts` 表自动发现合约，再逐个拉取行情。
2. **直连模式**：通过 `--ts-codes` 直接指定合约代码，跳过 `fut_contracts` 查询。

```powershell
# 模式 A：合约发现 —— 拉取 AU/AG/CU 三个品种在日期范围内的全部日线
python tushare_pg_ingest\ingest_daily.py --symbols AU,AG,CU --period D --start-date 20250101 --end-date 20250505

# 模式 A 进阶：仅拉取主力合约（MAIN）和连续合约（CONTINUOUS）
python tushare_pg_ingest\ingest_daily.py --symbols AU,AG,CU --contract-type MAIN,CONTINUOUS --period D --start-date 20250101 --end-date 20250505

# 模式 B：直连 —— 直接指定具体合约代码
python tushare_pg_ingest\ingest_daily.py --ts-codes AU2506.SHF,CU2506.SHF --period D --start-date 20250501 --end-date 20250505

# 周线 / 月线
python tushare_pg_ingest\ingest_daily.py --symbols AU,AG --period W --start-date 20250101 --end-date 20250505
python tushare_pg_ingest\ingest_daily.py --symbols AU,AG --period M --start-date 20250101 --end-date 20250505

# 干跑验证
python tushare_pg_ingest\ingest_daily.py --symbols AU --period D --start-date 20250501 --end-date 20250505 --dry-run
```

### ingest_settle.py

**用途**：从 Tushare `fut_settle` 拉取每日结算参数（交易保证金率、手续费率等），写入 `fut_settle`。

**已知限制**：
- Tushare `fut_settle` 当前主要覆盖 **SHFE** 和 **INE**；DCE / CZCE / CFFEX / GFEX 经常返回空结果。
- 字段 `offset_today_fee` 在文档中存在，但实际响应中通常不出现。

```powershell
# 按日期拉取（默认全部交易所，自动跳过周末）
python tushare_pg_ingest\ingest_settle.py --date 20250507

# 按日期范围
python tushare_pg_ingest\ingest_settle.py --start-date 20250501 --end-date 20250507

# 按合约代码拉取（忽略日期/交易所限制）
python tushare_pg_ingest\ingest_settle.py --ts-code AU2506.SHF,CU2506.SHF
```

### ingest_wsr.py

**用途**：从 Tushare `fut_wsr` 拉取仓单日报数据，写入 `fut_wsr`。

```powershell
# 拉取指定日期全部品种的仓单数据
python tushare_pg_ingest\ingest_wsr.py --date 20250507

# 拉取指定日期范围、指定品种
python tushare_pg_ingest\ingest_wsr.py --start-date 20250501 --end-date 20250507 --symbols AU,CU
```

### ingest_holding.py

**用途**：从 Tushare `fut_holding` 拉取期货公司持仓排名数据，写入 `fut_holding`。

```powershell
# 拉取指定日期全部交易所全部品种
python tushare_pg_ingest\ingest_holding.py --date 20250507

# 限定品种和交易所
python tushare_pg_ingest\ingest_holding.py --start-date 20250501 --end-date 20250507 --symbols AU,CU --exchanges SHFE
```

### ingest_price_limit.py

**用途**：从 Tushare `ft_limit` 拉取每日涨跌停板价格，写入 `fut_price_limits`。

```powershell
# 拉取全部品种
python tushare_pg_ingest\ingest_price_limit.py --date 20250507

# 限定品种
python tushare_pg_ingest\ingest_price_limit.py --start-date 20250501 --end-date 20250507 --symbols AU,CU
```

### ingest_mapping.py

**用途**：从 Tushare `fut_mapping` 拉取品种与主力合约的映射关系，更新 `varieties.contract_code` 字段。

```powershell
# 更新主力合约映射
python tushare_pg_ingest\ingest_mapping.py --start-date 20250501 --end-date 20250507

# 仅查看映射结果
python tushare_pg_ingest\ingest_mapping.py --start-date 20250501 --end-date 20250507 --dry-run
```

### ingest_weekly_detail.py

**用途**：从 Tushare `fut_weekly_monthly` 拉取期货周线/月线行情，写入 `fut_daily_data`（`period=W` 或 `M`）。

**注意**：
- 必须传入 `--freq week` 或 `--freq month`（默认 `week`）。
- 脚本按**品种级别 ts_code**（如 `SM.ZCE`、`AU.SHF`）逐个查询，而非按日期范围批量查询。这样可绕过 Tushare 单次查询 6000 条限制，确保数据完整。
- 默认查询 `varieties` 表中所有品种；可通过 `--symbols SM,AU` 限定品种，或通过 `--exchanges SHFE,DCE` 限定交易所。

```powershell
# 拉取所有品种的周线
python tushare_pg_ingest\ingest_weekly_detail.py --start-date 20250101 --end-date 20250505 --freq week

# 拉取指定品种的周线
python tushare_pg_ingest\ingest_weekly_detail.py --start-date 20250101 --end-date 20250505 --freq week --symbols SM,AU

# 拉取月线
python tushare_pg_ingest\ingest_weekly_detail.py --start-date 20250101 --end-date 20250505 --freq month

# 干跑预览
python tushare_pg_ingest\ingest_weekly_detail.py --start-date 20250101 --end-date 20250505 --dry-run
```

### ingest_commission_9qihuo.py

**用途**：通过 **AKShare**（非 Tushare）从[九期网](https://www.9qihuo.com)拉取期货手续费与保证金数据，支持保存 CSV 和写入数据库。

```powershell
# 仅保存 CSV（默认行为）
python tushare_pg_ingest\ingest_commission_9qihuo.py

# 拉取指定交易所
python tushare_pg_ingest\ingest_commission_9qihuo.py --exchange "上海期货交易所"

# 写入数据库 fut_trade_fee 表
python tushare_pg_ingest\ingest_commission_9qihuo.py --save-db --allow-sqlite

# 仅主力合约 + 更新 varieties 表保证金/手续费字段
python tushare_pg_ingest\ingest_commission_9qihuo.py --main-only --save-db --update-varieties --allow-sqlite
```

### ingest_all.py

**用途**：保守总入口，按推荐顺序串行调用上述各脚本，适合首次批量回填。

```powershell
# 默认回填全部数据层
python tushare_pg_ingest\ingest_all.py --start-date 20250501 --end-date 20250505

# 指定品种和交易所（减少 API 调用量）
python tushare_pg_ingest\ingest_all.py --start-date 20250501 --end-date 20250505 --symbols AU,AG,CU --exchanges SHFE,DCE,CZCE

# 跳过某些步骤（如跳过结算参数和持仓排名）
python tushare_pg_ingest\ingest_all.py --start-date 20250501 --end-date 20250505 --skip-settle --skip-holding

# 干跑验证全部流程
python tushare_pg_ingest\ingest_all.py --start-date 20250501 --end-date 20250505 --dry-run
```

**支持跳过的步骤**：`--skip-basic` / `--skip-contracts` / `--skip-daily` / `--skip-weekly-monthly` / `--skip-settle` / `--skip-wsr` / `--skip-holding` / `--skip-limit` / `--skip-mapping` / `--skip-weekly-detail`

### verify_fut_daily.py

**用途**：对 `fut_daily_data` 表进行多维数据质量验证，并可选与 Tushare API 进行随机抽检对比。

**验证维度**：
1. 基础统计：总行数、品种覆盖数、日期范围、周期分布
2. OHLC 一致性：`open <= high >= low`，`close` 在 `[low, high]` 内
3. 零值/负值价格检测
4. 单品种覆盖度：标记数据量偏少的品种
5. Tushare API 抽检：随机抽样对比本地与远端 OHLC 值

```powershell
# 基础验证（默认预期每个品种约 300 个交易日，抽检 5 条）
python tushare_pg_ingest\verify_fut_daily.py

# 调整预期交易日数（例如仅回填了 1 个月数据）
python tushare_pg_ingest\verify_fut_daily.py --expected-days 22

# 关闭 Tushare 抽检（节省 API 积分）
python tushare_pg_ingest\verify_fut_daily.py --spot-check 0
```

### check_dupes.py

**用途**：检查 `fut_daily_data` 表是否存在重复行（该表有唯一约束 `(variety_id, period, trade_date)`）。

```powershell
# 检查重复
python tushare_pg_ingest\check_dupes.py

# 显示前 50 组重复
python tushare_pg_ingest\check_dupes.py --limit 50
```

### delete_fut_daily_period.py

**用途**：按 `period`（以及可选的日期范围）删除 `fut_daily_data` 表中的数据。用于清理错误的周线/月线数据后重新回填。

```powershell
# 删除全部周线数据
python tushare_pg_ingest\delete_fut_daily_period.py --period W

# 删除指定日期范围的周线数据
python tushare_pg_ingest\delete_fut_daily_period.py --period W --start-date 20260101 --end-date 20260515

# 干跑预览
python tushare_pg_ingest\delete_fut_daily_period.py --period W --dry-run
```

---

## 通用参数

以下参数在绝大多数脚本中均可用：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--start-date` | str | — | 起始日期，格式 `YYYYMMDD` |
| `--end-date` | str | — | 结束日期，格式 `YYYYMMDD` |
| `--date` | str | — | 单日快捷参数，等价于 `start-date = end-date = date` |
| `--dry-run` | flag | `False` | 仅拉取和映射数据，**不写入数据库** |
| `--allow-sqlite` | flag | `False` | 允许写入 SQLite（默认强制 PostgreSQL） |
| `--min-interval` | float | `0.55` | 两次 Tushare API 调用之间的最小间隔（秒），防频控 |

---

## Tushare 接口速查与权限说明

| 脚本 | Tushare 接口 | 积分门槛 | 说明 |
|------|-------------|----------|------|
| `ingest_basic.py` | `fut_basic` | 120 积分 | 期货合约基础信息 |
| `ingest_contracts.py` | `fut_basic` | 120 积分 | 同上，写入 fut_contracts 表 |
| `ingest_daily.py` | `fut_daily` | 2000 积分 | 期货日线行情；周线/月线走 `fut_weekly_monthly` |
| `ingest_settle.py` | `fut_settle` | 2000 积分 | 交易结算参数；注意覆盖范围以 SHFE/INE 为主 |
| `ingest_wsr.py` | `fut_wsr` | 2000 积分 | 仓单日报 |
| `ingest_holding.py` | `fut_holding` | 2000 积分 | 会员持仓排名 |
| `ingest_price_limit.py` | `ft_limit` | 2000 积分 | 每日涨跌停板价格 |
| `ingest_mapping.py` | `fut_mapping` | 2000 积分 | 主力连续合约映射 |
| `ingest_weekly_detail.py` | `fut_weekly_monthly` | 2000 积分 | 周线/月线行情 |

> **积分参考**：Tushare 注册用户默认 120 积分，绑定手机后 2000 积分，高级数据需更多积分或付费。  
> 接口文档：https://tushare.pro/document/2

**分钟数据**：Tushare `ft_mins` 为独立的高频接口，通常需要额外权限，当前阶段仅保留占位脚本 `ingest_minutes.py`，未纳入默认回填流程。如需启用，请先确认账号具备该接口权限后再扩展实现。

---

## 常见问题

### Q1: 为什么 `ingest_settle.py` 拉取 DCE / CZCE 返回 0 条？

A: Tushare `fut_settle` 接口当前数据覆盖以 **SHFE** 和 **INE** 为主，其他交易所返回空是已知现象，非脚本错误。脚本已自动注入 `exchange` 字段并在 0 条时打印 `[WARN]` 提示。

### Q2: `ingest_daily.py` 报错 "no matching contracts in FutContractDB"

A: 请先执行 `ingest_contracts.py` 填充合约表；或改用 `--ts-codes` 参数直接指定合约代码。

### Q3: 如何减少 API 调用避免触发频控？

A: 
- 缩小 `--symbols` 范围，不要一次性全品种。
- 缩短日期范围，分批次执行。
- `ingest_daily.py` 使用 `--contract-type MAIN,CONTINUOUS` 仅拉主力/连续合约，避免成百上千个具体合约。
- 已内置 `TushareClient` 限速（默认 0.55 秒/次）和 3 次失败重试，一般无需额外调整。

### Q4: 回填后如何确认数据完整性？

A: 运行 `verify_fut_daily.py` 进行 OHLC 一致性、零值检测、覆盖度统计，并可开启 `--spot-check` 与 Tushare 远端进行抽样比对。

### Q5: `ingest_weekly_detail.py` 之前返回 0 条，现在怎么又有数据了？

A: 该脚本早期调用的是 `fut_weekly_detail`（交易周报，数据只更新到 2020 年）。现已改为调用 `fut_weekly_monthly`（周/月线行情），数据持续更新。请务必使用 `--freq week` 或 `--freq month` 参数。

### Q6: `ingest_weekly_detail.py` 按日期范围查询时数据不完整怎么办？

A: `fut_weekly_monthly` 按纯日期范围查询存在 6000 条硬上限，会导致早期数据被截断。当前脚本已改为**按品种级别 ts_code 逐个查询**（如 `SM.ZCE`），每个品种独立调用 API，可绕过此限制并获取完整历史。

### Q7: 手续费数据为什么走 AKShare 而不是 Tushare？

A: Tushare 暂未提供系统性的期货手续费/保证金明细接口。本项目通过 AKShare 对接九期网（`www.9qihuo.com`）来弥补该数据缺口。该脚本独立运行，不依赖 Tushare Token。

---

## 文件清单

```text
tushare_pg_ingest/
├── __init__.py
├── common.py                      # 共享工具（TushareClient、参数解析、数据库配置等）
├── ingest_all.py                  # 保守总入口，串行调用各脚本
├── ingest_basic.py                # 品种基础元数据 -> varieties
├── ingest_contracts.py            # 合约明细 -> fut_contracts
├── ingest_daily.py                # 日线/周线/月线 -> fut_daily_data
├── ingest_settle.py               # 结算参数 -> fut_settle
├── ingest_wsr.py                  # 仓单日报 -> fut_wsr
├── ingest_holding.py              # 持仓排名 -> fut_holding
├── ingest_price_limit.py          # 涨跌停价格 -> fut_price_limits
├── ingest_mapping.py              # 主力映射 -> varieties.contract_code
├── ingest_weekly_detail.py        # 周线/月线行情 -> fut_daily_data
├── ingest_commission_9qihuo.py    # 九期网手续费 -> fut_trade_fee / varieties
├── ingest_minutes.py              # ft_mins 占位（当前禁用）
├── verify_fut_daily.py            # fut_daily_data 数据质量验证
├── check_dupes.py                 # 重复行检查
├── delete_fut_daily_period.py     # 按 period 删除 fut_daily_data
└── README.md                      # 本文档
```
