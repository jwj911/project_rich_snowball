from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy.orm import selectinload

from models import SessionLocal, VarietyDB, ProductDB
from data_collector.base import BaseCollector
from data_collector.pipeline import DataPipeline
from data_collector.cleaner import clean_realtime, clean_kline
from config import DATA_SOURCE, ENV
from services.metrics import data_collection_runs_total, data_collection_duration_seconds

logger = logging.getLogger("data.scheduler")

# 根据配置动态选择 Collector 和 Adapter
from data_collector.adapters import (
    map_akshare_kline,
    map_akshare_realtime,
    map_mock_kline,
    map_mock_realtime,
    map_tushare_kline,
    map_tushare_realtime,
)


class _MappedFallbackCollector(BaseCollector):
    """Try collectors in order and return already-mapped internal rows."""

    def __init__(self, entries):
        self.entries = entries

    def fetch_realtime(self, symbol: str):
        for name, collector, realtime_adapter, _ in self.entries:
            try:
                raw = collector.fetch_realtime(symbol)
                if raw is None:
                    continue
                return realtime_adapter(raw, symbol)
            except Exception as e:
                logger.warning("%s realtime failed for %s, trying next source: %s", name, symbol, e)
        return None

    def fetch_kline(self, contract_code: str, period: str, limit: int = 100):
        for name, collector, _, kline_adapter in self.entries:
            try:
                raw_rows = collector.fetch_kline(contract_code, period, limit=limit)
                if not raw_rows:
                    continue
                return [kline_adapter(row, contract_code, period) for row in raw_rows]
            except Exception as e:
                logger.warning("%s kline failed for %s/%s, trying next source: %s", name, contract_code, period, e)
        return []


def _try_create(name, factory, realtime_adapter, kline_adapter):
    try:
        return name, factory(), realtime_adapter, kline_adapter
    except Exception as e:
        logger.warning("%s collector unavailable: %s", name, e)
        return None


# ------------------------------------------------------------------
# 延迟初始化：模块级变量初始为 None，首次使用时构建
# ------------------------------------------------------------------

_collector = None
_adapter_realtime = None
_adapter_kline = None
_tushare_entry = None
_pipeline_realtime = None
_pipeline_kline = None

# 扩展 pipeline 模块级变量
_pipeline_fut_daily = None
_pipeline_fut_settle = None
_pipeline_fut_weekly_detail = None
_pipeline_fut_wsr = None
_pipeline_fut_holding = None
_pipeline_fut_price_limit = None
_pipeline_fut_mapping = None
_pipeline_akshare_minute = None

_initialized = False


def _ensure_collectors():
    """延迟初始化 collector 和 pipeline。保证应用始终可启动。"""
    global _initialized
    global _collector, _adapter_realtime, _adapter_kline, _tushare_entry
    global _pipeline_realtime, _pipeline_kline
    global _pipeline_fut_daily, _pipeline_fut_settle
    global _pipeline_fut_weekly_detail, _pipeline_fut_wsr
    global _pipeline_fut_holding, _pipeline_fut_price_limit, _pipeline_fut_mapping
    global _pipeline_akshare_minute

    if _initialized:
        return

    data_source = (DATA_SOURCE or "mock").lower()
    entries = []
    tushare_entry = None

    if data_source in ("tushare", "auto"):
        from data_collector.tushare_collector import TushareCollector

        tushare_entry = _try_create(
            "tushare",
            TushareCollector,
            map_tushare_realtime,
            map_tushare_kline,
        )
        if tushare_entry:
            entries.append(tushare_entry)

    if data_source in ("tushare", "akshare", "auto"):
        from data_collector.akshare_collector import AkshareCollector

        akshare_entry = _try_create(
            "akshare",
            AkshareCollector,
            map_akshare_realtime,
            map_akshare_kline,
        )
        if akshare_entry:
            entries.append(akshare_entry)

    if not entries:
        # 生产环境不允许降级 Mock，避免向用户展示伪造行情
        if ENV == "production":
            raise RuntimeError(
                "No data collector is available in production. "
                "Check DATA_SOURCE, TUSHARE_TOKEN, and network connectivity."
            )
        # 非生产环境降级 Mock，保证开发可启动
        from data_collector.mock_collector import MockCollector
        mock_entry = _try_create(
            "mock",
            MockCollector,
            map_mock_realtime,
            map_mock_kline,
        )
        if mock_entry:
            entries.append(mock_entry)
            logger.critical("All real collectors failed, fallback to MockCollector")

    if not entries:
        logger.critical("All collectors failed; scheduler will not run any data collection jobs.")
        _initialized = True
        return

    if len(entries) == 1:
        name, collector, realtime_adapter, kline_adapter = entries[0]
        logger.info("Using %s collector", name)
    else:
        logger.info("Using collector fallback order: %s", " -> ".join(entry[0] for entry in entries))
        collector = _MappedFallbackCollector(entries)
        realtime_adapter = None
        kline_adapter = None

    _collector = collector
    _adapter_realtime = realtime_adapter
    _adapter_kline = kline_adapter
    _tushare_entry = tushare_entry

    _pipeline_realtime = DataPipeline(
        collector=_collector,
        adapter=_adapter_realtime,
        cleaner=clean_realtime,
    )

    _pipeline_kline = DataPipeline(
        collector=_collector,
        adapter=_adapter_kline,
        cleaner=clean_kline,
    )

    # 扩展：期货日线 / 结算 / 周报 / 仓单 / 持仓 pipeline（仅 Tushare 支持）
    if _tushare_entry:
        from data_collector.adapters import (
            map_tushare_fut_daily, map_tushare_fut_settle,
            map_tushare_fut_weekly_detail, map_tushare_fut_wsr,
            map_tushare_fut_holding, map_tushare_ft_limit,
            map_tushare_fut_mapping,
        )
        _, _tushare_collector, _, _ = _tushare_entry
        _pipeline_fut_daily = DataPipeline(collector=_tushare_collector, adapter=map_tushare_fut_daily)
        _pipeline_fut_settle = DataPipeline(collector=_tushare_collector, adapter=map_tushare_fut_settle)
        _pipeline_fut_weekly_detail = DataPipeline(collector=_tushare_collector, adapter=map_tushare_fut_weekly_detail)
        _pipeline_fut_wsr = DataPipeline(collector=_tushare_collector, adapter=map_tushare_fut_wsr)
        _pipeline_fut_holding = DataPipeline(collector=_tushare_collector, adapter=map_tushare_fut_holding)
        _pipeline_fut_price_limit = DataPipeline(collector=_tushare_collector, adapter=map_tushare_ft_limit)
        _pipeline_fut_mapping = DataPipeline(collector=_tushare_collector, adapter=map_tushare_fut_mapping)

    # 双系统：AkShare 分钟线专用 Pipeline
    try:
        from data_collector.akshare_collector import AkshareCollector
        from data_collector.adapters import map_akshare_kline
        _akshare_collector_minute = AkshareCollector()
        _pipeline_akshare_minute = DataPipeline(
            collector=_akshare_collector_minute,
            adapter=map_akshare_kline,
            cleaner=clean_kline,
        )
        logger.info("AkShare minute pipeline ready")
    except Exception as e:
        logger.warning("AkShare minute pipeline unavailable: %s", e)

    _initialized = True


def refresh_realtime_quotes():
    """Refresh realtime quotes."""
    _ensure_collectors()
    if not _pipeline_realtime:
        logger.warning("Realtime pipeline not available, skipping refresh")
        data_collection_runs_total.labels(task_name="refresh_realtime", status="skipped").inc()
        return
    logger.info("Refreshing realtime quotes...")
    start = time.time()
    db = SessionLocal()
    try:
        varieties = db.query(VarietyDB).all()
        symbols = [v.symbol for v in varieties]
        stats = _pipeline_realtime.run_realtime(symbols)
        logger.info(f"Refreshed realtime: {stats}")
        data_collection_runs_total.labels(task_name="refresh_realtime", status="success").inc()
    except Exception as e:
        logger.error(f"Refresh realtime failed: {e}")
        data_collection_runs_total.labels(task_name="refresh_realtime", status="failed").inc()
        raise
    finally:
        db.close()
        data_collection_duration_seconds.labels(task_name="refresh_realtime").observe(time.time() - start)


def sync_daily_kline():
    """Sync daily kline data (1d period)."""
    _ensure_collectors()
    if not _pipeline_kline:
        logger.warning("Kline pipeline not available, skipping sync")
        data_collection_runs_total.labels(task_name="sync_kline", status="skipped").inc()
        return
    logger.info("Syncing daily kline...")
    start = time.time()
    db = SessionLocal()
    success_count = 0
    fail_count = 0
    try:
        varieties = db.query(VarietyDB).all()
        for v in varieties:
            try:
                # Use 1d to avoid ft_mins quota limits on free-tier Tushare
                _pipeline_kline.run_kline(v.contract_code, "1d", limit=30)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to sync kline for {v.contract_code}: {e}")
                fail_count += 1
        logger.info(f"Synced kline for {len(varieties)} varieties")
        if fail_count == 0:
            data_collection_runs_total.labels(task_name="sync_kline", status="success").inc()
        else:
            data_collection_runs_total.labels(task_name="sync_kline", status="partial").inc()
    except Exception as e:
        logger.error(f"Sync kline failed: {e}")
        data_collection_runs_total.labels(task_name="sync_kline", status="failed").inc()
        raise
    finally:
        db.close()
        data_collection_duration_seconds.labels(task_name="sync_kline").observe(time.time() - start)


def sync_prices_to_products():
    """Copy realtime quote prices to legacy products."""
    logger.info("Syncing prices to products...")
    start = time.time()
    db = SessionLocal()
    try:
        from models import RealtimeQuoteDB
        quotes = db.query(RealtimeQuoteDB).options(selectinload(RealtimeQuoteDB.variety)).all()
        if not quotes:
            logger.info("No realtime quotes to sync")
            data_collection_runs_total.labels(task_name="sync_prices", status="success").inc()
            return

        symbols = [q.variety.symbol for q in quotes]
        products = {
            p.symbol: p
            for p in db.query(ProductDB).filter(ProductDB.symbol.in_(symbols)).all()
        }

        synced = 0
        for q in quotes:
            product = products.get(q.variety.symbol)
            if product:
                product.current_price = q.current_price
                product.change_percent = q.change_percent
                product.pre_settlement = q.pre_settlement
                product.high = q.high
                product.low = q.low
                product.volume = q.volume
                product.updated_at = q.updated_at
                synced += 1
        db.commit()
        logger.info(f"Synced {synced} prices to products")
        data_collection_runs_total.labels(task_name="sync_prices", status="success").inc()
    except Exception as e:
        logger.error(f"Sync prices failed: {e}")
        data_collection_runs_total.labels(task_name="sync_prices", status="failed").inc()
    finally:
        db.close()
        data_collection_duration_seconds.labels(task_name="sync_prices").observe(time.time() - start)


scheduler = BackgroundScheduler()


def start_scheduler():
    _ensure_collectors()
    scheduler.add_job(
        refresh_realtime_quotes,
        IntervalTrigger(seconds=60),
        id="realtime",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=10,
    )
    scheduler.add_job(
        sync_prices_to_products,
        IntervalTrigger(seconds=60),
        id="sync_products",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=10,
    )
    scheduler.add_job(
        sync_daily_kline,
        CronTrigger(hour=16, minute=5),
        id="daily_kline",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        sync_minute_kline,
        IntervalTrigger(minutes=15),
        id="minute_kline",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        sync_variety_metadata,
        CronTrigger(hour=2, minute=0),
        id="variety_metadata",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    # 扩展任务注册
    if _pipeline_fut_daily:
        scheduler.add_job(
            sync_fut_daily,
            CronTrigger(hour=16, minute=10),
            id="fut_daily",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
    if _pipeline_fut_settle:
        scheduler.add_job(
            sync_fut_settle,
            CronTrigger(hour=16, minute=15),
            id="fut_settle",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
    if _pipeline_fut_weekly_detail:
        scheduler.add_job(
            sync_fut_weekly_detail,
            CronTrigger(day_of_week="mon", hour=3, minute=0),
            id="fut_weekly_detail",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
    if _pipeline_fut_wsr:
        scheduler.add_job(
            sync_fut_wsr,
            CronTrigger(hour=16, minute=20),
            id="fut_wsr",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
    if _pipeline_fut_holding:
        scheduler.add_job(
            sync_fut_holding,
            CronTrigger(hour=16, minute=25),
            id="fut_holding",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
    if _pipeline_fut_price_limit:
        scheduler.add_job(
            sync_fut_price_limit,
            CronTrigger(hour=16, minute=30),
            id="fut_price_limit",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
    scheduler.start()
    logger.info("Scheduler started")


def sync_minute_kline():
    """Sync recent minute-level kline data via AkShare (dual-system architecture).

    Tushare handles daily+ data; AkShare handles minute-level data independently.
    """
    _ensure_collectors()
    if not _pipeline_akshare_minute:
        logger.info("Skipping minute kline: AkShare minute pipeline unavailable")
        return
    logger.info("Syncing minute kline via AkShare...")
    db = SessionLocal()
    try:
        varieties = db.query(VarietyDB).all()
        for v in varieties:
            try:
                _pipeline_akshare_minute.run_kline(v.contract_code, "1m", limit=5)
            except Exception as e:
                logger.error(f"Failed to sync minute kline for {v.contract_code}: {e}")
        logger.info(f"Synced minute kline for {len(varieties)} varieties")
    finally:
        db.close()


# ------------------------------------------------------------------
# 扩展：期货日线 / 结算 / 周报 / 仓单 / 持仓 定时任务
# ------------------------------------------------------------------

def _get_ts_code(variety):
    """Build a Tushare continuous ts_code from a VarietyDB row."""
    exchange_map = {
        "SHFE": "SHF",
        "DCE": "DCE",
        "ZCE": "ZCE",
        "CZCE": "ZCE",
        "INE": "INE",
        "CFFEX": "CFX",
        "GFEX": "GFE",
    }
    suffix = exchange_map.get(variety.exchange, "")
    if not suffix:
        raise ValueError(f"Unsupported exchange for tushare: {variety.exchange}")
    return f"{variety.symbol.upper()}.{suffix}"


def sync_fut_daily():
    """Sync recent futures daily bars."""
    _ensure_collectors()
    if not _pipeline_fut_daily:
        logger.debug("sync_fut_daily skipped: not tushare source")
        return
    logger.info("Syncing futures daily data...")
    db = SessionLocal()
    try:
        from datetime import timedelta
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
        varieties = db.query(VarietyDB).all()
        total = 0
        for v in varieties:
            try:
                ts_code = _get_ts_code(v)
                stats = _pipeline_fut_daily.run_fut_daily(ts_code, start_date, end_date, period="D")
                total += stats.get("processed", 0)
            except Exception as e:
                logger.error(f"Failed to sync daily for {v.symbol}: {e}")
        logger.info(f"Synced {total} daily rows for {len(varieties)} varieties")
    finally:
        db.close()


def sync_fut_settle():
    """Sync futures settlement parameters."""
    _ensure_collectors()
    if not _pipeline_fut_settle:
        logger.debug("sync_fut_settle skipped: not tushare source")
        return
    logger.info("Syncing futures settle data...")
    try:
        trade_date = datetime.now().strftime("%Y%m%d")
        stats = _pipeline_fut_settle.run_fut_settle(trade_date)
        logger.info(f"Synced settle: {stats}")
    except Exception as e:
        logger.error(f"Failed to sync settle: {e}")


def sync_fut_weekly_detail():
    """Sync futures weekly trading detail."""
    _ensure_collectors()
    if not _pipeline_fut_weekly_detail:
        logger.debug("sync_fut_weekly_detail skipped: not tushare source")
        return
    logger.info("Syncing futures weekly detail...")
    try:
        from datetime import timedelta
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        stats = _pipeline_fut_weekly_detail.run_fut_weekly_detail(start_date, end_date)
        logger.info(f"Synced weekly detail: {stats}")
    except Exception as e:
        logger.error(f"Failed to sync weekly detail: {e}")


def sync_fut_wsr():
    """Sync futures warehouse receipt data."""
    _ensure_collectors()
    if not _pipeline_fut_wsr:
        logger.debug("sync_fut_wsr skipped: not tushare source")
        return
    logger.info("Syncing futures warehouse receipts...")
    try:
        trade_date = datetime.now().strftime("%Y%m%d")
        stats = _pipeline_fut_wsr.run_fut_wsr(trade_date)
        logger.info(f"Synced WSR: {stats}")
    except Exception as e:
        logger.error(f"Failed to sync WSR: {e}")


def sync_fut_holding():
    """Sync futures holding rankings."""
    _ensure_collectors()
    if not _pipeline_fut_holding:
        logger.debug("sync_fut_holding skipped: not tushare source")
        return
    logger.info("Syncing futures holding data...")
    try:
        trade_date = datetime.now().strftime("%Y%m%d")
        stats = _pipeline_fut_holding.run_fut_holding(trade_date)
        logger.info(f"Synced holding: {stats}")
    except Exception as e:
        logger.error(f"Failed to sync holding: {e}")


def sync_fut_price_limit():
    """Daily sync for futures price limit data."""
    _ensure_collectors()
    if not _pipeline_fut_price_limit:
        logger.debug("sync_fut_price_limit skipped: not tushare source")
        return
    logger.info("Syncing futures price limit data...")
    try:
        trade_date = datetime.now().strftime("%Y%m%d")
        stats = _pipeline_fut_price_limit.run_fut_price_limit(trade_date=trade_date)
        logger.info(f"Synced price limit: {stats}")
    except Exception as e:
        logger.error(f"Failed to sync price limit: {e}")


def sync_variety_metadata():
    """Update main-contract mapping from Tushare fut_mapping."""
    _ensure_collectors()
    logger.info("Syncing variety metadata...")
    if not _pipeline_fut_mapping:
        logger.debug("sync_variety_metadata skipped: not tushare source")
        return
    try:
        trade_date = datetime.now().strftime("%Y%m%d")
        stats = _pipeline_fut_mapping.run_fut_mapping(trade_date=trade_date)
        logger.info(f"Synced variety metadata: {stats}")
    except Exception as e:
        logger.error(f"Failed to sync variety metadata: {e}")


def shutdown_scheduler():
    scheduler.shutdown()
    logger.info("Scheduler shutdown")
