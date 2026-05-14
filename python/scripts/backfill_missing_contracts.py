"""
补充 fut_contracts 中缺失的合约，以便回填 kline_data.contract_id。

运行方式:
    cd python
    python scripts/backfill_missing_contracts.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from models import SessionLocal, VarietyDB, FutContractDB

# 品种 ID → (symbol, exchange, ts_code_suffix)
MISSING_CONTRACTS = [
    # ZCE 品种
    {"variety_id": 7,  "symbol": "MA",  "contract_code": "MA2506", "ts_code": "MA2506.ZCE", "exchange": "CZCE"},
    {"variety_id": 9,  "symbol": "C",   "contract_code": "C2506",  "ts_code": "C2506.ZCE",  "exchange": "CZCE"},
    {"variety_id": 10, "symbol": "CF",  "contract_code": "CF2506", "ts_code": "CF2506.ZCE", "exchange": "CZCE"},
    # DCE 品种
    {"variety_id": 8,  "symbol": "M",   "contract_code": "M2506",  "ts_code": "M2506.DCE",  "exchange": "DCE"},
]


def insert_missing_contracts():
    db: Session = SessionLocal()
    try:
        inserted = 0
        skipped = 0
        for item in MISSING_CONTRACTS:
            variety = db.query(VarietyDB).filter(VarietyDB.id == item["variety_id"]).first()
            if not variety:
                print(f"品种 {item['variety_id']} 不存在，跳过")
                skipped += 1
                continue

            existing = db.query(FutContractDB).filter(FutContractDB.ts_code == item["ts_code"]).first()
            if existing:
                print(f"合约 {item['ts_code']} 已存在，跳过")
                skipped += 1
                continue

            contract = FutContractDB(
                ts_code=item["ts_code"],
                symbol=item["contract_code"],
                name=f"{item['symbol']}2506",
                fut_code=item["symbol"],
                exchange=item["exchange"],
                contract_type="1",
                is_active=False,  # 已过期合约
            )
            db.add(contract)
            inserted += 1
            print(f"插入合约: {item['ts_code']} ({item['contract_code']})")

        db.commit()
        print(f"\n插入: {inserted}, 跳过: {skipped}")
    finally:
        db.close()


if __name__ == "__main__":
    insert_missing_contracts()
