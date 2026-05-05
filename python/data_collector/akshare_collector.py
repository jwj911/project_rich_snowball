import logging
import re
import time
from typing import Any, Dict, List

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
                logger.warning("[retry %s/%s] %s, waiting %ss", attempt + 1, max_retries, e, wait)
                if attempt < max_retries - 1:
                    time.sleep(wait)
                else:
                    logger.error("Max retries exceeded: %s", e)
                    raise

    def fetch_realtime(self, symbol: str) -> Dict[str, Any] | None:
        """Fetch one AkShare realtime quote row and leave field mapping to adapters."""

        def _do():
            df = self.ak.futures_zh_spot(symbol=symbol, market="CF")
            if df is None or df.empty:
                return None
            row = df.iloc[0].to_dict()
            row["symbol"] = symbol
            return row

        return self._retry(_do)

    def fetch_kline(self, contract_code: str, period: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch minute/day kline data for the given concrete contract code."""

        def _do():
            period_map = {
                "1m": "1",
                "5m": "5",
                "15m": "15",
                "30m": "30",
                "1h": "60",
                "60m": "60",
                "1d": "D",
            }
            ak_period = period_map.get(period, "1")
            contract = _normalize_contract_code(contract_code)

            if ak_period == "D" and hasattr(self.ak, "futures_zh_daily_sina"):
                df = self.ak.futures_zh_daily_sina(symbol=contract)
            else:
                df = self.ak.futures_zh_minute_sina(symbol=contract, period=ak_period)

            if df is None or df.empty:
                return []

            records = df.tail(limit).to_dict("records")
            symbol = _symbol_from_contract(contract_code)
            for row in records:
                row["contract_code"] = contract_code
                row["symbol"] = symbol
                row["period"] = period
            return records

        return self._retry(_do)


def _normalize_contract_code(contract_code: str) -> str:
    """AkShare/Sina futures endpoints usually expect lowercase concrete contracts."""
    return contract_code.lower()


def _symbol_from_contract(contract_code: str) -> str:
    match = re.match(r"^([A-Za-z]+)", contract_code or "")
    return match.group(1).upper() if match else contract_code
