"""模拟持仓（Portfolio）API 测试。

覆盖：鉴权、CRUD、盈亏计算、权限隔离。
"""

import pytest


class TestPortfolioAuth:
    def test_list_requires_auth(self, client):
        resp = client.get("/api/portfolio")
        assert resp.status_code == 401

    def test_create_requires_auth(self, client):
        resp = client.post("/api/portfolio", json={"variety_id": 1, "direction": "long", "entry_price": "5000"})
        assert resp.status_code == 401

    def test_close_requires_auth(self, client):
        resp = client.post("/api/portfolio/1/close", json={"exit_price": "6000"})
        assert resp.status_code == 401

    def test_delete_requires_auth(self, client):
        resp = client.delete("/api/portfolio/1")
        assert resp.status_code == 401


class TestPortfolioCRUD:
    def test_create_trade_success(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/portfolio",
            json={"variety_id": variety.id, "direction": "long", "entry_price": "5000", "quantity": 2},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["variety_id"] == variety.id
        assert data["direction"] == "long"
        assert str(data["entry_price"]) == "5000.0000"
        assert data["quantity"] == 2
        assert data["status"] == "open"
        assert data["pnl"] is None

    def test_create_trade_invalid_direction(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/portfolio",
            json={"variety_id": variety.id, "direction": "invalid", "entry_price": "5000"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_trade_variety_not_found(self, client, auth_headers):
        resp = client.post(
            "/api/portfolio",
            json={"variety_id": 99999, "direction": "long", "entry_price": "5000"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_list_portfolio(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        client.post(
            "/api/portfolio",
            json={"variety_id": variety.id, "direction": "long", "entry_price": "5000"},
            headers=auth_headers,
        )
        client.post(
            "/api/portfolio",
            json={"variety_id": variety.id, "direction": "short", "entry_price": "6000"},
            headers=auth_headers,
        )
        resp = client.get("/api/portfolio", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

    def test_list_filter_by_status(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        client.post(
            "/api/portfolio",
            json={"variety_id": variety.id, "direction": "long", "entry_price": "5000"},
            headers=auth_headers,
        )
        resp = client.get("/api/portfolio?status=open", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["status"] == "open" for r in data)

    def test_close_trade_long_profit(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/portfolio",
            json={"variety_id": variety.id, "direction": "long", "entry_price": "5000", "quantity": 1},
            headers=auth_headers,
        )
        record_id = resp.json()["id"]

        resp = client.post(
            f"/api/portfolio/{record_id}/close",
            json={"exit_price": "6000"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "closed"
        assert data["exit_price"] == "6000.0000"
        # long: (6000 - 5000) * 1 * multiplier
        assert float(data["pnl"]) > 0
        assert data["pnl_percent"] is not None
        assert data["closed_at"] is not None

    def test_close_trade_short_profit(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/portfolio",
            json={"variety_id": variety.id, "direction": "short", "entry_price": "6000", "quantity": 1},
            headers=auth_headers,
        )
        record_id = resp.json()["id"]

        resp = client.post(
            f"/api/portfolio/{record_id}/close",
            json={"exit_price": "5000"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "closed"
        # short: (6000 - 5000) * 1 * multiplier
        assert float(data["pnl"]) > 0

    def test_close_trade_already_closed(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/portfolio",
            json={"variety_id": variety.id, "direction": "long", "entry_price": "5000"},
            headers=auth_headers,
        )
        record_id = resp.json()["id"]
        client.post(f"/api/portfolio/{record_id}/close", json={"exit_price": "6000"}, headers=auth_headers)

        resp = client.post(f"/api/portfolio/{record_id}/close", json={"exit_price": "7000"}, headers=auth_headers)
        assert resp.status_code == 400

    def test_delete_trade(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/portfolio",
            json={"variety_id": variety.id, "direction": "long", "entry_price": "5000"},
            headers=auth_headers,
        )
        record_id = resp.json()["id"]
        resp = client.delete(f"/api/portfolio/{record_id}", headers=auth_headers)
        assert resp.status_code == 204
        resp = client.get("/api/portfolio", headers=auth_headers)
        assert record_id not in [r["id"] for r in resp.json()]


class TestPortfolioPermissions:
    def test_close_not_owner_returns_403(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/portfolio",
            json={"variety_id": variety.id, "direction": "long", "entry_price": "5000"},
            headers=auth_headers,
        )
        record_id = resp.json()["id"]

        client.post("/api/auth/register", json={"username": "portfolio_user2", "email": "p2@test.com", "password": "password123"})
        resp = client.post("/api/auth/login", data={"username": "portfolio_user2", "password": "password123"})
        token2 = resp.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        resp = client.post(f"/api/portfolio/{record_id}/close", json={"exit_price": "6000"}, headers=headers2)
        assert resp.status_code == 403

    def test_delete_not_owner_returns_403(self, client, auth_headers, seed_varieties):
        variety = seed_varieties[0]
        resp = client.post(
            "/api/portfolio",
            json={"variety_id": variety.id, "direction": "long", "entry_price": "5000"},
            headers=auth_headers,
        )
        record_id = resp.json()["id"]

        client.post("/api/auth/register", json={"username": "portfolio_user3", "email": "p3@test.com", "password": "password123"})
        resp = client.post("/api/auth/login", data={"username": "portfolio_user3", "password": "password123"})
        token3 = resp.json()["access_token"]
        headers3 = {"Authorization": f"Bearer {token3}"}

        resp = client.delete(f"/api/portfolio/{record_id}", headers=headers3)
        assert resp.status_code == 403
