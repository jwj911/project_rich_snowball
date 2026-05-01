
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import Base, FuturesVarietyDB, KlineDataDB, WatchlistDB, CommentDB, OpinionDB
from datetime import datetime

@contextmanager
def get_db_session():
    engine = create_engine(
        "sqlite:///./futures_community.db",
        connect_args={"check_same_thread": False}
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_varieties(db):
    varieties = [
        {"code": "cu2401", "name": "铜", "exchange": "SHFE", "category": "金属", "contract_month": "2024-01", "tick_size": 10.0, "price_limit": 4.0},
        {"code": "al2401", "name": "铝", "exchange": "SHFE", "category": "金属", "contract_month": "2024-01", "tick_size": 5.0, "price_limit": 4.0},
        {"code": "zn2401", "name": "锌", "exchange": "SHFE", "category": "金属", "contract_month": "2024-01", "tick_size": 5.0, "price_limit": 4.0},
        {"code": "rb2401", "name": "螺纹钢", "exchange": "SHFE", "category": "建材", "contract_month": "2024-01", "tick_size": 1.0, "price_limit": 4.0},
        {"code": "hc2401", "name": "热卷", "exchange": "SHFE", "category": "建材", "contract_month": "2024-01", "tick_size": 1.0, "price_limit": 4.0},
        {"code": "au2401", "name": "黄金", "exchange": "SHFE", "category": "贵金属", "contract_month": "2024-01", "tick_size": 0.01, "price_limit": 4.0},
        {"code": "ag2401", "name": "白银", "exchange": "SHFE", "category": "贵金属", "contract_month": "2024-01", "tick_size": 1.0, "price_limit": 4.0},
        {"code": "bu2401", "name": "沥青", "exchange": "SHFE", "category": "能源化工", "contract_month": "2024-01", "tick_size": 2.0, "price_limit": 4.0},
        {"code": "ru2401", "name": "橡胶", "exchange": "SHFE", "category": "能源化工", "contract_month": "2024-01", "tick_size": 5.0, "price_limit": 4.0},
        {"code": "fu2401", "name": "燃油", "exchange": "SHFE", "category": "能源化工", "contract_month": "2024-01", "tick_size": 1.0, "price_limit": 4.0},
        {"code": "sc2401", "name": "原油", "exchange": "INE", "category": "能源化工", "contract_month": "2024-01", "tick_size": 1.0, "price_limit": 4.0},
        {"code": "ni2401", "name": "镍", "exchange": "SHFE", "category": "金属", "contract_month": "2024-01", "tick_size": 10.0, "price_limit": 4.0},
        {"code": "pb2401", "name": "铅", "exchange": "SHFE", "category": "金属", "contract_month": "2024-01", "tick_size": 5.0, "price_limit": 4.0},
        {"code": "sn2401", "name": "锡", "exchange": "SHFE", "category": "金属", "contract_month": "2024-01", "tick_size": 10.0, "price_limit": 4.0},
        {"code": "sp2401", "name": "纸浆", "exchange": "SHFE", "category": "农产品", "contract_month": "2024-01", "tick_size": 2.0, "price_limit": 4.0},
    ]
    
    for v in varieties:
        if not db.query(FuturesVarietyDB).filter(FuturesVarietyDB.code == v["code"]).first():
            db.add(FuturesVarietyDB(**v))
    db.commit()

def init_kline_data(db):
    klines = [
        {"variety_code": "cu2401", "time_period": "1H", "open_price": 72500.0, "high_price": 72650.0, "low_price": 72300.0, "close_price": 72580.0, "settlement_price": 72520.0, "volume": 15600, "open_interest": 45200, "trading_date": datetime(2024, 1, 15, 9, 0, 0)},
        {"variety_code": "cu2401", "time_period": "1H", "open_price": 72580.0, "high_price": 72780.0, "low_price": 72500.0, "close_price": 72680.0, "settlement_price": 72650.0, "volume": 14200, "open_interest": 44800, "trading_date": datetime(2024, 1, 15, 10, 0, 0)},
        {"variety_code": "cu2401", "time_period": "1H", "open_price": 72680.0, "high_price": 72850.0, "low_price": 72600.0, "close_price": 72750.0, "settlement_price": 72720.0, "volume": 16800, "open_interest": 45500, "trading_date": datetime(2024, 1, 15, 11, 0, 0)},
        {"variety_code": "cu2401", "time_period": "1H", "open_price": 72750.0, "high_price": 72900.0, "low_price": 72700.0, "close_price": 72820.0, "settlement_price": 72780.0, "volume": 12500, "open_interest": 45100, "trading_date": datetime(2024, 1, 15, 14, 0, 0)},
        {"variety_code": "cu2401", "time_period": "1H", "open_price": 72820.0, "high_price": 72950.0, "low_price": 72750.0, "close_price": 72880.0, "settlement_price": 72850.0, "volume": 13800, "open_interest": 44900, "trading_date": datetime(2024, 1, 15, 15, 0, 0)},
        {"variety_code": "au2401", "time_period": "1H", "open_price": 425.50, "high_price": 426.80, "low_price": 424.20, "close_price": 425.90, "settlement_price": 425.60, "volume": 8900, "open_interest": 23400, "trading_date": datetime(2024, 1, 15, 9, 0, 0)},
        {"variety_code": "au2401", "time_period": "1H", "open_price": 425.90, "high_price": 427.50, "low_price": 425.00, "close_price": 426.80, "settlement_price": 426.50, "volume": 7600, "open_interest": 23100, "trading_date": datetime(2024, 1, 15, 10, 0, 0)},
        {"variety_code": "au2401", "time_period": "1H", "open_price": 426.80, "high_price": 428.00, "low_price": 426.20, "close_price": 427.20, "settlement_price": 427.00, "volume": 9200, "open_interest": 23800, "trading_date": datetime(2024, 1, 15, 11, 0, 0)},
        {"variety_code": "rb2401", "time_period": "1H", "open_price": 3850.0, "high_price": 3875.0, "low_price": 3830.0, "close_price": 3862.0, "settlement_price": 3858.0, "volume": 45600, "open_interest": 125000, "trading_date": datetime(2024, 1, 15, 9, 0, 0)},
        {"variety_code": "rb2401", "time_period": "1H", "open_price": 3862.0, "high_price": 3885.0, "low_price": 3845.0, "close_price": 3878.0, "settlement_price": 3872.0, "volume": 42300, "open_interest": 124500, "trading_date": datetime(2024, 1, 15, 10, 0, 0)},
        {"variety_code": "rb2401", "time_period": "1H", "open_price": 3878.0, "high_price": 3895.0, "low_price": 3865.0, "close_price": 3888.0, "settlement_price": 3885.0, "volume": 48900, "open_interest": 126000, "trading_date": datetime(2024, 1, 15, 11, 0, 0)},
        {"variety_code": "sc2401", "time_period": "1H", "open_price": 582.0, "high_price": 585.5, "low_price": 579.0, "close_price": 583.5, "settlement_price": 583.0, "volume": 28500, "open_interest": 56200, "trading_date": datetime(2024, 1, 15, 9, 0, 0)},
        {"variety_code": "sc2401", "time_period": "1H", "open_price": 583.5, "high_price": 587.0, "low_price": 581.5, "close_price": 585.0, "settlement_price": 584.5, "volume": 26200, "open_interest": 55800, "trading_date": datetime(2024, 1, 15, 10, 0, 0)},
        {"variety_code": "al2401", "time_period": "1H", "open_price": 18520.0, "high_price": 18650.0, "low_price": 18450.0, "close_price": 18580.0, "settlement_price": 18550.0, "volume": 22400, "open_interest": 68500, "trading_date": datetime(2024, 1, 15, 9, 0, 0)},
        {"variety_code": "al2401", "time_period": "1H", "open_price": 18580.0, "high_price": 18720.0, "low_price": 18500.0, "close_price": 18650.0, "settlement_price": 18620.0, "volume": 20100, "open_interest": 68100, "trading_date": datetime(2024, 1, 15, 10, 0, 0)},
    ]
    
    for k in klines:
        db.add(KlineDataDB(**k))
    db.commit()

def init_watchlist(db):
    watchlists = [
        {"user_id": "user001", "variety_code": "cu2401", "is_followed": True, "resistance_level": 73000.0, "support_level": 72000.0, "notes": "关注突破情况"},
        {"user_id": "user001", "variety_code": "au2401", "is_followed": True, "resistance_level": 430.0, "support_level": 420.0, "notes": "中长期看好"},
        {"user_id": "user001", "variety_code": "rb2401", "is_followed": False, "resistance_level": 3900.0, "support_level": 3800.0, "notes": "观望中"},
        {"user_id": "user002", "variety_code": "sc2401", "is_followed": True, "resistance_level": 590.0, "support_level": 575.0, "notes": "波动较大"},
        {"user_id": "user002", "variety_code": "al2401", "is_followed": True, "resistance_level": 18800.0, "support_level": 18400.0, "notes": "基本面偏强"},
    ]
    
    for w in watchlists:
        db.add(WatchlistDB(**w))
    db.commit()

def init_comments(db):
    comments = [
        {"variety_code": "cu2401", "user_id": "user001", "content": "今天铜价走势很强，突破了关键阻力位，后续继续看好！", "created_at": datetime(2024, 1, 15, 10, 30, 0)},
        {"variety_code": "cu2401", "user_id": "user002", "content": "量能不足，谨防回调风险", "created_at": datetime(2024, 1, 15, 11, 15, 0)},
        {"variety_code": "au2401", "user_id": "user001", "content": "黄金避险属性支撑，长期持有", "created_at": datetime(2024, 1, 15, 9, 45, 0)},
        {"variety_code": "rb2401", "user_id": "user003", "content": "螺纹钢基本面转好，需求回暖", "created_at": datetime(2024, 1, 15, 14, 20, 0)},
        {"variety_code": "sc2401", "user_id": "user002", "content": "原油波动加剧，注意风险控制", "created_at": datetime(2024, 1, 15, 15, 0, 0)},
    ]
    
    for c in comments:
        db.add(CommentDB(**c))
    db.commit()

def init_opinions(db):
    opinions = [
        {"variety_code": "cu2401", "user_id": "user001", "type": "bullish", "reason": "宏观经济数据向好，铜需求预期增加", "target_price": 75000.0, "stop_loss": 71000.0, "created_at": datetime(2024, 1, 15, 9, 0, 0)},
        {"variety_code": "cu2401", "user_id": "user002", "type": "bearish", "reason": "库存压力较大，短期承压", "target_price": 70000.0, "stop_loss": 74000.0, "created_at": datetime(2024, 1, 15, 10, 30, 0)},
        {"variety_code": "cu2401", "user_id": "user003", "type": "neutral", "reason": "等待方向选择，观望为主", "target_price": None, "stop_loss": None, "created_at": datetime(2024, 1, 15, 11, 0, 0)},
        {"variety_code": "au2401", "user_id": "user001", "type": "bullish", "reason": "地缘政治风险支撑金价", "target_price": 435.0, "stop_loss": 418.0, "created_at": datetime(2024, 1, 15, 8, 30, 0)},
        {"variety_code": "rb2401", "user_id": "user002", "type": "bullish", "reason": "基建需求回暖，螺纹钢需求增加", "target_price": 4000.0, "stop_loss": 3750.0, "created_at": datetime(2024, 1, 15, 14, 0, 0)},
    ]
    
    for o in opinions:
        db.add(OpinionDB(**o))
    db.commit()

if __name__ == "__main__":
    with get_db_session() as db:
        init_varieties(db)
        init_kline_data(db)
        init_watchlist(db)
        init_comments(db)
        init_opinions(db)
    print("数据初始化完成")
