#!/usr/bin/env python3
"""交易日历自动更新脚本。

从 AKShare 拉取中国交易日历（A 股与期货交易日历基本一致），
增量更新 data/trading_calendar.json，供 TradingCalendar 优先加载。

调度建议：
    - 每月 1 日自动运行（scheduler 已集成）
    - 每年年初国务院公布新年度节假日安排后手动触发
    - 部署新环境时初始化最新日历

用法:
    cd python
    python scripts/update_trading_calendar.py

依赖:
    pip install akshare
"""

import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

# 项目根目录（python/ 的父目录）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUTPUT_PATH = os.path.join(_PROJECT_ROOT, "data", "trading_calendar.json")


def fetch_trading_days() -> list[str]:
    """通过 AKShare 获取历史交易日列表。"""
    try:
        import akshare as ak
    except ImportError as e:
        raise RuntimeError(
            "AKShare 未安装，请先执行: pip install akshare"
        ) from e

    df = ak.tool_trade_date_hist_sina()
    # df 列名为 trade_date，格式为 YYYY-MM-DD 字符串
    dates = sorted(df["trade_date"].astype(str).tolist())
    return dates


def load_existing_dates() -> set[str]:
    """加载本地已存在的交易日历。"""
    if os.path.exists(_OUTPUT_PATH):
        with open(_OUTPUT_PATH, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def main(force_full: bool = False):
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    existing = load_existing_dates()
    if existing and not force_full:
        logger.info("Existing calendar: %s dates (up to %s)", len(existing), max(existing))

    logger.info("Fetching trading calendar from AKShare...")
    dates = fetch_trading_days()
    logger.info("Fetched %s trading days (from %s to %s)", len(dates), dates[0], dates[-1])

    if not force_full and existing:
        merged = sorted(existing | set(dates))
        added = len(merged) - len(existing)
        if added == 0:
            logger.info("No new dates to add. Calendar is up to date.")
            return merged
        logger.info("Incremental update: added %s new dates.", added)
    else:
        merged = dates
        logger.info("Full refresh: wrote %s dates.", len(merged))

    # 确保输出目录存在
    os.makedirs(os.path.dirname(_OUTPUT_PATH), exist_ok=True)

    with open(_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    logger.info("Saved to %s", _OUTPUT_PATH)

    # 尝试热刷新内存中的 TradingCalendar
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from services.trading_calendar import TradingCalendar
        TradingCalendar().reload()
        logger.info("TradingCalendar reloaded in memory.")
    except Exception as e:
        logger.warning("Failed to reload TradingCalendar: %s", e)

    return merged


if __name__ == "__main__":
    main()
