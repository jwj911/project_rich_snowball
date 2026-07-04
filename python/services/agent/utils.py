"""Agent 通用工具函数。

提供品种别名解析、参数提取等被多个 Agent 复用的工具。
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from models import VarietyDB

logger = logging.getLogger(__name__)

# 常见品种中文别名 -> 品种代码。
# 该表用于补充数据库中暂时没有的别名，或作为快速匹配兜底。
_BUILTIN_NAME_MAP: dict[str, str] = {
    "螺纹": "RB",
    "螺纹钢": "RB",
    "热卷": "HC",
    "铁矿石": "I",
    "焦煤": "JM",
    "焦炭": "J",
    "动力煤": "ZC",
    "黄金": "AU",
    "白银": "AG",
    "铜": "CU",
    "铝": "AL",
    "锌": "ZN",
    "铅": "PB",
    "镍": "NI",
    "锡": "SN",
    "原油": "SC",
    "沥青": "BU",
    "燃油": "FU",
    "液化气": "PG",
    "橡胶": "RU",
    "20号胶": "NR",
    "纸浆": "SP",
    "棉花": "CF",
    "白糖": "SR",
    "豆粕": "M",
    "菜粕": "RM",
    "豆油": "Y",
    "棕榈油": "P",
    "菜籽油": "OI",
    "玉米": "C",
    "淀粉": "CS",
    "鸡蛋": "JD",
    "生猪": "LH",
    "苹果": "AP",
    "红枣": "CJ",
    "花生": "PK",
    "纯碱": "SA",
    "玻璃": "FG",
    "甲醇": "MA",
    "尿素": "UR",
    "乙二醇": "EG",
    "PTA": "TA",
    "PP": "PP",
    "PVC": "V",
    "塑料": "L",
    "苯乙烯": "EB",
    "短纤": "PF",
    "镍": "NI",
    "不锈钢": "SS",
    "锰硅": "SM",
    "硅铁": "SF",
    "线材": "WR",
    "纤板": "FB",
    "胶板": "BB",
    "粳稻": "JR",
    "晚稻": "LR",
    "早稻": "RI",
    "强麦": "WH",
    "普麦": "PM",
    "苹果": "AP",
    "国债": "T",
    "十年国债": "T",
    "五年国债": "TF",
    "二年国债": "TS",
}


@lru_cache(maxsize=1)
def _load_variety_aliases(db: Session) -> dict[str, str]:
    """从数据库加载品种别名映射。

    以 name 和 symbol 作为 key，分别映射到 symbol。
    结果被 lru_cache 缓存；如需刷新可调用 refresh_variety_alias_cache。
    """
    aliases: dict[str, str] = {}
    try:
        varieties = db.query(VarietyDB).filter(VarietyDB.is_active == True).all()  # noqa: E712
        for v in varieties:
            aliases[v.symbol.upper()] = v.symbol.upper()
            if v.name:
                aliases[v.name.strip()] = v.symbol.upper()
    except Exception:
        logger.exception("Failed to load variety aliases from DB")
    return aliases


def refresh_variety_alias_cache() -> None:
    """清空品种别名缓存，下次调用时重新从数据库加载。"""
    _load_variety_aliases.cache_clear()


def resolve_symbol(db: Session, query: str) -> str | None:
    """从用户查询中解析品种代码。

    解析优先级：
    1. 正则匹配 1~2 位大写字母（如 RB、AU、I）。
    2. 数据库中的品种名称 / 代码。
    3. 内置常见中文别名表兜底。

    Args:
        db: 数据库会话。
        query: 用户原始查询。

    Returns:
        品种代码（大写）或 None。
    """
    if not query:
        return None

    query = query.strip()

    # 1. 直接匹配大写字母代码（支持 1~2 位，避免匹配过长的无意义大写串）
    symbols = re.findall(r"\b([A-Z]{1,2})\b", query.upper())
    if symbols:
        return symbols[0]

    # 2. 加载数据库别名（含内置兜底）
    db_aliases = _load_variety_aliases(db)
    all_aliases = {**_BUILTIN_NAME_MAP, **db_aliases}

    # 优先匹配更长的名称，避免「螺纹钢」被「螺纹」覆盖
    sorted_names = sorted(all_aliases.keys(), key=len, reverse=True)
    for name in sorted_names:
        if name in query:
            return all_aliases[name].upper()

    return None


def extract_direction(query: str) -> str | None:
    """从查询中提取交易方向。"""
    if any(w in query for w in ["做多", "买入", "看涨", "多单", "多"]):
        return "long"
    if any(w in query for w in ["做空", "卖出", "看跌", "空单", "空"]):
        return "short"
    return None


def extract_price(query: str) -> float | None:
    """从查询中提取价格数字。

    优先匹配「xxx 元/点/价格」格式，否则返回最大数字。
    """
    prices = re.findall(r"(\d+\.?\d*)\s*(?:元|点|价格|price)", query)
    if prices:
        return float(prices[0])
    numbers = re.findall(r"\b(\d+\.\d+|\d+)\b", query)
    if numbers:
        return max(float(n) for n in numbers)
    return None
