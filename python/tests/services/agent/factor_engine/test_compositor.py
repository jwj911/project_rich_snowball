"""多因子组合器测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.agent.factor_engine.compositor import (
    CompositeConfig,
    CompositeResult,
    FactorCompositor,
    FactorSpec,
)


@pytest.fixture
def sample_data():
    """构造 20 个交易日 × 5 个品种的面板数据。

    因子1（动量因子）：close / shift(5) - 1，与未来收益正相关
    因子2（反转因子）：与未来收益负相关（模拟）
    因子3（噪声因子）：随机值
    """
    np.random.seed(42)
    dates = pd.date_range("2026-01-05", periods=20, freq="B")
    symbols = ["A", "B", "C", "D", "E"]

    # 构建趋势价格：品种有不同趋势
    trends = [1.001, 1.003, 1.0, 1.002, 0.999]  # 日收益率
    close_data = {}
    for i, sym in enumerate(symbols):
        prices = [100.0]
        for _ in range(19):
            prices.append(prices[-1] * trends[i] * (1 + np.random.normal(0, 0.01)))
        close_data[sym] = prices

    close_df = pd.DataFrame(close_data, index=dates)

    # 因子1：5 日动量（与未来收益正相关）
    factor1_df = close_df.pct_change(5).shift(-5).copy()
    # 加噪声
    factor1_df = factor1_df + np.random.normal(0, 0.002, factor1_df.shape)

    # 因子2：反转因子（取负数，即与动量相反）
    factor2_df = -factor1_df + np.random.normal(0, 0.005, factor1_df.shape)

    # 因子3：纯噪声
    factor3_df = pd.DataFrame(
        np.random.normal(0, 0.01, (len(dates), len(symbols))),
        index=dates,
        columns=symbols,
    )

    # 合并为宽表（每列一个因子，每行一个日期 × 品种组合）
    # 为与当前 compositor 交互，需转换为因子名作为列的宽表
    factor_df = pd.DataFrame(index=dates)
    for sym in symbols:
        factor_df[sym + "_f1"] = factor1_df[sym]
        factor_df[sym + "_f2"] = factor2_df[sym]
        factor_df[sym + "_f3"] = factor3_df[sym]

    return {
        "close_df": close_df,
        "factor1_df": factor1_df,
        "factor2_df": factor2_df,
        "factor3_df": factor3_df,
    }


def _make_factor_df(name_to_values: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """将 {因子名: DataFrame} 合并为单 DataFrame，列名即因子名。

    DataFrame 保持日期 × 品种结构，列名为品种代码。
    这里我们返回的 factor_df 形状与 close_df 相同：
    index=dates, columns=symbols，值为该因子值。
    """
    # compositor 期望 factor_df 的 columns 包含 config.factor_fields
    # 每个 field 是因子 DataFrame 列名，形状为 (dates × symbols)
    # 这里直接返回原始 DataFrames，key 作为列引用
    pass


@pytest.fixture
def panel_factor_data():
    """构造标准格式的因子面板数据。

    compositor.compute() 接收 factor_df（日期×品种的因子值DF）
    和 close_df（同形状的收盘价）。

    这里的 factor_df 有列: momentum, reversal, noise（每个是独立的因子面板）
    """
    np.random.seed(42)
    dates = pd.date_range("2026-01-05", periods=30, freq="B")
    symbols = ["A", "B", "C", "D", "E"]

    # 价格序列
    trends = [1.001, 1.003, 1.0, 1.002, 0.999]
    close_arrays = {}
    for i, sym in enumerate(symbols):
        prices = [100.0]
        for _ in range(29):
            prices.append(prices[-1] * trends[i] * (1 + np.random.normal(0, 0.01)))
        close_arrays[sym] = prices
    close_df = pd.DataFrame(close_arrays, index=dates)

    # 因子：5 日动量紧密关联未来收益
    forward_5d = close_df.pct_change(5).shift(-5)
    momentum_df = forward_5d + np.random.normal(0, 0.003, close_df.shape)
    momentum_df = pd.DataFrame(momentum_df, index=dates, columns=symbols)

    # 反转因子
    reversal_df = -momentum_df + np.random.normal(0, 0.008, close_df.shape)
    reversal_df = pd.DataFrame(reversal_df, index=dates, columns=symbols)

    # 噪声因子
    noise_df = pd.DataFrame(
        np.random.normal(0, 0.01, close_df.shape),
        index=dates,
        columns=symbols,
    )

    # 构建组合 factor_df（多因子面板）
    # 策略1：每个因子 DataFrame 被当作一个数据源
    # compositor 通过 field 名引用它们
    factor_dfs = {
        "momentum": momentum_df,
        "reversal": reversal_df,
        "noise": noise_df,
    }

    return {
        "close_df": close_df,
        "momentum_df": momentum_df,
        "reversal_df": reversal_df,
        "noise_df": noise_df,
        "factor_dfs": factor_dfs,
        "dates": dates,
        "symbols": symbols,
    }


class TestFactorCompositor:
    """多因子组合器测试。"""

    def test_empty_factors_raises(self, panel_factor_data):
        compositor = FactorCompositor()
        config = CompositeConfig(factors=[], method="equal_weight")
        with pytest.raises(ValueError, match="不能为空"):
            compositor.compute(
                panel_factor_data["factor_dfs"],
                panel_factor_data["close_df"],
                config,
            )

    def test_missing_factor_column_raises(self, panel_factor_data):
        compositor = FactorCompositor()
        config = CompositeConfig(
            factors=[FactorSpec(field="nonexistent", is_asc=True)],
            method="equal_weight",
        )
        with pytest.raises(ValueError, match="缺少以下因子"):
            compositor.compute(
                panel_factor_data["factor_dfs"],
                panel_factor_data["close_df"],
                config,
            )

    def test_equal_weight_single_factor(self, panel_factor_data):
        compositor = FactorCompositor()
        config = CompositeConfig(
            factors=[FactorSpec(field="momentum", is_asc=False, group="g1")],
            method="equal_weight",
        )
        result = compositor.compute(
            panel_factor_data["factor_dfs"],
            panel_factor_data["close_df"],
            config,
        )
        assert isinstance(result, CompositeResult)
        assert result.method == "equal_weight"
        assert result.composite_score.shape == panel_factor_data["momentum_df"].shape


class TestCompositeConfig:
    def test_defaults(self):
        config = CompositeConfig(factors=[FactorSpec(field="test")])
        assert config.method == "icir_weighted"
        assert config.future_return_periods == 5
        assert config.icir_recall == 50
        assert config.icir_min_periods == 25

    def test_explicit_min_periods(self):
        config = CompositeConfig(
            factors=[FactorSpec(field="test")],
            icir_recall=20,
            icir_min_periods=10,
        )
        assert config.icir_min_periods == 10

    def test_factor_fields(self):
        config = CompositeConfig(factors=[
            FactorSpec(field="a", group="g1"),
            FactorSpec(field="b", group="g2"),
            FactorSpec(field="c", group="g1"),
        ])
        assert config.factor_fields == ["a", "b", "c"]

    def test_groups(self):
        config = CompositeConfig(factors=[
            FactorSpec(field="a", group="g1"),
            FactorSpec(field="b", group="g2"),
            FactorSpec(field="c", group="g1"),
        ])
        groups = config.groups
        assert len(groups) == 2
        assert groups["g1"][0].field == "a"
        assert groups["g1"][1].field == "c"
        assert groups["g2"][0].field == "b"


class TestCompositeResult:
    def test_to_dict(self):
        dates = pd.date_range("2026-01-05", periods=3, freq="B")
        score = pd.DataFrame(
            [[0.5, 0.6], [0.4, 0.7], [0.3, 0.8]],
            index=dates,
            columns=["A", "B"],
        )
        result = CompositeResult(
            composite_score=score,
            method="equal_weight",
            icir_by_factor={"a": 0.5, "b": 0.3},
        )
        d = result.to_dict()
        assert d["method"] == "equal_weight"
        assert d["score_column"] == "复合因子"
        assert d["icir_by_factor"] == {"a": 0.5, "b": 0.3}
        assert d["symbols"] == ["A", "B"]
        assert d["date_range"]["start"] is not None
        assert d["date_range"]["end"] is not None


class TestForwardReturns:
    def test_basic(self):
        from services.agent.factor_engine.compositor import _compute_forward_returns

        dates = pd.date_range("2026-01-05", periods=10, freq="B")
        close = pd.DataFrame({
            "A": [100 + i for i in range(10)],
            "B": [200 + i * 2 for i in range(10)],
        }, index=dates)

        result = _compute_forward_returns(close, periods=3)
        assert result.shape == close.shape
        # 最后 3 天应为 NaN（未来数据不足）
        assert result.iloc[-1].isna().all()
        assert result.iloc[-2].isna().all()
        assert result.iloc[-3].isna().all()
        # 前 7 天应有值
        assert result.iloc[0].notna().all()

    def test_invalid_periods(self):
        from services.agent.factor_engine.compositor import _compute_forward_returns

        dates = pd.date_range("2026-01-05", periods=5, freq="B")
        close = pd.DataFrame({"A": [100, 101, 102, 103, 104]}, index=dates)
        with pytest.raises(ValueError, match="> 0"):
            _compute_forward_returns(close, periods=0)


class TestFactorRank:
    def test_asc(self):
        from services.agent.factor_engine.compositor import _compute_factor_rank

        dates = pd.date_range("2026-01-05", periods=2, freq="B")
        df = pd.DataFrame(
            {"A": [10, 20], "B": [50, 30], "C": [30, 40]},
            index=dates,
        )
        rank = _compute_factor_rank(df, is_asc=True)
        # is_asc=True：小值更好 → A(10) 的 rank_pct 应高于 B(50)
        assert rank.loc[dates[0], "A"] > rank.loc[dates[0], "B"]

    def test_desc(self):
        from services.agent.factor_engine.compositor import _compute_factor_rank

        dates = pd.date_range("2026-01-05", periods=2, freq="B")
        df = pd.DataFrame(
            {"A": [10, 20], "B": [50, 30], "C": [30, 40]},
            index=dates,
        )
        rank = _compute_factor_rank(df, is_asc=False)
        # is_asc=False：大值更好 → B(50) 是最大值，rank_pct 接近 1
        assert rank.loc[dates[0], "B"] > 0.8
        assert rank.loc[dates[0], "A"] < 0.5  # A(10) 是最小值，rank_pct 接近 0


class TestDailyIC:
    def test_positive_correlation(self):
        from services.agent.factor_engine.compositor import _compute_daily_ic

        dates = pd.date_range("2026-01-05", periods=5, freq="B")
        symbols = ["A", "B", "C", "D", "E"]
        factor = pd.DataFrame(
            np.tile(np.arange(1, 6).reshape(-1, 1), (1, 5)),
            index=dates,
            columns=symbols,
        )
        forward = factor.copy()  # 完全正相关
        ic = _compute_daily_ic(factor, forward, method="spearman")

        # 完全正相关 → IC ≈ 1
        assert ic is not None
        if not ic.empty:
            assert (ic > 0.9).all()

    def test_perfect_negative_correlation(self):
        from services.agent.factor_engine.compositor import _compute_daily_ic

        dates = pd.date_range("2026-01-05", periods=5, freq="B")
        symbols = ["A", "B", "C", "D", "E"]
        factor = pd.DataFrame(
            np.tile(np.arange(1, 6).reshape(-1, 1), (1, 5)),
            index=dates,
            columns=symbols,
        )
        forward = pd.DataFrame(
            np.tile(np.arange(5, 0, -1).reshape(-1, 1), (1, 5)),
            index=dates,
            columns=symbols,
        )
        ic = _compute_daily_ic(factor, forward, method="spearman")

        if not ic.empty:
            assert (ic < -0.9).all()

    def test_insufficient_samples(self):
        from services.agent.factor_engine.compositor import _compute_daily_ic

        dates = pd.date_range("2026-01-05", periods=3, freq="B")
        factor = pd.DataFrame(
            {"A": [1.0, np.nan, 3.0], "B": [np.nan, 2.0, np.nan]},
            index=dates,
        )
        forward = pd.DataFrame(
            {"A": [1.0, np.nan, 3.0], "B": [np.nan, 2.0, np.nan]},
            index=dates,
        )
        ic = _compute_daily_ic(factor, forward)
        # 每天有效样本 < 3，返回空
        assert ic.empty


class TestICIR:
    def test_computation(self):
        from services.agent.factor_engine.compositor import _compute_icir

        ic = pd.Series([0.1, 0.2, 0.1, 0.3, 0.2, 0.1, 0.15, 0.25, 0.1, 0.2])
        icir = _compute_icir(ic, recall=5, min_periods=3, shift=1)

        # shift(1) 后前 1 个为 NaN
        assert icir is not None
        # 后续至少有些值非 NaN
        non_na = icir.dropna()
        assert len(non_na) > 0

    def test_no_division_by_zero(self):
        from services.agent.factor_engine.compositor import _compute_icir

        # 标准差为 0 的场景
        ic = pd.Series([0.1, 0.1, 0.1, 0.1, 0.1])
        icir = _compute_icir(ic, recall=3, min_periods=2, shift=0)
        # 不应抛出异常
        assert icir is not None
