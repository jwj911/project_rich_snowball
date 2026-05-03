import time
import logging
from typing import List, Dict, Any
from datetime import datetime
from .base import BaseCollector

logger = logging.getLogger("data.akshare")


class AkshareCollector(BaseCollector):
    def __init__(self):
        try:
            import akshare as ak
            self.ak = ak
        except ImportError:
            raise ImportError("akshare is not installed. Run: pip install akshare")

    def _retry(self, func, max_retries=3):
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"[retry {attempt+1}/{max_retries}] {e}, waiting {wait}s")
                if attempt < max_retries - 1:
                    time.sleep(wait)
                else:
                    logger.error(f"Max retries exceeded: {e}")
                    raise

    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        def _do():
            df = self.ak.futures_zh_spot(symbol=symbol, market="CF")
            if df.empty:
                return None
            row = df.iloc[0]
            return {
                "symbol": symbol,
                "current_price": float(row.get("最新价", 0)),
                "change_percent": float(row.get("涨跌幅", 0)),
                "open_price": float(row.get("开盘价", 0)),
                "high": float(row.get("最高价", 0)),
                "low": float(row.get("最低价", 0)),
                "volume": int(row.get("成交量", 0)),
                "open_interest": int(row.get("持仓量", 0)),
                "updated_at": datetime.now(),
            }
        return self._retry(_do)

    def fetch_kline(self, symbol: str, period: str, limit: int = 100) -> List[Dict[str, Any]]:
        def _do():
            period_map = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "60m": "60", "1d": "D"}
            ak_period = period_map.get(period, "1")
            contract = f"{symbol}2506"
            df = self.ak.futures_zh_minute_sina(symbol=contract, period=ak_period)
            df = df.tail(limit)
            return df.rename(columns={
                "datetime": "trading_time",
                "open": "open_price",
                "high": "high_price",
                "low": "low_price",
                "close": "close_price",
                "volume": "volume",
            }).to_dict("records")
        return self._retry(_do)
