"""因子元数据。

轻量数据类，用于在注册表和计算函数之间传递因子定义。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FactorMeta:
    """单个因子的元数据。

    Attributes:
        name: 因子名，如 "EP"、"G161"。
        category: 类别标签，如 "估值"、"成长"、"波动"、"短期反转"、"长期反转"、"规模"。
        description: 因子含义的文字说明。
        params_schema: 参数 schema 列表，每条为 {"name": str, "type": str, "default": Any}。
        requires_fin_data: 需要的财务数据列名列表。
        requires_ov_data: 需要的其他数据列名列表。
        docs_url: 相关文档链接（可选）。
        usage_example: 配置示例（可选）。
    """

    name: str
    category: str = ""
    description: str = ""
    params_schema: list[dict[str, Any]] | None = None
    requires_fin_data: list[str] | None = None
    requires_ov_data: list[str] | None = None
    docs_url: str | None = None
    usage_example: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "params_schema": self.params_schema or [],
            "requires_fin_data": self.requires_fin_data or [],
            "requires_ov_data": self.requires_ov_data or [],
            "docs_url": self.docs_url,
            "usage_example": self.usage_example,
        }
