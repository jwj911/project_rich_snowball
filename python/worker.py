#!/usr/bin/env python3
"""独立数据采集 Worker 入口。

生产环境部署：
  python worker.py          # 纯 scheduler，不启动 FastAPI

开发环境（API + scheduler 同进程）：
  ENABLE_SCHEDULER=1 python main.py
"""
import logging
import os
import signal
import sys
import time

# 先加载 config，确保 .env 被解析（与 main.py 行为一致）
import config  # noqa: F401
from services.logging_config import setup_logging

# 确保 SECRET_KEY 存在
if not os.getenv("SECRET_KEY"):
    raise ValueError("SECRET_KEY environment variable is not set")

# 初始化结构化日志
setup_logging()

logger = logging.getLogger("worker")

# 全局退出标志，供 SIGTERM/SIGINT 处理器设置
_shutdown_requested = False


def _signal_handler(signum, frame):
    """处理 SIGTERM 和 SIGINT，触发优雅退出。"""
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info("Received %s, requesting graceful shutdown...", sig_name)
    _shutdown_requested = True


def main():
    # 注册信号处理器（SIGTERM 用于 Docker/K8s 优雅停止，SIGINT 用于 Ctrl+C）
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    # Windows 额外注册 SIGBREAK（Ctrl+Break），比 SIGTERM 更可靠
    if sys.platform == "win32" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _signal_handler)

    logger.info("Starting standalone scheduler worker...")

    from data_collector.init_varieties import init_varieties
    from data_collector.scheduler import shutdown_scheduler, start_scheduler
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
        while not _shutdown_requested:
            time.sleep(1)
    finally:
        shutdown_scheduler()
        from models import engine
        engine.dispose()
        logger.info("Scheduler worker stopped.")


if __name__ == "__main__":
    main()
