"""
K 线 API 稳定测试
================
验证：测试内显式插入 K 线数据，接口返回非空且结构正确

运行方式：
    cd python
    pytest tests/test_kline_seeded_api.py -v
"""

import datetime
import os
import sys
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from models import SessionLocal, VarietyDB, KlineDataDB
from fastapi.testclient import TestClient

client = TestClient(app)


def test_kline_seeded_data():
    """显式插入 K 线后接口应正确返回"""
    run_offset = int(uuid.uuid4().hex[:6], 16)
    db = SessionLocal()
    inserted_times = []
    try:
        au = db.query(VarietyDB).filter(VarietyDB.symbol == "AU").first()
        assert au is not None
        # 使用遥远的未来时间戳 + 随机偏移，确保重复运行不会撞唯一键。
        base_time = datetime.datetime(2099, 1, 1, 10, 0, 0) + datetime.timedelta(minutes=run_offset)
        for i in range(5):
            trading_time = base_time + datetime.timedelta(hours=i)
            inserted_times.append(trading_time)
            db.add(KlineDataDB(
                variety_id=au.id,
                period="1h",
                trading_time=trading_time,
                open_price=500.0 + i,
                high_price=510.0 + i,
                low_price=490.0 + i,
                close_price=505.0 + i,
                volume=1000 + i * 100,
            ))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/kline/AU?period=1h&limit=10")
    assert r.status_code == 200
    data = r.json()
    # 数据库中可能有历史数据，断言至少包含新插入的 5 条
    assert len(data) >= 5
    # 检查最新数据中包含我们插入的测试价格（API 按时间升序返回，最新的在最后）
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

    db = SessionLocal()
    try:
        au = db.query(VarietyDB).filter(VarietyDB.symbol == "AU").first()
        db.query(KlineDataDB).filter(
            KlineDataDB.variety_id == au.id,
            KlineDataDB.period == "1h",
            KlineDataDB.trading_time.in_(inserted_times),
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
