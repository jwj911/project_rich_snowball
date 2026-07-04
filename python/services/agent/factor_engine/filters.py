"""声明式过滤条件 DSL。

提供 FactorPipeline 用于在回测选股前按条件排除不符合要求的品种。
支持 val: 和 pct: 两种表达式前缀，以及 AND/OR 条件组合。

表达式语法：
    val:==X     值等于 X
    val:!=X     值不等于 X
    val:>X      值大于 X
    val:<X      值小于 X
    val:>=X     值大于等于 X
    val:<=X     值小于等于 X
    pct:>=X     在同日截面内的分位数 >= X（X 为 0~1 之间的小数）
    pct:<=X     在同日截面内的分位数 <= X

使用示例：
    conditions = [
        FilterCondition(field="close", expression="val:<100"),
        FilterCondition(field="is_suspended", expression="val:==0"),
    ]
    pipeline = FilterPipeline()
    filtered = pipeline.apply(df, conditions, date_col="trade_date")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_EXPR_PATTERN = re.compile(r"^(val|pct):(==|!=|>=|<=|>|<)(.+)$")

# val: 表达式不需要按日期分组计算，pct: 需要
_VAL_OPERATORS = frozenset({"==", "!=", ">", "<", ">=", "<="})
_PCT_OPERATORS = frozenset({">=", "<="})


@dataclass
class FilterCondition:
    """单个过滤条件。

    Attributes:
        field: 要过滤的 DataFrame 列名。
        params: 保留字段，用于因子参数传递（当前未使用，预留给外部因子求值后注入列的场景）。
        expression: 过滤表达式，如 "val:==0"、"pct:>=0.5"。
        is_and: True 表示与上一个条件做 AND，False 表示做 OR。
    """

    field: str
    params: Any = None
    expression: str = ""
    is_and: bool = True


@dataclass
class FilterResult:
    """过滤结果。

    Attributes:
        filtered: 过滤后的 DataFrame。
        mask: 每条记录是否保留的布尔序列。
        removed_count: 被过滤掉的行数。
        details: 每个条件的过滤统计。
    """

    filtered: pd.DataFrame
    mask: pd.Series
    removed_count: int
    details: list[dict[str, Any]] = field(default_factory=list)


def _parse_expression(expression: str) -> tuple[str, str, float]:
    """解析过滤表达式为 (类型, 操作符, 阈值)。

    Raises:
        ValueError: 表达式格式不合法。
    """
    expr = expression.strip()
    m = _EXPR_PATTERN.match(expr)
    if not m:
        raise ValueError(
            f"过滤表达式格式错误: {expr!r}，期望格式为 val:<op><value> 或 pct:<op><value>，例如 'val:==0'、'pct:>=0.5'"
        )
    op_type, operator, value_str = m.groups()
    try:
        value = float(value_str)
    except ValueError:
        raise ValueError(f"过滤表达式值无法解析为数字: {value_str!r}") from None
    return op_type, operator, value


def _eval_val_condition(series: pd.Series, operator: str, threshold: float) -> pd.Series:
    """对单个列求值 val: 条件，返回布尔序列。"""
    if operator == "==":
        return series == threshold
    if operator == "!=":
        return series != threshold
    if operator == ">":
        return series > threshold
    if operator == "<":
        return series < threshold
    if operator == ">=":
        return series >= threshold
    if operator == "<=":
        return series <= threshold
    raise ValueError(f"val: 不支持的操作符: {operator!r}")


def _eval_pct_condition(
    series: pd.Series,
    operator: str,
    threshold: float,
    group_keys: pd.Series,
) -> pd.Series:
    """按日期分组计算截面分位数条件，返回布尔序列。

    pct:>=X 表示保留分位数 >= X 的行（即排名靠前的）。
    pct:<=X 表示保留分位数 <= X 的行（即排名靠后的）。
    """
    if operator not in _PCT_OPERATORS:
        raise ValueError(f"pct: 只支持 >= 和 <= 操作符，不支持: {operator!r}")
    if not (0 <= threshold <= 1):
        raise ValueError(f"pct: 阈值必须在 0~1 之间，实际为 {threshold}")

    # 按日期分组计算截面分位排名（0~1，min_periods=1 确保单样本也能计算）
    rank_pct = series.groupby(group_keys).rank(pct=True)

    if operator == ">=":
        return rank_pct >= threshold
    return rank_pct <= threshold


def _safe_bool_mask(series: pd.Series) -> pd.Series:
    """将序列转为安全布尔掩码：NaN 视为 False。"""
    return series.fillna(False).astype(bool)


class FilterPipeline:
    """过滤流水线。

    按顺序对多个 FilterCondition 求值并组合布尔掩码，
    第一个条件总是开始一个新的掩码组，后续条件按 is_and 决定组合方式。
    """

    def apply(
        self,
        df: pd.DataFrame,
        conditions: list[FilterCondition],
        date_col: str = "trade_date",
    ) -> FilterResult:
        """应用过滤条件并返回过滤后的结果。

        Args:
            df: 待过滤的 DataFrame，每行为一条记录（品种 × 日期）。
            conditions: 过滤条件列表。
            date_col: 用于 pct: 表达式分组的日期列名。

        Returns:
            FilterResult，包含过滤后的 DataFrame 和统计信息。

        Raises:
            ValueError: 条件列表为空或某个条件引用了不存在的列。
        """
        if not conditions:
            raise ValueError("过滤条件列表不能为空")

        combined_mask: pd.Series | None = None
        logic_desc: list[str] = []
        details: list[dict[str, Any]] = []

        for _i, cond in enumerate(conditions):
            if cond.field not in df.columns:
                raise ValueError(f"过滤条件引用了不存在的列 {cond.field!r}，可用列: {sorted(df.columns.tolist())}")

            op_type, operator, threshold = _parse_expression(cond.expression)
            series = df[cond.field]

            if op_type == "val":
                raw_mask = _eval_val_condition(series, operator, threshold)
            elif op_type == "pct":
                if date_col not in df.columns:
                    raise ValueError(f"pct: 表达式需要日期分组列 {date_col!r}，但 DataFrame 中不存在该列")
                raw_mask = _eval_pct_condition(series, operator, threshold, df[date_col])
            else:
                raise ValueError(f"不支持的表达式类型: {op_type!r}")

            mask = _safe_bool_mask(raw_mask)
            removed = (~mask).sum()

            if combined_mask is None:
                combined_mask = mask
                logic_desc.append(f"{cond.field} {cond.expression}")
            elif cond.is_and:
                combined_mask = combined_mask & mask
                logic_desc.append(f"AND {cond.field} {cond.expression}")
            else:
                combined_mask = combined_mask | mask
                logic_desc.append(f"OR {cond.field} {cond.expression}")

            details.append(
                {
                    "field": cond.field,
                    "expression": cond.expression,
                    "is_and": cond.is_and,
                    "removed_by_this": int(removed),
                    "retained": int(mask.sum()),
                }
            )

        assert combined_mask is not None
        removed_count = int((~combined_mask).sum())
        logger.info(
            "FilterPipeline applied: %s → %d/%d rows removed (%.1f%%)",
            " ".join(logic_desc),
            removed_count,
            len(df),
            removed_count / len(df) * 100 if len(df) > 0 else 0,
        )

        return FilterResult(
            filtered=df[combined_mask].copy(),
            mask=combined_mask,
            removed_count=removed_count,
            details=details,
        )


def build_conditions_from_tuples(
    tuples: list[tuple[str, Any, str, bool]],
) -> list[FilterCondition]:
    """从元组列表构建 FilterCondition 列表。

    兼容凌烟阁风格的 filter_list 格式：
        [("近期停牌天数", 5, "val:==0", True), ("收盘价", "", "val:<20", True)]

    Args:
        tuples: 每个元组为 (field, params, expression, is_and)。

    Returns:
        FilterCondition 列表。
    """
    return [FilterCondition(field=f, params=p, expression=e, is_and=a) for f, p, e, a in tuples]
