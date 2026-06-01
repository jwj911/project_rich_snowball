import datetime
import logging
import os
import time

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from config import DATABASE_URL, ENV

logger = logging.getLogger(__name__)
SLOW_QUERY_THRESHOLD_SECONDS = float(os.getenv("SLOW_QUERY_THRESHOLD_SECONDS", "1.0"))

_IS_SQLITE = DATABASE_URL.startswith("sqlite")

if _IS_SQLITE:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        """启用 SQLite 外键约束（默认关闭），确保 ON DELETE CASCADE 生效。"""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类，替代 declarative_base() 以支持 mypy 类型检查。"""
    pass

# ---------- 连接池监控 ----------

def _update_pool_gauge():
    """将当前连接池状态同步到 Prometheus Gauge。SQLite 等 NullPool 环境自动跳过。"""
    try:
        pool = engine.pool
        if hasattr(pool, "size"):
            from services.metrics import db_pool_connections
            db_pool_connections.labels(state="size").set(pool.size())
        if hasattr(pool, "checkedin"):
            from services.metrics import db_pool_connections
            db_pool_connections.labels(state="checkedin").set(pool.checkedin())
        if hasattr(pool, "checkedout"):
            from services.metrics import db_pool_connections
            db_pool_connections.labels(state="checkedout").set(pool.checkedout())
        if hasattr(pool, "overflow"):
            from services.metrics import db_pool_connections
            db_pool_connections.labels(state="overflow").set(pool.overflow())
    except Exception:
        # 指标采集失败不应影响数据库连接本身
        pass


@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn, connection_record):
    from services.metrics import db_pool_connect_total
    db_pool_connect_total.inc()
    _update_pool_gauge()


@event.listens_for(engine, "close")
def _on_close(dbapi_conn, connection_record):
    from services.metrics import db_pool_close_total
    db_pool_close_total.inc()
    _update_pool_gauge()


@event.listens_for(engine, "checkout")
def _on_checkout(dbapi_conn, connection_record, connection_proxy):
    from services.metrics import db_pool_checkout_total
    db_pool_checkout_total.inc()
    _update_pool_gauge()


@event.listens_for(engine, "checkin")
def _on_checkin(dbapi_conn, connection_record):
    from services.metrics import db_pool_checkin_total
    db_pool_checkin_total.inc()
    _update_pool_gauge()

def _utc_now():
    return datetime.datetime.now(datetime.UTC)


# ========== 慢查询日志 ==========

@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.time()


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.time() - context._query_start_time
    if total > SLOW_QUERY_THRESHOLD_SECONDS:
        logger.warning(f"Slow query ({total:.2f}s): {statement[:500]}")


def init_db():
    # 生产环境不自动建表，依赖 alembic upgrade head 管理 schema
    if ENV == "production":
        return
    Base.metadata.create_all(bind=engine)
    if _IS_SQLITE:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL;"))
            conn.commit()


def get_engine_info() -> dict:
    """返回数据库引擎信息，供 /health 使用。"""
    info: dict[str, str | None] = {"driver": engine.driver, "database_url": DATABASE_URL.split("://")[0] + "://***"}
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
    role = Column(String(20), nullable=False, default="user")
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    comments = relationship("CommentDB", back_populates="user", passive_deletes=True)
    watchlists = relationship("WatchlistDB", back_populates="user", passive_deletes=True)
    opinions = relationship("OpinionDB", back_populates="user", passive_deletes=True)
    price_alerts = relationship("PriceAlertDB", back_populates="user", passive_deletes=True)
    price_levels = relationship("PriceLevelDB", back_populates="user", passive_deletes=True)
    refresh_tokens = relationship("RefreshTokenDB", back_populates="user", passive_deletes=True)


class CommentDB(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="SET NULL"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    price_level_id = Column(Integer, ForeignKey("price_levels.id", ondelete="SET NULL"), nullable=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    __table_args__ = (Index("idx_comments_created_at", "created_at"),)
    user = relationship("UserDB", back_populates="comments")
    variety = relationship("VarietyDB", back_populates="comments")
    price_level = relationship("PriceLevelDB", back_populates="comments")


class VarietyDB(Base):
    __tablename__ = "varieties"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    contract_code = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
    exchange = Column(String(20), nullable=False)
    category = Column(String(20), index=True)
    contract_month = Column(String(10))
    tick_size = Column(Numeric(19, 4))
    multiplier = Column(Numeric(19, 4))
    margin_rate = Column(Numeric(10, 4))
    commission = Column(Numeric(10, 4))
    listing_date = Column(DateTime(timezone=True))
    last_trading_date = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    realtime = relationship("RealtimeQuoteDB", back_populates="variety", uselist=False, passive_deletes=True)
    klines = relationship("KlineDataDB", back_populates="variety", passive_deletes=True)
    price_alerts = relationship("PriceAlertDB", back_populates="variety", passive_deletes=True)
    daily_data = relationship("FutDailyDataDB", back_populates="variety", passive_deletes=True)
    watchlists = relationship("WatchlistDB", back_populates="variety", passive_deletes=True)
    opinions = relationship("OpinionDB", back_populates="variety", passive_deletes=True)
    price_levels = relationship("PriceLevelDB", back_populates="variety", passive_deletes=True)
    comments = relationship("CommentDB", back_populates="variety", passive_deletes=True)


class FutContractDB(Base):
    """期货合约信息表（Tushare fut_basic）。存储具体合约元数据，供行情采集时轮询使用。

    注意：本表不标记"主力合约"布尔值。品种的主力合约来源是：
    1. VarietyDB.contract_code（当前主力合约代码）
    2. ContractRolloverDB（主力切换历史记录）
    需要判断某合约是否为主力时，应比对 VarietyDB.contract_code 或查询 rollover 链。
    """
    __tablename__ = "fut_contracts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), unique=True, nullable=False, index=True)
    symbol = Column(String(20), index=True)
    name = Column(String(50))
    fut_code = Column(String(10), index=True)
    exchange = Column(String(10), index=True)
    list_date = Column(DateTime(timezone=True), index=True)
    delist_date = Column(DateTime(timezone=True), index=True)
    multiplier = Column(Numeric(19, 4))
    trade_unit = Column(String(20))
    per_unit = Column(Numeric(19, 4))
    quote_unit = Column(String(20))
    d_month = Column(String(10))
    contract_type = Column(String(10), index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)
    __table_args__ = (
        UniqueConstraint("ts_code", name="uix_fut_contracts_ts_code"),
        Index("idx_fut_contracts_lookup", "fut_code", "exchange", "list_date"),
    )


class RealtimeQuoteDB(Base):
    __tablename__ = "realtime_quotes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="CASCADE"), unique=True, nullable=False)
    current_price = Column(Numeric(19, 4), nullable=False)
    pre_settlement = Column(Numeric(15, 4))
    change_percent = Column(Numeric(19, 4))
    open_price = Column(Numeric(19, 4))
    high = Column(Numeric(19, 4))
    low = Column(Numeric(19, 4))
    volume = Column(Integer)
    open_interest = Column(Integer)
    bid1 = Column(Numeric(19, 4))
    ask1 = Column(Numeric(19, 4))
    data_source = Column(String(20), nullable=True)
    limit_up = Column(Numeric(19, 4))
    limit_down = Column(Numeric(19, 4))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    variety = relationship("VarietyDB", back_populates="realtime")


class KlineDataDB(Base):
    __tablename__ = "kline_data"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False)
    contract_id = Column(Integer, ForeignKey("fut_contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    period = Column(String(10), nullable=False)
    trading_time = Column(DateTime(timezone=True), nullable=False)
    trading_date = Column(Date, nullable=True, index=True)
    open_price = Column(Numeric(19, 4), nullable=False)
    high_price = Column(Numeric(19, 4), nullable=False)
    low_price = Column(Numeric(19, 4), nullable=False)
    close_price = Column(Numeric(19, 4), nullable=False)
    volume = Column(Integer, nullable=False)
    open_interest = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    variety = relationship("VarietyDB", back_populates="klines")
    contract = relationship("FutContractDB")
    __table_args__ = (
        UniqueConstraint("variety_id", "contract_id", "period", "trading_time", name="uix_kline_contract"),
        Index("idx_kline_lookup", "variety_id", "period", "trading_time"),
        Index("idx_kline_contract_period_time", "contract_id", "period", "trading_time"),
    )


class ContractRolloverDB(Base):
    __tablename__ = "contract_rollovers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False, index=True)
    old_contract_id = Column(Integer, ForeignKey("fut_contracts.id", ondelete="SET NULL"), nullable=True)
    new_contract_id = Column(Integer, ForeignKey("fut_contracts.id", ondelete="SET NULL"), nullable=True)
    old_contract_code = Column(String(20), nullable=True)
    new_contract_code = Column(String(20), nullable=True)
    effective_date = Column(DateTime(timezone=True), nullable=False, index=True)
    source = Column(String(30), nullable=False, default="mapping_pipeline")
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    variety = relationship("VarietyDB")
    old_contract = relationship("FutContractDB", foreign_keys=[old_contract_id])
    new_contract = relationship("FutContractDB", foreign_keys=[new_contract_id])

    __table_args__ = (
        UniqueConstraint("variety_id", "effective_date", "new_contract_code", name="uix_rollover_variety_date_new"),
    )


class WatchlistDB(Base):
    __tablename__ = "watchlists"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False)
    resistance_level = Column(Numeric(15, 4))
    support_level = Column(Numeric(15, 4))
    notes = Column(Text)
    is_notified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    user = relationship("UserDB", back_populates="watchlists")
    variety = relationship("VarietyDB", back_populates="watchlists")
    __table_args__ = (
        UniqueConstraint("user_id", "variety_id", name="uix_watchlist_user_variety"),
    )


class PriceAlertDB(Base):
    """价格预警。

    用户为某个品种设置的价格触发型预警。
    当实时行情满足 alert_type 条件时，标记为已触发。
    """

    __tablename__ = "price_alerts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False)
    alert_type = Column(String(10), nullable=False)  # above | below
    target_price = Column(Numeric(15, 4), nullable=False)
    is_triggered = Column(Boolean, default=False, nullable=False)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    user = relationship("UserDB", back_populates="price_alerts")
    variety = relationship("VarietyDB", back_populates="price_alerts")


class OpinionDB(Base):
    """交易观点/日记。

    用户针对某个品种发表的多空观点，包含目标价、止损价和理由。
    支持状态流转：open -> closed_profit/closed_loss/expired。
    """

    __tablename__ = "opinions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(10), nullable=False)  # long | short | neutral
    reason = Column(Text)
    target_price = Column(Numeric(15, 4))
    stop_loss = Column(Numeric(15, 4))
    status = Column(String(20), nullable=False, default="open")  # open | closed_profit | closed_loss | expired
    closed_at = Column(DateTime(timezone=True), nullable=True)
    actual_outcome = Column(String(20), nullable=True)  # profit | loss | breakeven
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    user = relationship("UserDB", back_populates="opinions")
    variety = relationship("VarietyDB", back_populates="opinions")


class PriceLevelDB(Base):
    __tablename__ = "price_levels"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("fut_contracts.id", ondelete="CASCADE"), nullable=True, index=True)
    type = Column(String(20), nullable=False)  # support | resistance
    price = Column(Numeric(15, 4), nullable=False)
    scope = Column(String(20), nullable=False, default="continuous")  # continuous | main | contract
    note = Column(Text, nullable=True)
    source = Column(String(30), nullable=False, default="manual")
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)
    user = relationship("UserDB", back_populates="price_levels")
    variety = relationship("VarietyDB", back_populates="price_levels")
    contract = relationship("FutContractDB", backref="price_levels")
    comments = relationship("CommentDB", back_populates="price_level", passive_deletes=True)

    __table_args__ = (
        UniqueConstraint("user_id", "variety_id", "type", "price", "scope", "contract_id",
                         name="uix_user_variety_type_price_scope_contract"),
    )


class DataIngestionRunDB(Base):
    """采集批次质量追踪。"""
    __tablename__ = "data_ingestion_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(50), nullable=False, index=True)
    source = Column(String(50), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer, nullable=True)
    status = Column(String(20), default="running")
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    error_message = Column(Text)
    error_sample = Column(Text, nullable=True)
    window_start = Column(DateTime(timezone=True), nullable=True)
    window_end = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(Text)


class FutDailyDataDB(Base):
    """期货日线/周线/月线行情（Tushare fut_daily / pro_bar D/W/M）。"""
    __tablename__ = "fut_daily_data"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False)
    ts_code = Column(String(20), nullable=False)
    trade_date = Column(DateTime(timezone=True), nullable=False)
    pre_close = Column(Numeric(19, 4))
    pre_settle = Column(Numeric(19, 4))
    open_price = Column(Numeric(19, 4))
    high_price = Column(Numeric(19, 4))
    low_price = Column(Numeric(19, 4))
    close_price = Column(Numeric(19, 4))
    settle = Column(Numeric(19, 4))
    change1 = Column(Numeric(19, 4))
    change2 = Column(Numeric(19, 4))
    volume = Column(Integer)
    amount = Column(Numeric(19, 4))
    open_interest = Column(Integer)
    oi_chg = Column(Integer)
    period = Column(String(5), nullable=False)  # D, W, M
    created_at = Column(DateTime(timezone=True), default=_utc_now)
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
    trade_date = Column(DateTime(timezone=True), nullable=False)
    settle = Column(Numeric(15, 4))
    trading_fee_rate = Column(Numeric(19, 4))
    trading_fee = Column(Numeric(19, 4))
    delivery_fee = Column(Numeric(19, 4))
    b_hedging_margin_rate = Column(Numeric(19, 4))
    s_hedging_margin_rate = Column(Numeric(19, 4))
    long_margin_rate = Column(Numeric(19, 4))
    short_margin_rate = Column(Numeric(19, 4))
    offset_today_fee = Column(Numeric(19, 4))
    exchange = Column(String(10))
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uix_fut_settle"),
        Index("idx_fut_settle_ts_code", "ts_code"),
        Index("idx_fut_settle_trade_date", "trade_date"),
    )


class FutWeeklyDetailDB(Base):
    """期货主要品种交易周报（Tushare fut_weekly_detail）。"""
    __tablename__ = "fut_weekly_detail"
    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange = Column(String(10))
    prd = Column(String(10))
    name = Column(String(50))
    vol = Column(Numeric(19, 4))
    vol_yoy = Column(Numeric(19, 4))
    amount = Column(Numeric(19, 4))
    amout_yoy = Column(Numeric(19, 4))
    cumvol = Column(Numeric(19, 4))
    cumvol_yoy = Column(Numeric(19, 4))
    cumamt = Column(Numeric(19, 4))
    cumamt_yoy = Column(Numeric(19, 4))
    open_interest = Column(Numeric(19, 4))
    interest_wow = Column(Numeric(19, 4))
    mc_close = Column(Numeric(19, 4))
    close_wow = Column(Numeric(19, 4))
    week = Column(String(10))
    week_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    __table_args__ = (
        UniqueConstraint("week", "prd", "exchange", name="uix_fut_weekly_detail"),
        Index("idx_fut_weekly_lookup", "week", "prd", "exchange"),
    )


class FutWsrDB(Base):
    """期货仓单日报（Tushare fut_wsr）。"""
    __tablename__ = "fut_wsr"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(DateTime(timezone=True), nullable=False)
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
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    __table_args__ = (
        UniqueConstraint("trade_date", "symbol", "warehouse", "wh_id", name="uix_fut_wsr"),
        Index("idx_fut_wsr_lookup", "trade_date", "symbol", "warehouse"),
    )


class FutHoldingDB(Base):
    """期货每日成交持仓排名（Tushare fut_holding）。"""
    __tablename__ = "fut_holding"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(DateTime(timezone=True), nullable=False)
    symbol = Column(String(20), nullable=False)
    broker = Column(String(50))
    vol = Column(Integer)
    vol_chg = Column(Integer)
    long_hld = Column(Integer)
    long_chg = Column(Integer)
    short_hld = Column(Integer)
    short_chg = Column(Integer)
    exchange = Column(String(10))
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    __table_args__ = (
        UniqueConstraint("trade_date", "symbol", "broker", name="uix_fut_holding"),
        Index("idx_fut_holding_lookup", "trade_date", "symbol", "broker"),
    )


class FutPriceLimitDB(Base):
    """期货合约涨跌停价格（Tushare ft_limit）。"""
    __tablename__ = "fut_price_limits"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False)
    trade_date = Column(DateTime(timezone=True), nullable=False)
    name = Column(String(50))
    up_limit = Column(Numeric(19, 4))
    down_limit = Column(Numeric(19, 4))
    m_ratio = Column(Numeric(19, 4))
    cont = Column(String(20))
    exchange = Column(String(10))
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uix_fut_price_limits"),
    )


class FutIndexDB(Base):
    """期货指数行情（预留，接口权限待验证）。"""
    __tablename__ = "fut_index"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False)
    trade_date = Column(DateTime(timezone=True), nullable=False)
    close = Column(Numeric(19, 4))
    open_price = Column(Numeric(19, 4))
    high = Column(Numeric(19, 4))
    low = Column(Numeric(19, 4))
    pre_close = Column(Numeric(19, 4))
    change = Column(Numeric(19, 4))
    pct_chg = Column(Numeric(19, 4))
    vol = Column(Numeric(19, 4))
    amount = Column(Numeric(19, 4))
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uix_fut_index"),
        Index("idx_fut_index_ts_code", "ts_code"),
        Index("idx_fut_index_trade_date", "trade_date"),
    )


class FutTradeFeeDB(Base):
    """期货合约手续费与保证金（九期网 / AKShare futures_comm_info）。"""
    __tablename__ = "fut_trade_fee"
    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange = Column(String(20), nullable=False, index=True)
    contract_name = Column(String(50), nullable=False)
    contract_code = Column(String(20), nullable=False, index=True)
    current_price = Column(Numeric(19, 4))
    up_limit = Column(Numeric(19, 4))
    down_limit = Column(Numeric(19, 4))
    margin_buy_open = Column(Numeric(19, 4))
    margin_sell_open = Column(Numeric(19, 4))
    margin_per_hand = Column(Numeric(15, 2))
    fee_open_rate = Column(Numeric(19, 6))
    fee_open_fixed = Column(String(50))
    fee_close_yesterday_rate = Column(Numeric(19, 6))
    fee_close_yesterday_fixed = Column(String(50))
    fee_close_today_rate = Column(Numeric(19, 6))
    fee_close_today_fixed = Column(String(50))
    tick_profit_gross = Column(Integer)
    fee_total = Column(Numeric(19, 4))
    tick_profit_net = Column(Numeric(19, 4))
    remark = Column(String(20))
    fee_updated_at = Column(DateTime(timezone=True))
    price_updated_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    __table_args__ = (
        UniqueConstraint("contract_code", "fee_updated_at", name="uix_fut_trade_fee"),
        Index("idx_fut_trade_fee_lookup", "exchange", "contract_code", "fee_updated_at"),
    )


class RefreshTokenDB(Base):
    """Refresh Token 表，支持 token 轮转和吊销。"""
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    device_info = Column(String(200), nullable=True)  # 可选：记录设备/UA 摘要
    user = relationship("UserDB", back_populates="refresh_tokens")


class TradingCalendarDB(Base):
    """中国期货市场交易日历。"""
    __tablename__ = "trading_calendar"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(DateTime(timezone=True), nullable=False, index=True)
    is_trading_day = Column(Boolean, default=True, nullable=False)
    day_session_start = Column(String(5), default="09:00")
    day_session_end = Column(String(5), default="15:00")
    night_session_start = Column(String(5), default="21:00")
    night_session_end = Column(String(5), default="02:30")
    exchange = Column(String(10), default="ALL")
    remark = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    __table_args__ = (
        UniqueConstraint("trade_date", "exchange", name="uix_calendar_date_exchange"),
    )


class FrontendLogDB(Base):
    __tablename__ = "frontend_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    log_type = Column("type", String(20), nullable=False, index=True)
    level = Column(String(20), nullable=True, index=True)
    url = Column(String(500), nullable=True)
    user_agent = Column(String(500), nullable=True)
    release = Column(String(50), nullable=True)
    environment = Column(String(20), nullable=True)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), default=_utc_now, index=True)


class UserPreferenceDB(Base):
    """用户偏好设置。

    每个用户一条记录，注册时自动创建默认值。
    采用扁平字段设计，避免过度抽象；新增偏好直接加列。
    """

    __tablename__ = "user_preferences"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    theme = Column(String(20), nullable=False, default="dark")
    polling_interval_seconds = Column(Integer, nullable=False, default=30)
    notifications_enabled = Column(Boolean, nullable=False, default=True)
    language = Column(String(10), nullable=False, default="zh-CN")
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)
    user = relationship("UserDB", backref="preference", uselist=False, passive_deletes=True)


class NewsSourceDB(Base):
    """RSS 新闻源。

    每个源对应一个 RSS 订阅地址，后台定时或手动触发抓取。
    采用启用/禁用开关控制，错误次数过多可人工介入。
    """

    __tablename__ = "news_sources"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    category = Column(String(50), nullable=True)
    is_enabled = Column(Boolean, default=True, nullable=False)
    last_fetched_at = Column(DateTime(timezone=True), nullable=True)
    fetch_error_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utc_now)


class NewsArticleDB(Base):
    """RSS 抓取的新闻条目。

    同一篇文章通过 (source_id, url) 去重，避免重复入库。
    """

    __tablename__ = "news_articles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(
        Integer, ForeignKey("news_sources.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    title = Column(String(300), nullable=False)
    summary = Column(Text, nullable=True)
    url = Column(String(500), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at = Column(DateTime(timezone=True), default=_utc_now)

    __table_args__ = (
        UniqueConstraint("source_id", "url", name="uix_article_source_url"),
    )
