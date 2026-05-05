"""本地文件数据源：CSV / JSON。
用于历史数据回灌、回归测试、CI fixture。
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List, Dict

import pandas as pd

from .base import BaseCollector

logger = logging.getLogger("data.file")


class FileCollector(BaseCollector):
    """从本地 CSV / JSON 文件读取期货行情数据。

    文件命名约定：
    - 实时行情：{data_dir}/{symbol}_realtime.json
    - K 线数据：{data_dir}/{contract_code}_{period}.csv

    CSV 列名支持内部标准字段（open_price/high_price/low_price/close_price/volume/trading_time）
    或通用字段（open/high/low/close/vol/datetime）。
    """

    def __init__(self, data_dir: str = "./data/fixtures"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def fetch_realtime(self, symbol: str) -> Dict[str, Any] | None:
        """读取 JSON 格式的单条实时行情。"""
        path = self.data_dir / f"{symbol}_realtime.json"
        if not path.exists():
            logger.debug(f"Realtime fixture not found: {path}")
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load realtime fixture {path}: {e}")
            return None

    def fetch_kline(
        self,
        contract_code: str,
        period: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """读取 CSV 格式的 K 线数据。"""
        path = self.data_dir / f"{contract_code}_{period}.csv"
        if not path.exists():
            logger.debug(f"K-line fixture not found: {path}")
            return []

        try:
            df = pd.read_csv(path)
            if df.empty:
                return []

            # 统一列名映射（支持多种常见命名）
            col_map = {
                "datetime": "trading_time",
                "trade_time": "trading_time",
                "trade_date": "trading_time",
                "time": "trading_time",
            }
            df = df.rename(columns=col_map)

            # 按时间排序，取最后 limit 条
            if "trading_time" in df.columns:
                df = df.sort_values("trading_time").tail(limit)
            else:
                df = df.tail(limit)

            records = df.to_dict("records")
            # 为每条记录附加 contract_code
            for r in records:
                r["contract_code"] = contract_code
            return records

        except Exception as e:
            logger.error(f"Failed to load kline fixture {path}: {e}")
            return []
