"""因子注册表测试。"""

from __future__ import annotations

import pytest

from services.agent.factor_engine.factor_meta import FactorMeta
from services.agent.factor_engine.registry import FactorRegistry


class TestFactorRegistry:
    def test_register_and_get(self):
        reg = FactorRegistry()
        meta = FactorMeta(name="EP", category="估值", description="市盈率倒数")
        reg.register(meta)
        assert reg.get("EP") is meta
        assert reg.get("EP").category == "估值"
        assert reg.size == 1

    def test_register_overwrite(self):
        reg = FactorRegistry()
        reg.register(FactorMeta(name="X", category="估值"))
        reg.register(FactorMeta(name="X", category="成长"))
        assert reg.get("X").category == "成长"
        assert reg.size == 1

    def test_unregister(self):
        reg = FactorRegistry()
        reg.register(FactorMeta(name="EP", category="估值"))
        assert reg.unregister("EP") is True
        assert reg.get("EP") is None
        assert reg.size == 0
        assert reg.unregister("EP") is False

    def test_list_all(self):
        reg = FactorRegistry()
        reg.register(FactorMeta(name="a", category="估值"))
        reg.register(FactorMeta(name="b", category="成长"))
        all_factors = reg.list_all()
        assert len(all_factors) == 2

    def test_list_by_category(self):
        reg = FactorRegistry()
        reg.register(FactorMeta(name="EP", category="估值"))
        reg.register(FactorMeta(name="SP", category="估值"))
        reg.register(FactorMeta(name="ROE", category="成长"))
        valuation = reg.list_by_category("估值")
        assert len(valuation) == 2
        assert {f.name for f in valuation} == {"EP", "SP"}

    def test_list_by_category_empty(self):
        reg = FactorRegistry()
        assert reg.list_by_category("不存在的类别") == []

    def test_list_categories(self):
        reg = FactorRegistry()
        reg.register(FactorMeta(name="EP", category="估值"))
        reg.register(FactorMeta(name="ROE", category="成长"))
        cats = reg.list_categories()
        assert len(cats) == 2
        names = {c["name"] for c in cats}
        assert "估值" in names
        assert "成长" in names
        assert cats[0]["count"] > 0

    def test_search_by_name(self):
        reg = FactorRegistry()
        reg.register(FactorMeta(name="EP", category="估值"))
        reg.register(FactorMeta(name="ROE", category="成长"))
        reg.register(FactorMeta(name="SP", category="估值"))
        results = reg.search("EP")
        assert len(results) >= 1
        assert results[0].name == "EP"

    def test_search_by_description(self):
        reg = FactorRegistry()
        reg.register(FactorMeta(name="EP", category="估值", description="市盈率倒数因子"))
        reg.register(FactorMeta(name="ROE", category="成长"))
        results = reg.search("市盈率")
        assert len(results) == 1
        assert results[0].name == "EP"

    def test_search_no_match(self):
        reg = FactorRegistry()
        reg.register(FactorMeta(name="EP", category="估值"))
        assert reg.search("xyz不存在的") == []

    def test_clear(self):
        reg = FactorRegistry()
        reg.register(FactorMeta(name="EP", category="估值"))
        reg.clear()
        assert reg.size == 0
        assert reg.list_all() == []
        assert reg.list_categories() == []

    def test_category_reassignment_on_reregister(self):
        reg = FactorRegistry()
        reg.register(FactorMeta(name="EP", category="估值"))
        reg.register(FactorMeta(name="EP", category="成长"))
        assert "EP" not in reg.list_by_category("估值")
        growth = reg.list_by_category("成长")
        assert any(f.name == "EP" for f in growth)

    def test_default_category(self):
        reg = FactorRegistry()
        reg.register(FactorMeta(name="X", category=""))
        assert reg.get("X").category == ""
        others = reg.list_by_category("其他")
        assert any(f.name == "X" for f in others)


class TestFactorMeta:
    def test_to_dict(self):
        meta = FactorMeta(
            name="EP",
            category="估值",
            description="市盈率倒数",
            params_schema=[{"name": "period", "type": "str", "default": "ttm"}],
            requires_fin_data=["R_np@xbx_ttm"],
        )
        d = meta.to_dict()
        assert d["name"] == "EP"
        assert d["category"] == "估值"
        assert len(d["params_schema"]) == 1
        assert d["requires_fin_data"] == ["R_np@xbx_ttm"]
        assert d["requires_ov_data"] == []

    def test_minimal_to_dict(self):
        meta = FactorMeta(name="simple")
        d = meta.to_dict()
        assert d["name"] == "simple"
        assert d["category"] == ""
        assert d["params_schema"] == []
