from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import SessionLocal, ProductDB, UserDB, CommentDB, KlineDataDB, VarietyDB, RealtimeQuoteDB, FutContractDB
from utils import hash_password
from data_collector.mock_collector import MockCollector
from data_collector.upsert import insert_kline_bulk, upsert_realtime, upsert_fut_contract_bulk


def init_mock_data():
    db = SessionLocal()
    try:
        if db.query(ProductDB).count() == 0:
            products = [
                {"name": "黄金", "symbol": "AU", "current_price": 453.2, "change_percent": 1.25, "open_price": 447.5, "high": 455.8, "low": 446.2, "volume": 152340, "category": "贵金属", "margin": 8, "commission": 15},
                {"name": "白银", "symbol": "AG", "current_price": 5420, "change_percent": -0.85, "open_price": 5465, "high": 5500, "low": 5380, "volume": 89420, "category": "贵金属", "margin": 9, "commission": 12},
                {"name": "铜", "symbol": "CU", "current_price": 68450, "change_percent": 2.15, "open_price": 67000, "high": 68800, "low": 66800, "volume": 125680, "category": "有色金属", "margin": 10, "commission": 18},
                {"name": "螺纹钢", "symbol": "RB", "current_price": 3680, "change_percent": -1.32, "open_price": 3730, "high": 3750, "low": 3650, "volume": 2156800, "category": "黑色系", "margin": 12, "commission": 8},
                {"name": "铁矿石", "symbol": "I", "current_price": 825, "change_percent": 0.78, "open_price": 818, "high": 835, "low": 812, "volume": 985420, "category": "黑色系", "margin": 11, "commission": 10},
                {"name": "原油", "symbol": "SC", "current_price": 528.5, "change_percent": -2.15, "open_price": 540.0, "high": 542.0, "low": 525.0, "volume": 425680, "category": "能源化工", "margin": 15, "commission": 20},
                {"name": "甲醇", "symbol": "MA", "current_price": 2580, "change_percent": 1.05, "open_price": 2555, "high": 2600, "low": 2540, "volume": 1856420, "category": "能源化工", "margin": 8, "commission": 6},
                {"name": "豆粕", "symbol": "M", "current_price": 3250, "change_percent": 0.45, "open_price": 3235, "high": 3280, "low": 3220, "volume": 652340, "category": "农产品", "margin": 10, "commission": 7},
                {"name": "玉米", "symbol": "C", "current_price": 2455, "change_percent": -0.62, "open_price": 2470, "high": 2485, "low": 2440, "volume": 425680, "category": "农产品", "margin": 8, "commission": 5},
                {"name": "棉花", "symbol": "CF", "current_price": 16850, "change_percent": 1.88, "open_price": 16540, "high": 16920, "low": 16480, "volume": 285640, "category": "农产品", "margin": 12, "commission": 14},
            ]
            for p in products:
                db.add(ProductDB(**p))

        if db.query(UserDB).count() == 0:
            users = [
                {"username": "trader001", "email": "trader001@example.com", "password_hash": hash_password("password123")},
                {"username": "investor_wang", "email": "wang@example.com", "password_hash": hash_password("password123")},
                {"username": "futures_master", "email": "master@example.com", "password_hash": hash_password("password123")},
            ]
            for u in users:
                db.add(UserDB(**u))
            db.commit()

            comments = [
                {"product_id": 1, "user_id": 1, "content": "黄金近期走势强劲，受避险情绪影响明显，建议关注450美元阻力位。"},
                {"product_id": 1, "user_id": 2, "content": "美联储加息预期降温，金价有望继续上攻。"},
                {"product_id": 3, "user_id": 3, "content": "铜价突破68000，需求端预期改善，短期内看好。"},
                {"product_id": 6, "user_id": 1, "content": "原油回落至520附近，OPEC+减产消息需持续关注。"},
                {"product_id": 4, "user_id": 2, "content": "螺纹钢库存下降，基本面转好信号出现。"},
            ]
            for c in comments:
                db.add(CommentDB(**c))

        # 初始化实时行情
        if db.query(RealtimeQuoteDB).count() == 0:
            for p in db.query(ProductDB).all():
                upsert_realtime(db, {
                    "symbol": p.symbol,
                    "current_price": p.current_price,
                    "change_percent": p.change_percent,
                    "open_price": p.open_price,
                    "high": p.high,
                    "low": p.low,
                    "volume": p.volume,
                    "updated_at": datetime.now(timezone.utc),
                })

        # 确保每个品种都有对应的合约记录，供 K 线匹配 contract_id
        # 使用 upsert 避免 PostgreSQL 等环境下的唯一约束冲突
        varieties = db.query(VarietyDB).all()
        contract_rows = []
        for variety in varieties:
            contract_rows.append({
                "ts_code": f"{variety.contract_code}.{variety.exchange}",
                "symbol": variety.contract_code,
                "name": variety.name,
                "fut_code": variety.symbol,
                "exchange": variety.exchange,
                "is_active": True,
            })
        if contract_rows:
            upsert_fut_contract_bulk(db, contract_rows)
        db.commit()

        collector = MockCollector()
        for variety in varieties:
            # 同时生成 1h/1d（基础 K 线）和 D（连续/主力 K 线）数据
            for period, limit in (("1h", 120), ("1d", 90), ("D", 90)):
                has_kline = db.query(KlineDataDB).filter(
                    KlineDataDB.variety_id == variety.id,
                    KlineDataDB.period == period,
                ).first()
                if not has_kline:
                    rows = collector.fetch_kline(variety.contract_code, period, limit=limit)
                    insert_kline_bulk(db, rows, period)

        # 初始化实时行情数据（从 products 同步，确保 /api/realtime/{symbol} 可用）
        for product in db.query(ProductDB).all():
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == product.symbol).first()
            if variety and not db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first():
                db.add(RealtimeQuoteDB(
                    variety_id=variety.id,
                    current_price=product.current_price,
                    change_percent=product.change_percent,
                    open_price=product.open_price,
                    high=product.high,
                    low=product.low,
                    volume=product.volume,
                    updated_at=datetime.now(timezone.utc),
                ))

        # 初始化手续费/保证金数据，供 /api/varieties/{symbol}/fees 使用
        from models import FutTradeFeeDB
        if db.query(FutTradeFeeDB).count() == 0:
            for variety in varieties:
                db.add(FutTradeFeeDB(
                    exchange=variety.exchange,
                    contract_name=variety.name,
                    contract_code=variety.contract_code,
                    margin_per_hand=variety.margin_rate,
                    fee_open_fixed=str(variety.commission),
                    fee_updated_at=datetime.now(timezone.utc),
                ))

        db.commit()
        print("模拟数据初始化完成")
    finally:
        db.close()


if __name__ == "__main__":
    init_mock_data()
