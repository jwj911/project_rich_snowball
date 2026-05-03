from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseCollector(ABC):
    @abstractmethod
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取单个品种实时行情，返回字典或 None"""
        pass

    @abstractmethod
    def fetch_kline(self, symbol: str, period: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取 K 线数据
        :param symbol: 品种代码，如 "AU"
        :param period: 周期，如 "1m", "5m", "1h", "1d"
        :param limit: 返回条数上限
        """
        pass
