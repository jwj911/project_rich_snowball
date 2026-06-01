"""价格预警 API 测试。

覆盖：鉴权、CRUD、筛选、权限隔离、触发状态重置。
"""

import pytest


class TestPriceAlertAuth:
    def test_list_requires_auth(self, client):
        resp = client.get("/api/price-alerts")
        assert resp.status_code == 401

    def test_create_requires_auth(self, client):
        resp = client.post("/api/price-alerts", json={"variety_id": 1, "alert_type": "above", "target_price": "5000"})
        assert resp.status_code == 401

    def test_update_requires_auth(self, client):
        resp = client.put("/api/price-alerts/1", json={"target_price": "6000"})
        assert resp.status_code == 401

    def test_delete_requires_auth(self, client):
        resp = client.delete("/api/price-alerts/1")
        assert resp.status_code == 401


class TestPriceAlertCRUD:
    def test_create_alert_success(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/price-alerts",
            json={"variety_id": variety.id, "alert_type": "above", "target_price": "5000.50"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["variety_id"] == variety.id
        assert data["alert_type"] == "above"
        assert str(data["target_price"]) == "5000.5000"
        assert data["is_triggered"] is False

    def test_create_alert_invalid_type(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/price-alerts",
            json={"variety_id": variety.id, "alert_type": "invalid", "target_price": "5000"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_alert_variety_not_found(self, client, auth_headers):
        resp = client.post(
            "/api/price-alerts",
            json={"variety_id": 99999, "alert_type": "above", "target_price": "5000"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_list_alerts(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        client.post(
            "/api/price-alerts",
            json={"variety_id": variety.id, "alert_type": "above", "target_price": "5000"},
            headers=auth_headers,
        )
        client.post(
            "/api/price-alerts",
            json={"variety_id": variety.id, "alert_type": "below", "target_price": "4000"},
            headers=auth_headers,
        )
        resp = client.get("/api/price-alerts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        assert data[0]["alert_type"] == "below"

    def test_list_filter_by_variety(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        client.post(
            "/api/price-alerts",
            json={"variety_id": variety.id, "alert_type": "above", "target_price": "5000"},
            headers=auth_headers,
        )
        resp = client.get(f"/api/price-alerts?variety_id={variety.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(a["variety_id"] == variety.id for a in data)

    def test_list_filter_by_triggered(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        client.post(
            "/api/price-alerts",
            json={"variety_id": variety.id, "alert_type": "above", "target_price": "5000"},
            headers=auth_headers,
        )
        resp = client.get("/api/price-alerts?triggered=false", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(a["is_triggered"] is False for a in data)

    def test_triggered_endpoint(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/price-alerts",
            json={"variety_id": variety.id, "alert_type": "above", "target_price": "5000"},
            headers=auth_headers,
        )
        alert_id = resp.json()["id"]
        client.put(f"/api/price-alerts/{alert_id}", json={"is_triggered": True}, headers=auth_headers)

        resp = client.get("/api/price-alerts/triggered", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert all(a["is_triggered"] is True for a in data)

    def test_update_target_price_resets_triggered(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/price-alerts",
            json={"variety_id": variety.id, "alert_type": "above", "target_price": "5000"},
            headers=auth_headers,
        )
        alert_id = resp.json()["id"]
        client.put(f"/api/price-alerts/{alert_id}", json={"is_triggered": True}, headers=auth_headers)
        resp = client.put(
            f"/api/price-alerts/{alert_id}",
            json={"target_price": "6000"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_triggered"] is False
        assert data["triggered_at"] is None

    def test_delete_alert(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/price-alerts",
            json={"variety_id": variety.id, "alert_type": "above", "target_price": "5000"},
            headers=auth_headers,
        )
        alert_id = resp.json()["id"]
        resp = client.delete(f"/api/price-alerts/{alert_id}", headers=auth_headers)
        assert resp.status_code == 204
        resp = client.get(f"/api/price-alerts?variety_id={variety.id}", headers=auth_headers)
        assert alert_id not in [a["id"] for a in resp.json()]


class TestPriceAlertPermissions:
    def test_update_not_owner_returns_403(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/price-alerts",
            json={"variety_id": variety.id, "alert_type": "above", "target_price": "5000"},
            headers=auth_headers,
        )
        alert_id = resp.json()["id"]

        client.post(
            "/api/auth/register",
            json={"username": "alert_user2", "email": "alert2@test.com", "password": "password123"},
        )
        resp = client.post(
            "/api/auth/login",
            data={"username": "alert_user2", "password": "password123"},
        )
        token2 = resp.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        resp = client.put(
            f"/api/price-alerts/{alert_id}",
            json={"target_price": "6000"},
            headers=headers2,
        )
        assert resp.status_code == 403

    def test_delete_not_owner_returns_403(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/price-alerts",
            json={"variety_id": variety.id, "alert_type": "above", "target_price": "5000"},
            headers=auth_headers,
        )
        alert_id = resp.json()["id"]

        client.post(
            "/api/auth/register",
            json={"username": "alert_user3", "email": "alert3@test.com", "password": "password123"},
        )
        resp = client.post(
            "/api/auth/login",
            data={"username": "alert_user3", "password": "password123"},
        )
        token3 = resp.json()["access_token"]
        headers3 = {"Authorization": f"Bearer {token3}"}

        resp = client.delete(f"/api/price-alerts/{alert_id}", headers=headers3)
        assert resp.status_code == 403
