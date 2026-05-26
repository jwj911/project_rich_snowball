"""Collector Registry：管理数据采集器的延迟初始化与 fallback 链。

设计目标：
- 新增数据源时，只需在 COLLECTOR_SOURCES 中注册条目，无需修改 scheduler.py 主体。
- 采集 pipeline 的创建也集中于此，避免 scheduler.py 承担过多初始化逻辑。
"""

import logging

import requests

from data_collector.base import BaseCollector
from data_collector.cleaner import clean_kline, clean_realtime
from data_collector.pipeline import DataPipeline

logger = logging.getLogger("data.collector_registry")


class _MappedFallbackCollector(BaseCollector):
    """Try collectors in order and return already-mapped internal rows."""

    def __init__(self, entries):
        self.entries = entries

    def fetch_realtime(self, symbol: str):
        for name, collector, realtime_adapter, _ in self.entries:
            try:
                raw = collector.fetch_realtime(symbol)
                if raw is None:
                    continue
                return realtime_adapter(raw, symbol)
            except (requests.RequestException, ConnectionError, TimeoutError, OSError, KeyError, TypeError, ValueError) as e:
                logger.warning("%s realtime failed for %s, trying next source: %s", name, symbol, e)
        return None

    def fetch_kline(self, contract_code: str, period: str, limit: int = 100):
        for name, collector, _, kline_adapter in self.entries:
            try:
                raw_rows = collector.fetch_kline(contract_code, period, limit=limit)
                if not raw_rows:
                    continue
                adapted = []
                for row in raw_rows:
                    try:
                        adapted.append(kline_adapter(row, contract_code, period))
                    except (KeyError, TypeError, ValueError, IndexError) as e:
                        logger.warning("%s kline adapter failed for %s/%s row: %s", name, contract_code, period, e)
                return adapted
            except (requests.RequestException, ConnectionError, TimeoutError, OSError, KeyError, TypeError, ValueError) as e:
                logger.warning("%s kline failed for %s/%s, trying next source: %s", name, contract_code, period, e)
        return []


def _try_create(name, factory, realtime_adapter, kline_adapter):
    try:
        return name, factory(), realtime_adapter, kline_adapter
    except (ImportError, TypeError, ValueError, ConnectionError) as e:
        logger.warning("%s collector unavailable: %s", name, e)
        return None


# ------------------------------------------------------------------
# 注册表：按优先级降序排列。新增数据源只需在此添加条目。
# ------------------------------------------------------------------

def _tushare_entry():
    from data_collector.adapters import map_tushare_kline, map_tushare_realtime
    from data_collector.tushare_collector import TushareCollector
    return _try_create("tushare", TushareCollector, map_tushare_realtime, map_tushare_kline)


def _akshare_entry():
    from data_collector.adapters import map_akshare_kline, map_akshare_realtime
    from data_collector.akshare_collector import AkshareCollector
    return _try_create("akshare", AkshareCollector, map_akshare_realtime, map_akshare_kline)


def _mock_entry():
    from data_collector.adapters import map_mock_kline, map_mock_realtime
    from data_collector.mock_collector import MockCollector
    return _try_create("mock", MockCollector, map_mock_realtime, map_mock_kline)


# 优先级：tushare > akshare > mock（仅在非生产环境降级）
COLLECTOR_SOURCES = [
    {"name": "tushare", "sources": {"tushare", "auto"}, "factory": _tushare_entry},
    {"name": "akshare", "sources": {"akshare", "auto"}, "factory": _akshare_entry},
    {"name": "mock", "sources": {"mock", "auto"}, "factory": _mock_entry, "fallback_only": True},
]


def build_collector_entries(data_source: str, env: str):
    """根据 data_source 和 env 构建 collector fallback 链。

    返回 (entries, tushare_entry) 元组。
    entries 为 (name, collector, realtime_adapter, kline_adapter) 列表。
    """
    entries = []
    tushare_entry = None

    for cfg in COLLECTOR_SOURCES:
        if data_source not in cfg["sources"]:
            continue
        if cfg.get("fallback_only") and env == "production":
            continue

        entry = cfg["factory"]()
        if entry:
            entries.append(entry)
            if cfg["name"] == "tushare":
                tushare_entry = entry

    return entries, tushare_entry


def build_pipelines(collector, realtime_adapter, kline_adapter, tushare_entry=None):
    """基于 collector 和可选的 tushare_entry 构建所有 pipeline 实例。

    返回 dict，键包括：realtime, kline, fut_daily, fut_settle, ...
    """
    pipelines = {
        "realtime": DataPipeline(collector=collector, adapter=realtime_adapter, cleaner=clean_realtime),
        "kline": DataPipeline(collector=collector, adapter=kline_adapter, cleaner=clean_kline),
    }

    if tushare_entry:
        from data_collector.adapters import (
            map_tushare_ft_limit,
            map_tushare_fut_daily,
            map_tushare_fut_holding,
            map_tushare_fut_mapping,
            map_tushare_fut_settle,
            map_tushare_fut_weekly_detail,
            map_tushare_fut_wsr,
        )
        _, tc, _, _ = tushare_entry
        pipelines["fut_daily"] = DataPipeline(collector=tc, adapter=map_tushare_fut_daily)
        pipelines["fut_settle"] = DataPipeline(collector=tc, adapter=map_tushare_fut_settle)
        pipelines["fut_weekly_detail"] = DataPipeline(collector=tc, adapter=map_tushare_fut_weekly_detail)
        pipelines["fut_wsr"] = DataPipeline(collector=tc, adapter=map_tushare_fut_wsr)
        pipelines["fut_holding"] = DataPipeline(collector=tc, adapter=map_tushare_fut_holding)
        pipelines["fut_price_limit"] = DataPipeline(collector=tc, adapter=map_tushare_ft_limit)
        pipelines["fut_mapping"] = DataPipeline(collector=tc, adapter=map_tushare_fut_mapping)

    return pipelines


def build_akshare_minute_pipeline():
    """独立构建 AkShare 分钟线 Pipeline（双系统架构）。"""
    try:
        from data_collector.adapters import map_akshare_kline
        from data_collector.akshare_collector import AkshareCollector
        collector = AkshareCollector()
        return DataPipeline(collector=collector, adapter=map_akshare_kline, cleaner=clean_kline)
    except (ImportError, OSError, requests.RequestException) as e:
        logger.warning("AkShare minute pipeline unavailable: %s", e)
        return None
