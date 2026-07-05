"""性能优化相关测试。"""

from __future__ import annotations

from services.backtest.service import _backtest_cache_key


class TestBacktestCacheKey:
    def test_deterministic_hash(self):
        """相同参数生成相同缓存 key。"""
        key1 = _backtest_cache_key("AU", "1d", "long", [{"indicator": "sma5", "operator": ">", "indicator2": "sma20"}], [{"indicator": "sma5", "operator": "<", "indicator2": "sma20"}], 500)
        key2 = _backtest_cache_key("AU", "1d", "long", [{"indicator": "sma5", "operator": ">", "indicator2": "sma20"}], [{"indicator": "sma5", "operator": "<", "indicator2": "sma20"}], 500)
        assert key1 == key2
        assert key1.startswith("backtest:v2:AU:1d:long:")

    def test_different_params_different_key(self):
        """不同参数生成不同缓存 key。"""
        key1 = _backtest_cache_key("AU", "1d", "long", [{"indicator": "sma5", "operator": ">", "indicator2": "sma20"}], [{"indicator": "sma5", "operator": "<", "indicator2": "sma20"}], 500)
        key2 = _backtest_cache_key("AG", "1d", "long", [{"indicator": "sma5", "operator": ">", "indicator2": "sma20"}], [{"indicator": "sma5", "operator": "<", "indicator2": "sma20"}], 500)
        key3 = _backtest_cache_key("AU", "1d", "short", [{"indicator": "sma5", "operator": ">", "indicator2": "sma20"}], [{"indicator": "sma5", "operator": "<", "indicator2": "sma20"}], 500)
        assert key1 != key2
        assert key1 != key3

    def test_condition_order_invariant(self):
        """条件顺序不同但内容相同时，key 应该相同（因为 sort_keys=True）。"""
        key1 = _backtest_cache_key("AU", "1d", "long", [{"a": 1, "b": 2}], [{"c": 3}], 500)
        key2 = _backtest_cache_key("AU", "1d", "long", [{"b": 2, "a": 1}], [{"c": 3}], 500)
        assert key1 == key2
