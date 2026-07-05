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
    """初始化数据库 schema。

    生产环境依赖 alembic upgrade head 管理 schema 变更。
    非生产环境（开发/测试）使用 Base.metadata.create_all() 快速建表，
    避免 Alembic 历史迁移中 PostgreSQL 特有语法在 SQLite 上失败。

    注意: 在非生产环境新增表或列时，仍需要创建 Alembic 迁移脚本，
    并在 CI 中通过 PostgreSQL 执行所有迁移来验证兼容性。
    """
    if ENV == "production":
        from alembic import command
        from alembic.config import Config as AlembicConfig

        alembic_cfg = AlembicConfig(os.path.join(os.path.dirname(__file__), "alembic.ini"))
        command.upgrade(alembic_cfg, "head")
    else:
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
    trade_records = relationship("TradeRecordDB", back_populates="user", passive_deletes=True)
    chat_messages = relationship("ChatMessageDB", back_populates="user", passive_deletes=True)
    price_levels = relationship("PriceLevelDB", back_populates="user", passive_deletes=True)
    refresh_tokens = relationship("RefreshTokenDB", back_populates="user", passive_deletes=True)
    agent_tasks = relationship("AgentTaskDB", back_populates="user", passive_deletes=True)
    alert_events = relationship("AlertEventDB", back_populates="user", passive_deletes=True)
    alert_event_states = relationship("AlertEventUserStateDB", back_populates="user", passive_deletes=True)
    strategies = relationship("StrategyDB", back_populates="user", passive_deletes=True)
    backtest_runs = relationship("BacktestRunDB", back_populates="user", passive_deletes=True)
    evolution_runs = relationship("StrategyEvolutionRunDB", back_populates="user", passive_deletes=True)
    llm_configs = relationship("UserLLMConfigDB", back_populates="user", passive_deletes=True)


class CommentDB(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    price_level_id = Column(Integer, ForeignKey("price_levels.id", ondelete="SET NULL"), nullable=True, index=True)
    content = Column(Text, nullable=False)
    sentiment = Column(String(10), nullable=True)  # bullish | bearish | neutral
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
    alert_events = relationship("AlertEventDB", back_populates="related_variety", passive_deletes=True)
    trade_records = relationship("TradeRecordDB", back_populates="variety", passive_deletes=True)
    daily_data = relationship("FutDailyDataDB", back_populates="variety", passive_deletes=True)
    main_daily_data = relationship("FutMainDailyDataDB", back_populates="variety", passive_deletes=True)
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
    __table_args__ = (UniqueConstraint("user_id", "variety_id", name="uix_watchlist_user_variety"),)


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


class AlertEventDB(Base):
    """统一预警事件。

    记录新闻、市场、日历等事件本身；广播事件只存一条，用户已读/忽略状态
    存在 AlertEventUserStateDB，避免为每个用户复制事件内容。
    """

    __tablename__ = "alert_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(20), nullable=False)  # news | market | calendar
    severity = Column(String(20), nullable=False)  # low | medium | high | critical
    title = Column(String(300), nullable=False)
    summary = Column(Text, nullable=True)
    source_type = Column(String(30), nullable=False)  # news_article | price_alert | calendar
    source_id = Column(Integer, nullable=True)
    source_url = Column(String(500), nullable=True)
    related_variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    target_scope = Column(String(20), nullable=False, default="personal")  # personal | broadcast
    triggered_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)

    user = relationship("UserDB", back_populates="alert_events")
    related_variety = relationship("VarietyDB", back_populates="alert_events")
    user_states = relationship("AlertEventUserStateDB", back_populates="event", passive_deletes=True)

    __table_args__ = (
        Index("idx_alert_events_visible", "target_scope", "user_id", "created_at"),
        Index("idx_alert_events_category", "category", "severity", "created_at"),
        Index("idx_alert_events_source", "source_type", "source_id", "target_scope", "user_id"),
    )


class AlertEventUserStateDB(Base):
    """用户对预警事件的阅读/忽略状态。"""

    __tablename__ = "alert_event_user_states"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("alert_events.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    event = relationship("AlertEventDB", back_populates="user_states")
    user = relationship("UserDB", back_populates="alert_event_states")

    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uix_alert_event_state_event_user"),
        Index("idx_alert_event_states_user", "user_id", "dismissed_at", "read_at"),
    )


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
    trade_records = relationship("TradeRecordDB", back_populates="opinion", passive_deletes=True)


class TradeRecordDB(Base):
    """模拟持仓交易记录。

    用户基于观点创建的虚拟交易，支持盈亏计算与复盘。
    """

    __tablename__ = "trade_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False)
    opinion_id = Column(Integer, ForeignKey("opinions.id", ondelete="SET NULL"), nullable=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True)
    backtest_run_id = Column(Integer, ForeignKey("backtest_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    direction = Column(String(10), nullable=False)  # long | short
    entry_price = Column(Numeric(15, 4), nullable=False)
    exit_price = Column(Numeric(15, 4), nullable=True)
    quantity = Column(Integer, nullable=False, default=1)
    status = Column(String(10), nullable=False, default="open")  # open | closed
    pnl = Column(Numeric(15, 4), nullable=True)
    pnl_percent = Column(Numeric(15, 4), nullable=True)
    account_balance = Column(Numeric(15, 4), nullable=True)
    stop_loss_price = Column(Numeric(15, 4), nullable=True)
    take_profit_price = Column(Numeric(15, 4), nullable=True)
    margin_required = Column(Numeric(15, 4), nullable=True)
    risk_amount = Column(Numeric(15, 4), nullable=True)
    risk_reward_ratio = Column(Numeric(10, 4), nullable=True)
    source = Column(String(20), nullable=False, default="manual")
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    user = relationship("UserDB", back_populates="trade_records")
    variety = relationship("VarietyDB", back_populates="trade_records")
    opinion = relationship("OpinionDB", back_populates="trade_records")
    strategy = relationship("StrategyDB", back_populates="trade_records")
    backtest_run = relationship("BacktestRunDB", back_populates="trade_records")


class ChatMessageDB(Base):
    """AI 聊天对话历史。

    存储用户与 AI 助手的对话消息，role 区分 user/assistant。
    context_json 存储本次对话引用的数据库上下文摘要。
    """

    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    context_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    user = relationship("UserDB", back_populates="chat_messages")


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
        UniqueConstraint(
            "user_id",
            "variety_id",
            "type",
            "price",
            "scope",
            "contract_id",
            name="uix_user_variety_type_price_scope_contract",
        ),
        # PostgreSQL partial unique indexes：NULL 值不参与标准唯一约束比较，
        # 因此用 partial index 分别处理 contract_id 为 NULL 和 NOT NULL 的场景
        Index(
            "uix_price_levels_null_contract",
            "user_id",
            "variety_id",
            "type",
            "price",
            "scope",
            unique=True,
            postgresql_where=text("contract_id IS NULL"),
        ),
        Index(
            "uix_price_levels_not_null_contract",
            "user_id",
            "variety_id",
            "type",
            "price",
            "scope",
            "contract_id",
            unique=True,
            postgresql_where=text("contract_id IS NOT NULL"),
        ),
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
        UniqueConstraint("variety_id", "ts_code", "period", "trade_date", name="uix_fut_daily"),
        Index("idx_fut_daily_lookup", "variety_id", "period", "trade_date"),
    )


class FutMainDailyDataDB(Base):
    """期货主力/活跃品种日线/周线/月线行情（筛选后的核心品种池）。"""

    __tablename__ = "fut_main_daily_data"
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
    variety = relationship("VarietyDB", back_populates="main_daily_data")
    __table_args__ = (
        UniqueConstraint("variety_id", "ts_code", "period", "trade_date", name="uix_fut_main_daily"),
        Index("idx_fut_main_daily_lookup", "variety_id", "period", "trade_date"),
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
    __table_args__ = (UniqueConstraint("ts_code", "trade_date", name="uix_fut_price_limits"),)


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
    __table_args__ = (UniqueConstraint("trade_date", "exchange", name="uix_calendar_date_exchange"),)


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


class UserLLMConfigDB(Base):
    """用户级 OpenAI 兼容 LLM 配置。"""

    __tablename__ = "user_llm_configs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    provider = Column(String(50), nullable=False, default="openai-compatible")
    base_url = Column(String(500), nullable=False)
    model = Column(String(120), nullable=False)
    api_key_encrypted = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)
    user = relationship("UserDB", back_populates="llm_configs")


class NewsSourceDB(Base):
    """RSS 新闻源。

    每个源对应一个 RSS 订阅地址，后台定时或手动触发抓取。
    采用启用/禁用开关控制，错误次数过多可人工介入。
    user_id 为 NULL 时表示系统内置或公共源；有值时表示用户自定义源。
    """

    __tablename__ = "news_sources"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    category = Column(String(50), nullable=True)
    is_enabled = Column(Boolean, default=True, nullable=False)
    is_builtin = Column(Boolean, default=False, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
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
        Integer,
        ForeignKey("news_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(300), nullable=False)
    summary = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)
    url = Column(String(500), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at = Column(DateTime(timezone=True), default=_utc_now)

    __table_args__ = (UniqueConstraint("source_id", "url", name="uix_article_source_url"),)


class AgentTaskDB(Base):
    """Agent 任务主表。

    记录用户提交的 Agent 任务状态与结果，支持异步执行和状态追踪。
    """

    __tablename__ = "agent_tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_task_id = Column(
        Integer,
        ForeignKey("agent_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_type = Column(
        String(30), nullable=False, index=True
    )  # data | data_quality | tech_analysis | risk_management | analysis_pipeline | backtest | factor_mining | strategy_compiler
    query = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending | running | completed | failed
    result_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    user = relationship("UserDB", back_populates="agent_tasks")
    steps = relationship("AgentTaskStepDB", back_populates="task", passive_deletes=True)
    sub_tasks = relationship(
        "AgentTaskDB",
        back_populates="parent_task",
        passive_deletes=True,
        remote_side=[parent_task_id],
        foreign_keys=[parent_task_id],
        uselist=True,
    )
    parent_task = relationship(
        "AgentTaskDB",
        back_populates="sub_tasks",
        remote_side=[id],
        foreign_keys=[parent_task_id],
        uselist=False,
    )

    __table_args__ = (
        Index("idx_agent_tasks_user_status", "user_id", "status"),
        Index("idx_agent_tasks_created", "created_at"),
    )


class AgentTaskStepDB(Base):
    """Agent 任务执行步骤。

    记录 ReAct 链路的每一步（thought/action/observation）。
    """

    __tablename__ = "agent_task_steps"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    role = Column(String(20), nullable=False)  # thought | action | observation | system | error
    content = Column(Text, nullable=False)
    tool_name = Column(String(50), nullable=True)
    tool_input_json = Column(Text, nullable=True)
    tool_output_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    task = relationship("AgentTaskDB", back_populates="steps")

    __table_args__ = (
        UniqueConstraint("task_id", "step_number", name="uix_agent_step_number"),
        Index("idx_agent_task_steps_task", "task_id", "step_number"),
    )


class FactorDefinitionDB(Base):
    """Imported factor definitions that can be evaluated or selected by agents."""

    __tablename__ = "factor_definitions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    """NULL 表示系统内置因子（如万因子），非NULL表示用户自建因子。"""
    is_builtin = Column(Boolean, nullable=False, default=True, index=True)
    """True = 系统内置（不可删除），False = 用户自建。"""
    package_id = Column(String(80), nullable=False, default="manual", index=True)
    factor_id = Column(String(80), nullable=False, index=True)
    name = Column(String(240), nullable=False, index=True)
    source = Column(String(80), nullable=True, index=True)
    cluster_id = Column(String(80), nullable=True, index=True)
    is_cluster_rep = Column(Boolean, nullable=False, default=False)
    q_score = Column(Numeric(12, 6), nullable=True)
    rankic = Column(Numeric(18, 10), nullable=True)
    rankicir = Column(Numeric(18, 10), nullable=True)
    test_rankicir = Column(Numeric(18, 10), nullable=True)
    monotonicity = Column(Numeric(18, 10), nullable=True)
    ls_sharpe = Column(Numeric(18, 10), nullable=True)
    size_corr = Column(Numeric(18, 10), nullable=True)
    coverage = Column(Numeric(18, 10), nullable=True)
    source_expression = Column(Text, nullable=False)
    converted_formula = Column(Text, nullable=True)
    conversion_status = Column(String(30), nullable=False, default="pending", index=True)
    conversion_error = Column(Text, nullable=True)
    category = Column(String(60), nullable=True, index=True)
    fields_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    watermark_sig = Column(String(200), nullable=True)
    source_file = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        UniqueConstraint("package_id", "factor_id", name="uix_factor_definitions_package_factor"),
        Index("idx_factor_definitions_quality", "conversion_status", "q_score"),
        Index("idx_factor_definitions_source_category", "source", "category"),
    )


class StrategyDB(Base):
    """用户策略库。

    存储由 StrategyCompilerAgent 编译的策略 DSL，支持版本管理和回测历史关联。
    """

    __tablename__ = "strategies"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    symbol = Column(String(20), nullable=False, index=True)
    dsl_json = Column(Text, nullable=False)  # StrategyDSL JSON 序列化
    timeframe = Column(String(10), nullable=False, default="1d")
    direction = Column(String(10), nullable=False, default="long")
    is_active = Column(Boolean, nullable=False, default=True)
    is_builtin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)
    user = relationship("UserDB", back_populates="strategies")
    backtest_runs = relationship("BacktestRunDB", back_populates="strategy", passive_deletes=True)
    trade_records = relationship("TradeRecordDB", back_populates="strategy", passive_deletes=True)

    __table_args__ = (
        Index("idx_strategies_user_symbol", "user_id", "symbol"),
        Index("idx_strategies_created", "created_at"),
    )


class BacktestRunDB(Base):
    """策略回测运行记录。

    每次回测执行的结果快照，关联到策略或一次性查询。
    """

    __tablename__ = "backtest_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    query = Column(Text, nullable=True)  # 原始自然语言查询
    result_json = Column(Text, nullable=True)  # BacktestResult JSON 序列化
    metrics_score = Column(Integer, nullable=True)
    trade_count = Column(Integer, nullable=True)
    total_return_pct = Column(Numeric(10, 2), nullable=True)
    max_drawdown_pct = Column(Numeric(10, 2), nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending | running | completed | failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    strategy = relationship("StrategyDB", back_populates="backtest_runs")
    user = relationship("UserDB", back_populates="backtest_runs")
    trade_records = relationship("TradeRecordDB", back_populates="backtest_run", passive_deletes=True)

    __table_args__ = (
        Index("idx_backtest_runs_strategy", "strategy_id", "created_at"),
        Index("idx_backtest_runs_user_status", "user_id", "status"),
    )


# ---------------------------------------------------------------------------
# Strategy Evolution — 自进化策略 Agent 持久化模型
# ---------------------------------------------------------------------------


class StrategyEvolutionRunDB(Base):
    """策略进化运行记录。

    每次触发自进化策略 Agent 运行（手动或定时），生成一条记录。
    包含进化配置冻结快照、状态追踪和结果摘要。
    """

    __tablename__ = "strategy_evolution_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    config_json = Column(Text, nullable=False)  # 进化配置快照
    status = Column(String(20), nullable=False, default="pending")  # pending | running | completed | failed
    generations = Column(Integer, nullable=True)
    population_size = Column(Integer, nullable=True)
    best_strategy_id = Column(Integer, ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True)
    summary_json = Column(Text, nullable=True)  # 进化摘要（最优适应度、总评估次数等）
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)

    user = relationship("UserDB", back_populates="evolution_runs")
    generations_list = relationship("StrategyGenerationDB", back_populates="evolution_run", passive_deletes=True)
    best_strategy = relationship("StrategyDB")
    lifecycle = relationship("StrategyLifecycleDB", back_populates="evolution_run", uselist=False)

    __table_args__ = (
        Index("idx_evo_runs_user_status", "user_id", "status"),
        Index("idx_evo_runs_symbol", "symbol", "created_at"),
    )


class StrategyGenerationDB(Base):
    """策略进化代际快照。

    记录每一代的种群状态、适应度和多样性，用于回溯进化轨迹。
    """

    __tablename__ = "strategy_generations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    evolution_run_id = Column(
        Integer, ForeignKey("strategy_evolution_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    generation_number = Column(Integer, nullable=False)
    population_json = Column(Text, nullable=True)  # 种群个体序列化快照
    best_fitness = Column(Numeric(12, 4), nullable=True)
    avg_fitness = Column(Numeric(12, 4), nullable=True)
    diversity_score = Column(Numeric(6, 4), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)

    evolution_run = relationship("StrategyEvolutionRunDB", back_populates="generations_list")

    __table_args__ = (
        UniqueConstraint("evolution_run_id", "generation_number", name="uix_evo_gen_number"),
        Index("idx_evo_gen_fitness", "evolution_run_id", "generation_number"),
    )


class StrategyLifecycleDB(Base):
    """策略生命周期追踪。

    每个策略（不管来源）最多一条记录，跟踪其在生产环境中的持续表现。
    支持退化检测、状态转换和行动推荐。
    """

    __tablename__ = "strategy_lifecycle"
    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(
        Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    source = Column(String(20), nullable=False, default="manual")  # manual | evolved
    evolution_run_id = Column(
        Integer, ForeignKey("strategy_evolution_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status = Column(String(20), nullable=False, default="active")  # active | paper_trading | degraded | retired
    in_sample_metrics = Column(Text, nullable=True)  # IS 回测指标 JSON
    out_of_sample_metrics = Column(Text, nullable=True)  # OOS 回测指标 JSON
    walk_forward_metrics = Column(Text, nullable=True)  # Walk-forward 指标 JSON
    last_evaluated_at = Column(DateTime(timezone=True), nullable=True)
    performance_trend = Column(Numeric(10, 4), nullable=True)  # 滚动趋势斜率
    decay_score = Column(Numeric(10, 4), nullable=True)  # 0=健康, 100=完全失效
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    strategy = relationship("StrategyDB")
    evolution_run = relationship("StrategyEvolutionRunDB", back_populates="lifecycle")

    __table_args__ = (
        Index("idx_lifecycle_status", "status", "last_evaluated_at"),
        Index("idx_lifecycle_decay", "decay_score", "updated_at"),
    )
