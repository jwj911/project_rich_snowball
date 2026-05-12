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


def backfill():
    db: Session = SessionLocal()
    try:
        # 统计回填前
        total_null = db.query(KlineDataDB).filter(KlineDataDB.contract_id.is_(None)).count()
        print(f"回填前 contract_id 为 null 的记录: {total_null}")
        if total_null == 0:
            print("无需回填")
            return

        # 获取所有 contract_id 为 null 的 variety_id
        variety_ids = (
            db.query(KlineDataDB.variety_id)
            .filter(KlineDataDB.contract_id.is_(None))
            .distinct()
            .all()
        )
        variety_ids = [v[0] for v in variety_ids]
        print(f"涉及品种数: {len(variety_ids)}")

        # 批量获取 variety -> contract_code 映射
        varieties = db.query(VarietyDB).filter(VarietyDB.id.in_(variety_ids)).all()
        variety_contract_map = {v.id: v.contract_code for v in varieties if v.contract_code}

        # 批量获取 contract_code -> contract_id 映射
        # contract_code 通常是 symbol（不含后缀，如 "AU2506"）
        contract_codes = set(variety_contract_map.values())
        contracts_by_symbol = {
            c.symbol: c.id
            for c in db.query(FutContractDB).filter(FutContractDB.symbol.in_(contract_codes)).all()
        }
        contracts_by_ts = {
            c.ts_code: c.id
            for c in db.query(FutContractDB).filter(FutContractDB.ts_code.in_(contract_codes)).all()
        }
        contract_map = {**contracts_by_symbol, **contracts_by_ts}

        matched = 0
        unmatched_varieties = []

        for vid, code in variety_contract_map.items():
            cid = contract_map.get(code)
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

        # 统计回填后
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
