import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
from .base import BaseCollector


class MockCollector(BaseCollector):
    """模拟数据采集器：生成带随机游走的 OHLCV 数据"""

    BASE_PRICES = {
        "AU": 453.2, "AG": 5420, "CU": 68450, "RB": 3680,
        "I": 825, "SC": 528.5, "MA": 2580, "M": 3250,
        "C": 2455, "CF": 16850,
    }

    def __init__(self, seed: int = 42):
        random.seed(seed)
        self._states = {}

    def _get_base(self, symbol: str) -> float:
        return self.BASE_PRICES.get(symbol, 1000.0)

    def _next_price(self, symbol: str) -> float:
        base = self._get_base(symbol)
        last = self._states.get(symbol, base)
        mean_reversion = (base - last) * 0.02
        noise = random.gauss(0, base * 0.003)
        new_price = last + mean_reversion + noise
        new_price = max(base * 0.95, min(base * 1.05, new_price))
        self._states[symbol] = new_price
        return round(new_price, 2)

    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        price = self._next_price(symbol)
        base = self._get_base(symbol)
        change_percent = round((price - base) / base * 100, 2)
        return {
            "symbol": symbol,
            "current_price": price,
            "change_percent": change_percent,
            "open_price": round(price * random.uniform(0.995, 1.005), 2),
            "high": round(price * random.uniform(1.001, 1.01), 2),
            "low": round(price * random.uniform(0.99, 0.999), 2),
            "volume": random.randint(10000, 500000),
            "open_interest": random.randint(10000, 100000),
            "updated_at": datetime.now(),
        }

    def fetch_kline(self, symbol: str, period: str, limit: int = 100) -> List[Dict[str, Any]]:
        base = self._get_base(symbol)
        results = []
        now = datetime.now()
        interval_map = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "1d": 1440}
        minutes = interval_map.get(period, 60)

        close = base
        for i in range(limit, 0, -1):
            ts = now - timedelta(minutes=minutes * i)
            open_p = close
            close = round(base + random.gauss(0, base * 0.005), 2)
            high = max(open_p, close) * random.uniform(1.001, 1.008)
            low = min(open_p, close) * random.uniform(0.992, 0.999)
            results.append({
                "symbol": symbol,
                "trading_time": ts,
                "open_price": round(open_p, 2),
                "high_price": round(high, 2),
                "low_price": round(low, 2),
                "close_price": round(close, 2),
                "volume": random.randint(1000, 50000),
                "open_interest": random.randint(5000, 50000),
            })
        self._states[symbol] = close
        return results
