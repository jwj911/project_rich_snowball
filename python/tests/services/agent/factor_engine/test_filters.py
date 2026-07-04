"""声明式过滤条件 DSL 测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.agent.factor_engine.filters import (
    FilterCondition,
    FilterPipeline,
    FilterResult,
    build_conditions_from_tuples,
    _parse_expression,
    _eval_val_condition,
    _eval_pct_condition,
)


# ------------------------------------------------------------------
# 表达式解析
# ------------------------------------------------------------------


class TestParseExpression:
    def test_val_eq(self):
        op_type, operator, value = _parse_expression("val:==0")
        assert op_type == "val"
        assert operator == "=="
        assert value == 0.0

    def test_val_gt(self):
        op_type, operator, value = _parse_expression("val:>20")
        assert op_type == "val"
        assert operator == ">"
        assert value == 20.0

    def test_val_lt(self):
        op_type, operator, value = _parse_expression("val:<100")
        assert op_type == "val"
        assert operator == "<"
        assert value == 100.0

    def test_val_neq(self):
        op_type, operator, value = _parse_expression("val:!=1")
        assert op_type == "val"
        assert operator == "!="
        assert value == 1.0

    def test_val_ge(self):
        op_type, operator, value = _parse_expression("val:>=0.5")
        assert op_type == "val"
        assert operator == ">="
        assert value == 0.5

    def test_val_le(self):
        op_type, operator, value = _parse_expression("val:<=0.8")
        assert op_type == "val"
        assert operator == "<="
        assert value == 0.8

    def test_pct_ge(self):
        op_type, operator, value = _parse_expression("pct:>=0.5")
        assert op_type == "pct"
        assert operator == ">="
        assert value == 0.5

    def test_pct_le(self):
        op_type, operator, value = _parse_expression("pct:<=0.3")
        assert op_type == "pct"
        assert operator == "<="
        assert value == 0.3

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="格式错误"):
            _parse_expression("invalid")

    def test_invalid_operator(self):
        with pytest.raises(ValueError):
            _parse_expression("val:>>5")

    def test_negative_value(self):
        op_type, operator, value = _parse_expression("val:< -5")
        assert op_type == "val"
        assert operator == "<"
        assert value == -5.0


# ------------------------------------------------------------------
# 条件求值
# ------------------------------------------------------------------


class TestEvalValCondition:
    def test_eq_true(self):
        s = pd.Series([0, 1, 0, 2])
        result = _eval_val_condition(s, "==", 0)
        assert result.tolist() == [True, False, True, False]

    def test_neq(self):
        s = pd.Series([0, 1, 0, 2])
        result = _eval_val_condition(s, "!=", 0)
        assert result.tolist() == [False, True, False, True]

    def test_gt(self):
        s = pd.Series([10, 20, 30, 40])
        result = _eval_val_condition(s, ">", 25)
        assert result.tolist() == [False, False, True, True]

    def test_lt(self):
        s = pd.Series([10, 20, 30, 40])
        result = _eval_val_condition(s, "<", 25)
        assert result.tolist() == [True, True, False, False]

    def test_ge(self):
        s = pd.Series([10, 20, 30, 40])
        result = _eval_val_condition(s, ">=", 20)
        assert result.tolist() == [False, True, True, True]

    def test_le(self):
        s = pd.Series([10, 20, 30, 40])
        result = _eval_val_condition(s, "<=", 20)
        assert result.tolist() == [True, True, False, False]


class TestEvalPctCondition:
    def test_pct_ge(self):
        s = pd.Series([1, 2, 3, 4, 5])
        group = pd.Series(["A"] * 5)
        result = _eval_pct_condition(s, ">=", 0.5, group)
        # 5 个值，pct >= 0.5 保留排名靠前的 3 个
        assert result.sum() >= 2  # 至少保留后半部分

    def test_pct_le(self):
        s = pd.Series([1, 2, 3, 4, 5])
        group = pd.Series(["A"] * 5)
        result = _eval_pct_condition(s, "<=", 0.5, group)
        # pct <= 0.5 保留排名靠后的 3 个
        assert result.sum() >= 2

    def test_pct_invalid_threshold(self):
        s = pd.Series([1, 2, 3])
        group = pd.Series(["A"] * 3)
        with pytest.raises(ValueError, match="阈值"):
            _eval_pct_condition(s, ">=", 1.5, group)

    def test_pct_unsupported_operator(self):
        s = pd.Series([1, 2, 3])
        group = pd.Series(["A"] * 3)
        with pytest.raises(ValueError, match="pct"):
            _eval_pct_condition(s, "==", 0.5, group)


# ------------------------------------------------------------------
# FilterPipeline
# ------------------------------------------------------------------


@pytest.fixture
def sample_df():
    """构造 6 行 × 2 天 × 3 品种的测试数据。"""
    dates = ["2026-01-05", "2026-01-05", "2026-01-05", "2026-01-06", "2026-01-06", "2026-01-06"]
    return pd.DataFrame({
        "trade_date": dates,
        "symbol": ["A", "B", "C", "A", "B", "C"],
        "close": [10, 50, 100, 12, 48, 95],
        "is_suspended": [0, 1, 0, 0, 0, 0],
        "volume": [100, 200, 300, 150, 250, 350],
    })


class TestFilterPipeline:
    def test_single_val_eq(self, sample_df):
        pipeline = FilterPipeline()
        conds = [FilterCondition(field="is_suspended", expression="val:==0")]
        result = pipeline.apply(sample_df, conds, date_col="trade_date")

        assert len(result.filtered) == 5  # B on 01-05 has is_suspended=1
        assert result.removed_count == 1
        assert result.details[0]["removed_by_this"] == 1
        assert result.details[0]["retained"] == 5
        assert (result.filtered["is_suspended"] == 0).all()

    def test_single_val_lt(self, sample_df):
        pipeline = FilterPipeline()
        conds = [FilterCondition(field="close", expression="val:<100")]
        result = pipeline.apply(sample_df, conds, date_col="trade_date")

        # close >= 100: B on 01-06 is 95 → only C on 01-05 (100) is excluded
        # Actually close values: 10,50,100,12,48,95 → only C on 01-05 (100) fails val:<100
        assert len(result.filtered) == 5
        assert result.removed_count == 1

    def test_two_and_conditions(self, sample_df):
        pipeline = FilterPipeline()
        conds = [
            FilterCondition(field="is_suspended", expression="val:==0", is_and=True),
            FilterCondition(field="close", expression="val:<100", is_and=True),
        ]
        result = pipeline.apply(sample_df, conds, date_col="trade_date")

        # 排除 is_suspended=1 的 + close>=100 的 → 原始排除 1+1=2
        assert len(result.filtered) == 4
        assert result.removed_count == 2

    def test_or_condition(self, sample_df):
        pipeline = FilterPipeline()
        conds = [
            FilterCondition(field="is_suspended", expression="val:==0", is_and=True),
            FilterCondition(field="close", expression="val:>20", is_and=False),  # OR
        ]
        result = pipeline.apply(sample_df, conds, date_col="trade_date")

        # AND: is_suspended==0 → excludes B-01-05
        # OR: close>20 → adds back B-01-05 (close=50) but only if it wasn't already excluded
        # Actually: combined = mask1 | mask2 → all rows where (suspended==0) OR (close>20)
        # All rows satisfy at least one of these
        assert len(result.filtered) == 6
        assert result.removed_count == 0

    def test_pct_ge_condition(self, sample_df):
        pipeline = FilterPipeline()
        conds = [FilterCondition(field="close", expression="pct:>=0.5")]
        result = pipeline.apply(sample_df, conds, date_col="trade_date")

        # 每天 3 个品种，pct>=0.5 至少保留 1 个
        assert len(result.filtered) >= 2
        for detail in result.details:
            assert detail["field"] == "close"

    def test_empty_conditions_raises(self, sample_df):
        pipeline = FilterPipeline()
        with pytest.raises(ValueError, match="不能为空"):
            pipeline.apply(sample_df, [], date_col="trade_date")

    def test_missing_column_raises(self, sample_df):
        pipeline = FilterPipeline()
        conds = [FilterCondition(field="nonexistent", expression="val:==0")]
        with pytest.raises(ValueError, match="不存在的列"):
            pipeline.apply(sample_df, conds, date_col="trade_date")

    def test_pct_without_date_col_raises(self, sample_df):
        pipeline = FilterPipeline()
        conds = [FilterCondition(field="close", expression="pct:>=0.5")]
        df_no_date = sample_df.drop(columns=["trade_date"])
        with pytest.raises(ValueError, match="日期分组列"):
            pipeline.apply(df_no_date, conds, date_col="trade_date")

    def test_nan_in_column_becomes_false(self):
        pipeline = FilterPipeline()
        df = pd.DataFrame({
            "trade_date": ["2026-01-05", "2026-01-05"],
            "val": [np.nan, 1.0],
        })
        conds = [FilterCondition(field="val", expression="val:>0")]
        result = pipeline.apply(df, conds, date_col="trade_date")
        # NaN row is excluded
        assert len(result.filtered) == 1
        assert result.filtered["val"].iloc[0] == 1.0

    def test_result_types(self, sample_df):
        pipeline = FilterPipeline()
        conds = [FilterCondition(field="close", expression="val:<100")]
        result = pipeline.apply(sample_df, conds, date_col="trade_date")

        assert isinstance(result, FilterResult)
        assert isinstance(result.filtered, pd.DataFrame)
        assert isinstance(result.mask, pd.Series)
        assert isinstance(result.removed_count, int)
        assert isinstance(result.details, list)


# ------------------------------------------------------------------
# build_conditions_from_tuples
# ------------------------------------------------------------------


class TestBuildConditionsFromTuples:
    def test_standard_format(self):
        tuples = [
            ("近期停牌天数", 5, "val:==0", True),
            ("收盘价", "", "val:<20", True),
        ]
        conds = build_conditions_from_tuples(tuples)

        assert len(conds) == 2
        assert conds[0].field == "近期停牌天数"
        assert conds[0].params == 5
        assert conds[0].expression == "val:==0"
        assert conds[0].is_and is True
        assert conds[1].field == "收盘价"
        assert conds[1].params == ""
        assert conds[1].expression == "val:<20"

    def test_empty_list(self):
        conds = build_conditions_from_tuples([])
        assert conds == []
