# 期货交流社区 - 数据层 Pipeline 设计方案

> 版本：v2.0（执行校准版）  
> 日期：2026-05-04  
> 目标：在保留当前前端兼容层的前提下，打通「采集 → 映射 → 清洗 → 入库 → API/缓存 → 前端展示」全链路，并为后续合约维度、昨结算价、交易日历和 PostgreSQL 迁移预留空间。

---

## 一、设计结论

当前项目已经存在：

- `ProductDB`：旧前端兼容层，支撑 `/api/products`。
- `VarietyDB` / `RealtimeQuoteDB` / `KlineDataDB`：新行情数据模型。
- `MockCollector` / `AkshareCollector` / `cleaner.py` / `upsert.py` / `scheduler.py`：数据采集与入库雏形。

因此本版 Pipeline 不再建议“删除旧 ProductDB”或“大规模重建模型”。正确路线是：

1. **保留 `ProductDB` 作为兼容层**，短期继续服务旧前端。
2. **新数据主链路以 `varieties + realtime_quotes + kline_data` 为准**。
3. **通过同步任务将 `realtime_quotes` 映射回 `products`**，保证旧接口不破坏。
4. **所有 schema 变更走 Alembic**，包括 `pre_settlement`、资金精度字段、未来 `contract_code`。
5. **scheduler 默认不随 Web 进程启动**，通过 `ENABLE_SCHEDULER=true` 或独立 worker 启动。

---

## 二、端到端数据流

```text
External Source
  ├─ Akshare
  ├─ File CSV/JSON/Parquet
  └─ MockCollector
        ↓
Collector
  只负责获取原始数据，不承担业务清洗
        ↓
Adapter / Mapper
  将外部字段映射为内部标准字段
        ↓
Cleaner / Validator
  类型转换、OHLC 校验、昨结算价、异常过滤、去重
        ↓
Storage / Upsert
  批量写入 realtime_quotes / kline_data
        ↓
Compatibility Sync
  realtime_quotes → products
        ↓
API / Cache
  /api/varieties /api/realtime /api/kline /api/products
        ↓
Frontend
  旧页面继续读 products，新页面逐步迁移到 varieties/realtime/kline
```

---

## 三、数据源策略

| 数据源 | 用途 | 阶段 | 说明 |
|---|---|---|---|
| `MockCollector` | 本地开发、测试兜底 | P0/P1 | 不应在生产默认启用 |
| `akshare` | 实时行情、分钟/日 K | P1 | 免费但字段和稳定性需防腐层保护 |
| 本地文件 | 历史数据回灌、回归测试 | P1/P2 | 可复现、适合 CI fixture |
| Tushare | 可选补充源 | P3 | 需要 token 和积分，暂不作为执行依赖 |

执行阶段先做：

- P0：Mock 数据显式开关，禁止生产自动写弱口令用户。
- P1：Akshare 字段映射集中化，修复合约硬编码。
- P2：FileCollector 支持可复现历史数据导入。
- P3：多数据源优先级和熔断降级。

---

## 四、模块结构

```text
python/data_collector/
├── base.py                 # Collector 抽象接口
├── mock_collector.py        # 本地 mock 数据，开发/测试使用
├── akshare_collector.py     # Akshare 原始数据获取
├── adapters.py              # 字段映射：外部 raw → 内部标准字段
├── cleaner.py               # 类型转换、OHLC、异常过滤、去重
├── upsert.py                # 批量 upsert / insert
├── scheduler.py             # 调度入口，默认不自动启动
└── pipeline.py              # P1/P2 引入：编排 extract → map → clean → load
```

### 4.1 Collector 职责

Collector 只负责外部 I/O：

```python
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

class BaseCollector(ABC):
    @abstractmethod
    def fetch_realtime(self, symbol: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def fetch_kline(
        self,
        contract_code: str,
        period: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        ...
```

注意：K 线接口应优先接受 `contract_code`，而不是只接受品种 `symbol`。短期可由服务层把 `AU` 解析为当前主力 `AU2506`。

### 4.2 Adapter 职责

将不同外部源字段映射到内部标准字段。示例：

```python
def map_akshare_realtime(row: dict, symbol: str) -> dict:
    return {
        "symbol": symbol,
        "current_price": row.get("最新价"),
        "pre_settlement": row.get("昨结算") or row.get("昨结算价"),
        "open_price": row.get("开盘价"),
        "high": row.get("最高价"),
        "low": row.get("最低价"),
        "volume": row.get("成交量"),
        "open_interest": row.get("持仓量"),
        "bid1": row.get("买一价"),
        "ask1": row.get("卖一价"),
    }
```

字段变更只改 Adapter，不改 cleaner/upsert/API。

---

## 五、数据模型策略

### 5.1 保留兼容层

短期保留：

- `ProductDB`
- `/api/products`
- `/api/products/{id}`
- `/api/comments` 当前基于 `product_id` 的评论结构

原因：

- 前端当前仍依赖 products。
- 删除 ProductDB 会扩大改动面。
- 兼容层可以让数据 pipeline 和前端迁移解耦。

### 5.2 新行情主模型

新主链路继续使用：

- `VarietyDB`：品种/当前主力合约元数据。
- `RealtimeQuoteDB`：品种最新行情快照。
- `KlineDataDB`：K 线数据。

P1 建议新增：

- `RealtimeQuoteDB.pre_settlement`：昨结算价。
- `KlineDataDB.contract_code`：合约代码，短期可 nullable，迁移后逐步填充。

P2/P3 可考虑拆出：

- `ContractDB`：独立合约维度。
- `MainContractHistoryDB`：主力合约切换历史。
- `DataIngestionRunDB`：采集批次/质量状态。

### 5.3 精度策略

不要一次性把所有行情展示字段改 Decimal。

执行策略：

- P1：资金语义字段优先 `Numeric`，如 `margin`、`commission`、`target_price`、`stop_loss`。
- P1：`pre_settlement` 如参与涨跌幅计算，使用 `Numeric(15, 4)`。
- P2：评估 `current_price/open/high/low/close` 是否迁移 `Numeric`。
- API 短期保持 number 输出，避免前端大面积改动。

---

## 六、入库与同步策略

### 6.1 Realtime Upsert

实时行情以 `variety_id` 唯一：

```python
def upsert_realtime(db: Session, data: dict) -> None:
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == data["symbol"]).first()
    if not variety:
        return

    stmt = insert(RealtimeQuoteDB).values(
        variety_id=variety.id,
        current_price=data["current_price"],
        pre_settlement=data.get("pre_settlement"),
        change_percent=data.get("change_percent"),
        open_price=data.get("open_price"),
        high=data.get("high"),
        low=data.get("low"),
        volume=data.get("volume"),
        open_interest=data.get("open_interest"),
        updated_at=data["updated_at"],
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["variety_id"],
        set_={
            "current_price": data["current_price"],
            "pre_settlement": data.get("pre_settlement"),
            "change_percent": data.get("change_percent"),
            "open_price": data.get("open_price"),
            "high": data.get("high"),
            "low": data.get("low"),
            "volume": data.get("volume"),
            "open_interest": data.get("open_interest"),
            "updated_at": data["updated_at"],
        },
    )
    db.execute(stmt)
```

注意：commit 边界由调用方控制，便于批量事务。

### 6.2 K-line Bulk Insert

必须避免循环查 variety：

```python
def insert_kline_bulk(db: Session, rows: list[dict], period: str) -> None:
    symbols = {row["symbol"] for row in rows}
    varieties = {
        v.symbol: v.id
        for v in db.query(VarietyDB).filter(VarietyDB.symbol.in_(symbols)).all()
    }

    values = []
    for row in rows:
        variety_id = varieties.get(row["symbol"])
        if not variety_id:
            continue
        values.append({
            "variety_id": variety_id,
            "contract_code": row.get("contract_code"),
            "period": period,
            "trading_time": row["trading_time"],
            "open_price": row["open_price"],
            "high_price": row["high_price"],
            "low_price": row["low_price"],
            "close_price": row["close_price"],
            "volume": row["volume"],
            "open_interest": row.get("open_interest"),
        })

    if values:
        stmt = insert(KlineDataDB).values(values)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["variety_id", "period", "trading_time"]
        )
        db.execute(stmt)
```

长期如果 `contract_code` 加入唯一键，应改为：

```text
UNIQUE(contract_code, period, trading_time)
```

### 6.3 Products 兼容同步

`sync_prices_to_products()` 保留，但必须批量化：

```python
quotes = db.query(RealtimeQuoteDB).options(
    selectinload(RealtimeQuoteDB.variety)
).all()

symbols = {quote.variety.symbol for quote in quotes if quote.variety}
products = {
    product.symbol: product
    for product in db.query(ProductDB).filter(ProductDB.symbol.in_(symbols)).all()
}

for quote in quotes:
    if not quote.variety:
        continue
    product = products.get(quote.variety.symbol)
    if product:
        product.current_price = quote.current_price
        product.change_percent = quote.change_percent
        product.high = quote.high
        product.low = quote.low
        product.volume = quote.volume
        product.updated_at = quote.updated_at
```

---

## 七、清洗与业务校验

Cleaner 必须覆盖：

- 类型转换：空值、`"-"`、`None`、字符串数字。
- OHLC：`high >= max(open, close, low)`，`low <= min(open, close, high)`。
- 价格：`current_price > 0`。
- 成交量/持仓量：非负。
- 去重：K 线按 `(symbol/contract_code, period, trading_time)`。
- 昨结算价：缺失时不崩溃。
- 涨跌幅：优先基于 `pre_settlement` 计算；数据源直接给出的 `change_percent` 可作为参考或 fallback。

示例：

```python
def calc_change_percent(current_price: float, pre_settlement: float | None) -> float | None:
    if not pre_settlement or pre_settlement <= 0:
        return None
    return round((current_price - pre_settlement) / pre_settlement * 100, 4)
```

---

## 八、Scheduler 与执行模式

### 8.1 默认行为

- Web 服务默认不启动 scheduler。
- `.env` 显式设置 `ENABLE_SCHEDULER=true` 才启动。
- 生产长期应改为独立 worker。

### 8.2 任务规划

| 任务 | 频率 | 阶段 | 说明 |
---|---:|---|---|
| `refresh_realtime_quotes` | 30-60 秒 | P0/P1 | 刷新实时行情 |
| `sync_prices_to_products` | 30-60 秒 | P0/P1 | 兼容层同步 |
| `sync_daily_kline` | 每日收盘后 | P1 | 日/小时 K 线补全 |
| `sync_minute_kline` | 5 分钟 | P2 | 分钟 K 线增量 |
| `sync_variety_metadata` | 每周 | P2/P3 | 合约元数据更新 |

### 8.3 Job 保护

P1 必须加入：

```python
scheduler = BackgroundScheduler(job_defaults={
    "max_instances": 1,
    "coalesce": True,
    "misfire_grace_time": 30,
})
```

---

## 九、API 与前端迁移策略

### 9.1 保持旧接口

继续保证：

- `GET /api/products`
- `GET /api/products/{id}`
- `POST /api/comments`
- `GET /api/comments/user/{username}`

### 9.2 新接口作为主链路

逐步推动前端迁移到：

- `GET /api/varieties`
- `GET /api/varieties/{symbol}`
- `GET /api/realtime/{symbol}`
- `GET /api/kline/{symbol}?period=1h&limit=100`

### 9.3 兼容注意事项

- `/api/products` 添加分页时，短期仍返回数组，不引入 `{items,total}` 包裹。
- Decimal 字段短期输出 number，避免前端类型断裂。
- 时间统一 ISO 8601 字符串，K 线和 realtime/comment 保持一致。

---

## 十、数据质量与可观测性

P1/P2 建议增加采集状态记录，最低限度先用日志，长期加表：

```text
data_ingestion_runs
├─ id
├─ job_name
├─ source
├─ started_at
├─ finished_at
├─ status
├─ success_count
├─ failed_count
├─ skipped_count
├─ error_message
└─ metadata_json
```

关键指标：

- 每次采集成功数 / 失败数 / 跳过数。
- 最新行情更新时间。
- K 线缺口数量。
- 清洗失败率。
- 外部数据源连续失败次数。
- products 兼容同步成功数。

---

## 十一、SQLite 与 PostgreSQL 策略

短期：

- SQLite + timeout + WAL。
- scheduler 显式启动。
- 混合读写并发测试。

迁移信号：

- 同时在线用户 > 50。
- K 线数据 > 100 万条。
- 需要多实例部署。
- scheduler 必须独立 worker 化。
- SQLite 锁等待频繁出现。

长期：

- PostgreSQL。
- 可选 TimescaleDB。
- Redis 用于缓存/限流。

---

## 十二、执行阶段

### Phase 0：与后端 P0 对齐

- [ ] DB engine 条件化 + SQLite timeout/WAL。
- [ ] mock data 显式开关。
- [ ] scheduler 显式开关。
- [ ] realtime 缓存不存 ORM。
- [ ] 测试隔离。

### Phase 1：数据链路正确性

- [ ] `pre_settlement` Alembic 迁移。
- [ ] cleaner 增加完整 OHLC 校验。
- [ ] Akshare 合约硬编码修复。
- [ ] `sync_prices_to_products` 批量化。
- [ ] `insert_kline_bulk` 批量 variety lookup。
- [ ] K 线 `contract_code` 方案确定。

### Phase 2：数据质量与可观测性

- [ ] 采集状态日志/表。
- [ ] 文件数据导入器。
- [ ] K 线缺口检测。
- [ ] 外部源失败熔断/降级。
- [ ] `/health` 展示 DB/cache/scheduler 基础状态。

### Phase 3：前端迁移与生产化

- [ ] 前端列表页迁移 `/api/varieties`。
- [ ] 详情页使用 `/api/realtime/{symbol}` + `/api/kline/{symbol}`。
- [ ] PostgreSQL 迁移验证。
- [ ] Redis 缓存/限流。
- [ ] SSE/WebSocket 实时行情推送。

---

## 十三、最终结论

数据 Pipeline 的执行路线是：**不推倒重建，不删除兼容层，先修采集与缓存安全，再补业务字段与迁移，最后推进合约维度和前端新接口迁移**。

这条路线能让后端数据获取能力逐步变强，同时不破坏当前前端页面和旧接口。
