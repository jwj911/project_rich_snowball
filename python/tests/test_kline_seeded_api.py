"""
K 线 API 稳定测试
================
验证：测试内显式插入 K 线数据，接口返回非空且结构正确
"""

import datetime
import uuid


def test_kline_seeded_data(client, db_session, auth_headers):
    """显式插入 K 线后接口应正确返回"""
    from models import VarietyDB, KlineDataDB

    run_offset = int(uuid.uuid4().hex[:6], 16)
    au = db_session.query(VarietyDB).filter(VarietyDB.symbol == "AU").first()
    assert au is not None

    from models import FutContractDB
    contract = FutContractDB(
        ts_code="AU2506.SHF",
        symbol="AU2506",
        name="黄金2506",
        exchange="SHFE",
    )
    db_session.add(contract)
    db_session.flush()

    base_time = datetime.datetime(2099, 1, 1, 10, 0, 0) + datetime.timedelta(minutes=run_offset)
    inserted_times = []
    for i in range(5):
        trading_time = base_time + datetime.timedelta(hours=i)
        inserted_times.append(trading_time)
        db_session.add(KlineDataDB(
            variety_id=au.id,
            contract_id=contract.id,
            period="1h",
            trading_time=trading_time,
            open_price=500.0 + i,
            high_price=510.0 + i,
            low_price=490.0 + i,
            close_price=505.0 + i,
            volume=1000 + i * 100,
        ))
    db_session.commit()

    # 新版 /api/klines/{symbol} 默认返回当前主力合约 K 线；
    # 为验证显式插入的合约数据，需显式传入 contract_id。
    r = client.get(f"/api/klines/AU?period=1h&contract_id={contract.id}&limit=10", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 5
    opens = [c["open"] for c in data]
    assert 500.0 in opens
    assert 504.0 in opens
    for candle in data:
        assert "time" in candle
        assert "open" in candle
        assert "high" in candle
        assert "low" in candle
        assert "close" in candle
        assert "volume" in candle

    db_session.query(KlineDataDB).filter(
        KlineDataDB.variety_id == au.id,
        KlineDataDB.period == "1h",
        KlineDataDB.trading_time.in_(inserted_times),
    ).delete(synchronize_session=False)
    db_session.commit()
