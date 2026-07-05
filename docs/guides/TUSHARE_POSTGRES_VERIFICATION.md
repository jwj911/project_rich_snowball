# Tushare → PostgreSQL 验证与回归指南

> 适用范围：第一阶段稳定性收口后的本地真实数据验证、PostgreSQL upsert 回归、后续排查 Tushare 采集链路问题。

本文档区分两类验证：

1. **真实数据验证**：使用本地 `.env` 中的 `TUSHARE_TOKEN` 拉取 Tushare 数据，灌入本地 PostgreSQL，验证真实链路。
2. **自动化回归测试**：使用可控样本直接验证 PostgreSQL upsert，不依赖 Tushare 网络、积分、交易日或接口权限。

---

## 一、前置条件

### 1. 启动 PostgreSQL

```powershell
cd D:\Code\project_rich_snowball
docker-compose up -d postgres
```

当前 `docker-compose.yml` 映射端口为：

```text
localhost:15432 -> container:5432
```

本地 PostgreSQL 连接串建议为：

```powershell
$env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
```

### 2. 设置运行环境

在已激活的后端虚拟环境中执行：

```powershell
cd D:\Code\project_rich_snowball\python

$env:SECRET_KEY="test-secret-key-for-local-development-123456"
$env:ENV="development"
$env:ENABLE_SCHEDULER="0"
$env:DATABASE_URL="postgresql://futures:futures123@localhost:15432/futures_community"
```

`.env` 中应已配置：

```env
TUSHARE_TOKEN=你的真实 token
DATA_SOURCE=tushare
```

不要把真实 token 提交到版本控制，也不要贴到聊天记录中。

### 3. 执行迁移

```powershell
alembic upgrade head
```

正常输出通常包含：

```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

如果没有 `Running upgrade ...`，通常表示数据库已经在最新 revision。

可用以下命令确认：

```powershell
alembic current
alembic heads
```

---

## 二、Tushare API 权限验证

先运行项目已有的探测脚本：

```powershell
python scripts/verify_tushare.py
```

### 已验证通过的典型结果

本地验证中已经观察到：

- `fut_daily(ts_code="AU.SHF")` 返回 21 条日线数据。
- `pro_bar(asset="FT", freq="D", ts_code="AU.SHF")` 返回 21 条日线数据。
- `fut_basic(exchange="SHFE", fut_type="2")` 返回 40 条合约信息。
- 返回字段包含当前 adapter 需要的核心字段：
  - `ts_code`
  - `trade_date`
  - `pre_close`
  - `pre_settle`
  - `open`
  - `high`
  - `low`
  - `close`
  - `settle`
  - `change1`
  - `change2`
  - `vol`
  - `amount`
  - `oi`
  - `oi_chg`

### 分钟线失败不一定是异常

如果 `ft_mins` 或 `pro_bar(freq="1min")` 输出类似：

```text
频率超限
```

这通常是 Tushare 积分、权限或调用频率限制导致。第一阶段验证可以先使用 `1d` 日线，不阻塞日线采集链路。

---

## 三、小样本真实数据灌库

使用本地研究脚本：

```powershell
python scripts/ingest_tushare_sample.py --symbols AU --period 1d --limit 10
```

或跳过 realtime，只验证 K 线日线：

```powershell
python scripts/ingest_tushare_sample.py --symbols AU,AG,CU --period 1d --limit 20 --skip-realtime
```

脚本会：

- 从项目根目录 `.env` 加载 `TUSHARE_TOKEN`，但不会打印 token。
- 初始化品种元数据。
- 使用 `TushareCollector` 拉取小样本。
- 通过正式 `DataPipeline` 写入 PostgreSQL。
- 输出写入前后计数和 delta。

### 已验证通过的典型结果

清理 AU/AG/CU 旧 `1d` K 线后：

```text
deleted 90
Before counts: realtime_quotes=10, kline_data=210
AU processed=20, failed=0, skipped=0
AG processed=20, failed=0, skipped=0
CU processed=20, failed=0, skipped=0
After counts: realtime_quotes=10, kline_data=270
Delta: realtime_quotes=0, kline_data=60
```

含义：

- 清理了 3 个品种 × 30 条旧日线。
- 成功写入 3 个品种 × 20 条 Tushare 日线。
- `failed=0, skipped=0`，说明 collector、adapter、cleaner、upsert 均未阻断。

如果不清理旧数据，可能看到：

```text
processed=0, skipped=20
Delta: kline_data=0
```

这通常表示 `kline_data` 中已存在相同 `variety_id + period + trading_time`，而当前 K 线写入策略是 `on_conflict_do_nothing`。这是预期行为，不代表 Tushare 拉取失败。

---

## 四、清理并重灌局部 K 线

本地研究库中，如果需要清理 AU/AG/CU 的 `1d` K 线后重灌：

```powershell
python -c "from models import SessionLocal,VarietyDB,KlineDataDB; db=SessionLocal(); ids=[v.id for v in db.query(VarietyDB).filter(VarietyDB.symbol.in_(['AU','AG','CU'])).all()]; n=db.query(KlineDataDB).filter(KlineDataDB.variety_id.in_(ids),KlineDataDB.period=='1d').delete(synchronize_session=False); db.commit(); print('deleted', n); db.close()"
```

然后重灌：

```powershell
python scripts/ingest_tushare_sample.py --symbols AU,AG,CU --period 1d --limit 20 --skip-realtime
```

---

## 五、验证数据库和 API

### 1. 直接查数据库

```powershell
python -c "from models import SessionLocal,VarietyDB,KlineDataDB; db=SessionLocal(); rows=db.query(KlineDataDB).join(VarietyDB).filter(VarietyDB.symbol=='AU',KlineDataDB.period=='1d').order_by(KlineDataDB.trading_time.desc()).limit(5).all(); print([(r.trading_time, r.open_price, r.high_price, r.low_price, r.close_price, r.volume) for r in rows]); db.close()"
```

已验证的典型输出：

```text
[
  (datetime.datetime(2026, 4, 30, 0, 0), 1005.0, 1016.38, 996.12, 1016.12, 230115),
  (datetime.datetime(2026, 4, 29, 0, 0), 1015.18, 1016.76, 1007.24, 1011.88, 223967),
  ...
]
```

### 2. 通过 API 查询

```powershell
python -c "from fastapi.testclient import TestClient; from main import app; c=TestClient(app); r=c.get('/api/kline/AU?period=1d&limit=5'); print(r.status_code); print(r.json())"
```

已验证的典型输出：

```text
200
[
  {'time': '2026-04-24T00:00:00', 'open': 1045.0, 'high': 1045.54, 'low': 1030.7, 'close': 1032.12, 'volume': 232408},
  ...
  {'time': '2026-04-30T00:00:00', 'open': 1005.0, 'high': 1016.38, 'low': 996.12, 'close': 1016.12, 'volume': 230115}
]
```

这说明：

```text
Tushare 日线 -> adapter -> cleaner -> PostgreSQL upsert -> /api/kline
```

链路已经通过真实数据验证。

---

## 六、PostgreSQL upsert 自动化回归测试

真实 Tushare 数据适合人工研究，但不适合作为唯一自动化测试来源，因为它依赖：

- token 是否可用
- 积分和权限
- 外部网络
- 交易日和接口状态
- 调用频率限制

因此新增了可重复的 PostgreSQL 专项测试：

```powershell
pytest tests/test_postgres_upsert_integration.py -v
```

该测试只在 PostgreSQL 环境下执行，SQLite 环境会 skip。

覆盖路径：

- `upsert_realtime`
- `insert_kline_bulk`
- `upsert_fut_daily_bulk`
- `upsert_fut_settle_bulk`
- `upsert_fut_price_limit_bulk`

关键断言：

- realtime 冲突时更新已有行。
- K 线冲突时不重复插入。
- 期货日线冲突时更新 OHLCV。
- 结算数据冲突时更新结算参数。
- 涨跌停数据冲突时更新涨跌停字段。

---

## 七、常见问题

### 1. `realtime skipped`

当前 `fetch_realtime()` 使用当天 `fut_daily` 近似实时行情。如果当天非交易日、数据尚未更新，或接口返回空，可能出现：

```text
realtime stats: processed=0, failed=0, skipped=1
```

这不影响日线 K 线验证。后续可以考虑将 realtime 改成读取最近一个有效交易日，或引入真正实时/准实时源。

### 2. `kline processed=0, skipped=N`

通常表示相同日期的 K 线已经存在，当前冲突策略是 `on_conflict_do_nothing`。

研究阶段可以清理局部数据后重灌；正式策略上，后续可评估是否将 K 线冲突策略改为可控更新。

### 3. 主力合约仍显示 `AU2506`

当前 `varieties.contract_code` 是兼容字段，可能落后于真实主力。Tushare 日线查询会 fallback 到连续主力 `AU.SHF`，所以日线验证仍可通过。

第二阶段会重建合约模型，将 K 线绑定具体 `contract_id`，并记录主力换月历史。

---

## 八、当前验证结论

截至 2026-05-05，本地已经验证：

- Tushare token 可用。
- Tushare 日线字段与当前 adapter 匹配。
- PostgreSQL 写入链路可写入真实 AU/AG/CU 日线。
- `/api/kline/AU?period=1d&limit=5` 可读出真实 Tushare K 线。
- 分钟线受频率/权限限制，暂不作为第一阶段阻断项。

