import pytest
from fastapi.testclient import TestClient
from main import app
from models import (
    SessionLocal, VarietyDB, FutContractDB, KlineDataDB,
    ContractRolloverDB, UserDB,
)
from utils import hash_password
from routers.auth import clear_rate_limit_store

client = TestClient(app)


def _create_test_user(db, username="contract_tester", password="testpass123"):
    user = db.query(UserDB).filter(UserDB.username == username).first()
    if user:
        return user
    user = UserDB(
        username=username,
        email=f"{username}@test.com",
        hashed_password=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _get_or_create_user(username="contract_tester", password="testpass123"):
    db = SessionLocal()
    try:
        user = db.query(UserDB).filter(UserDB.username == username).first()
        if not user:
            user = UserDB(
                username=username,
                email=f"{username}@test.com",
                password_hash=hash_password(password),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()


def _login(username="contract_tester", password="testpass123"):
    _get_or_create_user(username, password)
    clear_rate_limit_store()
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(autouse=True)
def clean_db():
    db = SessionLocal()
    try:
        db.query(ContractRolloverDB).delete()
        db.query(KlineDataDB).delete()
        db.query(FutContractDB).filter(FutContractDB.symbol.in_(["TEST2501", "TEST2502"])).delete()
        db.query(VarietyDB).filter(VarietyDB.symbol == "TEST").delete()
        db.commit()
    finally:
        db.close()
    yield


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
        ts_code="TEST2501.SHFE",
        symbol="TEST2501",
        name="测试合约01",
        fut_code="TEST",
        exchange="SHFE",
        list_date=None,
        delist_date=None,
        is_active=True,
    )
    c2 = FutContractDB(
        ts_code="TEST2502.SHFE",
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


def test_list_contracts():
    db = SessionLocal()
    try:
        variety, c1, c2 = _setup_variety_and_contracts(db)
        token = _login()

        # 按品种筛选（数据库中可能有大量真实合约，不加筛选会分页截断）
        r = client.get(f"/api/contracts?variety_id={variety.id}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert any(x["symbol"] == "TEST2501" for x in data)
        assert any(x["symbol"] == "TEST2502" for x in data)
        assert all(x["fut_code"] == "TEST" for x in data)
    finally:
        db.close()


def test_get_contract_detail():
    db = SessionLocal()
    try:
        _, c1, _ = _setup_variety_and_contracts(db)
        token = _login()

        r = client.get(f"/api/contracts/{c1.id}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["symbol"] == "TEST2501"
        assert data["ts_code"] == "TEST2501.SHFE"

        # 不存在
        r = client.get("/api/contracts/999999", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404
    finally:
        db.close()


def test_get_contract_kline():
    db = SessionLocal()
    try:
        _, c1, _ = _setup_variety_and_contracts(db)
        # 插入 K 线
        k1 = KlineDataDB(
            variety_id=db.query(VarietyDB).filter(VarietyDB.symbol == "TEST").first().id,
            contract_id=c1.id,
            period="D",
            trading_time="2025-01-15T00:00:00",
            open_price=100.0,
            high_price=110.0,
            low_price=95.0,
            close_price=105.0,
            volume=1000,
        )
        db.add(k1)
        db.commit()

        token = _login()
        r = client.get(
            f"/api/contracts/{c1.id}/kline?period=D",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["open"] == 100.0
        assert data[0]["volume"] == 1000
    finally:
        db.close()


def test_variety_contracts():
    db = SessionLocal()
    try:
        variety, c1, c2 = _setup_variety_and_contracts(db)
        token = _login()

        r = client.get(
            f"/api/varieties/{variety.id}/contracts",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2

        # active_only
        c1.is_active = False
        db.commit()
        r = client.get(
            f"/api/varieties/{variety.id}/contracts?active_only=true",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "TEST2502"
    finally:
        db.close()


def test_variety_rollovers():
    db = SessionLocal()
    try:
        variety, c1, c2 = _setup_variety_and_contracts(db)
        rollover = ContractRolloverDB(
            variety_id=variety.id,
            old_contract_id=c1.id,
            new_contract_id=c2.id,
            old_contract_code="TEST2501",
            new_contract_code="TEST2502",
            effective_date="2025-02-01T00:00:00",
            source="test",
        )
        db.add(rollover)
        db.commit()

        token = _login()
        r = client.get(
            f"/api/varieties/{variety.id}/rollovers",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["old_contract_code"] == "TEST2501"
        assert data[0]["new_contract_code"] == "TEST2502"
    finally:
        db.close()


def test_continuous_kline():
    db = SessionLocal()
    try:
        variety, c1, c2 = _setup_variety_and_contracts(db)
        # 插入两段 K 线，分属不同合约
        from datetime import datetime
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
        k2 = KlineDataDB(
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
        rollover = ContractRolloverDB(
            variety_id=variety.id,
            old_contract_id=c1.id,
            new_contract_id=c2.id,
            old_contract_code="TEST2501",
            new_contract_code="TEST2502",
            effective_date=datetime(2025, 2, 1),
            source="test",
        )
        db.add_all([k1, k2, rollover])
        db.commit()

        token = _login()
        r = client.get(
            "/api/kline/TEST/continuous?period=D",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        # 第一段 c1
        assert data[0]["open"] == 100.0
        assert data[0]["contract_code"] == "TEST2501"
        # 第二段 c2
        assert data[1]["open"] == 200.0
        assert data[1]["contract_code"] == "TEST2502"
    finally:
        db.close()


def test_main_contract_kline():
    db = SessionLocal()
    try:
        variety, c1, c2 = _setup_variety_and_contracts(db)
        # 设置当前主力为 c2
        variety.contract_code = "TEST2502"
        db.commit()

        from datetime import datetime
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
        db.add(k)
        db.commit()

        token = _login()
        r = client.get(
            "/api/kline/TEST/main?period=D",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["contract_code"] == "TEST2502"
    finally:
        db.close()
