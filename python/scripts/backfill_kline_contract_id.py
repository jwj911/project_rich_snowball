"""
回填 K 线合约归属脚本
========================
将 kline_data 表中 contract_id 为 null 的记录，按当前 variety.contract_code
匹配 fut_contracts 进行回填。

运行方式：
    cd python
    python scripts/backfill_kline_contract_id.py

输出：
    - 回填成功条数
    - 无法匹配的 variety 列表
    - 回填后的 null 计数
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from models import SessionLocal, KlineDataDB, VarietyDB, FutContractDB


def _resolve_contract_id(db: Session, contract_code: str) -> int | None:
    """将 contract_code（如 AU2506, MA2506）解析为 fut_contracts.id。
    尝试顺序：symbol 精确匹配 -> ts_code 精确匹配 -> ZCE 格式 symbol -> ZCE 格式 ts_code。
    """
    if not contract_code:
        return None

    # 1. symbol 精确匹配（如 M2506）
    c = db.query(FutContractDB).filter(FutContractDB.symbol == contract_code).first()
    if c:
        return c.id

    # 2. ts_code 精确匹配（如 AU2506.SHF）
    c = db.query(FutContractDB).filter(FutContractDB.ts_code == contract_code).first()
    if c:
        return c.id

    # 3. ZCE 格式：去掉世纪前缀（MA2506 -> MA506）
    if len(contract_code) > 4 and contract_code[-4:].isdigit():
        zce_symbol = contract_code[:-4] + contract_code[-3:]
        c = db.query(FutContractDB).filter(FutContractDB.symbol == zce_symbol).first()
        if c:
            return c.id
        # 4. ZCE ts_code 格式
        c = db.query(FutContractDB).filter(FutContractDB.ts_code == contract_code + ".ZCE").first()
        if c:
            return c.id
        # 5. DCE ts_code 格式
        c = db.query(FutContractDB).filter(FutContractDB.ts_code == contract_code + ".DCE").first()
        if c:
            return c.id
        # 6. SHFE ts_code 格式
        c = db.query(FutContractDB).filter(FutContractDB.ts_code == contract_code + ".SHF").first()
        if c:
            return c.id
        # 7. INE ts_code 格式
        c = db.query(FutContractDB).filter(FutContractDB.ts_code == contract_code + ".INE").first()
        if c:
            return c.id

    return None


def backfill():
    db: Session = SessionLocal()
    try:
        total_null = db.query(KlineDataDB).filter(KlineDataDB.contract_id.is_(None)).count()
        print(f"回填前 contract_id 为 null 的记录: {total_null}")
        if total_null == 0:
            print("无需回填")
            return

        variety_ids = (
            db.query(KlineDataDB.variety_id)
            .filter(KlineDataDB.contract_id.is_(None))
            .distinct()
            .all()
        )
        variety_ids = [v[0] for v in variety_ids]
        print(f"涉及品种数: {len(variety_ids)}")

        varieties = db.query(VarietyDB).filter(VarietyDB.id.in_(variety_ids)).all()
        variety_contract_map = {v.id: v.contract_code for v in varieties if v.contract_code}

        matched = 0
        unmatched_varieties = []

        for vid, code in variety_contract_map.items():
            cid = _resolve_contract_id(db, code)
            if not cid:
                unmatched_varieties.append((vid, code))
                continue

            count = (
                db.query(KlineDataDB)
                .filter(KlineDataDB.variety_id == vid, KlineDataDB.contract_id.is_(None))
                .update({"contract_id": cid}, synchronize_session=False)
            )
            matched += count
            print(f"  Variety {vid} -> Contract {code} ({cid}): 回填 {count} 条")

        db.commit()

        remaining_null = db.query(KlineDataDB).filter(KlineDataDB.contract_id.is_(None)).count()
        print("\n========== 回填报告 ==========")
        print(f"回填前 null 数: {total_null}")
        print(f"回填成功:       {matched}")
        print(f"回填后 null 数: {remaining_null}")
        if unmatched_varieties:
            print(f"\n无法匹配的品种 ({len(unmatched_varieties)}):")
            for vid, code in unmatched_varieties:
                print(f"  variety_id={vid}, contract_code={code}")
        print("==============================")

    finally:
        db.close()


if __name__ == "__main__":
    backfill()
