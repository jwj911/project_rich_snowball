import logging
import os
import sys
import time
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from config import DATA_SOURCE, ENV
from data_collector.collector_registry import (
    build_akshare_minute_pipeline,
    build_collector_entries,
    build_pipelines,
)
from data_collector.job_registry import build_job_configs, register_jobs
from models import ProductDB, SessionLocal, VarietyDB
from services.metrics import data_collection_duration_seconds, data_collection_runs_total
from services.realtime_state import mark_realtime_updated
from services.trading_calendar import _cn_date, is_trading_day

logger = logging.getLogger("data.scheduler")

# ------------------------------------------------------------------
# 模块级 pipeline 实例（向后兼容，供任务函数直接使用）
# ------------------------------------------------------------------
_pipelines: dict = {}
_pipeline_akshare_minute = None
_initialized = False


def _ensure_collectors():
    """延迟初始化 collector 和 pipeline。保证应用始终可启动。"""
    global _initialized, _pipelines, _pipeline_akshare_minute
    if _initialized:
        return

    data_source = (DATA_SOURCE or "mock").lower()
    entries, tushare_entry = build_collector_entries(data_source, ENV)

    if not entries:
        if ENV == "production":
            raise RuntimeError(
                "No data collector is available in production. "
                "Check DATA_SOURCE, TUSHARE_TOKEN, and network connectivity."
            )
        logger.critical("All collectors failed; scheduler will not run any data collection jobs.")
        _initialized = True
        return

    if len(entries) == 1:
        name, collector, realtime_adapter, kline_adapter = entries[0]
        logger.info("Using %s collector", name)
    else:
        from data_collector.collector_registry import _MappedFallbackCollector
        logger.info("Using collector fallback order: %s", " -> ".join(entry[0] for entry in entries))
        collector = _MappedFallbackCollector(entries)
        realtime_adapter = None
        kline_adapter = None

    _pipelines = build_pipelines(collector, realtime_adapter, kline_adapter, tushare_entry)
    _pipeline_akshare_minute = build_akshare_minute_pipeline()
    _initialized = True


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def _pipeline(name: str):
    _ensure_collectors()
    return _pipelines.get(name)


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


# ------------------------------------------------------------------
# 核心采集任务
# ------------------------------------------------------------------

def refresh_realtime_quotes():
    """Refresh realtime quotes."""
    if not is_trading_day(_cn_date()):
        logger.info("refresh_realtime_quotes skipped: non-trading day")
        return
    pipeline = _pipeline("realtime")
    if not pipeline:
        logger.warning("Realtime pipeline not available, skipping refresh")
        data_collection_runs_total.labels(task_name="refresh_realtime", status="skipped").inc()
        return
    logger.info("Refreshing realtime quotes...")
    start = time.time()
    db = SessionLocal()
    try:
        varieties = db.query(VarietyDB).all()
        symbols = [v.symbol for v in varieties]
        stats = pipeline.run_realtime(symbols)
        logger.info("Refreshed realtime: %s", stats)
        mark_realtime_updated()
        data_collection_runs_total.labels(task_name="refresh_realtime", status="success").inc()
    except (SQLAlchemyError, OSError) as e:
        logger.error("Refresh realtime failed: %s", e)
        data_collection_runs_total.labels(task_name="refresh_realtime", status="failed").inc()
        raise
    finally:
        db.close()
        data_collection_duration_seconds.labels(task_name="refresh_realtime").observe(time.time() - start)


def sync_daily_kline():
    """Sync daily kline data (1d period)."""
    if not is_trading_day(_cn_date()):
        logger.info("sync_daily_kline skipped: non-trading day")
        return
    pipeline = _pipeline("kline")
    if not pipeline:
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
                pipeline.run_kline(v.contract_code, "1d", limit=30)
                success_count += 1
            except (SQLAlchemyError, OSError) as e:
                logger.error("Failed to sync kline for %s: %s", v.contract_code, e)
                fail_count += 1
        logger.info("Synced kline for %d varieties", len(varieties))
        if fail_count == 0:
            data_collection_runs_total.labels(task_name="sync_kline", status="success").inc()
        else:
            data_collection_runs_total.labels(task_name="sync_kline", status="partial").inc()
    except (SQLAlchemyError, OSError) as e:
        logger.error("Sync kline failed: %s", e)
        data_collection_runs_total.labels(task_name="sync_kline", status="failed").inc()
        raise
    finally:
        db.close()
        data_collection_duration_seconds.labels(task_name="sync_kline").observe(time.time() - start)


def sync_prices_to_products():
    """Copy realtime quote prices to legacy products."""
    if not is_trading_day(_cn_date()):
        logger.info("Non-trading day, skip sync_prices_to_products")
        return
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
        varieties = {v.id: v for v in db.query(VarietyDB).filter(VarietyDB.symbol.in_(symbols)).all()}

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
                product.limit_up = q.limit_up
                product.limit_down = q.limit_down
                product.updated_at = q.updated_at
                variety = varieties.get(q.variety_id)
                if variety and variety.tick_size is not None:
                    tick = float(variety.tick_size)
                    s = f"{tick:.10f}".rstrip("0")
                    product.price_precision = len(s.split(".")[1]) if "." in s else 0
                synced += 1
        db.commit()
        logger.info("Synced %d prices to products", synced)
        data_collection_runs_total.labels(task_name="sync_prices", status="success").inc()
    except (SQLAlchemyError, OSError) as e:
        logger.error("Sync prices failed: %s", e)
        data_collection_runs_total.labels(task_name="sync_prices", status="failed").inc()
        raise
    finally:
        db.close()
        data_collection_duration_seconds.labels(task_name="sync_prices").observe(time.time() - start)


def refresh_and_sync():
    """组合任务：先刷新实时行情，再同步到兼容层 products 表。"""
    try:
        refresh_realtime_quotes()
    except (SQLAlchemyError, OSError):
        logger.error("refresh_realtime_quotes failed, skipping sync_prices_to_products")
        return
    try:
        sync_prices_to_products()
    except (SQLAlchemyError, OSError):
        logger.error("sync_prices_to_products failed after realtime refresh")


# ------------------------------------------------------------------
# 扩展采集任务
# ------------------------------------------------------------------

def sync_minute_kline():
    """Sync recent minute-level kline data via AkShare."""
    if not is_trading_day(_cn_date()):
        logger.info("sync_minute_kline skipped: non-trading day")
        return
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
                _pipeline_akshare_minute.run_kline(v.contract_code, "1m", limit=15)
            except (SQLAlchemyError, OSError) as e:
                logger.error("Failed to sync minute kline for %s: %s", v.contract_code, e)
        logger.info("Synced minute kline for %d varieties", len(varieties))
    finally:
        db.close()


def sync_fut_daily():
    """Sync recent futures daily bars."""
    if not is_trading_day(_cn_date()):
        logger.info("sync_fut_daily skipped: non-trading day")
        return
    pipeline = _pipeline("fut_daily")
    if not pipeline:
        logger.debug("sync_fut_daily skipped: not tushare source")
        return
    logger.info("Syncing futures daily data...")
    db = SessionLocal()
    try:
        end_date = _cn_date().strftime("%Y%m%d")
        start_date = (_cn_date() - timedelta(days=10)).strftime("%Y%m%d")
        varieties = db.query(VarietyDB).all()
        total = 0
        for v in varieties:
            try:
                ts_code = _get_ts_code(v)
                stats = pipeline.run_fut_daily(ts_code, start_date, end_date, period="D")
                total += stats.get("processed", 0)
            except (SQLAlchemyError, OSError) as e:
                logger.error("Failed to sync daily for %s: %s", v.symbol, e)
        logger.info("Synced %d daily rows for %d varieties", total, len(varieties))
    finally:
        db.close()


def sync_fut_settle():
    """Sync futures settlement parameters."""
    if not is_trading_day(_cn_date()):
        logger.info("sync_fut_settle skipped: non-trading day")
        return
    pipeline = _pipeline("fut_settle")
    if not pipeline:
        logger.debug("sync_fut_settle skipped: not tushare source")
        return
    logger.info("Syncing futures settle data...")
    try:
        trade_date = _cn_date().strftime("%Y%m%d")
        stats = pipeline.run_fut_settle(trade_date)
        logger.info("Synced settle: %s", stats)
    except (SQLAlchemyError, OSError) as e:
        logger.error("Failed to sync settle: %s", e)


def sync_fut_weekly_detail():
    """Sync futures weekly trading detail."""
    if not is_trading_day(_cn_date()):
        logger.info("sync_fut_weekly_detail skipped: non-trading day")
        return
    pipeline = _pipeline("fut_weekly_detail")
    if not pipeline:
        logger.debug("sync_fut_weekly_detail skipped: not tushare source")
        return
    logger.info("Syncing futures weekly detail...")
    try:
        end_date = _cn_date().strftime("%Y%m%d")
        start_date = (_cn_date() - timedelta(days=30)).strftime("%Y%m%d")
        stats = pipeline.run_fut_weekly_detail(start_date, end_date)
        logger.info("Synced weekly detail: %s", stats)
    except (SQLAlchemyError, OSError) as e:
        logger.error("Failed to sync weekly detail: %s", e)


def sync_fut_wsr():
    """Sync futures warehouse receipt data."""
    if not is_trading_day(_cn_date()):
        logger.info("sync_fut_wsr skipped: non-trading day")
        return
    pipeline = _pipeline("fut_wsr")
    if not pipeline:
        logger.debug("sync_fut_wsr skipped: not tushare source")
        return
    logger.info("Syncing futures warehouse receipts...")
    try:
        trade_date = _cn_date().strftime("%Y%m%d")
        stats = pipeline.run_fut_wsr(trade_date)
        logger.info("Synced WSR: %s", stats)
    except (SQLAlchemyError, OSError) as e:
        logger.error("Failed to sync WSR: %s", e)


def sync_fut_holding():
    """Sync futures holding rankings."""
    if not is_trading_day(_cn_date()):
        logger.info("sync_fut_holding skipped: non-trading day")
        return
    pipeline = _pipeline("fut_holding")
    if not pipeline:
        logger.debug("sync_fut_holding skipped: not tushare source")
        return
    logger.info("Syncing futures holding data...")
    try:
        trade_date = _cn_date().strftime("%Y%m%d")
        stats = pipeline.run_fut_holding(trade_date)
        logger.info("Synced holding: %s", stats)
    except (SQLAlchemyError, OSError) as e:
        logger.error("Failed to sync holding: %s", e)


def sync_fut_price_limit():
    """Daily sync for futures price limit data."""
    if not is_trading_day(_cn_date()):
        logger.info("sync_fut_price_limit skipped: non-trading day")
        return
    pipeline = _pipeline("fut_price_limit")
    if not pipeline:
        logger.debug("sync_fut_price_limit skipped: not tushare source")
        return
    logger.info("Syncing futures price limit data...")
    try:
        trade_date = _cn_date().strftime("%Y%m%d")
        stats = pipeline.run_fut_price_limit(trade_date=trade_date)
        logger.info("Synced price limit: %s", stats)
    except (SQLAlchemyError, OSError) as e:
        logger.error("Failed to sync price limit: %s", e)


def sync_trading_calendar():
    """自动同步交易日历：每月 1 日从 AKShare 增量更新 JSON 并热刷新内存缓存。"""
    logger.info("Syncing trading calendar...")
    try:
        import importlib.util
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scripts", "update_trading_calendar.py"
        )
        if not os.path.exists(script_path):
            logger.warning("update_trading_calendar.py not found at %s", script_path)
            return
        spec = importlib.util.spec_from_file_location("update_trading_calendar", script_path)
        if spec is None or spec.loader is None:
            logger.warning("Cannot load update_trading_calendar module")
            return
        mod = importlib.util.module_from_spec(spec)
        sys.modules["update_trading_calendar"] = mod
        spec.loader.exec_module(mod)
        mod.main(force_full=False)
        logger.info("Trading calendar sync completed")
    except ImportError as e:
        logger.warning("AKShare not available, skipping trading calendar sync: %s", e)
    except (ConnectionError, TypeError, ValueError, OSError) as e:
        logger.error("Failed to sync trading calendar: %s", e)


def sync_variety_metadata():
    """Update main-contract mapping from Tushare fut_mapping."""
    pipeline = _pipeline("fut_mapping")
    if not pipeline:
        logger.debug("sync_variety_metadata skipped: not tushare source")
        return
    logger.info("Syncing variety metadata...")
    try:
        trade_date = _cn_date().strftime("%Y%m%d")
        stats = pipeline.run_fut_mapping(trade_date=trade_date)
        logger.info("Synced variety metadata: %s", stats)
    except (SQLAlchemyError, OSError) as e:
        logger.error("Failed to sync variety metadata: %s", e)


# ------------------------------------------------------------------
# Scheduler 生命周期
# ------------------------------------------------------------------

scheduler = BackgroundScheduler()


def start_scheduler():
    _ensure_collectors()
    jobs = build_job_configs(
        refresh_and_sync_func=refresh_and_sync,
        sync_daily_kline_func=sync_daily_kline,
        sync_minute_kline_func=sync_minute_kline,
        sync_trading_calendar_func=sync_trading_calendar,
        sync_variety_metadata_func=sync_variety_metadata,
        sync_fut_daily_func=sync_fut_daily if _pipeline("fut_daily") else None,
        sync_fut_settle_func=sync_fut_settle if _pipeline("fut_settle") else None,
        sync_fut_weekly_detail_func=sync_fut_weekly_detail if _pipeline("fut_weekly_detail") else None,
        sync_fut_wsr_func=sync_fut_wsr if _pipeline("fut_wsr") else None,
        sync_fut_holding_func=sync_fut_holding if _pipeline("fut_holding") else None,
        sync_fut_price_limit_func=sync_fut_price_limit if _pipeline("fut_price_limit") else None,
    )
    register_jobs(scheduler, jobs)
    scheduler.start()
    logger.info("Scheduler started")


def shutdown_scheduler():
    scheduler.shutdown(wait=True, timeout=10)
    logger.info("Scheduler shutdown")
