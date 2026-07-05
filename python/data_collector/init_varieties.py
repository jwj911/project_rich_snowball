"""Seed the futures variety metadata used by collectors and APIs."""
from models import SessionLocal, VarietyDB

DEFAULT_VARIETIES = [
    {
        "symbol": "AU",
        "contract_code": "AU2506",
        "name": "黄金",
        "exchange": "SHFE",
        "category": "贵金属",
        "margin_rate": 8,
        "commission": 15,
    },
    {
        "symbol": "AG",
        "contract_code": "AG2506",
        "name": "白银",
        "exchange": "SHFE",
        "category": "贵金属",
        "margin_rate": 9,
        "commission": 12,
    },
    {
        "symbol": "CU",
        "contract_code": "CU2506",
        "name": "铜",
        "exchange": "SHFE",
        "category": "有色金属",
        "margin_rate": 10,
        "commission": 18,
    },
    {
        "symbol": "RB",
        "contract_code": "RB2506",
        "name": "螺纹钢",
        "exchange": "SHFE",
        "category": "黑色系",
        "margin_rate": 12,
        "commission": 8,
    },
    {
        "symbol": "I",
        "contract_code": "I2506",
        "name": "铁矿石",
        "exchange": "DCE",
        "category": "黑色系",
        "margin_rate": 11,
        "commission": 10,
    },
    {
        "symbol": "SC",
        "contract_code": "SC2506",
        "name": "原油",
        "exchange": "INE",
        "category": "能源化工",
        "margin_rate": 15,
        "commission": 20,
    },
    {
        "symbol": "MA",
        "contract_code": "MA2506",
        "name": "甲醇",
        "exchange": "ZCE",
        "category": "能源化工",
        "margin_rate": 8,
        "commission": 6,
    },
    {
        "symbol": "M",
        "contract_code": "M2506",
        "name": "豆粕",
        "exchange": "DCE",
        "category": "农产品",
        "margin_rate": 10,
        "commission": 7,
    },
    {
        "symbol": "C",
        "contract_code": "C2506",
        "name": "玉米",
        "exchange": "DCE",
        "category": "农产品",
        "margin_rate": 8,
        "commission": 5,
    },
    {
        "symbol": "CF",
        "contract_code": "CF2506",
        "name": "棉花",
        "exchange": "ZCE",
        "category": "农产品",
        "margin_rate": 12,
        "commission": 14,
    },
]


def init_varieties() -> None:
    db = SessionLocal()
    try:
        created = 0
        updated = 0
        for item in DEFAULT_VARIETIES:
            variety = db.query(VarietyDB).filter(VarietyDB.symbol == item["symbol"]).first()
            if variety:
                for key, value in item.items():
                    # 保留已有的 contract_code，避免覆盖 fut_mapping 更新后的主力合约
                    if key == "contract_code" and getattr(variety, key, None):
                        continue
                    setattr(variety, key, value)
                updated += 1
            else:
                db.add(VarietyDB(**item))
                created += 1
        db.commit()
        print(f"Initialized varieties: created={created}, updated={updated}")
    finally:
        db.close()


if __name__ == "__main__":
    init_varieties()
