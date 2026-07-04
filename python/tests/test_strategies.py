"""Strategy workspace API tests."""

from decimal import Decimal

from models import RealtimeQuoteDB, StrategyDB, UserDB
from utils import hash_password


def _get_auth_user(db_session):
    """获取 auth_headers 注册的用户。"""
    return db_session.query(UserDB).filter_by(username="integration_tester").first()


def _create_strategy(
    db_session,
    user_id: int,
    symbol: str = "AU",
    direction: str = "long",
    is_builtin: bool = False,
) -> StrategyDB:
    strategy = StrategyDB(
        user_id=user_id,
        name=f"{symbol} test strategy",
        description="test",
        symbol=symbol,
        dsl_json='{"entry":{"conditions":[{"left":"close","operator":">","right":"ma20"}]},"exit":{"conditions":[{"left":"close","operator":"<","right":"ma20"}]}}',
        timeframe="1d",
        direction=direction,
        is_active=True,
        is_builtin=is_builtin,
    )
    db_session.add(strategy)
    db_session.flush()
    db_session.refresh(strategy)
    return strategy


def _seed_quote(db_session, variety_id: int, price: str = "5000") -> None:
    """为品种写入实时行情；若已存在则先删除，避免唯一约束冲突。"""
    db_session.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety_id).delete(
        synchronize_session=False
    )
    db_session.add(
        RealtimeQuoteDB(
            variety_id=variety_id,
            current_price=Decimal(price),
            change_percent=Decimal("0"),
        )
    )
    db_session.flush()


class TestListStrategies:
    def test_returns_own_strategies(self, client, auth_headers, db_session):
        user = _get_auth_user(db_session)
        strategy = _create_strategy(db_session, user.id)

        resp = client.get("/api/strategies", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert any(s["id"] == strategy.id for s in data)

    def test_returns_builtin_strategies_for_other_users(self, client, auth_headers, db_session):
        other_user = UserDB(
            username="strategy_builtin_owner",
            email="builtin_owner@test.com",
            password_hash=hash_password("password123"),
        )
        db_session.add(other_user)
        db_session.flush()
        db_session.refresh(other_user)
        builtin = _create_strategy(db_session, other_user.id, is_builtin=True)

        resp = client.get("/api/strategies", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert any(s["id"] == builtin.id and s["is_builtin"] is True for s in data)

    def test_hides_non_builtin_strategies_from_others(self, client, auth_headers, db_session):
        other_user = UserDB(
            username="strategy_private_owner",
            email="private_owner@test.com",
            password_hash=hash_password("password123"),
        )
        db_session.add(other_user)
        db_session.flush()
        db_session.refresh(other_user)
        private = _create_strategy(db_session, other_user.id, is_builtin=False)

        resp = client.get("/api/strategies", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert all(s["id"] != private.id for s in data)


class TestGetStrategy:
    def test_can_view_builtin_strategy(self, client, auth_headers, db_session):
        other_user = UserDB(
            username="strategy_builtin_get_owner",
            email="builtin_get_owner@test.com",
            password_hash=hash_password("password123"),
        )
        db_session.add(other_user)
        db_session.flush()
        db_session.refresh(other_user)
        builtin = _create_strategy(db_session, other_user.id, is_builtin=True)

        resp = client.get(f"/api/strategies/{builtin.id}", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == builtin.id
        assert data["is_builtin"] is True

    def test_cannot_view_private_strategy_of_other_user(self, client, auth_headers, db_session):
        other_user = UserDB(
            username="strategy_private_get_owner",
            email="private_get_owner@test.com",
            password_hash=hash_password("password123"),
        )
        db_session.add(other_user)
        db_session.flush()
        db_session.refresh(other_user)
        private = _create_strategy(db_session, other_user.id, is_builtin=False)

        resp = client.get(f"/api/strategies/{private.id}", headers=auth_headers)

        assert resp.status_code == 403


class TestDeleteStrategy:
    def test_cannot_delete_builtin_strategy(self, client, auth_headers, db_session):
        user = _get_auth_user(db_session)
        builtin = _create_strategy(db_session, user.id, is_builtin=True)

        resp = client.delete(f"/api/strategies/{builtin.id}", headers=auth_headers)

        assert resp.status_code == 403
        db_session.refresh(builtin)
        assert builtin.is_active is True

    def test_can_delete_own_non_builtin_strategy(self, client, auth_headers, db_session):
        user = _get_auth_user(db_session)
        strategy = _create_strategy(db_session, user.id, is_builtin=False)

        resp = client.delete(f"/api/strategies/{strategy.id}", headers=auth_headers)

        assert resp.status_code == 200
        db_session.refresh(strategy)
        assert strategy.is_active is False


class TestStrategyPortfolioPlan:
    def test_generate_plan_success(self, client, auth_headers, seed_varieties, db_session):
        user = _get_auth_user(db_session)
        variety = seed_varieties[0]
        variety.margin_rate = Decimal("0.10")
        variety.multiplier = Decimal("10")
        variety.tick_size = Decimal("1")
        strategy = _create_strategy(db_session, user.id, symbol=variety.symbol)
        _seed_quote(db_session, variety.id, "5000")

        resp = client.post(
            f"/api/strategies/{strategy.id}/portfolio-plan",
            json={"account_balance": "100000", "risk_level": "medium"},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy_id"] == strategy.id
        assert data["variety_id"] == variety.id
        assert data["entry_price"] == "5000.0"
        assert data["suggested_quantity"] >= 1
        assert data["can_create"] is True
        assert float(data["stop_loss_price"]) > 0
        assert float(data["take_profit_price"]) > 0

    def test_generate_plan_strategy_not_found(self, client, auth_headers):
        resp = client.post(
            "/api/strategies/999999/portfolio-plan",
            json={"account_balance": "100000", "risk_level": "medium", "entry_price": "5000"},
            headers=auth_headers,
        )

        assert resp.status_code == 404

    def test_generate_plan_rejects_non_owner(self, client, auth_headers, seed_varieties, db_session):
        other_user = UserDB(
            username="strategy_other",
            email="strategy_other@test.com",
            password_hash=hash_password("password123"),
        )
        db_session.add(other_user)
        db_session.flush()
        db_session.refresh(other_user)
        strategy = _create_strategy(db_session, other_user.id, symbol=seed_varieties[0].symbol)

        resp = client.post(
            f"/api/strategies/{strategy.id}/portfolio-plan",
            json={"account_balance": "100000", "risk_level": "medium", "entry_price": "5000"},
            headers=auth_headers,
        )

        assert resp.status_code == 403

    def test_generate_plan_requires_price_when_quote_missing(self, client, auth_headers, seed_varieties, db_session):
        user = _get_auth_user(db_session)
        variety = seed_varieties[0]
        strategy = _create_strategy(db_session, user.id, symbol=variety.symbol)

        # 清理该品种已有实时行情，确保无行情时接口正确要求传入入场价
        db_session.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).delete(
            synchronize_session=False
        )
        db_session.flush()

        resp = client.post(
            f"/api/strategies/{strategy.id}/portfolio-plan",
            json={"account_balance": "100000", "risk_level": "medium"},
            headers=auth_headers,
        )

        assert resp.status_code == 400
