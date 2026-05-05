import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime,
    Text, ForeignKey, Boolean, UniqueConstraint, Index, text, Numeric
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from config import DATABASE_URL

_IS_SQLITE = DATABASE_URL.startswith("sqlite")

if _IS_SQLITE:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    Base.metadata.create_all(bind=engine)
    if _IS_SQLITE:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL;"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS alembic_version (
                    version_num VARCHAR(32) NOT NULL,
                    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                )
            """))
            conn.execute(text("""
                INSERT OR IGNORE INTO alembic_version (version_num)
                VALUES ('7a8e00d86747')
            """))
            conn.commit()


def get_engine_info() -> dict:
    """返回数据库引擎信息，供 /health 使用。"""
    info = {"driver": engine.driver, "database_url": DATABASE_URL.split("://")[0] + "://***"}
    if _IS_SQLITE:
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA journal_mode;"))
            info["journal_mode"] = result.scalar()
    return info


class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    comments = relationship("CommentDB", back_populates="user")
    watchlists = relationship("WatchlistDB", back_populates="user")
    opinions = relationship("OpinionDB", back_populates="user")


class ProductDB(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    symbol = Column(String(20), unique=True, index=True, nullable=False)
    current_price = Column(Float, nullable=False)
    change_percent = Column(Float, default=0)
    pre_settlement = Column(Numeric(15, 4))
    open_price = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Float)
    category = Column(String(20))
    margin = Column(Numeric(10, 4), default=0)
    commission = Column(Numeric(10, 4), default=0)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
    comments = relationship("CommentDB", back_populates="product")


class CommentDB(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    user = relationship("UserDB", back_populates="comments")
    product = relationship("ProductDB", back_populates="comments")


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
    margin_rate = Column(Numeric(10, 4))
    commission = Column(Numeric(10, 4))
    listing_date = Column(DateTime)
    last_trading_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    realtime = relationship("RealtimeQuoteDB", back_populates="variety", uselist=False)
    klines = relationship("KlineDataDB", back_populates="variety")
    daily_data = relationship("FutDailyDataDB", back_populates="variety")
    watchlists = relationship("WatchlistDB", back_populates="variety")
    opinions = relationship("OpinionDB", back_populates="variety")


class RealtimeQuoteDB(Base):
    __tablename__ = "realtime_quotes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id"), unique=True, nullable=False)
    current_price = Column(Float, nullable=False)
    pre_settlement = Column(Numeric(15, 4))
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


class WatchlistDB(Base):
    __tablename__ = "watchlists"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    variety_id = Column(Integer, ForeignKey("varieties.id"), nullable=False)
    resistance_level = Column(Numeric(15, 4))
    support_level = Column(Numeric(15, 4))
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
    type = Column(String(10), nullable=False)
    reason = Column(Text)
    target_price = Column(Numeric(15, 4))
    stop_loss = Column(Numeric(15, 4))
    created_at = Column(DateTime, default=datetime.datetime.now)
    user = relationship("UserDB", back_populates="opinions")
    variety = relationship("VarietyDB", back_populates="opinions")


class DataIngestionRunDB(Base):
    """采集批次质量追踪。"""
    __tablename__ = "data_ingestion_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(50), nullable=False, index=True)
    source = Column(String(50), nullable=False)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime)
    status = Column(String(20), default="running")
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    error_message = Column(Text)
    metadata_json = Column(Text)


class FutDailyDataDB(Base):
    """期货日线/周线/月线行情（Tushare fut_daily / pro_bar D/W/M）。"""
    __tablename__ = "fut_daily_data"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id"), nullable=False)
    ts_code = Column(String(20), nullable=False)
    trade_date = Column(DateTime, nullable=False)
    pre_close = Column(Float)
    pre_settle = Column(Float)
    open_price = Column(Float)
    high_price = Column(Float)
    low_price = Column(Float)
    close_price = Column(Float)
    settle = Column(Float)
    change1 = Column(Float)
    change2 = Column(Float)
    volume = Column(Integer)
    amount = Column(Float)
    open_interest = Column(Integer)
    oi_chg = Column(Integer)
    period = Column(String(5), nullable=False)  # D, W, M
    created_at = Column(DateTime, default=datetime.datetime.now)
    variety = relationship("VarietyDB", back_populates="daily_data")
    __table_args__ = (
        UniqueConstraint("variety_id", "period", "trade_date", name="uix_fut_daily"),
        Index("idx_fut_daily_lookup", "variety_id", "period", "trade_date"),
    )


class FutSettleDB(Base):
    """期货每日结算参数（Tushare fut_settle）。"""
    __tablename__ = "fut_settle"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False)
    trade_date = Column(DateTime, nullable=False)
    settle = Column(Numeric(15, 4))
    trading_fee_rate = Column(Float)
    trading_fee = Column(Float)
    delivery_fee = Column(Float)
    b_hedging_margin_rate = Column(Float)
    s_hedging_margin_rate = Column(Float)
    long_margin_rate = Column(Float)
    short_margin_rate = Column(Float)
    offset_today_fee = Column(Float)
    exchange = Column(String(10))
    created_at = Column(DateTime, default=datetime.datetime.now)
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uix_fut_settle"),
    )


class FutWeeklyDetailDB(Base):
    """期货主要品种交易周报（Tushare fut_weekly_detail）。"""
    __tablename__ = "fut_weekly_detail"
    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange = Column(String(10))
    prd = Column(String(10))
    name = Column(String(50))
    vol = Column(Float)
    vol_yoy = Column(Float)
    amount = Column(Float)
    amout_yoy = Column(Float)
    cumvol = Column(Float)
    cumvol_yoy = Column(Float)
    cumamt = Column(Float)
    cumamt_yoy = Column(Float)
    open_interest = Column(Float)
    interest_wow = Column(Float)
    mc_close = Column(Float)
    close_wow = Column(Float)
    week = Column(String(10))
    week_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.now)


class FutWsrDB(Base):
    """期货仓单日报（Tushare fut_wsr）。"""
    __tablename__ = "fut_wsr"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(DateTime, nullable=False)
    symbol = Column(String(10), nullable=False)
    fut_name = Column(String(50))
    warehouse = Column(String(100))
    wh_id = Column(String(20))
    pre_vol = Column(Integer)
    vol = Column(Integer)
    vol_chg = Column(Integer)
    area = Column(String(50))
    year = Column(String(10))
    grade = Column(String(20))
    brand = Column(String(50))
    place = Column(String(50))
    pd = Column(Integer)
    is_ct = Column(String(10))
    unit = Column(String(10))
    exchange = Column(String(10))
    created_at = Column(DateTime, default=datetime.datetime.now)


class FutHoldingDB(Base):
    """期货每日成交持仓排名（Tushare fut_holding）。"""
    __tablename__ = "fut_holding"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(DateTime, nullable=False)
    symbol = Column(String(20), nullable=False)
    broker = Column(String(50))
    vol = Column(Integer)
    vol_chg = Column(Integer)
    long_hld = Column(Integer)
    long_chg = Column(Integer)
    short_hld = Column(Integer)
    short_chg = Column(Integer)
    exchange = Column(String(10))
    created_at = Column(DateTime, default=datetime.datetime.now)


class FutPriceLimitDB(Base):
    """期货合约涨跌停价格（预留，接口权限待验证）。"""
    __tablename__ = "fut_price_limits"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False)
    trade_date = Column(DateTime, nullable=False)
    up_limit = Column(Float)
    down_limit = Column(Float)
    exchange = Column(String(10))
    created_at = Column(DateTime, default=datetime.datetime.now)
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uix_fut_price_limits"),
    )


class FutIndexDB(Base):
    """期货指数行情（预留，接口权限待验证）。"""
    __tablename__ = "fut_index"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False)
    trade_date = Column(DateTime, nullable=False)
    close = Column(Float)
    open_price = Column(Float)
    high = Column(Float)
    low = Column(Float)
    pre_close = Column(Float)
    change = Column(Float)
    pct_chg = Column(Float)
    vol = Column(Float)
    amount = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.now)
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uix_fut_index"),
    )
