# 后端数据层大迭代计划

> 版本：v1.0  
> 日期：2026-05-01  
> 依据：`DATA_PIPELINE_DESIGN.md` + 当前代码审查结果  
> 目标：重建数据模型层、打通数据采集 Pipeline、补齐 K 线与实时行情 API、实现动态价格更新

---

## 一、当前状态 vs 目标状态

### 1.1 当前状态（As-Is）

```
python/
├── main.py              # 316 行，含所有模型/路由/业务逻辑
├── init_data.py         # 引用不存在的模型，无法运行
├── requirements.txt     # 依赖列表
└── futures_community.db # SQLite 数据库（3 张表）
```

| 维度 | 现状 |
|------|------|
| 数据模型 | 仅 `UserDB` / `ProductDB` / `CommentDB`，`init_data.py` 引用的 `FuturesVarietyDB` 等不存在 |
| K 线数据 | 无表、无 API、前端只能展示固定 mock 数据 |
| 实时行情 | 无表、无 API、`ProductDB` 价格是静态死数据 |
| 自选股/观点 | 无表、无 API |
| 数据采集 | 无采集器、无定时任务 |
| 代码组织 | 单文件堆砌，无分层 |

### 1.2 目标状态（To-Be）

```
python/
├── main.py                      # 仅做 App 组装与启动
├── models.py                    # 统一 ORM 模型层（8 张表）
├── schemas.py                   # Pydantic DTO
├── dependencies.py              # get_db / get_current_user
├── config.py                    # 环境变量与全局配置
├── routers/
│   ├── __init__.py
│   ├── auth.py                  # 注册/登录/用户信息
│   ├── varieties.py             # 品种列表/详情/分类/搜索
│   ├── kline.py                 # K 线数据查询
│   ├── realtime.py              # 实时行情快照
│   ├── comments.py              # 评论 CRUD
│   └── watchlist.py             # 自选股/观点（可选）
├── data_collector/
│   ├── __init__.py
│   ├── base.py                  # 采集器抽象基类
│   ├── akshare_collector.py     # akshare 适配器
│   ├── cleaner.py               # 数据清洗与标准化
│   ├── scheduler.py             # APScheduler 定时任务配置
│   └── init_varieties.py        # 品种元数据初始化脚本
├── alembic/                     # 数据库迁移
├── tests/
│   └── test_p0_fixes.py         # 已有测试
├── .env                         # 环境变量
├── requirements.txt
└── futures_community.db
```

| 维度 | 目标 |
|------|------|
| 数据模型 | 8 张表：users、varieties、realtime_quotes、kline_data、comments、watchlists、opinions、products(兼容视图) |
| K 线数据 | 支持 1m/5m/15m/30m/1h/1d/1w 查询，按品种+周期+时间索引 |
| 实时行情 | 每 30s 采集一次，内存缓存 5s，Upsert 到 realtime_quotes |
| 动态价格 | 定时任务刷新 `current_price` / `change_percent` / `high` / `low` / `volume` |
| 代码组织 | 模型/Schema/路由/依赖完全拆分，遵循 FastAPI 最佳实践 |

---

## 二、迭代阶段总览

| 阶段 | 名称 | 预计工期 | 核心产出 | 前置依赖 |
|------|------|----------|----------|----------|
| **阶段一** | 模型层重建 + Alembic 迁移 | 1~2 天 | `models.py`、8 张表、可运行的 `init_data.py` | 无 |
| **阶段二** | 数据采集与清洗 | 1~2 天 | `data_collector/`、定时任务、品种元数据初始化 | 阶段一 |
| **阶段三** | API 层重构与补全 | 1 天 | `routers/`、`schemas.py`、K 线/实时行情/分页/搜索 API | 阶段一 |
| **阶段四** | 动态价格更新 + 缓存 | 0.5~1 天 | 定时刷新价格、内存缓存、前端轮询对接 | 阶段二+三 |

> **建议执行顺序**：阶段一 → 阶段二与阶段三可并行（二偏数据、三偏接口） → 阶段四收尾

---

## 三、阶段一：模型层重建 + Alembic 迁移（1~2 天）

### 3.1 目标
- 统一并扩展数据模型，消除 `init_data.py` 的 `ImportError`
- 引入 Alembic 做 schema 版本管理
- 保留旧 `ProductDB` 作为兼容层（前端暂不改动）
- 新建 `init_varieties.py` 替代旧的 `init_data.py`

### 3.2 涉及文件

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `python/models.py` | 统一 ORM 模型 |
| 新建 | `python/config.py` | 数据库 URL、SECRET_KEY 等配置 |
| 新建 | `python/alembic.ini` + `alembic/` | 迁移配置 |
| 新建 | `python/data_collector/init_varieties.py` | 品种元数据初始化 |
| 修改 | `python/main.py` | 删除模型定义，改为从 models 导入 |
| 修改 | `python/requirements.txt` | 追加 alembic |
| 删除（或归档） | `python/init_data.py` | 旧初始化脚本，功能被新脚本替代 |

### 3.3 模型定义（models.py）

基于 `DATA_PIPELINE_DESIGN.md` 的 Schema，保留已有模型，扩展新模型：

```python
# python/models.py
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime,
    Text, ForeignKey, Boolean, UniqueConstraint, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import datetime
from config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class VarietyDB(Base):
    """品种元数据表（替代/扩展 ProductDB）"""
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
    comments = relationship("CommentDB", back_populates="variety")
    watchlists = relationship("WatchlistDB", back_populates="variety")
    opinions = relationship("OpinionDB", back_populates="variety")


class RealtimeQuoteDB(Base):
    """实时行情快照表"""
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
    """K 线数据表"""
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


class UserDB(Base):
    """用户表（保留原有）"""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    comments = relationship("CommentDB", back_populates="user")
    watchlists = relationship("WatchlistDB", back_populates="user")
    opinions = relationship("OpinionDB", back_populates="user")


class CommentDB(Base):
    """评论表（关联到 varieties 而非 products）"""
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    user = relationship("UserDB", back_populates="comments")
    variety = relationship("VarietyDB", back_populates="comments")


class WatchlistDB(Base):
    """用户自选股/关注列表"""
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
    """用户观点/涨跌观点"""
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


class ProductDB(Base):
    """
    兼容层：保留旧 ProductDB，前端 /api/products 继续走此表。
    阶段四后，通过定时任务将 realtime_quotes 数据同步到此处，
    或改为 varieties + realtime_quotes 的视图/联合查询。
    """
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    symbol = Column(String(20), unique=True, index=True, nullable=False)
    current_price = Column(Float, nullable=False)
    change_percent = Column(Float, default=0)
    open_price = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Float)
    category = Column(String(20))
    margin = Column(Float, default=0)
    commission = Column(Float, default=0)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
```

### 3.4 配置中心（config.py）

```python
# python/config.py
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./futures_community.db")
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
```

### 3.5 Alembic 初始化命令

```bash
cd python
pip install alembic

# 初始化
alembic init alembic

# 修改 alembic.ini：sqlalchemy.url = sqlite:///./futures_community.db
# 修改 alembic/env.py：target_metadata = models.Base.metadata

# 生成首个迁移脚本（创建所有表）
alembic revision --autogenerate -m "init_all_tables"

# 执行迁移
alembic upgrade head
```

### 3.6 品种元数据初始化脚本

```python
# python/data_collector/init_varieties.py
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, VarietyDB
from config import DATABASE_URL


@contextmanager
def get_db_session():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_varieties():
    varieties = [
        {"symbol": "AU", "contract_code": "AU2506", "name": "黄金", "exchange": "SHFE", "category": "贵金属", "margin_rate": 8, "commission": 15},
        {"symbol": "AG", "contract_code": "AG2506", "name": "白银", "exchange": "SHFE", "category": "贵金属", "margin_rate": 9, "commission": 12},
        {"symbol": "CU", "contract_code": "CU2506", "name": "铜", "exchange": "SHFE", "category": "有色金属", "margin_rate": 10, "commission": 18},
        {"symbol": "RB", "contract_code": "RB2506", "name": "螺纹钢", "exchange": "SHFE", "category": "黑色系", "margin_rate": 12, "commission": 8},
        {"symbol": "I", "contract_code": "I2506", "name": "铁矿石", "exchange": "DCE", "category": "黑色系", "margin_rate": 11, "commission": 10},
        {"symbol": "SC", "contract_code": "SC2506", "name": "原油", "exchange": "INE", "category": "能源化工", "margin_rate": 15, "commission": 20},
        {"symbol": "MA", "contract_code": "MA2506", "name": "甲醇", "exchange": "ZCE", "category": "能源化工", "margin_rate": 8, "commission": 6},
        {"symbol": "M", "contract_code": "M2506", "name": "豆粕", "exchange": "DCE", "category": "农产品", "margin_rate": 10, "commission": 7},
        {"symbol": "C", "contract_code": "C2506", "name": "玉米", "exchange": "DCE", "category": "农产品", "margin_rate": 8, "commission": 5},
        {"symbol": "CF", "contract_code": "CF2506", "name": "棉花", "exchange": "ZCE", "category": "农产品", "margin_rate": 12, "commission": 14},
    ]

    with get_db_session() as db:
        for v in varieties:
            if not db.query(VarietyDB).filter(VarietyDB.symbol == v["symbol"]).first():
                db.add(VarietyDB(**v))
        db.commit()
        print(f"已初始化 {len(varieties)} 个品种")


if __name__ == "__main__":
    init_varieties()
```

### 3.7 阶段一验收标准

- [ ] `python/models.py` 包含全部 8 个模型定义，无语法错误
- [ ] `alembic upgrade head` 成功创建所有表
- [ ] `python/data_collector/init_varieties.py` 运行后，`varieties` 表有 10 条数据
- [ ] 旧的 `init_data.py` 已删除或归档，不再引起 `ImportError`
- [ ] `main.py` 能从 `models` 导入所有模型，自身不再定义模型

---

## 四、阶段二：数据采集与清洗（1~2 天）

### 4.1 目标
- 实现基于 akshare 的期货数据采集器
- 实现数据清洗器（字段映射、类型转换、数值校验、去重）
- 配置 APScheduler 定时任务（实时行情 30s、日 K 收盘后）
- 采集器可独立运行，也可被主进程调用

### 4.2 涉及文件

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `python/data_collector/__init__.py` | 包标记 |
| 新建 | `python/data_collector/base.py` | 采集器抽象基类 |
| 新建 | `python/data_collector/akshare_collector.py` | akshare 适配器 |
| 新建 | `python/data_collector/cleaner.py` | 数据清洗器 |
| 新建 | `python/data_collector/scheduler.py` | APScheduler 定时任务 |
| 新建 | `python/data_collector/upsert.py` | SQLite Upsert 工具函数 |
| 修改 | `python/requirements.txt` | 追加 akshare、apscheduler、pandas、numpy |

### 4.3 采集器基类（base.py）

直接复用 `DATA_PIPELINE_DESIGN.md` 中的设计：

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from datetime import datetime

class BaseCollector(ABC):
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
        """
        pass
```

### 4.4 akshare 适配器（akshare_collector.py）

```python
import akshare as ak
from datetime import datetime
from .base import BaseCollector

class AkshareCollector(BaseCollector):
    def fetch_varieties(self):
        df = ak.futures_contract_info()
        varieties = df[["品种代码", "品种名称", "交易所", "合约乘数", "保证金率"]].drop_duplicates("品种代码")
        return varieties.to_dict("records")

    def fetch_realtime(self, symbol: str):
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
            "updated_at": datetime.now(),
        }

    def fetch_kline(self, symbol: str, period: str, start: datetime, end: datetime):
        period_map = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "60m": "60", "1d": "D"}
        ak_period = period_map.get(period, "1")
        df = ak.futures_zh_minute_sina(symbol=symbol, period=ak_period)
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

### 4.5 数据清洗器（cleaner.py）

```python
import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger("data.cleaner")

def clean_realtime(raw: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    try:
        current = float(raw.get("current_price") or 0)
        open_p = float(raw.get("open_price") or 0)
        high = float(raw.get("high") or 0)
        low = float(raw.get("low") or 0)
        volume = int(raw.get("volume") or 0)

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
            "change_percent": round(float(raw.get("change_percent") or 0), 2),
            "updated_at": raw.get("updated_at") or datetime.now(),
        }
    except Exception as e:
        logger.error(f"clean_realtime failed for {symbol}: {e}")
        return None

def clean_kline(raw_list: List[Dict[str, Any]], symbol: str) -> List[Dict[str, Any]]:
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
            })
        except Exception as e:
            logger.warning(f"skip invalid kline row: {e}")
            continue
    return cleaned
```

### 4.6 Upsert 工具（upsert.py）

```python
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from models import RealtimeQuoteDB, KlineDataDB

def upsert_realtime(db: Session, data: dict):
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
    stmt = insert(KlineDataDB).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["variety_id", "period", "trading_time"])
    db.execute(stmt)
    db.commit()
```

### 4.7 定时任务调度（scheduler.py）

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import logging

logger = logging.getLogger("data.scheduler")
scheduler = BackgroundScheduler()

def refresh_realtime_quotes():
    """每 30 秒刷新实时行情"""
    logger.info("Refreshing realtime quotes...")
    # 实现：遍历 varieties，调用 AkshareCollector.fetch_realtime + clean + upsert
    pass

def sync_daily_kline():
    """每天 16:05 补全日 K"""
    logger.info("Syncing daily kline...")
    # 实现：遍历 varieties，调用 AkshareCollector.fetch_kline + clean + bulk insert
    pass

scheduler.add_job(refresh_realtime_quotes, IntervalTrigger(seconds=30), id="realtime", replace_existing=True)
scheduler.add_job(sync_daily_kline, CronTrigger(hour=16, minute=5), id="daily_kline", replace_existing=True)

def start_scheduler():
    scheduler.start()
    logger.info("Scheduler started")

def shutdown_scheduler():
    scheduler.shutdown()
    logger.info("Scheduler shutdown")
```

### 4.8 阶段二验收标准

- [ ] `python -m data_collector.akshare_collector` 可独立运行并打印品种列表
- [ ] `cleaner.py` 对脏数据（负数价格、 high < low 等）正确过滤
- [ ] `upsert_realtime` 测试：重复插入同一品种只更新价格，不新增记录
- [ ] `scheduler.py` 启动后，每 30s 控制台有刷新日志（可先用 mock 数据测试）
- [ ] akshare 采集失败时有 try/except + logger.error，不崩溃

---

## 五、阶段三：API 层重构与补全（1 天）

### 5.1 目标
- 拆分 `main.py` 为 FastAPI 标准项目结构
- 补齐 K 线查询、实时行情、品种分页/分类/搜索 API
- 保留 `/api/products` 兼容层，前端无需立即改动
- `schemas.py` 统一定义所有 Pydantic DTO

### 5.2 涉及文件

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `python/schemas.py` | Pydantic DTO |
| 新建 | `python/dependencies.py` | get_db、get_current_user |
| 新建 | `python/routers/__init__.py` | 包标记 |
| 新建 | `python/routers/auth.py` | 注册/登录/Me |
| 新建 | `python/routers/varieties.py` | 品种列表/详情/分类/搜索 |
| 新建 | `python/routers/kline.py` | K 线数据查询 |
| 新建 | `python/routers/realtime.py` | 实时行情快照 |
| 新建 | `python/routers/comments.py` | 评论 CRUD |
| 修改 | `python/main.py` | 只做 app = FastAPI() + include_router |

### 5.3 schemas.py（核心 DTO）

```python
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import List, Optional
from datetime import datetime as dt
import html

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: dt

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class VarietyResponse(BaseModel):
    id: int
    symbol: str
    name: str
    exchange: str
    category: Optional[str]
    current_price: float
    change_percent: float
    margin_rate: Optional[float]
    commission: Optional[float]

class KlineResponse(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int

class RealtimeResponse(BaseModel):
    symbol: str
    current_price: float
    change_percent: float
    open_price: Optional[float]
    high: Optional[float]
    low: Optional[float]
    volume: Optional[int]
    updated_at: dt

class CommentCreate(BaseModel):
    variety_id: int
    content: str = Field(..., min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def sanitize_content(cls, v: str) -> str:
        return html.escape(v.strip())

class CommentResponse(BaseModel):
    id: int
    variety_id: int
    user_id: int
    username: str
    content: str
    created_at: dt
```

### 5.4 路由示例（varieties.py + kline.py）

```python
# python/routers/varieties.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from models import VarietyDB
from schemas import VarietyResponse
from dependencies import get_db

router = APIRouter(prefix="/api/varieties", tags=["品种"])

@router.get("", response_model=List[VarietyResponse])
def get_varieties(
    category: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    q = db.query(VarietyDB)
    if category:
        q = q.filter(VarietyDB.category == category)
    if search:
        q = q.filter(VarietyDB.name.contains(search))
    return q.offset(skip).limit(limit).all()

@router.get("/{symbol}", response_model=VarietyResponse)
def get_variety(symbol: str, db: Session = Depends(get_db)):
    v = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not v:
        raise HTTPException(404, "品种不存在")
    return v
```

```python
# python/routers/kline.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from models import KlineDataDB, VarietyDB
from schemas import KlineResponse
from dependencies import get_db

router = APIRouter(prefix="/api/kline", tags=["K线"])

@router.get("/{symbol}", response_model=List[KlineResponse])
def get_kline(
    symbol: str,
    period: str = Query("1h", regex="^(1m|5m|15m|30m|1h|1d|1w)$"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
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
        }
        for k in reversed(klines)
    ]
```

### 5.5 main.py 最终形态

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from config import SECRET_KEY
from models import init_db
from routers import auth, varieties, kline, realtime, comments

app = FastAPI(title="期货交流社区 API", version="2.0.0")

origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(varieties.router)
app.include_router(kline.router)
app.include_router(realtime.router)
app.include_router(comments.router)

# 兼容旧 /api/products 路由（可映射到 varieties）
# @app.get("/api/products") ...

if __name__ == "__main__":
    init_db()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 5.6 阶段三验收标准

- [ ] `main.py` 行数 < 50，只做路由组装
- [ ] `/api/varieties` 支持 `?category=贵金属&search=黄金&skip=0&limit=20`
- [ ] `/api/kline/{symbol}?period=1h&limit=100` 返回正确 OHLCV JSON
- [ ] `/api/realtime/{symbol}` 返回最新行情快照
- [ ] 旧 `/api/products` 仍能访问（兼容层）
- [ ] FastAPI Swagger UI (`/docs`) 可正常打开，所有接口有文档

---

## 六、阶段四：动态价格更新 + 缓存（0.5~1 天）

### 6.1 目标
- 定时任务将 `realtime_quotes` 的最新价格同步到 `products` 表（兼容前端旧接口）
- 内存缓存实时行情，减少数据库查询压力
- 前端价格自动轮询刷新

### 6.2 涉及文件

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `python/data_collector/scheduler.py` | 增加价格同步任务 |
| 新建 | `python/services/cache.py` | 简单内存缓存 |
| 修改 | `python/routers/realtime.py` | 读取时优先走缓存 |
| 修改 | `frontend/lib/api.ts` | 增加轮询机制 |
| 修改 | `frontend/app/page.tsx` / `products/page.tsx` | 接入实时刷新 |

### 6.3 价格同步任务

```python
# 在 scheduler.py 中增加
def sync_prices_to_products():
    """每 30 秒将 realtime_quotes 同步到 products 表"""
    from sqlalchemy.orm import Session
    from models import SessionLocal, RealtimeQuoteDB, ProductDB

    db = SessionLocal()
    try:
        quotes = db.query(RealtimeQuoteDB).all()
        for q in quotes:
            product = db.query(ProductDB).filter(ProductDB.symbol == q.variety.symbol).first()
            if product:
                product.current_price = q.current_price
                product.change_percent = q.change_percent
                product.high = q.high
                product.low = q.low
                product.volume = q.volume
                product.updated_at = q.updated_at
        db.commit()
        logger.info(f"Synced {len(quotes)} prices to products")
    finally:
        db.close()

scheduler.add_job(sync_prices_to_products, IntervalTrigger(seconds=30), id="sync_prices", replace_existing=True)
```

### 6.4 内存缓存（services/cache.py）

```python
from datetime import datetime, timedelta

_realtime_cache = {}
_realtime_cache_time = {}

def get_cached_realtime(symbol: str, db_fetch_func):
    now = datetime.now()
    if symbol in _realtime_cache:
        if now - _realtime_cache_time[symbol] < timedelta(seconds=5):
            return _realtime_cache[symbol]
    data = db_fetch_func()
    _realtime_cache[symbol] = data
    _realtime_cache_time[symbol] = now
    return data
```

### 6.5 前端轮询

```typescript
// frontend/lib/api.ts 新增
async getRealtime(symbol: string): Promise<RealtimeQuote> {
    return this.request<RealtimeQuote>(`/api/realtime/${symbol}`)
}

// frontend/app/page.tsx
useEffect(() => {
    const interval = setInterval(() => {
        api.getProducts().then(setProducts).catch(console.error)
    }, 30000)
    return () => clearInterval(interval)
}, [])
```

### 6.6 阶段四验收标准

- [ ] 后端启动后，每 30s `products` 表价格自动更新（观察数据库）
- [ ] `/api/realtime/{symbol}` 5s 内重复请求走缓存，不查数据库
- [ ] 前端页面每 30s 自动刷新价格，无闪烁
- [ ] `/api/products` 返回的价格与 `/api/realtime/{symbol}` 一致

---

## 七、与 DATA_PIPELINE_DESIGN.md 的对照表

| DATA_PIPELINE 章节 | 本计划对应阶段 | 状态 |
|--------------------|----------------|------|
| 一、总体架构 | 全阶段 | 作为总体框架 |
| 二、数据采集层 | 阶段二 | 完全复用设计 |
| 三、数据清洗层 | 阶段二 | 完全复用设计 |
| 四、数据库 Schema | 阶段一 | 完全复用，增加兼容层说明 |
| 五、入库策略 | 阶段二 | 完全复用 upsert 设计 |
| 六、数据服务层 | 阶段三 | 完全复用 API 设计 |
| 七、内存缓存 | 阶段四 | 完全复用缓存策略 |
| 八、实施 Checklist | 全阶段 | 按 1→2→3→4 顺序执行 |
| 九、依赖清单 | 阶段一+二 | 已合并到 requirements.txt |
| 十、风险与注意事项 | 全阶段 | 已融入各阶段验收标准 |

---

## 八、风险与回滚策略

| 风险 | 影响 | 应对策略 |
|------|------|----------|
| akshare 数据源不稳定 | 实时行情中断 | 失败时保留上一次有效数据，记录日志，指数退避重试（最多 3 次） |
| SQLite 并发写入锁 | 定时任务与 API 同时写库阻塞 | 短期可用；长期迁移 PostgreSQL（SQLAlchemy 模型无需改动） |
| 模型变更导致旧数据丢失 | 用户/评论数据丢失 | Alembic 迁移前备份 `futures_community.db`；先迁移 schema，再迁移数据 |
| 前端兼容层失效 | `/api/products` 返回空 | 阶段四结束前保留 `ProductDB`，通过定时任务同步数据 |
| K 线数据量膨胀 | 查询变慢 | 只保留最近 3 个月分钟 K 线；更早年份只留日 K；定期归档 |

---

## 九、执行 Checklist

### 启动前准备
- [ ] 备份当前 `futures_community.db`
- [ ] 确认 `.env` 中 `SECRET_KEY` 已设置
- [ ] 创建 feature branch：`git checkout -b backend-data-iteration`

### 阶段一
- [ ] `pip install alembic`
- [ ] 新建 `models.py`，定义全部 8 个模型
- [ ] `alembic init` 并配置 `env.py`
- [ ] `alembic revision --autogenerate -m "init"`
- [ ] `alembic upgrade head`
- [ ] 运行 `init_varieties.py` 灌入品种元数据
- [ ] 删除/归档旧 `init_data.py`

### 阶段二
- [ ] `pip install akshare apscheduler pandas numpy`
- [ ] 实现 `data_collector/base.py`、`akshare_collector.py`、`cleaner.py`
- [ ] 实现 `upsert.py`
- [ ] 配置 `scheduler.py`，测试 mock 数据定时刷新
- [ ] 测试 akshare 采集器独立运行

### 阶段三
- [ ] 新建 `schemas.py`、`dependencies.py`
- [ ] 拆分 `routers/`：auth、varieties、kline、realtime、comments
- [ ] 重写 `main.py` 为路由组装器
- [ ] 测试 `/api/varieties`、`/api/kline/{symbol}`、`/api/realtime/{symbol}`
- [ ] 确认 `/api/products` 兼容层仍可用
- [ ] 打开 `/docs` 检查 Swagger 文档

### 阶段四
- [ ] 在 scheduler 中增加 `sync_prices_to_products`
- [ ] 实现 `services/cache.py`
- [ ] 修改 `realtime.py` 走缓存
- [ ] 前端 `api.ts` 增加 `getRealtime` + 轮询
- [ ] 前端 `page.tsx` / `products/page.tsx` 接入自动刷新
- [ ] 全链路测试：采集 → 入库 → API → 前端展示

---

> **建议节奏**：阶段一完成后可提交一次 PR；阶段二+三可并行推进（一人写采集、一人写 API）；阶段四收尾。整个迭代预计 **4~6 天** 完成。
