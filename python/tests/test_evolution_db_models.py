"""Strategy Evolution DB 模型单元测试。

测试 StrategyEvolutionRunDB, StrategyGenerationDB, StrategyLifecycleDB 的 CRUD 和关系。
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models import (
    StrategyDB,
    StrategyEvolutionRunDB,
    StrategyGenerationDB,
    StrategyLifecycleDB,
)


def _create_user(db: Session):
    from models import UserDB
    user = UserDB(
        username="evo_model_user", email="evo_model@test.com",
        password_hash="hash", role="user",
    )
    db.add(user)
    db.flush()
    return user


def _create_strategy(db: Session, user_id: int, symbol: str = "RB") -> StrategyDB:
    s = StrategyDB(
        user_id=user_id, name=f"strategy-{symbol}", symbol=symbol,
        dsl_json=json.dumps({}), timeframe="1d", direction="long",
    )
    db.add(s)
    db.flush()
    return s


class TestEvolutionRunDB:
    def test_create_minimal(self, db_session):
        user = _create_user(db_session)
        run = StrategyEvolutionRunDB(
            user_id=user.id, symbol="RB",
            config_json=json.dumps({"generations": 10}),
            status="completed", generations=10, population_size=40,
            summary_json=json.dumps({"best_fitness": 85.0}),
        )
        db_session.add(run)
        db_session.commit()

        fetched = db_session.query(StrategyEvolutionRunDB).filter_by(id=run.id).first()
        assert fetched is not None
        assert fetched.symbol == "RB"
        assert fetched.status == "completed"
        summary = json.loads(fetched.summary_json)
        assert summary["best_fitness"] == 85.0

    def test_create_with_best_strategy(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)
        run = StrategyEvolutionRunDB(
            user_id=user.id, symbol="AU",
            config_json=json.dumps({}), status="completed",
            best_strategy_id=strategy.id,
        )
        db_session.add(run)
        db_session.commit()

        fetched = db_session.query(StrategyEvolutionRunDB).filter_by(id=run.id).first()
        assert fetched.best_strategy_id == strategy.id

    def test_create_failed(self, db_session):
        user = _create_user(db_session)
        run = StrategyEvolutionRunDB(
            user_id=user.id, symbol="RB",
            config_json="{}", status="failed",
            error_message="No data available",
        )
        db_session.add(run)
        db_session.commit()

        fetched = db_session.query(StrategyEvolutionRunDB).filter_by(id=run.id).first()
        assert fetched.status == "failed"
        assert fetched.error_message == "No data available"

    def test_user_relationship(self, db_session):
        from models import UserDB
        user = _create_user(db_session)
        run1 = StrategyEvolutionRunDB(user_id=user.id, symbol="RB", config_json="{}", status="completed")
        run2 = StrategyEvolutionRunDB(user_id=user.id, symbol="AU", config_json="{}", status="completed")
        db_session.add_all([run1, run2])
        db_session.commit()

        # Reload user with runs
        fetched_user = db_session.query(UserDB).filter_by(id=user.id).first()
        assert len(fetched_user.evolution_runs) == 2


class TestGenerationDB:
    def test_create_generation(self, db_session):
        user = _create_user(db_session)
        run = StrategyEvolutionRunDB(user_id=user.id, symbol="RB", config_json="{}", status="running")
        db_session.add(run)
        db_session.flush()

        gen = StrategyGenerationDB(
            evolution_run_id=run.id,
            generation_number=0,
            best_fitness=Decimal("72.5"),
            avg_fitness=Decimal("45.3"),
            diversity_score=Decimal("0.65"),
        )
        db_session.add(gen)
        db_session.commit()

        fetched = db_session.query(StrategyGenerationDB).filter_by(id=gen.id).first()
        assert float(fetched.best_fitness) == 72.5
        assert float(fetched.avg_fitness) == 45.3
        assert float(fetched.diversity_score) == 0.65

    def test_unique_run_generation(self, db_session):
        user = _create_user(db_session)
        run = StrategyEvolutionRunDB(user_id=user.id, symbol="RB", config_json="{}", status="running")
        db_session.add(run)
        db_session.flush()

        gen1 = StrategyGenerationDB(evolution_run_id=run.id, generation_number=0)
        gen2 = StrategyGenerationDB(evolution_run_id=run.id, generation_number=0)  # duplicate
        db_session.add_all([gen1, gen2])

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_cascade_delete(self, db_session):
        user = _create_user(db_session)
        run = StrategyEvolutionRunDB(user_id=user.id, symbol="CU", config_json="{}", status="completed")
        db_session.add(run)
        db_session.flush()

        gen = StrategyGenerationDB(evolution_run_id=run.id, generation_number=0)
        db_session.add(gen)
        db_session.commit()

        # Delete the run → generation should cascade
        db_session.delete(run)
        db_session.commit()

        gens = db_session.query(StrategyGenerationDB).filter_by(evolution_run_id=run.id).all()
        assert len(gens) == 0


class TestLifecycleDB:
    def test_create_lifecycle(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)

        lc = StrategyLifecycleDB(
            strategy_id=strategy.id, source="evolved",
            status="active", decay_score=Decimal("10"),
            in_sample_metrics='{"sharpe": 2.0}',
        )
        db_session.add(lc)
        db_session.commit()

        fetched = db_session.query(StrategyLifecycleDB).filter_by(strategy_id=strategy.id).first()
        assert fetched.source == "evolved"
        assert fetched.status == "active"
        assert float(fetched.decay_score) == 10

    def test_unique_strategy(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)

        lc1 = StrategyLifecycleDB(strategy_id=strategy.id, source="manual", status="active")
        lc2 = StrategyLifecycleDB(strategy_id=strategy.id, source="evolved", status="active")
        db_session.add_all([lc1, lc2])

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_source_enum_values(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)

        for source in ("manual", "evolved"):
            lc = StrategyLifecycleDB(strategy_id=strategy.id, source=source, status="active")
            db_session.add(lc)
            db_session.commit()
            db_session.delete(lc)
            db_session.commit()

    def test_status_values(self, db_session):
        user = _create_user(db_session)

        for i, status in enumerate(["active", "paper_trading", "degraded", "retired"]):
            strategy = _create_strategy(db_session, user.id, symbol=f"T{i}")
            lc = StrategyLifecycleDB(strategy_id=strategy.id, source="manual", status=status)
            db_session.add(lc)
            db_session.commit()

            fetched = db_session.query(StrategyLifecycleDB).filter_by(strategy_id=strategy.id).first()
            assert fetched.status == status

    def test_evolution_run_nullable(self, db_session):
        user = _create_user(db_session)
        strategy = _create_strategy(db_session, user.id)

        # No evolution_run_id → should work (manual source)
        lc = StrategyLifecycleDB(
            strategy_id=strategy.id, source="manual",
            status="active", evolution_run_id=None,
        )
        db_session.add(lc)
        db_session.commit()

        fetched = db_session.query(StrategyLifecycleDB).filter_by(strategy_id=strategy.id).first()
        assert fetched.evolution_run_id is None
