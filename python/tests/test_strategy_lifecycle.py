"""StrategyLifecycleManager 单元测试。

测试策略生命周期管理器的注册、衰减检测、行动推荐和策略对比功能。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from models import (
    BacktestRunDB,
    StrategyDB,
    StrategyEvolutionRunDB,
    StrategyLifecycleDB,
)
from services.agent.evolution.strategy_lifecycle import StrategyLifecycleManager


def _create_user(db: Session):
    """创建测试用户。"""
    from models import UserDB
    user = UserDB(username="test_lifecycle_user", email="lifecycle@test.com", password_hash="hash", role="user")
    db.add(user)
    db.flush()
    return user


def _create_strategy(db: Session, user_id: int, symbol: str = "RB", name: str = "test") -> StrategyDB:
    """创建测试策略。"""
    s = StrategyDB(
        user_id=user_id,
        name=name,
        symbol=symbol,
        dsl_json=json.dumps({}),
        timeframe="1d",
        direction="long",
    )
    db.add(s)
    db.flush()
    return s


def _create_backtest_run(db: Session, strategy_id: int, user_id: int, metrics: dict) -> BacktestRunDB:
    """创建测试回测运行记录。"""
    r = BacktestRunDB(
        strategy_id=strategy_id,
        user_id=user_id,
        status="completed",
        result_json=json.dumps({"metrics": metrics}),
    )
    db.add(r)
    db.flush()
    return r


# ---------------------------------------------------------------------------
# Test: register_strategy
# ---------------------------------------------------------------------------


class TestRegisterStrategy:
    def test_register_manual(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)

        StrategyLifecycleManager.register_strategy(
            db_session,
            strategy_id=strategy.id,
            source="manual",
            is_metrics={"sharpe": 1.5, "profit_factor": 2.0, "win_rate": 0.5},
        )

        lc = db_session.query(StrategyLifecycleDB).filter_by(strategy_id=strategy.id).first()
        assert lc is not None
        assert lc.source == "manual"
        assert lc.status == "active"
        assert lc.evolution_run_id is None
        assert lc.decay_score == 0
        metrics = json.loads(lc.in_sample_metrics)
        assert metrics["sharpe"] == 1.5

    def test_register_evolved(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)

        StrategyLifecycleManager.register_strategy(
            db_session,
            strategy_id=strategy.id,
            source="evolved",
            evolution_run_id=None,  # 不需要真实的 run_id
            is_metrics={"sharpe": 2.0},
            oos_metrics={"sharpe": 1.5},
        )

        lc = db_session.query(StrategyLifecycleDB).filter_by(strategy_id=strategy.id).first()
        assert lc.source == "evolved"
        is_metrics = json.loads(lc.in_sample_metrics)
        assert is_metrics["sharpe"] == 2.0
        oos_metrics = json.loads(lc.out_of_sample_metrics)
        assert oos_metrics["sharpe"] == 1.5

    def test_register_idempotent(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)

        StrategyLifecycleManager.register_strategy(db_session, strategy.id, source="manual")
        # 第二次注册不应创建重复记录
        StrategyLifecycleManager.register_strategy(db_session, strategy.id, source="evolved")

        count = db_session.query(StrategyLifecycleDB).filter_by(strategy_id=strategy.id).count()
        assert count == 1


# ---------------------------------------------------------------------------
# Test: evaluate_decay
# ---------------------------------------------------------------------------


class TestEvaluateDecay:
    def test_no_lifecycle(self, db_session):
        result = StrategyLifecycleManager.evaluate_decay(db_session, 99999)
        assert result["decay_score"] == 0
        assert result["recommended_action"] == "keep"
        assert "error" in result["details"]

    def test_no_data(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)
        StrategyLifecycleManager.register_strategy(db_session, strategy.id, source="manual")
        # No IS metrics and no backtest runs → insufficient data
        result = StrategyLifecycleManager.evaluate_decay(db_session, strategy.id)
        assert result["decay_score"] == 0

    def test_no_degradation(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)
        StrategyLifecycleManager.register_strategy(
            db_session, strategy.id, source="manual",
            is_metrics={"sharpe": 1.5, "profit_factor": 2.0, "win_rate": 0.5, "trade_count": 20},
        )
        # Recent metrics are similar → low decay
        result = StrategyLifecycleManager.evaluate_decay(
            db_session, strategy.id,
            recent_metrics={"sharpe": 1.4, "profit_factor": 1.9, "win_rate": 0.48, "trade_count": 18},
        )
        assert result["decay_score"] < 20
        assert result["recommended_action"] == "keep"

    def test_sharpe_degradation(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)
        StrategyLifecycleManager.register_strategy(
            db_session, strategy.id, source="manual",
            is_metrics={"sharpe": 2.0, "profit_factor": 3.0, "win_rate": 0.6, "trade_count": 30},
        )
        # Severe degradation in all dimensions
        result = StrategyLifecycleManager.evaluate_decay(
            db_session, strategy.id,
            recent_metrics={"sharpe": -0.5, "profit_factor": 0.8, "win_rate": 0.2, "trade_count": 5},
        )
        assert result["decay_score"] > 60
        assert result["recommended_action"] in ("re_optimize", "retire")

    def test_uses_latest_backtest(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)
        StrategyLifecycleManager.register_strategy(
            db_session, strategy.id, source="manual",
            is_metrics={"sharpe": 2.0, "profit_factor": 3.0, "win_rate": 0.6, "trade_count": 30},
        )
        # Create a backtest run with good recent metrics
        _create_backtest_run(db_session, strategy.id, user.id, {
            "sharpe": 1.9, "profit_factor": 2.8, "win_rate": 0.58, "trade_count": 28,
        })
        # Don't pass recent_metrics — should use latest backtest
        result = StrategyLifecycleManager.evaluate_decay(db_session, strategy.id)
        assert result["decay_score"] < 20


# ---------------------------------------------------------------------------
# Test: recommend_action
# ---------------------------------------------------------------------------


class TestRecommendAction:
    def test_keep(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)
        lc = StrategyLifecycleDB(
            strategy_id=strategy.id, source="manual", status="active",
            decay_score=Decimal("5"), in_sample_metrics="{}",
        )
        db_session.add(lc)
        db_session.commit()

        action = StrategyLifecycleManager.recommend_action(db_session, strategy.id)
        assert action == "keep"

    def test_paper_trade(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)
        lc = StrategyLifecycleDB(
            strategy_id=strategy.id, source="manual", status="active",
            decay_score=Decimal("30"), in_sample_metrics="{}",
        )
        db_session.add(lc)
        db_session.commit()

        action = StrategyLifecycleManager.recommend_action(db_session, strategy.id)
        assert action == "paper_trade"

    def test_re_optimize(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)
        lc = StrategyLifecycleDB(
            strategy_id=strategy.id, source="manual", status="active",
            decay_score=Decimal("55"), in_sample_metrics="{}",
        )
        db_session.add(lc)
        db_session.commit()

        action = StrategyLifecycleManager.recommend_action(db_session, strategy.id)
        assert action == "re_optimize"

    def test_retire(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)
        lc = StrategyLifecycleDB(
            strategy_id=strategy.id, source="manual", status="active",
            decay_score=Decimal("80"), in_sample_metrics="{}",
        )
        db_session.add(lc)
        db_session.commit()

        action = StrategyLifecycleManager.recommend_action(db_session, strategy.id)
        assert action == "retire"

    def test_no_lifecycle(self, db_session):
        action = StrategyLifecycleManager.recommend_action(db_session, 99999)
        assert action == "keep"


# ---------------------------------------------------------------------------
# Test: detect_decay
# ---------------------------------------------------------------------------


class TestDetectDecay:
    def test_insufficient_runs(self, db_session):
        result = StrategyLifecycleManager.detect_decay(db_session, 99999)
        assert result["decay_score"] == 0
        assert "note" in result

    def test_degradation_signals(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)

        # Good early backtest
        _create_backtest_run(db_session, strategy.id, user.id, {
            "sharpe": 2.5, "profit_factor": 3.0, "win_rate": 0.6, "trade_count": 40,
        })
        # Degraded late backtest
        _create_backtest_run(db_session, strategy.id, user.id, {
            "sharpe": -0.3, "profit_factor": 0.9, "win_rate": 0.25, "trade_count": 10,
        })

        result = StrategyLifecycleManager.detect_decay(db_session, strategy.id)
        # Should detect multiple decay signals
        assert result["decay_score"] > 0
        assert len(result["decay_signals"]) > 0

    def test_no_degradation_signals(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)

        _create_backtest_run(db_session, strategy.id, user.id, {
            "sharpe": 2.0, "profit_factor": 2.5, "win_rate": 0.55, "trade_count": 25,
        })
        _create_backtest_run(db_session, strategy.id, user.id, {
            "sharpe": 2.1, "profit_factor": 2.6, "win_rate": 0.56, "trade_count": 24,
        })

        result = StrategyLifecycleManager.detect_decay(db_session, strategy.id)
        assert result["decay_score"] == 0


# ---------------------------------------------------------------------------
# Test: compare_strategies
# ---------------------------------------------------------------------------


class TestCompareStrategies:
    def test_ranking(self, db_session):
        user = _create_user(db_session)
        s_good = _create_strategy(db_session, user.id, symbol="RB", name="Good")
        s_bad = _create_strategy(db_session, user.id, symbol="AU", name="Bad")

        StrategyLifecycleManager.register_strategy(
            db_session, s_good.id, source="evolved",
            is_metrics={"sharpe": 2.0, "profit_factor": 3.0},
        )
        StrategyLifecycleManager.register_strategy(
            db_session, s_bad.id, source="manual",
            is_metrics={"sharpe": 0.5, "profit_factor": 1.2},
        )

        # Set bad one as degraded and good one as healthy (explicit decimals)
        lc_good = db_session.query(StrategyLifecycleDB).filter_by(strategy_id=s_good.id).first()
        lc_good.decay_score = Decimal("5")
        lc_bad = db_session.query(StrategyLifecycleDB).filter_by(strategy_id=s_bad.id).first()
        lc_bad.decay_score = Decimal("80")
        db_session.commit()

        results = StrategyLifecycleManager.compare_strategies(db_session, [s_good.id, s_bad.id])
        assert len(results) == 2
        # Healthy strategy (low decay) should rank before degraded one (high decay)
        assert results[0]["strategy_id"] == s_good.id
        assert results[0]["decay_score"] == 5.0
        assert results[1]["decay_score"] == 80.0

    def test_includes_missing_strategies(self, db_session):
        user = _create_user(db_session)
        s1 = _create_strategy(db_session, user.id, symbol="RB", name="WithLifecycle")
        s2 = _create_strategy(db_session, user.id, symbol="AU", name="WithoutLifecycle")

        StrategyLifecycleManager.register_strategy(db_session, s1.id, source="manual")
        # s2 has no lifecycle record

        results = StrategyLifecycleManager.compare_strategies(db_session, [s1.id, s2.id])
        assert len(results) == 2
        assert results[0]["has_lifecycle"] is True
        assert results[1]["has_lifecycle"] is False


# ---------------------------------------------------------------------------
# Test: get_lifecycle_summary
# ---------------------------------------------------------------------------


class TestLifecycleSummary:
    def test_with_lifecycle(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)
        StrategyLifecycleManager.register_strategy(
            db_session, strategy.id, source="evolved",
            is_metrics={"sharpe": 2.0},
            oos_metrics={"sharpe": 1.5},
        )

        summary = StrategyLifecycleManager.get_lifecycle_summary(db_session, strategy.id)
        assert summary["has_lifecycle"] is True
        assert summary["source"] == "evolved"
        assert summary["in_sample_metrics"]["sharpe"] == 2.0
        assert summary["out_of_sample_metrics"]["sharpe"] == 1.5

    def test_without_lifecycle(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)

        summary = StrategyLifecycleManager.get_lifecycle_summary(db_session, strategy.id)
        assert summary["has_lifecycle"] is False
