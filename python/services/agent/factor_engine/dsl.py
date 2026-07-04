"""因子 DSL 安全求值器。

基于 Python ast 白名单实现，禁止任意代码执行。
支持面板数据字段（open/high/low/close/volume）和常用时间序列/横截面算子。
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PanelData:
    """因子面板数据。

    每个字段都是一个 DataFrame，index 为日期，columns 为品种代码。
    """

    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame

    def to_dict(self) -> dict[str, pd.DataFrame]:
        return {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


# 允许的 AST 节点类型
_ALLOWED_AST_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.BoolOp,
    ast.Call,
    ast.Name,
    ast.Constant,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.And,
    ast.Or,
)

# 允许直接访问的面板字段
_ALLOWED_FIELDS = {"open", "high", "low", "close", "volume"}


def _validate_ast(node: ast.AST) -> None:
    """递归校验 AST 节点是否全部在白名单内。"""
    if not isinstance(node, _ALLOWED_AST_NODES):
        raise ValueError(f"因子公式包含不允许的语法节点：{type(node).__name__}")
    for child in ast.iter_child_nodes(node):
        _validate_ast(child)


# ---------- 时间序列算子 ----------


def _ts_mean(df: pd.DataFrame, window: int) -> pd.DataFrame:
    return df.rolling(window=window, min_periods=1).mean()


def _ts_std(df: pd.DataFrame, window: int) -> pd.DataFrame:
    return df.rolling(window=window, min_periods=1).std()


def _ema(df: pd.DataFrame, span: int) -> pd.DataFrame:
    return df.ewm(span=span, adjust=False).mean()


def _ts_dema(df: pd.DataFrame, span: int) -> pd.DataFrame:
    ema = _ema(df, span)
    return 2.0 * ema - _ema(ema, span)


def _ts_sum(df: pd.DataFrame, window: int) -> pd.DataFrame:
    return df.rolling(window=window, min_periods=1).sum()


def _ts_median(df: pd.DataFrame, window: int) -> pd.DataFrame:
    return df.rolling(window=window, min_periods=1).median()


def _ts_max(df: pd.DataFrame, window: int) -> pd.DataFrame:
    return df.rolling(window=window, min_periods=1).max()


def _ts_min(df: pd.DataFrame, window: int) -> pd.DataFrame:
    return df.rolling(window=window, min_periods=1).min()


def _ts_midpoint(df: pd.DataFrame, window: int) -> pd.DataFrame:
    rolling = df.rolling(window=window, min_periods=1)
    return (rolling.max() + rolling.min()) / 2.0


def _ts_inverse_cv(df: pd.DataFrame, window: int) -> pd.DataFrame:
    rolling = df.rolling(window=window, min_periods=1)
    return rolling.mean() / rolling.std().replace(0, np.nan)


def _ts_maxmin(df: pd.DataFrame, window: int) -> pd.DataFrame:
    rolling = df.rolling(window=window, min_periods=1)
    min_value = rolling.min()
    return (df - min_value) / (rolling.max() - min_value).replace(0, np.nan)


def _ts_mean_return(df: pd.DataFrame, window: int) -> pd.DataFrame:
    one_period_return = np.sign(df) * (df - df.shift(1)) / df.abs().replace(0, np.nan)
    return one_period_return.rolling(window=window, min_periods=1).mean()


def _ts_skew(df: pd.DataFrame, window: int) -> pd.DataFrame:
    return df.rolling(window=window, min_periods=1).skew()


def _ts_kurt(df: pd.DataFrame, window: int) -> pd.DataFrame:
    return df.rolling(window=window, min_periods=1).kurt()


def _ts_delay(df: pd.DataFrame, window: int) -> pd.DataFrame:
    return df.shift(window)


def _ts_delta(df: pd.DataFrame, window: int) -> pd.DataFrame:
    return df - df.shift(window)


def _ts_rank(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """时间序列排名：当前值在过去 window 期中的分位排名（0~1）。"""
    return df.rolling(window=window, min_periods=1).apply(
        lambda x: (x.argsort().iloc[-1] + 1) / len(x) if len(x) > 0 else np.nan,
        raw=False,
    )


def _ts_zscore(df: pd.DataFrame, window: int) -> pd.DataFrame:
    mean = df.rolling(window=window, min_periods=1).mean()
    std = df.rolling(window=window, min_periods=1).std()
    return (df - mean) / std.replace(0, np.nan)


def _ts_corr(x: pd.DataFrame, y: pd.DataFrame, window: int) -> pd.DataFrame:
    """两个序列的滚动相关系数。"""
    return x.rolling(window=window, min_periods=1).corr(y)


def _ts_cov(x: pd.DataFrame, y: pd.DataFrame, window: int) -> pd.DataFrame:
    return x.rolling(window=window, min_periods=1).cov(y)


def _ts_regression_beta(x: pd.DataFrame, y: pd.DataFrame, window: int) -> pd.DataFrame:
    covariance = x.rolling(window=window, min_periods=1).cov(y)
    variance = y.rolling(window=window, min_periods=1).var()
    return covariance / variance.replace(0, np.nan)


# ---------- 横截面算子 ----------


def _rank(df: pd.DataFrame) -> pd.DataFrame:
    """横截面排名（0~1，最小为 0，最大为 1）。"""
    return df.rank(axis=1, pct=True)


def _zscore(df: pd.DataFrame) -> pd.DataFrame:
    """横截面 z-score。"""
    mean = df.mean(axis=1)
    std = df.std(axis=1)
    return df.sub(mean, axis=0).div(std.replace(0, np.nan), axis=0)


def _sign(df: pd.DataFrame) -> pd.DataFrame:
    return np.sign(df)


def _abs(df: pd.DataFrame) -> pd.DataFrame:
    return df.abs()


def _log(df: pd.DataFrame) -> pd.DataFrame:
    return np.log(df.replace(0, np.nan))


def _sqrt(df: pd.DataFrame) -> pd.DataFrame:
    return np.sqrt(df.clip(lower=0))


def _exp(df: pd.DataFrame) -> pd.DataFrame:
    return np.exp(df)


def _clip(df: pd.DataFrame, lower: float | None = None, upper: float | None = None) -> pd.DataFrame:
    return df.clip(lower=lower, upper=upper)


def _build_namespace(panel: PanelData) -> dict[str, Any]:
    """构建因子求值的安全命名空间。"""
    namespace: dict[str, Any] = panel.to_dict()
    functions: dict[str, Callable[..., Any]] = {
        # 时间序列
        "ema": _ema,
        "ts_dema": _ts_dema,
        "ts_mean": _ts_mean,
        "ts_std": _ts_std,
        "ts_sum": _ts_sum,
        "ts_median": _ts_median,
        "ts_max": _ts_max,
        "ts_min": _ts_min,
        "ts_midpoint": _ts_midpoint,
        "ts_inverse_cv": _ts_inverse_cv,
        "ts_maxmin": _ts_maxmin,
        "ts_mean_return": _ts_mean_return,
        "ts_skew": _ts_skew,
        "ts_kurt": _ts_kurt,
        "ts_delay": _ts_delay,
        "ts_delta": _ts_delta,
        "ts_rank": _ts_rank,
        "ts_zscore": _ts_zscore,
        "ts_corr": _ts_corr,
        "ts_cov": _ts_cov,
        "ts_regression_beta": _ts_regression_beta,
        # 横截面
        "rank": _rank,
        "zscore": _zscore,
        "sign": _sign,
        # 逐元素函数
        "abs": _abs,
        "log": _log,
        "sqrt": _sqrt,
        "exp": _exp,
        "clip": _clip,
    }
    namespace.update(functions)
    return namespace


def validate_factor_formula(formula: str) -> None:
    """校验因子公式是否安全。

    安全条件：
    1. 只能包含白名单 AST 节点。
    2. 所有 Name 节点必须是允许的面板字段或函数名。
    3. 不允许属性访问、导入、lambda 等。
    """
    if not formula or not formula.strip():
        raise ValueError("因子公式不能为空")

    try:
        tree = ast.parse(formula.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"因子公式语法错误：{exc}") from exc

    _validate_ast(tree)

    # 额外校验 Name 节点
    namespace = _build_namespace(
        PanelData(
            open=pd.DataFrame(),
            high=pd.DataFrame(),
            low=pd.DataFrame(),
            close=pd.DataFrame(),
            volume=pd.DataFrame(),
        )
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in namespace:
                raise ValueError(f"因子公式包含未定义的标识符：{node.id}")


def evaluate_factor(formula: str, panel: PanelData) -> pd.DataFrame:
    """安全地求值因子公式，返回因子值 DataFrame。

    Args:
        formula: 因子表达式字符串，例如 "close / ts_delay(close, 5) - 1"。
        panel: 面板数据。

    Returns:
        与 panel.close 形状相同的 DataFrame，表示每个品种在每个日期的因子值。
    """
    validate_factor_formula(formula)

    namespace = _build_namespace(panel)
    tree = ast.parse(formula.strip(), mode="eval")
    code = compile(tree, filename="<factor>", mode="eval")

    try:
        result = eval(code, {"__builtins__": {}}, namespace)  # noqa: S307
    except Exception as exc:
        raise ValueError(f"因子公式求值失败：{exc}") from exc

    if not isinstance(result, pd.DataFrame):
        raise ValueError(f"因子公式求值结果必须是 DataFrame，实际为 {type(result).__name__}")

    # 对齐 index/columns，确保返回形状一致
    result = result.reindex_like(panel.close)
    return result
