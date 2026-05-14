#!/usr/bin/env python3
"""独立数据采集 Worker 入口。

生产环境部署：
  python worker.py          # 纯 scheduler，不启动 FastAPI

开发环境（API + scheduler 同进程）：
  ENABLE_SCHEDULER=1 python main.py
"""
import os
import sys
import logging

# 确保 SECRET_KEY 存在
if not os.getenv("SECRET_KEY"):
    raise ValueError("SECRET_KEY environment variable is not set")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("worker")


def main():
    logger.info("Starting standalone scheduler worker...")

    from data_collector.scheduler import start_scheduler, shutdown_scheduler
    from data_collector.init_varieties import init_varieties
    from models import init_db

    init_db()
    init_varieties()

    # 开发环境下初始化 mock 数据
    env = os.getenv("ENV", "development")
    if env != "production":
        from data_collector.init_mock_data import init_mock_data
        init_mock_data()

    start_scheduler()
    logger.info("Scheduler worker started. Press Ctrl+C to stop.")

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal...")
    finally:
        shutdown_scheduler()
        logger.info("Scheduler worker stopped.")


if __name__ == "__main__":
    main()
