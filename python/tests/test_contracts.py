from datetime import datetime

from models import (
    VarietyDB, FutContractDB, KlineDataDB,
    ContractRolloverDB, UserDB,
)
from utils import hash_password
from routers.auth import clear_rate_limit_store


def _create_test_user(db, username="contract_tester", password="testpass123"):
    user = UserDB(
        username=username,
        email=f"{username}@test.com",
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client, username="contract_tester", password="testpass123"):
    clear_rate_limit_store()
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _setup_variety_and_contracts(db):
    """创建测试品种和合约。"""
    variety = VarietyDB(
        symbol="TEST",
        name="测试品种",
        exchange="SHFE",
        contract_code="TEST2502",
    )
    db.add(variety)
    db.commit()
    db.refresh(variety)

    c1 = FutContractDB(
        ts_code="TEST2501.SHF",
        symbol="TEST2501",
        name="测试合约01",
        fut_code="TEST",
        exchange="SHFE",
        list_date=None,
        delist_date=None,
        is_active=True,
    )
    c2 = FutContractDB(
        ts_code="TEST2502.SHF",
        symbol="TEST2502",
        name="测试合约02",
        fut_code="TEST",
        exchange="SHFE",
        list_date=None,
        delist_date=None,
        is_active=True,
    )
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)

    return variety, c1, c2


def test_list_contracts(client, db_session):
    variety, c1, c2 = _setup_variety_and_contracts(db_session)
    _create_test_user(db_session)
    token = _login(client)

    r = client.get(f"/api/contracts?variety_id={variety.id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert any(x["symbol"] == "TEST2501" for x in data)
    assert any(x["symbol"] == "TEST2502" for x in data)
    assert all(x["fut_code"] == "TEST" for x in data)


def test_get_contract_detail(client, db_session):
    _, c1, _ = _setup_variety_and_contracts(db_session)
    _create_test_user(db_session)
    token = _login(client)

    r = client.get(f"/api/contracts/{c1.id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "TEST2501"
    assert data["ts_code"] == "TEST2501.SHF"

    r = client.get("/api/contracts/999999", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_get_contract_kline(client, db_session):
    _, c1, _ = _setup_variety_and_contracts(db_session)
    _create_test_user(db_session)

    k1 = KlineDataDB(
        variety_id=db_session.query(VarietyDB).filter(VarietyDB.symbol == "TEST").first().id,
        contract_id=c1.id,
        period="D",
        trading_time=datetime(2025, 1, 15),
        open_price=100.0,
        high_price=110.0,
        low_price=95.0,
        close_price=105.0,
        volume=1000,
    )
    db_session.add(k1)
    db_session.commit()

    token = _login(client)
    r = client.get(
        f"/api/contracts/{c1.id}/kline?period=D",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["open"] == 100.0
    assert data[0]["volume"] == 1000


def test_variety_contracts(client, db_session):
    variety, c1, c2 = _setup_variety_and_contracts(db_session)
    _create_test_user(db_session)
    token = _login(client)

    r = client.get(
        f"/api/varieties/{variety.id}/contracts",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2

    c1.is_active = False
    db_session.commit()
    r = client.get(
        f"/api/varieties/{variety.id}/contracts?active_only=true",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "TEST2502"


def test_variety_rollovers(client, db_session):
    variety, c1, c2 = _setup_variety_and_contracts(db_session)
    _create_test_user(db_session)

    rollover = ContractRolloverDB(
        variety_id=variety.id,
        old_contract_id=c1.id,
        new_contract_id=c2.id,
        old_contract_code="TEST2501",
        new_contract_code="TEST2502",
        effective_date=datetime(2025, 2, 1),
        source="test",
    )
    db_session.add(rollover)
    db_session.commit()

    token = _login(client)
    r = client.get(
        f"/api/varieties/{variety.id}/rollovers",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["old_contract_code"] == "TEST2501"
    assert data[0]["new_contract_code"] == "TEST2502"


def test_continuous_kline(client, db_session):
    """连续 K 线默认启用反向调整，消除换月跳空。"""
    variety, c1, c2 = _setup_variety_and_contracts(db_session)
    _create_test_user(db_session)

    # 旧合约 K 线
    k1 = KlineDataDB(
        variety_id=variety.id,
        contract_id=c1.id,
        period="D",
        trading_time=datetime(2025, 1, 10),
        open_price=100.0,
        high_price=110.0,
        low_price=95.0,
        close_price=105.0,
        volume=1000,
    )
    # 新合约 K 线（close 比旧合约高 5，形成换月跳空）
    k2 = KlineDataDB(
        variety_id=variety.id,
        contract_id=c2.id,
        period="D",
        trading_time=datetime(2025, 2, 5),
        open_price=108.0,
        high_price=118.0,
        low_price=103.0,
        close_price=110.0,
        volume=2000,
    )
    rollover = ContractRolloverDB(
        variety_id=variety.id,
        old_contract_id=c1.id,
        new_contract_id=c2.id,
        old_contract_code="TEST2501",
        new_contract_code="TEST2502",
        effective_date=datetime(2025, 2, 1),
        source="test",
    )
    db_session.add_all([k1, k2, rollover])
    db_session.commit()

    token = _login(client)
    r = client.get(
        "/api/klines/TEST/continuous?period=D",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    # 旧合约数据应被反向调整：减去 gap = 110 - 105 = 5
    assert data[0]["contract_code"] == "TEST2501"
    assert data[0]["open"] == 95.0
    assert data[0]["high"] == 105.0
    assert data[0]["low"] == 90.0
    assert data[0]["close"] == 100.0
    # 新合约数据保持不变
    assert data[1]["contract_code"] == "TEST2502"
    assert data[1]["open"] == 108.0
    assert data[1]["close"] == 110.0


def test_main_contract_kline(client, db_session):
    variety, c1, c2 = _setup_variety_and_contracts(db_session)
    _create_test_user(db_session)
    variety.contract_code = "TEST2502"
    db_session.commit()

    k = KlineDataDB(
        variety_id=variety.id,
        contract_id=c2.id,
        period="D",
        trading_time=datetime(2025, 2, 5),
        open_price=200.0,
        high_price=210.0,
        low_price=195.0,
        close_price=205.0,
        volume=2000,
    )
    db_session.add(k)
    db_session.commit()

    token = _login(client)
    r = client.get(
        "/api/klines/TEST/main?period=D",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["contract_code"] == "TEST2502"


def test_continuous_and_main_kline_accept_period_aliases(client, db_session):
    variety, c1, _ = _setup_variety_and_contracts(db_session)
    _create_test_user(db_session)
    variety.contract_code = "TEST2501"

    db_session.add(KlineDataDB(
        variety_id=variety.id,
        contract_id=c1.id,
        period="1d",
        trading_time=datetime(2025, 1, 10),
        open_price=100.0,
        high_price=110.0,
        low_price=95.0,
        close_price=105.0,
        volume=1000,
    ))
    db_session.commit()

    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    continuous = client.get("/api/klines/TEST/continuous?period=D", headers=headers)
    assert continuous.status_code == 200
    assert len(continuous.json()) == 1

    main = client.get("/api/klines/TEST/main?period=D", headers=headers)
    assert main.status_code == 200
    assert len(main.json()) == 1

    contract = client.get(f"/api/contracts/{c1.id}/kline?period=1d", headers=headers)
    assert contract.status_code == 200
    assert len(contract.json()) == 1
