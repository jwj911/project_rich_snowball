"""策略参数优化引擎测试。"""

from __future__ import annotations

from services.backtest.optimization_engine import (
    _build_sensitivity_matrix,
    _calculate_composite_score,
    optimize_strategy_params,
    substitute_params,
)


class TestSubstituteParams:
    def test_replaces_placeholder(self):
        conditions = [
            {"indicator": "sma{short}", "operator": "cross_above", "indicator2": "sma{long}"},
        ]
        params = {"short": 5, "long": 20}
        result = substitute_params(conditions, params)
        assert result[0]["indicator"] == "sma5"
        assert result[0]["indicator2"] == "sma20"

    def test_preserves_non_string_values(self):
        conditions = [
            {"indicator": "close", "operator": ">", "value": 100},
        ]
        result = substitute_params(conditions, {"short": 5})
        assert result[0]["value"] == 100

    def test_multiple_conditions(self):
        conditions = [
            {"indicator": "sma{short}", "operator": "cross_above", "indicator2": "sma{long}"},
            {"indicator": "rsi{period}", "operator": "below", "value": 30},
        ]
        params = {"short": 10, "long": 30, "period": 14}
        result = substitute_params(conditions, params)
        assert result[0]["indicator"] == "sma10"
        assert result[1]["indicator"] == "rsi14"


class TestCalculateCompositeScore:
    def test_sharpe_and_return_weight(self):
        metrics = {
            "sharpe": 2.0,
            "total_return_pct": 30.0,
            "max_drawdown_pct": 10.0,
            "win_rate_pct": 60.0,
            "trade_count": 10,
        }
        weights = {"sharpe": 0.5, "total_return_pct": 0.3, "max_drawdown_pct": -0.2, "win_rate_pct": 0.0}
        score = _calculate_composite_score(metrics, weights)
        expected = 2.0 * 0.5 + 30.0 * 0.3 + 10.0 * (-0.2)
        assert round(score, 2) == round(expected, 2)

    def test_trade_count_penalty(self):
        metrics = {
            "sharpe": 2.0,
            "total_return_pct": 30.0,
            "max_drawdown_pct": 10.0,
            "win_rate_pct": 60.0,
            "trade_count": 1,
        }
        weights = {"sharpe": 0.5, "total_return_pct": 0.3, "max_drawdown_pct": -0.2, "win_rate_pct": 0.0}
        score = _calculate_composite_score(metrics, weights)
        expected = 2.0 * 0.5 + 30.0 * 0.3 + 10.0 * (-0.2) - 20.0
        assert round(score, 2) == round(expected, 2)


class TestBuildSensitivityMatrix:
    def test_single_param(self):
        results = [
            {"params": {"short": 5}, "score": 10.0},
            {"params": {"short": 10}, "score": 20.0},
            {"params": {"short": 5}, "score": 12.0},
        ]
        matrix = _build_sensitivity_matrix(results, ["short"])
        assert matrix["short"]["5"] == 11.0  # (10 + 12) / 2
        assert matrix["short"]["10"] == 20.0

    def test_two_params(self):
        results = [
            {"params": {"short": 5, "long": 20}, "score": 10.0},
            {"params": {"short": 5, "long": 30}, "score": 15.0},
            {"params": {"short": 10, "long": 20}, "score": 20.0},
            {"params": {"short": 10, "long": 30}, "score": 25.0},
        ]
        matrix = _build_sensitivity_matrix(results, ["short", "long"])
        assert matrix["short"]["5"] == 12.5  # (10 + 15) / 2
        assert matrix["short"]["10"] == 22.5  # (20 + 25) / 2
        assert matrix["long"]["20"] == 15.0  # (10 + 20) / 2
        assert matrix["long"]["30"] == 20.0  # (15 + 25) / 2


class TestOptimizeStrategyParams:
    """集成测试：需要数据库中已有 K 线数据。"""

    def test_combination_count_and_top_results(self, db_session, seed_varieties, monkeypatch):
        """验证优化引擎能正确枚举组合并返回 Top-N 结果。"""
        import random

        def _mock_run_dsl_backtest(db, symbol, period, direction, entry_conditions, exit_conditions, **kwargs):
            """Mock 回测，返回与参数相关的评分。"""
            short = 5
            long = 20
            for cond in entry_conditions:
                ind = cond.get("indicator", "")
                if ind.startswith("sma"):
                    short = int(ind.replace("sma", ""))
                ind2 = cond.get("indicator2", "")
                if ind2.startswith("sma"):
                    long = int(ind2.replace("sma", ""))
            # 模拟评分：短周期小、长周期大，评分更好
            score = 100 - short * 2 + long * 0.5
            return {
                "metrics": {
                    "total_return_pct": score,
                    "max_drawdown_pct": 10.0,
                    "win_rate_pct": 55.0,
                    "profit_factor": 1.5,
                    "sharpe": score / 20,
                    "trade_count": 10,
                    "score": int(score),
                }
            }

        monkeypatch.setattr(
            "services.backtest.optimization_engine.run_dsl_backtest",
            _mock_run_dsl_backtest,
        )

        variety = seed_varieties[0]
        entry_conditions = [
            {"indicator": "sma{short}", "operator": "cross_above", "indicator2": "sma{long}"},
        ]
        exit_conditions = [
            {"indicator": "sma{short}", "operator": "cross_below", "indicator2": "sma{long}"},
        ]
        param_space = {"short": [5, 10], "long": [20, 30]}

        result = optimize_strategy_params(
            db_session,
            symbol=variety.symbol,
            period="1d",
            direction="long",
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            param_space=param_space,
            initial_cash=100_000,
            quantity=1,
            limit=500,
            top_n=2,
        )

        assert result["total_combinations"] == 4
        assert result["tested_combinations"] == 4
        assert len(result["top_results"]) == 2
        assert result["best_params"] in (
            {"short": 5, "long": 30},
            {"short": 5, "long": 20},
            {"short": 10, "long": 30},
            {"short": 10, "long": 20},
        )
        assert "sensitivity_matrix" in result
        assert "short" in result["sensitivity_matrix"]
        assert "long" in result["sensitivity_matrix"]
        assert result["runtime_seconds"] >= 0

    def test_rejects_too_many_combinations(self, db_session):
        """组合超过 1000 时应抛出 ValueError。"""
        entry_conditions = [{"indicator": "sma{short}", "operator": "cross_above", "indicator2": "sma{long}"}]
        exit_conditions = [{"indicator": "sma{short}", "operator": "cross_below", "indicator2": "sma{long}"}]
        param_space = {"short": list(range(100)), "long": list(range(100))}  # 100*100 = 10000

        try:
            optimize_strategy_params(
                db_session,
                symbol="AU",
                period="1d",
                direction="long",
                entry_conditions=entry_conditions,
                exit_conditions=exit_conditions,
                param_space=param_space,
            )
            assert False, "应抛出 ValueError"
        except ValueError as exc:
            assert "参数组合过多" in str(exc)
