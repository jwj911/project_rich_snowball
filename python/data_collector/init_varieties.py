from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import VarietyDB
from config import DATABASE_URL


@contextmanager
def get_db_session():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_varieties():
    varieties = [
        {"symbol": "AU", "contract_code": "AU2506", "name": "黄金", "exchange": "SHFE", "category": "贵金属", "margin_rate": 8, "commission": 15},
        {"symbol": "AG", "contract_code": "AG2506", "name": "白银", "exchange": "SHFE", "category": "贵金属", "margin_rate": 9, "commission": 12},
        {"symbol": "CU", "contract_code": "CU2506", "name": "铜", "exchange": "SHFE", "category": "有色金属", "margin_rate": 10, "commission": 18},
        {"symbol": "RB", "contract_code": "RB2506", "name": "螺纹钢", "exchange": "SHFE", "category": "黑色系", "margin_rate": 12, "commission": 8},
        {"symbol": "I", "contract_code": "I2506", "name": "铁矿石", "exchange": "DCE", "category": "黑色系", "margin_rate": 11, "commission": 10},
        {"symbol": "SC", "contract_code": "SC2506", "name": "原油", "exchange": "INE", "category": "能源化工", "margin_rate": 15, "commission": 20},
        {"symbol": "MA", "contract_code": "MA2506", "name": "甲醇", "exchange": "ZCE", "category": "能源化工", "margin_rate": 8, "commission": 6},
        {"symbol": "M", "contract_code": "M2506", "name": "豆粕", "exchange": "DCE", "category": "农产品", "margin_rate": 10, "commission": 7},
        {"symbol": "C", "contract_code": "C2506", "name": "玉米", "exchange": "DCE", "category": "农产品", "margin_rate": 8, "commission": 5},
        {"symbol": "CF", "contract_code": "CF2506", "name": "棉花", "exchange": "ZCE", "category": "农产品", "margin_rate": 12, "commission": 14},
    ]

    with get_db_session() as db:
        count = 0
        for v in varieties:
            if not db.query(VarietyDB).filter(VarietyDB.symbol == v["symbol"]).first():
                db.add(VarietyDB(**v))
                count += 1
        db.commit()
        print(f"已初始化 {count} 个新品种，跳过已存在的")


if __name__ == "__main__":
    init_varieties()
