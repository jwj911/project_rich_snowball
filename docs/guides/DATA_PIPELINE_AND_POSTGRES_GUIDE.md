# 期货交流社区 — 数据流转与 PostgreSQL 部署指南

> 本文档面向开发/运维人员，说明数据从产生到入库的完整链路，以及如何从 SQLite 切换到 PostgreSQL（Docker 方式）。

***

## 一、数据从产生到入库的完整流程

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              外部数据源                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────────┐  │
│  │ Tushare Pro │  │   AkShare   │  │           MockCollector             │  │
│  │  (主力合约)  │  │  (备用源)   │  │         (随机游走数据)               │  │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────┬───────────────────┘  │
└─────────┼────────────────┼────────────────────────────┼──────────────────────┘
          │                │                            │
          ▼                ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           调度触发层 (Scheduler)                              │
│  APScheduler BackgroundScheduler                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  30s   │ refresh_realtime_quotes  (实时行情)                            │  │
│  │  30s   │ sync_prices_to_products  (兼容层同步)                          │  │
│  │  5min  │ sync_minute_kline        (分钟K线)                             │  │
│  │  16:05 │ sync_daily_kline         (日K线补全)                           │  │
│  │  16:10 │ sync_fut_daily           (期货日线 D/W/M)  ← Tushare only      │  │
│  │  16:15 │ sync_fut_settle          (结算参数)       ← Tushare only      │  │
│  │  16:20 │ sync_fut_wsr             (仓单日报)       ← Tushare only      │  │
│  │  16:25 │ sync_fut_holding         (持仓排名)       ← Tushare only      │  │
│  │  16:30 │ sync_fut_price_limit     (涨跌停价)       ← Tushare only      │  │
│  │  周一03:00 │ sync_fut_weekly_detail (交易周报)    ← Tushare only      │  │
│  │  周日02:00 │ sync_variety_metadata  (合约元数据)                       │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           采集层 (Collector)                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  _MappedFallbackCollector (自动故障转移)                                │  │
│  │    顺序：Tushare → AkShare → Mock                                      │  │
│  │    任一下游失败自动尝试下一个源                                         │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│  核心接口：fetch_realtime / fetch_kline / fetch_daily / fetch_settle / ...  │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Pipeline 编排层 (DataPipeline)                        │
│  统一流程：extract → adapter → cleaner → upsert → record_run               │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────────┐  │
│  │ extract │ → │ adapter │ → │ cleaner │ → │ upsert  │ → │ record_run  │  │
│  │  拉取   │   │ 字段映射 │   │ 数据校验 │   │ 批量写入 │   │ 批次追踪    │  │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            适配层 (Adapters)                                  │
│  职责：外部数据源字段 → 内部标准字段（唯一变更点）                             │
│  例如：Tushare "vol" → 内部 "volume"；"oi" → "open_interest"               │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            清洗层 (Cleaner)                                   │
│  clean_realtime：必填字段检查 / 价格>0 / OHLC一致性 / change_percent 补算   │
│  clean_kline：    必填字段检查 / OHLC一致性 / 去重 / 按时间升序排序           │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            写入层 (Upsert)                                    │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  表                  │ 冲突处理策略    │ 业务唯一键                      │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │  realtime_quotes     │ UPDATE          │ variety_id                      │  │
│  │  kline_data          │ DO NOTHING      │ variety_id + period + time      │  │
│  │  fut_daily_data      │ UPDATE          │ variety_id + period + date      │  │
│  │  fut_settle          │ UPDATE          │ ts_code + trade_date            │  │
│  │  fut_weekly_detail   │ DO NOTHING      │ week + prd + exchange           │  │
│  │  fut_wsr             │ DO NOTHING      │ date + symbol + warehouse + id  │  │
│  │  fut_holding         │ DO NOTHING      │ date + symbol + broker          │  │
│  │  fut_price_limits    │ UPDATE          │ ts_code + trade_date            │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         质量追踪层 (DataIngestionRunDB)                       │
│  每个 Pipeline 运行结束后，通过独立 Session 写入：                             │
│  - job_name / source / started_at / finished_at / status                    │
│  - success_count / failed_count / skipped_count                             │
│  - error_message / metadata_json                                            │
│  独立 Session 设计：主事务 rollback 不影响失败记录留存                        │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         兼容同步层 (Legacy Sync)                              │
│  sync_prices_to_products：                                                   │
│    将 realtime_quotes 最新价格同步到 products 表（供旧前端 /api/products 使用）│
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            数据库层 (Database)                                │
│  SQLite  (开发，WAL模式)        ←── 默认                                     │
│  PostgreSQL (生产，连接池)       ←── docker-compose 一键启动                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 各环节详细说明

#### ① 数据源产生层

| 数据源               | 数据类型                                           | 说明                    |
| ----------------- | ---------------------------------------------- | --------------------- |
| **Tushare Pro**   | 实时行情、1min/5min/日/周/月 K线、结算参数、持仓排名、仓单、交易周报、涨跌停价 | 主力合约格式 `AU.SHF`，需积分权限 |
| **AkShare**       | 实时行情、K线                                        | 免费，作为 Tushare 故障降级    |
| **MockCollector** | 全部类型                                           | 随机游走，开发/测试使用          |

#### ② 调度触发层

`scheduler.py` 使用 `APScheduler` 的后台调度器：

- **IntervalTrigger**：高频任务（30s 实时、5min 分钟K线）
- **CronTrigger**：日终任务（16:05\~16:30 密集批次、周一/周日低频任务）
- **故障转移**：`DATA_SOURCE=auto` 时启用 `_MappedFallbackCollector`，Tushare 失败自动切 AkShare，再失败切 Mock

#### ③ Pipeline 编排层

`DataPipeline` 是**唯一被 Scheduler 直接调用的入口**，封装了完整的 ETL 流程：

```python
# 以实时行情为例
pipeline.run_realtime(symbols=["AU", "I", "MA", ...])
#   1. 遍历 symbols，逐个调用 collector.fetch_realtime(symbol)
#   2. adapter(raw, symbol) → 字段映射
#   3. cleaner(data, symbol) → 校验，失败返回 None（跳过）
#   4. upsert_realtime(db, data) → 写入/更新
#   5. db.commit() → 事务提交
#   6. _record_run(...) → 批次追踪（独立 Session）
```

#### ④ 清洗层规则

`cleaner.py` 的核心校验逻辑：

1. **必填字段**：`current_price`, `high`, `low`, `volume` 不可为 None
2. **价格有效性**：`current_price > 0`，`high >= low`，`high >= max(open, close)`，`low <= min(open, close)`
3. **change\_percent 补算**：若上游未提供，利用 `pre_settlement` 自动计算
4. **K线去重**：按 `(trading_time, period)` 去重

#### ⑤ 写入层设计原则

- **本模块不执行** **`commit`**，commit 由 Pipeline/Scheduler 控制事务边界
- **批量写入**：K线、日线等使用 `insert().values([...])` 一次性提交
- **SQLite ON CONFLICT**：利用 `sqlalchemy.dialects.sqlite.insert` 的 `on_conflict_do_update/do_nothing`
- **PostgreSQL 兼容**：`insert()` 语法在 PostgreSQL 中同样生效（使用 `INSERT ... ON CONFLICT`）

***

## 二、PostgreSQL + Docker 安装与切换指南

### 2.1 前置要求

- Docker Desktop（Windows）或 Docker Engine（Linux）已安装并运行
- 项目根目录已有 `docker-compose.yml`

### 2.2 一键启动 PostgreSQL + Redis

在项目根目录执行：

```powershell
# 1. 启动 PostgreSQL 16 + Redis 7（后台运行）
docker-compose up -d postgres redis

# 2. 查看容器状态
docker-compose ps

# 3. 查看 PostgreSQL 日志（确认启动成功）
docker-compose logs -f postgres
```

启动后：

- PostgreSQL 端口：`localhost:5432`
- 数据库名：`futures_community`
- 用户名/密码：`futures` / `futures123`
- Redis 端口：`localhost:6379`

### 2.3 安装 PostgreSQL 驱动

```powershell
cd python
pip install psycopg2-binary
```

### 2.4 切换数据库（SQLite → PostgreSQL）

#### 步骤 1：修改 `.env`

```bash
# 注释掉 SQLite 配置
# DATABASE_URL=sqlite:///./futures_community.db

# 启用 PostgreSQL
DATABASE_URL=postgresql://futures:futures123@localhost:5432/futures_community
```

#### 步骤 2：运行 Alembic 迁移

```powershell
cd python
alembic upgrade head
```

> **注意**：首次切到 PostgreSQL 时，`alembic upgrade head` 会自动创建所有表。如果之前用 SQLite 已经有数据，需要额外做数据迁移（见 2.5）。

#### 步骤 3：验证连接

```powershell
cd python
python -c "from models import engine, get_engine_info; print(get_engine_info())"
```

期望输出类似：

```python
{'driver': 'psycopg2', 'database_url': 'postgresql://***'}
```

#### 步骤 4：启动后端

```powershell
cd python
python main.py
```

### 2.5（可选）SQLite 数据迁移到 PostgreSQL

如果 SQLite 中已有历史数据，可使用 `pgloader` 或 Python 脚本迁移：

```powershell
# 方案 A：使用 pgloader（需安装 pgloader）
pgloader sqlite:///./futures_community.db postgresql://futures:futures123@localhost/futures_community

# 方案 B：Python 脚本导出导入（推荐，更可控）
```

提供一个简单的迁移脚本 `migrate_sqlite_to_pg.py`：

```python
"""将 SQLite 数据迁移到 PostgreSQL。运行前确保 PostgreSQL 已创建空表（alembic upgrade head）。"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./futures_community.db"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import models

# 源：SQLite
sqlite_engine = create_engine("sqlite:///./futures_community.db", connect_args={"check_same_thread": False})
SQLiteSession = sessionmaker(bind=sqlite_engine)
src = SQLiteSession()

# 目标：PostgreSQL（通过环境变量或硬编码）
os.environ["DATABASE_URL"] = "postgresql://futures:futures123@localhost:5432/futures_community"
import importlib
importlib.reload(models)
pg_engine = models.engine
PGSession = sessionmaker(bind=pg_engine)
dst = PGSession()

# 按依赖顺序迁移（先用户、品种，后评论、K线等）
tables = [
    models.UserDB,
    models.VarietyDB,
    models.ProductDB,
    models.RealtimeQuoteDB,
    models.KlineDataDB,
    models.CommentDB,
    models.WatchlistDB,
    models.OpinionDB,
    models.DataIngestionRunDB,
    models.FutDailyDataDB,
    models.FutSettleDB,
    models.FutWeeklyDetailDB,
    models.FutWsrDB,
    models.FutHoldingDB,
    models.FutPriceLimitDB,
    models.FutIndexDB,
]

for table in tables:
    rows = src.query(table).all()
    if not rows:
        continue
    count = 0
    for row in rows:
        # 将对象转为字典，排除 SQLAlchemy 内部状态
        data = {c.name: getattr(row, c.name) for c in table.__table__.columns}
        dst.execute(table.__table__.insert().values(data))
        count += 1
    dst.commit()
    print(f"Migrated {count} rows from {table.__tablename__}")

src.close()
dst.close()
print("Migration completed.")
```

### 2.6 常见问题

#### Q1: Alembic 在 PostgreSQL 上失败？

确保 `alembic.ini` 中 `sqlalchemy.url` 已更新，或直接用环境变量：

```powershell
$env:DATABASE_URL="postgresql://futures:futures123@localhost:5432/futures_community"
alembic upgrade head
```

#### Q2: Windows 上 Docker 端口冲突？

如果本地已安装 PostgreSQL 并占用 5432 端口：

- 停止本地 PostgreSQL 服务，或
- 修改 `docker-compose.yml` 端口映射为 `"5433:5432"`，并相应修改 `DATABASE_URL`

#### Q3: 需要重新初始化品种和 Mock 数据？

切换数据库后，`main.py` 的 lifespan 会自动执行 `init_db()` + `init_varieties()` + `init_mock_data()`（非生产环境），无需手动操作。

***

## 三、快速参考：核心配置项

| 环境变量               | 说明                | 示例                                                      |
| ------------------ | ----------------- | ------------------------------------------------------- |
| `DATABASE_URL`     | 数据库连接串            | `sqlite:///./futures_community.db` 或 `postgresql://...` |
| `DATA_SOURCE`      | 数据源               | `mock` / `tushare` / `akshare` / `auto`                 |
| `TUSHARE_TOKEN`    | Tushare Pro token | `your_token_here`                                       |
| `SECRET_KEY`       | JWT 签名密钥          | 强随机字符串，≥32 字符                                           |
| `ENABLE_SCHEDULER` | 是否启动定时任务          | `1`（默认）/ `0`                                            |

***

*文档版本：2026-05-04*
