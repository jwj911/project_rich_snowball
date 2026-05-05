from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseCollector(ABC):
    @abstractmethod
    def fetch_realtime(self, symbol: str) -> Dict[str, Any]:
        """获取单个品种实时行情，返回字典或 None"""
        pass

    # 扩展接口（仅 Tushare 支持，其他 Collector 默认空实现）
    def fetch_daily(self, ts_code: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        return []

    def fetch_weekly(self, ts_code: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        return []

    def fetch_monthly(self, ts_code: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        return []

    def fetch_settle(self, trade_date: str, exchange: str = None) -> List[Dict[str, Any]]:
        return []

    def fetch_weekly_detail(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        return []

    def fetch_wsr(self, trade_date: str, symbol: str = None) -> List[Dict[str, Any]]:
        return []

    def fetch_holding(self, trade_date: str, symbol: str = None, exchange: str = None) -> List[Dict[str, Any]]:
        return []

    def fetch_basic(
        self,
        exchange: str,
        fut_type: str = "1",
        fut_code: str = None,
        list_date: str = None,
    ) -> List[Dict[str, Any]]:
        return []

    def fetch_mapping(self, ts_code: str = None, trade_date: str = None) -> List[Dict[str, Any]]:
        return []

    def fetch_limit(self, trade_date: str = None, ts_code: str = None) -> List[Dict[str, Any]]:
        return []

    @abstractmethod
    def fetch_kline(self, contract_code: str, period: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取 K 线数据
        :param contract_code: 合约代码，如 "AU2406"
        :param period: 周期，如 "1m", "5m", "1h", "1d"
        :param limit: 返回条数上限
        """
        pass
