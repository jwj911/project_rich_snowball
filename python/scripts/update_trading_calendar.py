#!/usr/bin/env python3
"""交易日历自动更新脚本。

从 AKShare 拉取中国交易日历（A 股与期货交易日历基本一致），
写入 data/trading_calendar.json，供 TradingCalendar 优先加载。

建议在以下时机运行：
    - 每年年初国务院公布新年度节假日安排后
    - 发现 fallback 硬编码假期与实际不符时
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


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    logger.info("Fetching trading calendar from AKShare...")
    dates = fetch_trading_days()
    logger.info("Fetched %s trading days (from %s to %s)", len(dates), dates[0], dates[-1])

    # 确保输出目录存在
    os.makedirs(os.path.dirname(_OUTPUT_PATH), exist_ok=True)

    with open(_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dates, f, ensure_ascii=False, indent=2)

    logger.info("Saved to %s", _OUTPUT_PATH)


if __name__ == "__main__":
    main()
