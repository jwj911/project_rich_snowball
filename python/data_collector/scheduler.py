import logging
import os
import sys
import time
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.exc import SQLAlchemyError

from config import DATA_SOURCE, ENV
from data_collector.collector_registry import (
    build_akshare_minute_pipeline,
    build_collector_entries,
    build_pipelines,
)
from data_collector.job_registry import build_job_configs, register_jobs
from models import NewsArticleDB, NewsSourceDB, PriceAlertDB, RealtimeQuoteDB, SessionLocal, VarietyDB
from services.metrics import data_collection_duration_seconds, data_collection_runs_total
from services.news_fetcher import fetch_all_enabled_sources
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


def _get_active_varieties(db):
    """获取活跃品种列表，避免全量加载已下架/不活跃品种。"""
    return db.query(VarietyDB).filter(VarietyDB.is_active == True).all()  # noqa: E712


def _should_skip_daily_task(job_name: str, trade_date: str, db) -> bool:
    """幂等检查：同一天同一任务已成功执行过则跳过。

    防止手动重试或 misfire 补执行时产生重复数据。
    """
    from models import DataIngestionRunDB
    try:
        dt = datetime.strptime(trade_date, "%Y%m%d")
        exists = (
            db.query(DataIngestionRunDB)
            .filter(DataIngestionRunDB.job_name == job_name)
            .filter(DataIngestionRunDB.status == "success")
            .filter(DataIngestionRunDB.started_at >= dt)
            .filter(DataIngestionRunDB.started_at < _cn_date() + timedelta(days=1))
            .first()
        )
        if exists:
            logger.info("Idempotent skip: %s for %s already succeeded", job_name, trade_date)
            return True
    except Exception as e:
        logger.warning("Idempotency check failed for %s: %s", job_name, e)
    return False


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
        varieties = _get_active_varieties(db)
        symbols = [v.symbol for v in varieties]
        stats = pipeline.run_realtime(symbols)
        logger.info(
            "realtime_quotes_updated",
            extra={
                "task_name": "refresh_realtime",
                "symbol_count": len(symbols),
                "stats": stats,
            },
        )
        mark_realtime_updated()
        _check_price_alerts(db)
        data_collection_runs_total.labels(task_name="refresh_realtime", status="success").inc()
    except (SQLAlchemyError, OSError) as e:
        logger.error("Refresh realtime failed: %s", e)
        data_collection_runs_total.labels(task_name="refresh_realtime", status="failed").inc()
        raise
    finally:
        db.close()
        data_collection_duration_seconds.labels(task_name="refresh_realtime").observe(time.time() - start)


def _check_price_alerts(db):
    """检查所有未触发的价格预警，根据实时行情标记触发状态。"""
    try:
        alerts = (
            db.query(PriceAlertDB)
            .filter(PriceAlertDB.is_triggered.is_(False))
            .all()
        )
        if not alerts:
            return

        triggered_count = 0
        for alert in alerts:
            quote = (
                db.query(RealtimeQuoteDB)
                .filter(RealtimeQuoteDB.variety_id == alert.variety_id)
                .first()
            )
            if not quote:
                continue

            current = quote.current_price
            if current is None:
                continue

            triggered = False
            if alert.alert_type == "above" and current >= alert.target_price:
                triggered = True
            elif alert.alert_type == "below" and current <= alert.target_price:
                triggered = True

            if triggered:
                alert.is_triggered = True
                alert.triggered_at = datetime.now(UTC)
                triggered_count += 1

        if triggered_count > 0:
            db.commit()
            logger.info("Price alerts triggered: %d", triggered_count)
    except (SQLAlchemyError, OSError) as e:
        logger.error("Failed to check price alerts: %s", e)


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
        varieties = _get_active_varieties(db)
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
        varieties = _get_active_varieties(db)
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
        varieties = _get_active_varieties(db)
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
    trade_date = _cn_date().strftime("%Y%m%d")
    db = SessionLocal()
    try:
        if _should_skip_daily_task("sync_fut_settle", trade_date, db):
            return
    finally:
        db.close()
    logger.info("Syncing futures settle data...")
    try:
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
    end_date = _cn_date().strftime("%Y%m%d")
    start_date = (_cn_date() - timedelta(days=30)).strftime("%Y%m%d")
    param_key = f"{start_date}_{end_date}"
    db = SessionLocal()
    try:
        if _should_skip_daily_task("sync_fut_weekly_detail", param_key, db):
            return
    finally:
        db.close()
    logger.info("Syncing futures weekly detail...")
    try:
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
    trade_date = _cn_date().strftime("%Y%m%d")
    db = SessionLocal()
    try:
        if _should_skip_daily_task("sync_fut_wsr", trade_date, db):
            return
    finally:
        db.close()
    logger.info("Syncing futures warehouse receipts...")
    try:
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
    trade_date = _cn_date().strftime("%Y%m%d")
    db = SessionLocal()
    try:
        if _should_skip_daily_task("sync_fut_holding", trade_date, db):
            return
    finally:
        db.close()
    logger.info("Syncing futures holding data...")
    try:
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
    trade_date = _cn_date().strftime("%Y%m%d")
    db = SessionLocal()
    try:
        if _should_skip_daily_task("sync_fut_price_limit", trade_date, db):
            return
    finally:
        db.close()
    logger.info("Syncing futures price limit data...")
    try:
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


def _ensure_builtin_news_sources(db):
    """确保系统内置 RSS 新闻源已初始化。"""
    builtins = [
        ("新浪财经期货", "https://finance.sina.com.cn/future/", "综合财经"),
        ("东方财富期货", "https://futures.eastmoney.com/", "综合财经"),
        ("期货日报", "https://www.qhrb.com.cn/", "行业媒体"),
    ]
    for name, url, category in builtins:
        exists = db.query(NewsSourceDB.id).filter(NewsSourceDB.url == url).first()
        if not exists:
            db.add(NewsSourceDB(name=name, url=url, category=category, is_builtin=True, is_enabled=True))
    db.commit()


def sync_news():
    """定时抓取所有启用的 RSS 新闻源，并为新增文章生成 AI 摘要。"""
    logger.info("Syncing news from RSS sources...")
    db = SessionLocal()
    try:
        _ensure_builtin_news_sources(db)
        result = fetch_all_enabled_sources(db)
        total_new = sum(result.values())
        logger.info("News sync completed: %d sources, %d new articles", len(result), total_new)

        # 为未生成 AI 摘要的最新文章批量生成摘要
        if total_new > 0:
            from services.ai_chat import summarize_article_sync
            unsummarized = (
                db.query(NewsArticleDB)
                .filter(NewsArticleDB.ai_summary.is_(None))
                .order_by(NewsArticleDB.fetched_at.desc())
                .limit(10)
                .all()
            )
            for article in unsummarized:
                summary = summarize_article_sync(article.title, article.summary or "")
                if summary:
                    article.ai_summary = summary
                    db.commit()
                    logger.info("AI summary generated for article: %s", article.title[:40])
    except (SQLAlchemyError, OSError) as e:
        logger.error("Failed to sync news: %s", e)
    finally:
        db.close()


# ------------------------------------------------------------------
# Scheduler 生命周期
# ------------------------------------------------------------------

scheduler = BackgroundScheduler()


def start_scheduler():
    _ensure_collectors()
    jobs = build_job_configs(
        refresh_realtime_quotes_func=refresh_realtime_quotes,
        sync_daily_kline_func=sync_daily_kline,
        sync_minute_kline_func=sync_minute_kline,
        sync_trading_calendar_func=sync_trading_calendar,
        sync_variety_metadata_func=sync_variety_metadata,
        sync_news_func=sync_news,
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
