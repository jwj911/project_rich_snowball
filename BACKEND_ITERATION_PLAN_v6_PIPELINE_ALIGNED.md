# 期货社区后端重构 — Pipeline 对齐版迭代计划 v6

> 版本：v6.0（Pipeline 对齐完整版）  
> 日期：2026-05-04  
> 综合来源：`DATA_PIPELINE_DESIGN.md` v2.0 + `BACKEND_ITERATION_PLAN_v5_ROBUST.md`  
> 核心原则：**Pipeline 数据流优先、兼容层渐进迁移、Schema 变更可回滚、精度策略分阶段**

---

## 一、v5 相对 Pipeline 设计的不完善之处

对比 `DATA_PIPELINE_DESIGN.md` 后，v5 存在以下 10 处缺失或冲突：

| # | 缺失/冲突项 | Pipeline 设计 | v5 状态 | 影响 |
|---|-----------|-------------|---------|------|
| 1 | **Adapter 层缺失** | P1 新建 `adapters.py`，集中字段映射 | v5 未提及 Adapter 模块 | Akshare 字段变更时影响面扩散到 cleaner/upsert/API |
| 2 | **Pipeline 编排缺失** | P1/P2 引入 `pipeline.py`：`extract→map→clean→load` | v5 无 Pipeline 编排概念 | 采集器与入库逻辑仍耦合在 scheduler 中 |
| 3 | **精度策略冲突** | P1 只做资金字段 Decimal，行情字段 P2 评估 | v5 P0 要求全量 Float→Decimal | 前端兼容性风险被低估，改动面过大 |
| 4 | **FileCollector 缺失** | P2 支持 CSV/JSON/Parquet 历史回灌 | v5 完全未提及 | 无法做可复现的回归测试和历史数据导入 |
| 5 | **K 线接口签名** | `fetch_kline` 应接受 `contract_code` | v5 未提及接口变更 | 合约维度扩展时回溯成本大 |
| 6 | **Commit 边界设计** | commit 由调用方控制，便于批量事务 | v5 未提及 | upsert 函数内部 commit 导致无法批量回滚 |
| 7 | **数据质量表缺失** | P2 建议 `data_ingestion_runs` 表 | v5 无此设计 | 无法追踪采集批次质量和故障 |
| 8 | **分钟 K 线任务缺失** | P2 增加 `sync_minute_kline` (5分钟) | v5 只有日 K | 分钟级数据缺失 |
| 9 | **合约元数据更新缺失** | P2/P3 `sync_variety_metadata` (每周) | v5 无此任务 | 合约换月信息无法自动更新 |
| 10 | **迁移信号未定义** | 明确 5 个 PostgreSQL 迁移触发条件 | v5 只说"长期迁移" | 无法判断迁移时机 |

本文档将以上 10 项全部纳入，并重新校准优先级。

---

## 二、Pipeline 端到端数据流（全局视图）

```text
External Source                    # Akshare / File / Mock
       ↓
Collector (base.py)                # 纯 I/O，无业务逻辑
       ↓
Adapter (adapters.py)              # 外部字段 → 内部标准字段
       ↓
Pipeline (pipeline.py)             # extract → map → clean → load 编排
       ↓
Cleaner (cleaner.py)               # 类型转换、OHLC、异常过滤、去重
       ↓
Storage (upsert.py)                # 批量 upsert / insert，commit 由 Pipeline 控制
       ↓
Compatibility Sync                 # realtime_quotes → products
       ↓
API / Cache / Frontend             # varieties / realtime / kline / products
```

**铁律**：
- Collector 只负责外部 I/O，不清洗。
- Adapter 只负责字段映射，不查询数据库。
- Cleaner 只负责业务校验，不感知数据源。
- Upsert 只负责写入，commit 边界由 Pipeline 控制。
- Scheduler 只负责任务调度，不直接调用 Collector/Cleaner/Upsert。

---

## 三、P0 修复清单（本周必须完成）

P0 目标：**消除安全、启动、缓存、测试隔离风险**。不涉及 schema 迁移或 Pipeline 重构。

### 3.1 DB Engine 条件化 + WAL + 健康检查

与 v5 一致，见 `BACKEND_ITERATION_PLAN_v5_ROBUST.md §2.1`。

### 3.2 Mock / Scheduler 环境隔离

与 v5 一致，见 `BACKEND_ITERATION_PLAN_v5_ROBUST.md §2.2`。

### 3.3 RobustCache 重写

与 v5 一致，见 `BACKEND_ITERATION_PLAN_v5_ROBUST.md §2.3`。

### 3.4 Auth 限流 + 恒定时间登录

与 v5 一致，见 `BACKEND_ITERATION_PLAN_v5_ROBUST.md §2.4`。

### 3.5 测试隔离基础设施

与 v5 一致，见 `BACKEND_ITERATION_PLAN_v5_ROBUST.md §2.5`。

**Pipeline 对齐补充**：
- P0 测试必须能覆盖 `MockCollector` → `cleaner` → `upsert` 全链路。
- 使用 `seed_varieties` fixture 注入测试数据，不依赖外部 akshare。

---

## 四、P1 修复清单（第 2-3 周）：数据链路正确性

### 4.1 精度策略校准（修正 v5 冲突）

**修订策略**（与 Pipeline 对齐）：

```python
# P1 只做资金语义字段
margin = Column(Numeric(10, 4), default=0)
commission = Column(Numeric(10, 4), default=0)
target_price = Column(Numeric(15, 4))
stop_loss = Column(Numeric(15, 4))

# P1 新增 pre_settlement 用 Numeric
pre_settlement = Column(Numeric(15, 4))

# P1 行情字段仍保留 Float，P2 评估后再迁移
current_price = Column(Float, nullable=False)   # P2 再评估
open_price = Column(Float)
high = Column(Float)
low = Column(Float)
```

**理由**：
- 行情展示字段精度要求到小数点后 2 位，Float 在 ±1e-6 范围内可接受。
- 资金计算字段（保证金、手续费）必须精确，优先迁移 Decimal。
- 避免 P0/P1 阶段前端大规模类型适配。

### 4.2 K 线接口签名统一（修正 v5 缺失 #5）

**文件**：`python/data_collector/base.py`、`pipeline.py`、`variety_collector` 相关

**修订内容**：
- `BaseCollector.fetch_kline` 首参从 `symbol: str` 改为 `contract_code: str`，与 Pipeline 设计一致。
- `DataPipeline.run_kline` 同步改为 `run_kline(self, contract_code: str, period: str, ...)`。
- 内部通过 `contract_code` 查询 `VarietyDB` 获取 `symbol` 与 `variety_id`。

**理由**：
- 品种（variety）与合约（contract）是不同维度；K 线数据本质挂靠在合约上。
- 不提前统一签名，P3/P4 主连拼接和合约换月将产生大量回溯修改。

**验收**：
- [ ] `fetch_kline` 所有实现类（Mock / Akshare / File）首参均为 `contract_code`。
- [ ] Pipeline 内部通过 `contract_code` 反查 `variety_id`，不再直接传 `symbol`。

---

### 4.3 Adapter 层（新增，P1 必须）

**文件**：`python/data_collector/adapters.py`（新建）

```python
"""外部数据源字段 → 内部标准字段映射。
所有字段变更只改此处，不扩散到 cleaner/upsert/API。
"""
from typing import Any

def map_akshare_realtime(row: dict[str, Any], symbol: str) -> dict[str, Any]:
    """Akshare futures_zh_spot 原始行 → 内部标准字段"""
    return {
        "symbol": symbol,
        "current_price": _to_float(row.get("最新价")),
        "pre_settlement": _to_float(row.get("昨结算") or row.get("昨结算价")),
        "open_price": _to_float(row.get("开盘价")),
        "high": _to_float(row.get("最高价")),
        "low": _to_float(row.get("最低价")),
        "volume": _to_int(row.get("成交量")),
        "open_interest": _to_int(row.get("持仓量")),
        "bid1": _to_float(row.get("买一价")),
        "ask1": _to_float(row.get("卖一价")),
        "updated_at": datetime.now(timezone.utc),
    }

def map_akshare_kline(row: dict[str, Any], symbol: str, period: str) -> dict[str, Any]:
    """Akshare K 线原始行 → 内部标准字段"""
    return {
        "symbol": symbol,
        "period": period,
        "trading_time": _parse_datetime(row.get("时间") or row.get("datetime")),
        "open_price": _to_float(row.get("开盘") or row.get("open")),
        "high_price": _to_float(row.get("最高") or row.get("high")),
        "low_price": _to_float(row.get("最低") or row.get("low")),
        "close_price": _to_float(row.get("收盘") or row.get("close")),
        "volume": _to_int(row.get("成交量") or row.get("volume")),
        "open_interest": _to_int(row.get("持仓量") or row.get("持仓")),
    }

def _to_float(val: Any) -> float | None:
    if val in (None, "-", "", "None"):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def _to_int(val: Any) -> int | None:
    if val in (None, "-", "", "None"):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None

def _parse_datetime(val: Any):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y%m%d %H:%M:%S", "%Y-%m-%d"]:
        try:
            return datetime.strptime(str(val), fmt)
        except ValueError:
            continue
    return None
```

**验收**：
- [ ] akshare 字段变更时，只改 `adapters.py`，不改 cleaner/upsert。
- [ ] `"-"`、`""`、`"None"` 均被正确处理为 `None`。
- [ ] 日期格式兼容 3 种常见格式。

### 4.4 Cleaner 完整校验（与 Pipeline 对齐）

**文件**：`python/data_collector/cleaner.py`

```python
"""数据清洗与业务校验。不感知数据源，只处理内部标准字段。"""
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

def clean_realtime(data: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    """清洗单条实时行情。返回 None 表示丢弃。"""
    if not data or not isinstance(data, dict):
        return None
    
    # 必填字段检查
    required = ["current_price", "high", "low", "volume"]
    if any(data.get(k) is None for k in required):
        logger.debug(f"[{symbol}] Missing required fields")
        return None
    
    # 价格正数检查
    current_price = data["current_price"]
    if current_price <= 0:
        logger.debug(f"[{symbol}] Invalid price: {current_price}")
        return None
    
    # OHLC 逻辑检查
    if not _valid_ohlc({
        "open_price": data.get("open_price", current_price),
        "high_price": data["high"],
        "low_price": data["low"],
        "close_price": current_price,
    }):
        logger.warning(f"[{symbol}] OHLC inconsistency: {data}")
        return None
    
    # 涨跌幅计算（优先使用 pre_settlement）
    change_percent = data.get("change_percent")
    pre_settlement = data.get("pre_settlement")
    if change_percent is None and pre_settlement and pre_settlement > 0:
        change_percent = round((current_price - pre_settlement) / pre_settlement * 100, 4)
    
    return {
        "symbol": symbol,
        "current_price": float(current_price),
        "pre_settlement": float(pre_settlement) if pre_settlement else None,
        "change_percent": float(change_percent) if change_percent else 0.0,
        "open_price": float(data.get("open_price", current_price)),
        "high": float(data["high"]),
        "low": float(data["low"]),
        "volume": int(data["volume"]),
        "open_interest": int(data["open_interest"]) if data.get("open_interest") else None,
        "updated_at": data.get("updated_at", datetime.now(timezone.utc)),
    }

def clean_kline(rows: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    """清洗 K 线列表，去重并按时间排序。"""
    seen = set()
    cleaned = []
    
    for row in rows:
        if not _valid_ohlc(row):
            logger.debug(f"[{symbol}] Skipping invalid OHLC row: {row}")
            continue
        
        key = (row.get("trading_time"), row.get("period"))
        if key in seen:
            continue
        seen.add(key)
        
        cleaned.append({
            "symbol": symbol,
            "contract_code": row.get("contract_code"),
            "period": row["period"],
            "trading_time": row["trading_time"],
            "open_price": float(row["open_price"]),
            "high_price": float(row["high_price"]),
            "low_price": float(row["low_price"]),
            "close_price": float(row["close_price"]),
            "volume": int(row["volume"]),
            "open_interest": int(row["open_interest"]) if row.get("open_interest") else None,
        })
    
    cleaned.sort(key=lambda x: x["trading_time"])
    return cleaned

def _valid_ohlc(row: dict[str, Any]) -> bool:
    """OHLC 逻辑一致性校验。"""
    open_p = row.get("open_price") or row.get("open")
    high = row.get("high_price") or row.get("high")
    low = row.get("low_price") or row.get("low")
    close = row.get("close_price") or row.get("close")
    
    if any(v is None for v in [open_p, high, low, close]):
        return False
    
    if any(v < 0 for v in [open_p, high, low, close]):
        return False
    if high < low:
        return False
    if high < max(open_p, close):
        return False
    if low > min(open_p, close):
        return False
    
    return True
```

**验收**：
- [ ] `"-"`、`""`、`"None"` 经 Adapter 处理后为 `None`，Cleaner 不崩溃。
- [ ] `high < low` 丢弃。
- [ ] `high < max(open, close)` 丢弃。
- [ ] `pre_settlement` 缺失时，`change_percent` 保留数据源原始值或设为 0。
- [ ] K 线去重：相同 `(trading_time, period)` 只保留第一条。

### 4.5 Upsert Commit 边界控制（修正 v5 缺失）

**文件**：`python/data_collector/upsert.py`

```python
"""批量写入。本模块不执行 commit，commit 由 Pipeline/Scheduler 控制。"""

def upsert_realtime(db: Session, data: dict) -> None:
    """写入或更新实时行情。调用方负责 commit。"""
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == data["symbol"]).first()
    if not variety:
        logger.warning(f"Variety not found: {data['symbol']}")
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

def insert_kline_bulk(db: Session, rows: list[dict], period: str) -> int:
    """批量写入 K 线。返回实际写入条数。调用方负责 commit。"""
    if not rows:
        return 0
    
    symbols = {row["symbol"] for row in rows}
    varieties = {
        v.symbol: v.id
        for v in db.query(VarietyDB).filter(VarietyDB.symbol.in_(symbols)).all()
    }
    
    values = []
    skipped = 0
    for row in rows:
        variety_id = varieties.get(row["symbol"])
        if not variety_id:
            skipped += 1
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
    
    if not values:
        return 0
    
    stmt = insert(KlineDataDB).values(values)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["variety_id", "period", "trading_time"]
    )
    result = db.execute(stmt)
    
    inserted = result.rowcount if hasattr(result, "rowcount") else len(values)
    if skipped:
        logger.warning(f"K-line bulk insert skipped {skipped} rows (variety not found)")
    return inserted
```

### 4.6 Pipeline 编排器（新增，P1 必须）

**文件**：`python/data_collector/pipeline.py`（新建）

```python
"""数据采集 Pipeline：extract → map → clean → load。
Scheduler 只调用 Pipeline.run()，不直接操作 Collector/Cleaner/Upsert。
"""
import logging
from typing import Type

from data_collector.base import BaseCollector
from data_collector.adapters import map_akshare_realtime, map_akshare_kline
from data_collector.cleaner import clean_realtime, clean_kline
from data_collector.upsert import upsert_realtime, insert_kline_bulk
from models import SessionLocal

logger = logging.getLogger(__name__)

class DataPipeline:
    """可配置的采集 Pipeline。"""
    
    def __init__(
        self,
        collector: BaseCollector,
        adapter=None,
        cleaner=None,
    ):
        self.collector = collector
        self.adapter = adapter
        self.cleaner = cleaner
    
    def run_realtime(self, symbols: list[str]) -> dict:
        """执行实时行情采集 Pipeline。返回统计信息。"""
        stats = {"processed": 0, "failed": 0, "skipped": 0}
        db = SessionLocal()
        
        try:
            for symbol in symbols:
                try:
                    raw = self.collector.fetch_realtime(symbol)
                    if raw is None:
                        stats["skipped"] += 1
                        continue
                    
                    # Adapter 映射
                    if self.adapter:
                        raw = self.adapter(raw, symbol)
                    
                    # Cleaner 校验
                    if self.cleaner:
                        data = self.cleaner(raw, symbol)
                        if data is None:
                            stats["skipped"] += 1
                            continue
                    else:
                        data = raw
                    
                    upsert_realtime(db, data)
                    stats["processed"] += 1
                    
                except Exception as exc:
                    stats["failed"] += 1
                    logger.error(f"Pipeline failed for {symbol}: {exc}", exc_info=True)
            
            db.commit()
            logger.info(f"Realtime pipeline completed: {stats}")
            return stats
            
        except Exception as exc:
            db.rollback()
            logger.critical(f"Realtime pipeline aborted: {exc}", exc_info=True)
            raise
        finally:
            db.close()
    
    def run_kline(self, symbol: str, period: str, limit: int = 100) -> dict:
        """执行 K 线采集 Pipeline。"""
        stats = {"processed": 0, "failed": 0, "skipped": 0}
        db = SessionLocal()
        
        try:
            raw_rows = self.collector.fetch_kline(symbol, period, limit=limit)
            if not raw_rows:
                return stats
            
            # Adapter 映射
            if self.adapter:
                raw_rows = [self.adapter(row, symbol, period) for row in raw_rows]
            
            # Cleaner 校验
            if self.cleaner:
                rows = self.cleaner(raw_rows, symbol)
            else:
                rows = raw_rows
            
            inserted = insert_kline_bulk(db, rows, period)
            db.commit()
            
            stats["processed"] = inserted
            stats["skipped"] = len(raw_rows) - inserted
            logger.info(f"K-line pipeline completed: {stats}")
            return stats
            
        except Exception as exc:
            db.rollback()
            logger.critical(f"K-line pipeline aborted: {exc}", exc_info=True)
            raise
        finally:
            db.close()
```

**Mock / 初始化数据适配**：
- `init_mock_data.py` 与 `init_varieties.py` 在 P1 完成后需通过 `Adapter` 生成内部标准字段，再落入数据库。
- 避免种子数据绕过 Cleaner 导致字段不一致（如 `"-"` 未转 `None`）。

**Scheduler 改造**：

```python
# scheduler.py
from data_collector.pipeline import DataPipeline
from data_collector.mock_collector import MockCollector
from data_collector.adapters import map_akshare_realtime
from data_collector.cleaner import clean_realtime

pipeline = DataPipeline(
    collector=MockCollector(),  # P1 可切换为 AkshareCollector + 熔断器
    adapter=map_akshare_realtime,
    cleaner=clean_realtime,
)

def refresh_realtime_quotes():
    symbols = [v.symbol for v in db.query(VarietyDB).all()]
    stats = pipeline.run_realtime(symbols)
    # stats 可用于监控告警
```

**验收**：
- [ ] Scheduler 只调用 `pipeline.run_realtime()`，不直接操作 collector/cleaner/upsert。
- [ ] Pipeline 异常时 `db.rollback()`，已处理的数据不残留。
- [ ] `stats` 返回 processed/failed/skipped 计数。
- [ ] `init_mock_data.py` 生成的数据通过 Cleaner 校验后入库。

### 4.7 同步任务批量化（与 Pipeline 对齐）

见 `BACKEND_ITERATION_PLAN_v5_ROBUST.md §3.3`。

### 4.8 完整 P1 检查表

| # | 问题 | 文件 | 修复方案 | Pipeline 对齐点 |
|---|------|------|----------|----------------|
| 1 | 精度策略校准 | `models.py` | 资金字段 `Numeric`，行情字段保留 Float | 与 Pipeline §5.3 一致 |
| 2 | `pre_settlement` 迁移 | Alembic | 新增字段，`Nullable=True` | Pipeline §5.2 |
| 3 | Adapter 层 | 新建 `adapters.py` | 集中字段映射 | Pipeline §4.2 |
| 4 | Cleaner 完整校验 | `cleaner.py` | `"-"/"None"` 处理、OHLC、去重 | Pipeline §7 |
| 5 | Upsert commit 边界 | `upsert.py` | 不内部 commit，由 Pipeline 控制 | Pipeline §6.1 |
| 6 | Pipeline 编排 | 新建 `pipeline.py` | `extract→map→clean→load` | Pipeline §4 |
| 6a| K 线接口签名统一 | `base.py` / `pipeline.py` | `fetch_kline(contract_code, ...)` | 修正 v5 #5 |
| 7 | K-line bulk variety 查询 | `upsert.py` | 单次查询 symbol→id dict | Pipeline §6.2 |
| 8 | sync_prices N+1 | `scheduler.py` | `selectinload` + 批量 product 映射 | Pipeline §6.3 |
| 9 | Product comments N+1 | `products.py` | `selectinload` + limit 100 | Pipeline §9.1 |
| 10 | 输入验证增强 | `schemas.py` | `EmailStr` + pattern + length | v5 P1 |
| 11 | 空白评论 | `schemas.py` | `mode="before"` strip 校验 | v5 P1 |
| 12 | JWT 异常粒度 | `dependencies.py` | 只 catch `PyJWTError` + `ValueError` | v5 P1 |
| 13 | Akshare 硬编码合约 | `akshare_collector.py` | DB 查 active contract | Pipeline §4.1 |
| 14 | Production docs | `main.py` | `docs_url=None` in prod | v5 P1 |
| 15 | CORS 环境配置 | `main.py` | 从 `CORS_ORIGINS` 读取 | v5 P1 |
| 16 | Products 分页 | `products.py` | `skip/limit` 可选，默认 limit=1000 | Pipeline §9.3 |
| 17 | 评论统一鉴权 | `comments.py` | `Depends(get_current_user_dependency)` | v5 P1 |
| 18 | `/health` /ready | 新建 | DB ping + cache stats + scheduler | v5 P1 |
| 19 | Scheduler 重入保护 | `scheduler.py` | `max_instances=1, coalesce, misfire_grace_time` | Pipeline §8.3 |
| 20 | SECRET_KEY 强度 | `config.py` | 生产 `>= 32` chars | v5 P1 |

---

## 五、P2 优化清单（第 4-6 周）：数据质量与可观测性

### 5.1 SQLite Alembic 限制说明（P1-P2 前置）

**背景**：
SQLite 对 `ALTER TABLE` 支持有限（不支持 `DROP COLUMN`、`ALTER COLUMN` 类型变更）。当 P1 引入 `pre_settlement`（`Nullable=True`）及 P2 新增 `data_ingestion_runs` 时，Alembic `autogenerate` 生成的迁移脚本在 SQLite 上可能执行失败。

**应对措施**：
1. 新增列使用 `batch_alter_table`（Alembic `op.batch_alter_table`）或重建表模式。
2. 在 `alembic/env.py` 中开启 `render_as_batch=True`：
   ```python
   context.configure(
       connection=connection,
       target_metadata=target_metadata,
       render_as_batch=True,  # 关键：启用 SQLite batch 模式
   )
   ```
3. 每次生成迁移后，**人工审阅**迁移脚本，确认 SQLite 兼容性；禁止直接 `alembic upgrade head` 不检查。

**验收**：
- [ ] `alembic/env.py` 已配置 `render_as_batch=True`。
- [ ] P1 `pre_settlement` 迁移脚本在全新 SQLite 库与已有库上均能通过。

---

### 5.2 FileCollector（新增，修正 v5 缺失）

**文件**：`python/data_collector/file_collector.py`（新建）

```python
"""本地文件数据源：CSV / JSON / Parquet。
用于历史数据回灌、回归测试、CI fixture。
"""
import json
import pandas as pd
from pathlib import Path
from typing import Any

from data_collector.base import BaseCollector

class FileCollector(BaseCollector):
    def __init__(self, data_dir: str = "./data/fixtures"):
        self.data_dir = Path(data_dir)
    
    def fetch_realtime(self, symbol: str) -> dict[str, Any] | None:
        path = self.data_dir / f"{symbol}_realtime.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)
    
    def fetch_kline(
        self,
        contract_code: str,
        period: str,
        start=None,
        end=None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        path = self.data_dir / f"{contract_code}_{period}.csv"
        if not path.exists():
            return []
        
        df = pd.read_csv(path)
        if start:
            df = df[df["trading_time"] >= start]
        if end:
            df = df[df["trading_time"] <= end]
        
        df = df.sort_values("trading_time").tail(limit)
        return df.to_dict("records")
```

**验收**：
- [ ] 从 CSV 回灌 1000 条 K 线数据，Pipeline 正常处理。
- [ ] CI 中使用 FileCollector 替代 akshare，测试可复现。

### 5.3 数据质量表（新增，修正 v5 缺失）

**文件**：`python/models.py`（新增模型）

```python
class DataIngestionRunDB(Base):
    """采集批次质量追踪。"""
    __tablename__ = "data_ingestion_runs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(50), nullable=False, index=True)
    source = Column(String(50), nullable=False)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime)
    status = Column(String(20), default="running")  # running/success/failed
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    error_message = Column(Text)
    metadata_json = Column(Text)  # JSON 字符串，存储额外信息
```

**Pipeline 集成**：

```python
# pipeline.py
from models import DataIngestionRunDB, SessionLocal

def run_realtime(self, symbols: list[str]) -> dict:
    run = DataIngestionRunDB(
        job_name="refresh_realtime_quotes",
        source=self.collector.__class__.__name__,
        started_at=datetime.now(timezone.utc),
    )
    db = SessionLocal()
    db.add(run)
    db.commit()
    
    try:
        stats = {"processed": 0, "failed": 0, "skipped": 0}
        # ... 采集逻辑 ...
        
        run.status = "success"
        run.success_count = stats["processed"]
        run.failed_count = stats["failed"]
        run.skipped_count = stats["skipped"]
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)[:1000]
    finally:
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.close()
    
    return stats
```

**验收**：
- [ ] 每次采集后 `data_ingestion_runs` 有记录。
- [ ] 失败时 `error_message` 非空。
- [ ] 可通过 `SELECT * FROM data_ingestion_runs ORDER BY started_at DESC LIMIT 10` 查看质量。

### 5.4 分钟 K 线任务（新增，修正 v5 缺失）

**文件**：`python/data_collector/scheduler.py`

```python
# P2 增加分钟 K 线任务
scheduler.add_job(
    sync_minute_kline,
    IntervalTrigger(minutes=5),
    id="minute_kline",
    replace_existing=True,
)

def sync_minute_kline():
    """每 5 分钟采集一次分钟 K 线。"""
    symbols = [v.symbol for v in db.query(VarietyDB).all()]
    for symbol in symbols:
        try:
            pipeline.run_kline(symbol, period="1m", limit=5)
        except Exception as exc:
            logger.error(f"Minute kline failed for {symbol}: {exc}")
```

### 5.5 合约元数据更新（新增，修正 v5 缺失）

**文件**：`python/data_collector/scheduler.py`

```python
# P2/P3 增加合约元数据更新
scheduler.add_job(
    sync_variety_metadata,
    CronTrigger(day_of_week="sun", hour=2, minute=0),
    id="variety_metadata",
    replace_existing=True,
)

def sync_variety_metadata():
    """每周日凌晨更新合约元数据（主力合约、到期日等）。"""
    # 从 akshare 获取合约列表，更新 VarietyDB.active_contract
    pass
```

### 5.6 完整 P2 检查表

| # | 问题 | 修复方案 | Pipeline 对齐点 |
|---|------|----------|----------------|
| 1 | FileCollector | 新建 `file_collector.py` | Pipeline §3 |
| 2 | 数据质量表 | 新建 `DataIngestionRunDB` | Pipeline §10 |
| 3 | 分钟 K 线任务 | `sync_minute_kline` (5分钟) | Pipeline §8.2 |
| 4 | 合约元数据更新 | `sync_variety_metadata` (每周) | Pipeline §8.2 |
| 4a| SQLite Alembic batch 模式 | `alembic/env.py` `render_as_batch=True` | 避免迁移失败 |
| 5 | K 线缺口检测 | 对比 `data_ingestion_runs` 与 K 线表时间序列 | Pipeline §10 |
| 6 | 外部源熔断降级 | CircuitBreaker + MockCollector fallback | v5 专项 |
| 7 | 错误响应标准化 | `{code, message, errors[], timestamp}` | v5 P2 |
| 8 | 结构化日志 | JSON format | v5 P2 |
| 9 | CI/CD | GitHub Actions | v5 P2 |
| 10 | 契约快照 | OpenAPI diff | v5 P2 |
| 11 | 性能基线 | pytest-benchmark | v5 P2 |
| 12 | Import/类型规范 | isort / mypy | v5 P2 |

---

## 六、P3 生产化清单（第 7-8 周）

### 6.1 Product 兼容层生命周期评估（P3 前置）

**背景**：
当前系统存在**模型双轨制**：旧 `ProductDB` + `/api/products/*` 供现有前端调用；新 `VarietyDB` / `RealtimeQuoteDB` / `KlineDataDB` + `/api/varieties`、`/api/realtime`、`/api/kline` 是正式数据层。`scheduler.py` 每 30 秒将 `realtime_quotes` 同步回 `products` 表保证兼容。

**P3 评估动作**：
1. 统计 `/api/products/*` 接口调用量（通过日志或 `data_ingestion_runs` 间接估算）。
2. 确认前端所有页面已切至 `/api/varieties`、`/api/realtime`、`/api/kline`。
3. 若调用量连续 7 天为 0，则在 P3 末尾或 P4 初**废弃 Product 兼容层**：
   - 删除 `ProductDB` 模型与 `products` 表（Alembic 迁移）。
   - 删除 `routers/products.py` 或保留 410 Gone 响应。
   - 停止 `sync_to_products` 定时任务，减少 50% 写负载。

**验收**：
- [ ] P3 评审会议明确 Product 层废弃时间表。
- [ ] 废弃前 2 周在前端代码中搜索 `api/products` 引用，确认清零。

---

### 6.2 PostgreSQL 迁移信号（新增，修正 v5 缺失）

**明确 5 个迁移触发条件**（满足任意 2 个即启动迁移）：

1. 同时在线用户 > 50
2. K 线数据量 > 100 万条
3. 需要多实例部署（> 1 个 Web worker）
4. Scheduler 必须独立 worker 化
5. SQLite `database is locked` 每周出现 > 3 次

**迁移准备**：
- 使用 `pgloader` 或自定义脚本迁移 SQLite → PostgreSQL
- 验证 Alembic 迁移在 PostgreSQL 上可执行
- 性能基线对比：同一查询在 SQLite vs PostgreSQL 的延迟

### 6.3 完整 P3 检查表

| # | 问题 | 修复方案 |
|---|------|----------|
| 1 | PostgreSQL 迁移 | `pgloader` + Alembic 验证 |
| 2 | Redis 缓存 | 替换内存缓存，支持分布式 |
| 3 | Redis 限流 | 替换 slowapi 内存限流 |
| 4 | Scheduler 独立 worker | `python -m data_collector.worker` |
| 5 | 交易日历 | `exchange_calendars` 或自建表 |
| 6 | 夜盘处理 | 交易时段分段生成 K 线 |
| 7 | 50 并发 Locust 压测 | 错误率 0%，P95 < 200ms |

---

## 七、P4 高级特性（第 9-12 周）

| # | 问题 | 修复方案 |
|---|------|----------|
| 1 | SSE/WebSocket 推送 | 替代前端轮询 |
| 2 | 合约换月自动处理 | `MainContractHistoryDB` + 自动切换 |
| 3 | 主连 K 线拼接 | 多合约 K 线按换月时间拼接 |
| 4 | 审计日志 | 用户操作全记录 |
| 5 | Prometheus + Sentry | 指标 + 错误追踪 |
| 6 | 混沌测试 | 磁盘满、网络分区、DB 故障注入 |

---

## 八、Review 计划（Pipeline 对齐版）

### 8.1 七维检查表

| 维度 | 权重 | 当前 | 目标 | 关键检查项 |
|------|------|------|------|-----------|
| Pipeline 完整性 | 15% | 4/10 | 8/10 | Adapter→Pipeline→Cleaner→Upsert 链路完整 |
| 架构设计 | 10% | 7/10 | 8/10 | Service 层、防腐层 |
| 性能并发 | 15% | 5/10 | 8/10 | WAL、缓存锁、N+1、深分页 |
| 安全边界 | 15% | 7/10 | 9/10 | 限流、JWT、CORS、时序攻击 |
| 可观测性 | 15% | 3/10 | 8/10 | 结构化日志、/health、数据质量表 |
| 业务正确 | 15% | 5/10 | 8/10 | OHLC、昨结算价、精度、合约 |
| 灾难恢复 | 15% | 2/10 | 7/10 | 熔断、降级、备份、回滚、重试 |
| **总体** | **100%** | **56/100** | **80/100** | |

### 8.2 Review 执行流程

**Round 1：Pipeline 链路审计**
- Collector 是否只负责 I/O
- Adapter 是否集中了所有字段映射
- Cleaner 是否不感知数据源
- Upsert 是否不内部 commit
- Scheduler 是否只调用 Pipeline

**Round 2：数据质量审计**
- `data_ingestion_runs` 是否有每次采集记录
- 失败采集是否有 `error_message`
- K 线数据是否有时间缺口
- 清洗失败率是否 < 1%

**Round 3-7**：同 v5（安全审计、并发压测、混沌工程、性能压测、灾难恢复）

---

## 九、时间线（Pipeline 对齐版）

```
Week 1 (P0 - 安全与隔离)
├─ Day 1: DB engine 条件化 + WAL + PRAGMA + 健康检查
├─ Day 2: Mock/Scheduler 环境隔离 + 生产断言
├─ Day 3: RobustCache 重写（RLock + LRU + ORM 检测）
├─ Day 4: Auth 限流 + 恒定时间登录
├─ Day 5: 测试隔离 conftest.py + 事务回滚
└─ Day 6-7: P0 Review + 安全审计 + 并发测试

Week 2-3 (P1 - Pipeline 数据链路)
├─ Day 1:   K 线接口签名统一（contract_code）+ base.py 调整
├─ Day 2:   Adapter 层 + Cleaner 完整校验（"-"/"None" 处理、OHLC）
├─ Day 3:   Pipeline 编排器（extract→map→clean→load）
├─ Day 4:   Upsert commit 边界控制 + K-line bulk 优化
├─ Day 5:   pre_settlement Alembic 迁移 + SQLite batch 模式验证
├─ Day 6:   精度策略（资金 Decimal）+ sync_prices N+1 修复
├─ Day 7:   Product comments N+1 修复 + init_mock_data 适配 Pipeline
├─ Day 8:   Scheduler 重入保护 + Akshare 合约硬编码修复
└─ Day 9-10: /health /ready + 输入验证 + JWT 异常粒度 + P1 Review

Week 4-6 (P2 - 可观测性与数据质量)
├─ Day 1-2:  FileCollector + pandas 依赖评估 + 历史数据回灌测试
├─ Day 3-4:  DataIngestionRunDB + Pipeline 集成 + metadata_json 使用规范
├─ Day 5:    分钟 K 线任务 + 合约元数据更新
├─ Day 6:    K 线缺口检测 + 熔断器设计
├─ Day 7:    DB 重试装饰器 + 结构化日志
├─ Day 8:    错误响应标准化 + CI/CD 脚手架
├─ Day 9:    契约快照 + 性能基线
└─ Day 10:   P2 Review + 数据质量审计

Week 7-8 (P3 - 生产化)
├─ Day 1-2:  Product 兼容层调用量统计 + 废弃/保留决策
├─ Day 3-4:  PostgreSQL 迁移验证（触发条件评估）
├─ Day 5:    Redis 缓存 + 分布式限流
├─ Day 6:    Scheduler 独立 worker
├─ Day 7:    交易日历 + 夜盘处理
├─ Day 8:    Docker Compose backend 服务启用验证
├─ Day 9:    50 并发 Locust 压测
└─ Day 10:   P3 Review + 容量测试

Week 9-12 (P4 - 高级特性)
├─ SSE/WebSocket 实时推送
├─ 合约换月 + 主连 K 线拼接
├─ 审计日志 + Prometheus + Sentry
├─ 混沌测试
└─ P4 Review + 生产验收
```

---

## 十、验收标准（Pipeline 对齐版）

| 阶段 | 标准 |
|------|------|
| **P0 完成** | pytest 全绿；测试隔离；缓存并发安全；限流生效；生产断言生效；WAL 确认 |
| **P1 完成** | + Pipeline 链路审计通过（Collector→Adapter→Cleaner→Upsert）；Adapter 字段映射集中；Cleaner 处理 `"-"`/`"None"`；Upsert 不内部 commit；pre_settlement 迁移完成；sync_prices N+1 修复 |
| **P2 完成** | + FileCollector 可用；DataIngestionRunDB 有记录；分钟 K 线任务运行；K 线缺口检测通过；熔断降级自动切换 |
| **上线标准** | P0 + P1 完成；旧接口兼容；前端联调通过；init_mock_data 通过 Cleaner；混沌测试通过（kill scheduler/DB locked/采集器失败） |
| **生产级标准** | 全部 P1-P3 完成；PostgreSQL 验证；监控告警接入；100 万 K线 < 200ms；50 并发 0% 错误；数据质量表可追溯 30 天 |

---

## 十一、一句话总结

> **v6.0 的核心变化是"Pipeline 数据流优先"：新增 Adapter 防腐层、Pipeline 编排器、FileCollector、数据质量表、分钟 K 线任务、合约元数据更新，并将精度策略从"全量 Decimal"修正为"资金字段优先"。10 处 v5 相对 Pipeline 设计的缺失已全部补齐，确保采集→映射→清洗→入库→同步→API 全链路可观测、可回滚、可降级。**
