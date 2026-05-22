from urllib.parse import unquote

from models import ProductDB


def _seed_products(db_session):
    db_session.query(ProductDB).delete()
    products = [
        ProductDB(
            name="白银",
            symbol="AG",
            current_price=5400,
            change_percent=1.5,
            volume=3000,
            category="贵金属",
        ),
        ProductDB(
            name="黄金",
            symbol="AU",
            current_price=450,
            change_percent=-0.8,
            volume=2000,
            category="贵金属",
        ),
        ProductDB(
            name="螺纹钢",
            symbol="RB",
            current_price=3600,
            change_percent=0.3,
            volume=5000,
            category="黑色系",
        ),
    ]
    db_session.add_all(products)
    db_session.commit()


def test_products_query_filters_sorts_paginates_and_returns_stats(client, auth_headers, db_session):
    _seed_products(db_session)

    response = client.get(
        "/api/products",
        params={
            "search": "贵金属",
            "direction": "up",
            "sort_by": "volume",
            "sort_order": "desc",
            "skip": 0,
            "limit": 1,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert [item["symbol"] for item in data] == ["AG"]
    assert response.headers["X-Total-Count"] == "1"
    assert response.headers["X-Up-Count"] == "1"
    assert response.headers["X-Down-Count"] == "0"
    assert response.headers["X-Total-Volume"] == "3000"
    categories = [unquote(category) for category in response.headers["X-Categories"].split(",")]
    assert "贵金属" in categories
    assert "黑色系" in categories


def test_products_query_respects_pagination(client, auth_headers, db_session):
    _seed_products(db_session)

    response = client.get(
        "/api/products",
        params={
            "sort_by": "volume",
            "sort_order": "desc",
            "skip": 1,
            "limit": 1,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert [item["symbol"] for item in data] == ["AG"]
    assert response.headers["X-Total-Count"] == "3"
