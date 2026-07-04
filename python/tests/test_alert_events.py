from datetime import UTC, datetime
from decimal import Decimal


class TestAlertEventAuth:
    def test_events_requires_auth(self, client):
        resp = client.get("/api/alerts/events")
        assert resp.status_code == 401

    def test_summary_requires_auth(self, client):
        resp = client.get("/api/alerts/summary")
        assert resp.status_code == 401


class TestAlertEventVisibility:
    def test_broadcast_news_visible_to_users_and_state_isolated(self, client, auth_headers, db_session):
        from models import AlertEventDB, UserDB

        event = AlertEventDB(
            category="news",
            severity="critical",
            title="FOMC 决议公布",
            source_type="news_article",
            source_id=1,
            target_scope="broadcast",
            triggered_at=datetime.now(UTC),
        )
        db_session.add(event)
        db_session.commit()

        resp = client.get("/api/alerts/events", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["read_at"] is None

        resp = client.put(f"/api/alerts/events/{event.id}/read", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["read_at"] is not None

        client.post(
            "/api/auth/register",
            json={"username": "alert_reader2", "email": "alert_reader2@test.com", "password": "password123"},
        )
        login = client.post("/api/auth/login", data={"username": "alert_reader2", "password": "password123"})
        headers2 = {"Authorization": f"Bearer {login.json()['access_token']}"}
        resp = client.get("/api/alerts/events", headers=headers2)
        assert resp.status_code == 200
        assert resp.json()[0]["read_at"] is None

        user1 = db_session.query(UserDB).filter(UserDB.username == "integration_tester").one()
        user2 = db_session.query(UserDB).filter(UserDB.username == "alert_reader2").one()
        assert user1.id != user2.id

    def test_dismiss_hides_event_for_current_user_only(self, client, auth_headers, db_session):
        from models import AlertEventDB

        event = AlertEventDB(
            category="news",
            severity="high",
            title="矿山坍塌影响铜供应",
            source_type="news_article",
            source_id=2,
            target_scope="broadcast",
            triggered_at=datetime.now(UTC),
        )
        db_session.add(event)
        db_session.commit()

        resp = client.put(f"/api/alerts/events/{event.id}/dismiss", headers=auth_headers)
        assert resp.status_code == 200

        resp = client.get("/api/alerts/events", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

        client.post(
            "/api/auth/register",
            json={"username": "alert_reader3", "email": "alert_reader3@test.com", "password": "password123"},
        )
        login = client.post("/api/auth/login", data={"username": "alert_reader3", "password": "password123"})
        headers3 = {"Authorization": f"Bearer {login.json()['access_token']}"}
        resp = client.get("/api/alerts/events", headers=headers3)
        assert resp.status_code == 200
        assert len(resp.json()) == 1


def test_news_alert_rule_creates_broadcast_once(db_session):
    from models import AlertEventDB, NewsArticleDB, NewsSourceDB
    from services.alert_events import create_news_alert_for_article

    source = NewsSourceDB(name="test", url="https://example.com/rss.xml", is_enabled=True, is_builtin=True)
    db_session.add(source)
    db_session.flush()
    article = NewsArticleDB(
        source_id=source.id,
        title="美联储 FOMC 决议公布，市场波动加剧",
        summary="CPI 与利率路径成为焦点",
        url="https://example.com/fomc",
        published_at=datetime.now(UTC),
    )
    db_session.add(article)
    db_session.flush()

    first = create_news_alert_for_article(db_session, article)
    second = create_news_alert_for_article(db_session, article)
    db_session.commit()

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert db_session.query(AlertEventDB).count() == 1
    assert first.category == "news"
    assert first.target_scope == "broadcast"


def test_price_alert_trigger_creates_market_event_once(db_session, seed_varieties):
    from data_collector.scheduler import _check_price_alerts
    from models import AlertEventDB, PriceAlertDB, RealtimeQuoteDB, UserDB
    from utils import hash_password

    user = UserDB(username="price_alert_user", email="price-alert@test.com", password_hash=hash_password("password123"))
    variety = seed_varieties[0]
    alert = PriceAlertDB(
        user=user,
        variety=variety,
        alert_type="above",
        target_price=Decimal("100.0000"),
        is_triggered=False,
    )
    quote = RealtimeQuoteDB(variety_id=variety.id, current_price=Decimal("101.0000"))
    db_session.add_all([user, alert, quote])
    db_session.commit()

    _check_price_alerts(db_session)
    _check_price_alerts(db_session)

    events = db_session.query(AlertEventDB).all()
    assert len(events) == 1
    assert events[0].category == "market"
    assert events[0].user_id == user.id
    assert events[0].source_id == alert.id
