# 期货交流社区 — 数据层端到端 Pipeline 设计方案

> 目标：打通「数据采集 → 清洗 → 入库 → 后端服务 → 前端展示」全链路，解决当前项目中数据模型分裂、K线数据缺失、价格静态化等核心问题。

---

## 一、总体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据层 Pipeline                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │  数据采集层  │ → │  数据清洗层  │ → │  数据存储层  │ → │  数据服务层  │  │
│  │  (Collector)│    │  (Cleaner)  │    │  (Storage)  │    │  (API/Cache)│  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └──────┬──────┘  │
│         ↑                                                         │         │
│         │  外部数据源                                               │         │
│    (爬虫 / akshare / Tushare / 文件)                                ↓         │
│                                                           ┌─────────────┐   │
│                                                           │  前端展示层  │   │
│                                                           │ (Next.js)   │   │
│                                                           └─────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、数据采集层（Collector）

### 2.1 数据源选型建议

| 数据源 | 获取方式 | 适用场景 | 成本 | 推荐度 |
|--------|----------|----------|------|--------|
| **akshare** | Python pip 安装，直接调用 | 国内期货实时/历史行情 | 免费 | ⭐⭐⭐⭐⭐ |
| **Tushare** | API Token 调用 | 期货日线/分钟线 | 积分制（部分免费） | ⭐⭐⭐⭐ |
| **自建爬虫** | requests + BeautifulSoup / Playwright | 特定网站数据补充 | 自行维护 | ⭐⭐⭐ |
| **本地文件** | CSV / JSON / Parquet 批量导入 | 已有历史数据迁移 | 免费 | ⭐⭐⭐⭐ |

**推荐组合**：
- **实时行情**（最新价、涨跌幅）：`akshare.futures_zh_spot()` 或 `akshare.futures_zh_realtime()`，每 30~60 秒拉取一次
- **历史 K 线**（1分钟/5分钟/日K）：`akshare.futures_zh_minute_sina()` / `akshare.futures_daily()`，每日收盘后批量补全
- **品种元数据**（合约代码、交易所、乘数、保证金率）：`akshare.futures_contract_info()`，一次性抓取后定期更新

### 2.2 采集器代码结构

```
python/
├── data_collector/
│   ├── __init__.py
│   ├── base.py              # 采集器抽象基类
│   ├── akshare_collector.py # akshare 适配器
│   ├── file_collector.py    # 本地文件适配器
│   └── scheduler.py         # 定时任务调度
```

**核心采集器基类**（`base.py`）：

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from datetime import datetime

class BaseCollector(ABC):
    """数据采集器抽象基类"""

    @abstractmethod
    def fetch_varieties(self) -> List[Dict[str, Any]]:
        """获取品种元数据列表"""
        pass

    @abstractmethod
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取单个品种实时行情"""
        pass

    @abstractmethod
    def fetch_kline(self, symbol: str, period: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        """
        获取 K 线数据
        :param symbol: 品种代码，如 "CU2506"
        :param period: 周期，如 "1m", "5m", "1h", "1d"
        :param start: 开始时间
        :param end: 结束时间
        """
        pass
```

**akshare 适配器示例**（`akshare_collector.py`）：

```python
import akshare as ak
from datetime import datetime
from .base import BaseCollector

class AkshareCollector(BaseCollector):
    """基于 akshare 的国内期货数据采集器"""

    def fetch_varieties(self):
        """获取国内期货品种列表"""
        df = ak.futures_contract_info()
        # 按品种代码去重，取主力合约信息
        varieties = df[["品种代码", "品种名称", "交易所", "合约乘数", "保证金率"]].drop_duplicates("品种代码")
        return varieties.to_dict("records")

    def fetch_realtime(self, symbol: str):
        """获取实时行情（sina 源）"""
        df = ak.futures_zh_spot(symbol=symbol, market="CF")
        if df.empty:
            return None
        row = df.iloc[0]
        return {
            "symbol": symbol,
            "current_price": float(row.get("最新价", 0)),
            "change_percent": float(row.get("涨跌幅", 0)),
            "open_price": float(row.get("开盘价", 0)),
            "high": float(row.get("最高价", 0)),
            "low": float(row.get("最低价", 0)),
            "volume": int(row.get("成交量", 0)),
            "open_interest": int(row.get("持仓量", 0)),
            "bid1": float(row.get("买一价", 0)),
            "ask1": float(row.get("卖一价", 0)),
            "timestamp": datetime.now(),
        }

    def fetch_kline(self, symbol: str, period: str, start: datetime, end: datetime):
        """获取历史 K 线"""
        # akshare 周期映射
        period_map = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "60m": "60", "1d": "D"}
        ak_period = period_map.get(period, "1")
        df = ak.futures_zh_minute_sina(symbol=symbol, period=ak_period)
        # 过滤时间范围并标准化字段
        df["datetime"] = pd.to_datetime(df["datetime"])
        mask = (df["datetime"] >= start) & (df["datetime"] <= end)
        df = df.loc[mask]
        return df.rename(columns={
            "datetime": "trading_time",
            "open": "open_price",
            "high": "high_price",
            "low": "low_price",
            "close": "close_price",
            "volume": "volume",
        }).to_dict("records")
```

### 2.3 定时采集策略

| 任务 | 频率 | 内容 | 执行方式 |
|------|------|------|----------|
| 实时行情刷新 | 每 30~60 秒 | 拉取所有活跃品种的 `current_price`、`change_percent`、`volume`、`open_interest` | APScheduler `IntervalTrigger` |
| 分钟 K 线补全 | 每 5 分钟 | 增量拉取本交易日分钟 K 线 | APScheduler `IntervalTrigger` |
| 日 K 线补全 | 每日 16:00 | 拉取当日日 K 线 | APScheduler `CronTrigger(hour=16)` |
| 品种元数据同步 | 每周一次 | 检查新上市/下市合约，更新品种表 | APScheduler `CronTrigger(day_of_week="sun", hour=2)` |

**调度器配置**（`scheduler.py`）：

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()

# 实时行情：每 30 秒
scheduler.add_job(
    refresh_realtime_quotes,
    IntervalTrigger(seconds=30),
    id="realtime",
    replace_existing=True,
)

# 日 K 补全：每天 16:05
scheduler.add_job(
    sync_daily_kline,
    CronTrigger(hour=16, minute=5),
    id="daily_kline",
    replace_existing=True,
)

scheduler.start()
```

> **依赖**：`pip install apscheduler pandas akshare`

---

## 三、数据清洗与标准化（Cleaner）

### 3.1 清洗流程

```
原始数据（Raw）
    ↓
┌─────────────────────────────────────────┐
│ 1. 字段映射（Field Mapping）              │
│    将不同数据源的字段名统一为标准命名       │
│    如 sina 的 "最新价" → "current_price"  │
├─────────────────────────────────────────┤
│ 2. 类型转换（Type Casting）               │
│    字符串 → float / int / datetime        │
│    处理 "-"、""、None 等空值               │
├─────────────────────────────────────────┤
│ 3. 数值校验（Validation）                 │
│    价格 > 0，high ≥ low，volume ≥ 0       │
│    涨跌幅在 ±20% 范围内（异常值过滤）      │
├─────────────────────────────────────────┤
│ 4. 去重（Deduplication）                  │
│    K线数据按 (symbol, trading_time) 去重  │
│    实时行情保留最新一条                    │
├─────────────────────────────────────────┤
│ 5. 标准化输出（Normalization）            │
│    统一时间戳格式（UTC / 北京时间）         │
│    统一价格精度（保留 2 位或品种指定精度）  │
└─────────────────────────────────────────┘
    ↓
清洗后数据（Clean）
```

### 3.2 清洗器代码

```python
# python/data_collector/cleaner.py
from datetime import datetime
from typing import Dict, Any, List
import logging

logger = logging.getLogger("data.cleaner")

def clean_realtime(raw: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """清洗实时行情数据"""
    try:
        current = float(raw.get("current_price") or 0)
        open_p = float(raw.get("open_price") or 0)
        high = float(raw.get("high") or 0)
        low = float(raw.get("low") or 0)
        volume = int(raw.get("volume") or 0)
        oi = int(raw.get("open_interest") or 0)

        # 校验
        if current <= 0 or high < low or volume < 0:
            logger.warning(f"[skip] invalid data for {symbol}: {raw}")
            return None

        return {
            "symbol": symbol,
            "current_price": round(current, 2),
            "open_price": round(open_p, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "volume": volume,
            "open_interest": oi,
            "change_percent": round(float(raw.get("change_percent") or 0), 2),
            "updated_at": raw.get("timestamp") or datetime.now(),
        }
    except Exception as e:
        logger.error(f"clean_realtime failed for {symbol}: {e}")
        return None

def clean_kline(raw_list: List[Dict[str, Any]], symbol: str) -> List[Dict[str, Any]]:
    """清洗 K 线数据"""
    cleaned = []
    seen = set()

    for raw in raw_list:
        try:
            ts = raw.get("trading_time")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))

            key = (symbol, ts)
            if key in seen:
                continue
            seen.add(key)

            open_p = float(raw.get("open_price", 0))
            high = float(raw.get("high_price", 0))
            low = float(raw.get("low_price", 0))
            close = float(raw.get("close_price", 0))
            volume = int(raw.get("volume", 0))
            oi = int(raw.get("open_interest", 0)) if raw.get("open_interest") else None

            if high < low or close <= 0:
                continue

            cleaned.append({
                "symbol": symbol,
                "trading_time": ts,
                "open_price": round(open_p, 2),
                "high_price": round(high, 2),
                "low_price": round(low, 2),
                "close_price": round(close, 2),
                "volume": volume,
                "open_interest": oi,
            })
        except Exception as e:
            logger.warning(f"skip invalid kline row: {e}")
            continue

    return cleaned
```

---

## 四、数据库 Schema 设计（Storage）

### 4.1 表结构设计

基于你已有的 `main.py` 进行扩展，保留 `UserDB`、`CommentDB`，将 `ProductDB` 拆分为更专业的数据模型：

```sql
-- 1. 品种元数据表（交易所、合约信息）
CREATE TABLE varieties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) UNIQUE NOT NULL,       -- 品种代码，如 "CU"
    contract_code VARCHAR(30) UNIQUE NOT NULL, -- 合约代码，如 "CU2506"
    name VARCHAR(50) NOT NULL,                -- 品种名称，如 "沪铜"
    exchange VARCHAR(20) NOT NULL,            -- 交易所：SHFE / DCE / CZCE / INE / GFEX
    category VARCHAR(20),                     -- 分类：金属 / 能源化工 / 农产品 / 黑色系 / 贵金属
    contract_month VARCHAR(10),               -- 合约月份
    tick_size DECIMAL(10,4),                  -- 最小变动价位
    multiplier DECIMAL(10,2),                 -- 合约乘数
    margin_rate DECIMAL(5,2),                 -- 保证金率 %
    commission DECIMAL(10,2),                 -- 手续费
    listing_date DATE,                        -- 上市日期
    last_trading_date DATE,                   -- 最后交易日
    is_active BOOLEAN DEFAULT 1,              -- 是否活跃（主力合约）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. 实时行情快照表（最新价，高频更新）
CREATE TABLE realtime_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    variety_id INTEGER NOT NULL REFERENCES varieties(id),
    current_price DECIMAL(15,4) NOT NULL,
    change_percent DECIMAL(8,4),
    open_price DECIMAL(15,4),
    high DECIMAL(15,4),
    low DECIMAL(15,4),
    volume INTEGER,
    open_interest INTEGER,                    -- 持仓量
    bid1 DECIMAL(15,4),                       -- 买一价
    ask1 DECIMAL(15,4),                       -- 卖一价
    updated_at DATETIME NOT NULL,
    UNIQUE(variety_id)
);

-- 3. K 线数据表（按时间周期存储）
CREATE TABLE kline_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    variety_id INTEGER NOT NULL REFERENCES varieties(id),
    period VARCHAR(10) NOT NULL,              -- 1m / 5m / 15m / 30m / 1h / 1d / 1w
    trading_time DATETIME NOT NULL,
    open_price DECIMAL(15,4) NOT NULL,
    high_price DECIMAL(15,4) NOT NULL,
    low_price DECIMAL(15,4) NOT NULL,
    close_price DECIMAL(15,4) NOT NULL,
    volume INTEGER NOT NULL,
    open_interest INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(variety_id, period, trading_time)  -- 防止重复入库
);

-- 4. 用户自选股 / 关注列表
CREATE TABLE watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    variety_id INTEGER NOT NULL REFERENCES varieties(id),
    resistance_level DECIMAL(15,4),           -- 用户设定的阻力位
    support_level DECIMAL(15,4),              -- 用户设定的支撑位
    notes TEXT,
    is_notified BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, variety_id)
);

-- 5. 用户观点 / 涨跌观点（看涨/看跌/中性）
CREATE TABLE opinions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    variety_id INTEGER NOT NULL REFERENCES varieties(id),
    type VARCHAR(10) NOT NULL CHECK(type IN ('bullish', 'bearish', 'neutral')),
    reason TEXT,
    target_price DECIMAL(15,4),
    stop_loss DECIMAL(15,4),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 索引优化
CREATE INDEX idx_kline_lookup ON kline_data(variety_id, period, trading_time);
CREATE INDEX idx_realtime_time ON realtime_quotes(updated_at);
CREATE INDEX idx_varieties_category ON varieties(category);
CREATE INDEX idx_varieties_active ON varieties(is_active);
```

### 4.2 SQLAlchemy 模型定义（`models.py`）

建议将模型从 `main.py` 中抽离，单独维护：

```python
# python/models.py
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey, Boolean, UniqueConstraint, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import datetime

Base = declarative_base()

class VarietyDB(Base):
    __tablename__ = "varieties"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    contract_code = Column(String(30), unique=True, nullable=False)
    name = Column(String(50), nullable=False)
    exchange = Column(String(20), nullable=False)
    category = Column(String(20), index=True)
    contract_month = Column(String(10))
    tick_size = Column(Float)
    multiplier = Column(Float)
    margin_rate = Column(Float)
    commission = Column(Float)
    listing_date = Column(DateTime)
    last_trading_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    realtime = relationship("RealtimeQuoteDB", back_populates="variety", uselist=False)
    klines = relationship("KlineDataDB", back_populates="variety")
    watchlists = relationship("WatchlistDB", back_populates="variety")
    opinions = relationship("OpinionDB", back_populates="variety")

class RealtimeQuoteDB(Base):
    __tablename__ = "realtime_quotes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id"), unique=True, nullable=False)
    current_price = Column(Float, nullable=False)
    change_percent = Column(Float)
    open_price = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Integer)
    open_interest = Column(Integer)
    bid1 = Column(Float)
    ask1 = Column(Float)
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.now)

    variety = relationship("VarietyDB", back_populates="realtime")

class KlineDataDB(Base):
    __tablename__ = "kline_data"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id"), nullable=False)
    period = Column(String(10), nullable=False)
    trading_time = Column(DateTime, nullable=False)
    open_price = Column(Float, nullable=False)
    high_price = Column(Float, nullable=False)
    low_price = Column(Float, nullable=False)
    close_price = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False)
    open_interest = Column(Integer)
    created_at = Column(DateTime, default=datetime.datetime.now)

    variety = relationship("VarietyDB", back_populates="klines")

    __table_args__ = (
        UniqueConstraint("variety_id", "period", "trading_time", name="uix_kline"),
        Index("idx_kline_lookup", "variety_id", "period", "trading_time"),
    )

# 保留原有用户/评论模型
class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    comments = relationship("CommentDB", back_populates="user")
    watchlists = relationship("WatchlistDB", back_populates="user")
    opinions = relationship("OpinionDB", back_populates="user")

class CommentDB(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    user = relationship("UserDB", back_populates="comments")

class WatchlistDB(Base):
    __tablename__ = "watchlists"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    variety_id = Column(Integer, ForeignKey("varieties.id"), nullable=False)
    resistance_level = Column(Float)
    support_level = Column(Float)
    notes = Column(Text)
    is_notified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    user = relationship("UserDB", back_populates="watchlists")
    variety = relationship("VarietyDB", back_populates="watchlists")

class OpinionDB(Base):
    __tablename__ = "opinions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    variety_id = Column(Integer, ForeignKey("varieties.id"), nullable=False)
    type = Column(String(10), nullable=False)  # bullish / bearish / neutral
    reason = Column(Text)
    target_price = Column(Float)
    stop_loss = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.now)
    user = relationship("UserDB", back_populates="opinions")
    variety = relationship("VarietyDB", back_populates="opinions")
```

### 4.3 入库策略（Upsert）

实时行情和 K 线都需要"存在则更新、不存在则插入"：

```python
from sqlalchemy.dialects.sqlite import insert

def upsert_realtime(db: Session, data: dict):
    """实时行情 upsert"""
    stmt = insert(RealtimeQuoteDB).values(**data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["variety_id"],
        set_={
            "current_price": data["current_price"],
            "change_percent": data["change_percent"],
            "high": data["high"],
            "low": data["low"],
            "volume": data["volume"],
            "updated_at": data["updated_at"],
        }
    )
    db.execute(stmt)
    db.commit()

def insert_kline_bulk(db: Session, rows: list):
    """K 线批量插入（忽略重复）"""
    stmt = insert(KlineDataDB).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["variety_id", "period", "trading_time"])
    db.execute(stmt)
    db.commit()
```

> SQLite 3.24+ 支持 `ON CONFLICT`，确保你的 SQLite 版本 ≥ 3.24。

---

## 五、后端数据服务层（API / Cache）

### 5.1 新增 API 设计

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/varieties` | GET | 品种列表（关联实时行情） |
| `/api/varieties/{symbol}` | GET | 品种详情（含最新行情） |
| `/api/kline/{symbol}` | GET | K 线数据，`?period=1h&limit=100` |
| `/api/realtime` | GET | 所有品种实时行情快照 |
| `/api/realtime/{symbol}` | GET | 单个品种实时行情 |

### 5.2 K 线 API 实现示例

```python
@app.get("/api/kline/{symbol}")
def get_kline(
    symbol: str,
    period: str = Query("1h", regex="^(1m|5m|15m|30m|1h|1d|1w)$"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        raise HTTPException(404, "品种不存在")

    klines = (
        db.query(KlineDataDB)
        .filter(KlineDataDB.variety_id == variety.id, KlineDataDB.period == period)
        .order_by(KlineDataDB.trading_time.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "time": k.trading_time.isoformat(),
            "open": k.open_price,
            "high": k.high_price,
            "low": k.low_price,
            "close": k.close_price,
            "volume": k.volume,
            "open_interest": k.open_interest,
        }
        for k in reversed(klines)
    ]
```

### 5.3 内存缓存策略

实时行情查询频繁，可用简单内存缓存减少数据库压力：

```python
from functools import lru_cache
from datetime import datetime, timedelta

# 品种元数据很少变化，可缓存
@lru_cache(maxsize=128)
def get_variety_by_symbol(symbol: str):
    ...

# 实时行情缓存 5 秒
_realtime_cache = {}
_realtime_cache_time = {}

def get_cached_realtime(symbol: str, db: Session):
    now = datetime.now()
    if symbol in _realtime_cache:
        if now - _realtime_cache_time[symbol] < timedelta(seconds=5):
            return _realtime_cache[symbol]
    data = db.query(RealtimeQuoteDB)...  # 查库
    _realtime_cache[symbol] = data
    _realtime_cache_time[symbol] = now
    return data
```

> 如果后续用户量变大，可升级为 Redis 缓存。

---

## 六、前端数据消费策略

### 6.1 数据流设计

```
页面加载
    ↓
Server Component 预取品种列表（SSR）
    ↓
Client Component 挂载后启动轮询
    ↓
每 30s 调用 /api/realtime 刷新价格
    ↓
用户切换周期 → 调用 /api/kline/{symbol}?period=xxx
```

### 6.2 API 客户端扩展（`lib/api.ts`）

```typescript
// 新增 K 线接口
async getKline(symbol: string, period: string = '1h', limit: number = 100): Promise<KlineData[]> {
  return this.request<KlineData[]>(`/api/kline/${symbol}?period=${period}&limit=${limit}`)
}

// 新增实时行情接口
async getRealtime(symbol: string): Promise<RealtimeQuote> {
  return this.request<RealtimeQuote>(`/api/realtime/${symbol}`)
}
```

### 6.3 K 线图数据绑定

```typescript
// products/[id]/page.tsx
const [klineData, setKlineData] = useState<KlineData[]>([])
const [period, setPeriod] = useState('1h')

useEffect(() => {
  api.getKline(product.symbol, period).then(setKlineData)
}, [period, product.symbol])

// KlineChart 传入真实数据
<KlineChart data={klineData} symbol={product.symbol} ... />
```

### 6.4 实时价格轮询

```typescript
// 在品种列表页 / 详情页启用
useEffect(() => {
  const interval = setInterval(() => {
    api.getRealtime(symbol).then(quote => {
      setProduct(prev => ({ ...prev, current_price: quote.current_price, change_percent: quote.change_percent }))
    })
  }, 30000) // 30 秒轮询
  return () => clearInterval(interval)
}, [symbol])
```

---

## 七、SQLite vs PostgreSQL 选型建议

| 维度 | SQLite | PostgreSQL |
|------|--------|------------|
| **部署复杂度** | 零配置，单文件 | 需安装服务 |
| **并发写入** | 较差（写锁） | 优秀（MVCC） |
| **数据量** | < 10GB 可用 | 无上限 |
| **K线查询性能** | 10万条内可接受 | 百万级轻松 |
| **时间序列扩展** | 无 | TimescaleDB |
| **推荐阶段** | **开发 / 个人使用** | **生产 / 多用户** |

**建议**：
- **现阶段**：继续使用 SQLite，数据量可控，部署简单
- **迁移信号**：当同时在线用户 > 50，或 K 线数据 > 100 万条，或需要多实例部署时，迁移到 PostgreSQL + TimescaleDB
- **迁移成本**：SQLAlchemy 模型基本无需改动，只需更换 `DATABASE_URL`

---

## 八、实施 Checklist（按优先级）

### 阶段 1：数据模型重建（1~2 天）
- [ ] 新建 `python/models.py`，定义 `VarietyDB`、`RealtimeQuoteDB`、`KlineDataDB`、`WatchlistDB`、`OpinionDB`
- [ ] 保留并迁移 `UserDB`、`CommentDB`
- [ ] 删除旧的 `ProductDB`（或保留作为视图兼容层）
- [ ] 初始化脚本自动建表并灌入品种元数据

### 阶段 2：采集器开发（1~2 天）
- [ ] 安装 `akshare`、`apscheduler`、`pandas`
- [ ] 实现 `AkshareCollector` 适配器
- [ ] 实现数据清洗器 `cleaner.py`
- [ ] 配置定时任务（实时行情 30s、日 K 收盘后）

### 阶段 3：后端 API 补全（1 天）
- [ ] 新增 `/api/varieties`、`/api/kline/{symbol}`、`/api/realtime/{symbol}`
- [ ] 修改 `/api/products` 兼容层（如前端暂不改动，可映射到 varieties + realtime join）
- [ ] 增加内存缓存

### 阶段 4：前端对接（1 天）
- [ ] `api.ts` 增加 K 线、实时行情接口
- [ ] 品种详情页 `KlineChart` 绑定真实数据
- [ ] 增加价格自动轮询刷新
- [ ] 统一涨跌幅颜色体系

---

## 九、关键依赖清单

```txt
# python/requirements.txt 新增
akshare>=1.14.0
apscheduler>=3.10.0
pandas>=2.0.0
numpy>=1.24.0
passlib[bcrypt]>=1.7.4      # 替换 SHA256
python-dotenv>=1.0.0         # 环境变量管理
```

```bash
# 前端无需新增依赖（使用原生 fetch + setInterval 即可）
# 如需更优雅的数据管理，可选装：
npm install swr          # 数据获取 + 缓存 + 轮询
```

---

## 十、风险与注意事项

1. **akshare 稳定性**：akshare 依赖新浪财经等数据源，可能在交易时段出现限流或字段变更。建议：
   - 增加重试机制（最多 3 次，指数退避）
   - 抓取失败时保留上一次有效数据
   - 记录失败日志以便排查

2. **SQLite 并发写入**：定时任务与后端 API 同时写库可能触发锁等待。建议：
   - 采集器与后端使用同一个数据库连接池
   - 或采集器独立写库文件，后端只读（复杂，不推荐）
   - 短期可用，长期建议 PostgreSQL

3. **K 线数据膨胀**：分钟 K 线增长最快。建议：
   - 只保留最近 3 个月的分钟 K 线
   - 更早年份保留日 K 即可
   - 定期归档冷数据到 CSV / Parquet
