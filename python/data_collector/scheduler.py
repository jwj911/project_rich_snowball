from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import logging

from models import SessionLocal, VarietyDB, ProductDB
from .upsert import upsert_realtime, insert_kline_bulk
from .cleaner import clean_realtime, clean_kline
from .mock_collector import MockCollector

logger = logging.getLogger("data.scheduler")

_collector = MockCollector()


def refresh_realtime_quotes():
    """每 30 秒刷新实时行情"""
    logger.info("Refreshing realtime quotes...")
    db = SessionLocal()
    try:
        varieties = db.query(VarietyDB).all()
        for v in varieties:
            try:
                raw = _collector.fetch_realtime(v.symbol)
                if raw:
                    data = clean_realtime(raw, v.symbol)
                    if data:
                        upsert_realtime(db, data)
            except Exception as e:
                logger.error(f"Failed to refresh {v.symbol}: {e}")
        logger.info(f"Refreshed {len(varieties)} varieties")
    finally:
        db.close()


def sync_daily_kline():
    """每天 16:05 补全日 K 线"""
    logger.info("Syncing daily kline...")
    db = SessionLocal()
    try:
        varieties = db.query(VarietyDB).all()
        for v in varieties:
            try:
                raw_list = _collector.fetch_kline(v.symbol, "1h", limit=24)
                cleaned = clean_kline(raw_list, v.symbol)
                insert_kline_bulk(db, cleaned, "1h")
            except Exception as e:
                logger.error(f"Failed to sync kline for {v.symbol}: {e}")
        logger.info(f"Synced kline for {len(varieties)} varieties")
    finally:
        db.close()


def sync_prices_to_products():
    """每 30 秒将 realtime_quotes 同步到 products 兼容层"""
    logger.info("Syncing prices to products...")
    db = SessionLocal()
    try:
        from models import RealtimeQuoteDB
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
    except Exception as e:
        logger.error(f"Sync prices failed: {e}")
    finally:
        db.close()


scheduler = BackgroundScheduler()


def start_scheduler():
    scheduler.add_job(refresh_realtime_quotes, IntervalTrigger(seconds=30), id="realtime", replace_existing=True)
    scheduler.add_job(sync_prices_to_products, IntervalTrigger(seconds=30), id="sync_products", replace_existing=True)
    scheduler.add_job(sync_daily_kline, CronTrigger(hour=16, minute=5), id="daily_kline", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started")


def shutdown_scheduler():
    scheduler.shutdown()
    logger.info("Scheduler shutdown")
