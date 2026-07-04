"""因子注册表。

提供因子按类别的统一注册、发现、元数据查询能力。
与 factor_definitions 数据库表互补：数据库存持久化元数据和统计指标，
注册表提供运行时的因子类别组织和发现。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from services.agent.factor_engine.factor_meta import FactorMeta

logger = logging.getLogger(__name__)

# 预设因子类别及其含义
_BUILTIN_CATEGORIES: dict[str, str] = {
    "估值": "衡量股票/品种的相对便宜程度，如 PE、PB、EP、企业价值倍数等",
    "成长": "衡量公司盈利/收入增长速度和趋势，如 ROE、净利润同比增速等",
    "波动": "衡量价格波动程度，如振幅、标准差等",
    "短期反转": "衡量近期价格反转倾向，如短期收益率反转指标",
    "长期反转": "衡量中长期趋势延续或反转倾向",
    "规模": "衡量市值、成交额等规模特征",
    "动量": "衡量价格动量强度和方向",
    "价量": "衡量价格与成交量之间的关系",
    "流动性": "衡量品种的流动性特征，如换手率、买卖价差等",
    "其他": "尚未归类的因子",
}


class FactorRegistry:
    """因子注册中心。

    支持：
    - 按名称注册因子元数据
    - 按类别枚举因子
    - 从数据库批量加载因子定义
    - 搜索（按名称/描述模糊匹配）

    使用方式：
        reg = FactorRegistry()
        reg.register(FactorMeta(name="EP", category="估值", description="市盈率倒数"))
        reg.register(FactorMeta(name="ROE", category="成长"))
        valuation_factors = reg.list_by_category("估值")
    """

    def __init__(self) -> None:
        self._factors: dict[str, FactorMeta] = {}
        self._by_category: dict[str, list[str]] = defaultdict(list)

    # ---- 注册 / 注销 ----

    def register(self, meta: FactorMeta) -> None:
        """注册一个因子。同名因子会覆盖旧定义。"""
        # 从旧分类中移除
        if meta.name in self._factors:
            old_cat = self._factors[meta.name].category
            if old_cat and meta.name in self._by_category.get(old_cat, []):
                self._by_category[old_cat].remove(meta.name)

        self._factors[meta.name] = meta
        cat = meta.category or "其他"
        if meta.name not in self._by_category[cat]:
            self._by_category[cat].append(meta.name)

    def unregister(self, name: str) -> bool:
        """注销一个因子。返回 True 表示成功。"""
        if name not in self._factors:
            return False
        meta = self._factors.pop(name)
        cat = meta.category or "其他"
        if name in self._by_category.get(cat, []):
            self._by_category[cat].remove(name)
        return True

    # ---- 查询 ----

    def get(self, name: str) -> FactorMeta | None:
        """按名获取因子元数据。"""
        return self._factors.get(name)

    def list_all(self) -> list[FactorMeta]:
        """列出所有已注册因子。"""
        return list(self._factors.values())

    def list_by_category(self, category: str) -> list[FactorMeta]:
        """列出某类别下的所有因子。"""
        names = self._by_category.get(category, [])
        return [self._factors[n] for n in names if n in self._factors]

    def list_categories(self) -> list[dict[str, Any]]:
        """列出所有类别及其因子计数和描述。"""
        return [
            {
                "name": cat,
                "description": _BUILTIN_CATEGORIES.get(cat, ""),
                "count": len(factors),
            }
            for cat, factors in self._by_category.items()
        ]

    def search(self, query: str) -> list[FactorMeta]:
        """模糊搜索因子：匹配名称或描述中包含查询字符串的因子。"""
        q = query.lower()
        results: list[FactorMeta] = []
        for meta in self._factors.values():
            if q in meta.name.lower() or (meta.description and q in meta.description.lower()):
                results.append(meta)
        return results

    # ---- 批量加载 ----

    def load_from_db(self, db_session: Any) -> int:
        """从 factor_definitions 表批量加载因子定义到注册表。

        每个数据库行作为一个 FactorMeta 注册。已存在的同名因子会被覆盖。
        """
        from models import FactorDefinitionDB

        rows = (
            db_session.query(FactorDefinitionDB)
            .filter(
                FactorDefinitionDB.is_active.is_(True)  # noqa: E712
            )
            .all()
        )

        count = 0
        for row in rows:
            # 从 package_id 推断类别
            category = _infer_category(row.package_id or "", row.name or "")
            meta = FactorMeta(
                name=row.factor_id or row.name,
                category=category,
                description=_build_description(row),
                params_schema=None,
                requires_fin_data=None,
                requires_ov_data=None,
                usage_example=row.source_expression,
            )
            self.register(meta)
            count += 1

        logger.info("从数据库加载了 %d 个因子定义", count)
        return count

    @property
    def size(self) -> int:
        return len(self._factors)

    def clear(self) -> None:
        """清空所有注册。"""
        self._factors.clear()
        self._by_category.clear()


def _infer_category(package_id: str, name: str) -> str:
    """从 package_id 和名称推断因子类别。"""
    pid = package_id.lower()
    name_lower = name.lower()
    # 按优先级匹配
    for keyword, cat in [
        ("估值", "估值"),
        ("valuation", "估值"),
        ("成长", "成长"),
        ("growth", "成长"),
        ("波动", "波动"),
        ("volatility", "波动"),
        ("动量", "动量"),
        ("momentum", "动量"),
        ("反转", "短期反转"),
        ("reversal", "短期反转"),
        ("规模", "规模"),
        ("size", "规模"),
        ("流动性", "流动性"),
        ("liquidity", "流动性"),
        ("价量", "价量"),
    ]:
        if keyword in pid or keyword in name_lower:
            return cat
    return "其他"


def _build_description(row: Any) -> str:
    """从数据库行构建因子描述文本。"""
    parts: list[str] = []
    if hasattr(row, "source") and row.source:
        parts.append(f"来源: {row.source}")
    if hasattr(row, "rankicir") and row.rankicir is not None:
        parts.append(f"Rank ICIR: {float(row.rankicir):.4f}")
    if hasattr(row, "coverage") and row.coverage is not None:
        parts.append(f"覆盖率: {float(row.coverage):.1%}")
    return "，".join(parts) if parts else ""
