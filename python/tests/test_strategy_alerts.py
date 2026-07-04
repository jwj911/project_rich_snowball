"""策略告警事件测试。"""

from __future__ import annotations

from models import AlertEventDB
from services.alert_events import (
    STRATEGY_BACKTEST_SOURCE_TYPE,
    STRATEGY_OPTIMIZATION_SOURCE_TYPE,
    create_strategy_alert_for_backtest,
    create_strategy_alert_for_optimization,
)


class TestStrategyAlertEvents:
    def test_create_backtest_alert(self, db_session, seed_user):
        event = create_strategy_alert_for_backtest(
            db_session,
            strategy_id=1,
            user_id=seed_user.id,
            symbol="AU",
            error_message="回测执行异常: K 线数据不足",
        )
        db_session.flush()

        assert event.id is not None
        assert event.category == "strategy"
        assert event.severity == "medium"
        assert "AU" in event.title
        assert "回测失败" in event.title
        assert "回测执行异常" in event.summary
        assert event.source_type == STRATEGY_BACKTEST_SOURCE_TYPE
        assert event.source_id == 1
        assert event.user_id == seed_user.id
        assert event.target_scope == "personal"
        assert event.source_url == "/strategies/1"

    def test_create_backtest_alert_default_message(self, db_session, seed_user):
        event = create_strategy_alert_for_backtest(
            db_session,
            strategy_id=2,
            user_id=seed_user.id,
            symbol="RB",
        )
        db_session.flush()

        assert "RB" in event.title
        assert "回测失败" in event.title
        assert "回测执行过程中发生异常" in event.summary

    def test_create_optimization_alert(self, db_session, seed_user):
        event = create_strategy_alert_for_optimization(
            db_session,
            strategy_id=3,
            user_id=seed_user.id,
            symbol="CU",
            error_message="参数组合过多 (10000)",
        )
        db_session.flush()

        assert event.id is not None
        assert event.category == "strategy"
        assert event.severity == "medium"
        assert "CU" in event.title
        assert "参数优化失败" in event.title
        assert "参数组合过多" in event.summary
        assert event.source_type == STRATEGY_OPTIMIZATION_SOURCE_TYPE
        assert event.source_id == 3
        assert event.user_id == seed_user.id
        assert event.target_scope == "personal"
        assert event.source_url == "/strategies/3"

    def test_backtest_alert_queryable(self, db_session, seed_user):
        event = create_strategy_alert_for_backtest(
            db_session,
            strategy_id=1,
            user_id=seed_user.id,
            symbol="AU",
            error_message="测试",
        )
        db_session.flush()

        found = db_session.query(AlertEventDB).filter(
            AlertEventDB.user_id == seed_user.id,
            AlertEventDB.category == "strategy",
        ).first()
        assert found is not None
        assert found.id == event.id
