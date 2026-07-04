#!/usr/bin/env python3
"""更新 factor_definitions 的 package_id 为从1开始的连续编号。

用法：
    cd python
    .venv/Scripts/python.exe scripts/migrate_factor_package_id.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dependencies import get_db  # noqa: E402, I001
from models import FactorDefinitionDB  # noqa: E402, I001

PACK_MAP = {
    "factor_pack_021": "1",
    "factor_pack_022": "2",
    "factor_pack_023": "3",
    "factor_pack_024": "4",
    "factor_pack_025": "5",
    "factor_pack_026": "6",
    "factor_pack_027": "7",
    "factor_pack_028": "8",
    "factor_pack_029": "9",
    "factor_pack_030": "10",
    "factor_pack_031": "11",
    "factor_pack_032": "12",
}


def main() -> None:
    db = next(get_db())
    updated = 0
    try:
        factors = db.query(FactorDefinitionDB).all()
        for f in factors:
            old_id = f.package_id
            new_id = PACK_MAP.get(old_id)
            if new_id and old_id != new_id:
                f.package_id = new_id
                updated += 1
                print(f"  {f.factor_id}: {old_id} -> {new_id}")
            elif not new_id:
                print(f"  WARN: {f.factor_id} has unknown package_id={old_id}, skipped")
        db.commit()
        print(f"\nDone: updated={updated} / total={len(factors)}")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
