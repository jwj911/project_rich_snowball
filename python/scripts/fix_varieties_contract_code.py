"""
修复 varieties.contract_code 同步脚本
===================================
将 varieties 表中每个品种的 contract_code 更新为 fut_contracts 中最新活跃合约代码。
解决 init_varieties 硬编码默认值导致主力合约信息过时的问题。

运行方式:
    cd python
    .venv\Scripts\python.exe scripts/fix_varieties_contract_code.py [--dry-run]

输出:
    - 更新品种数 / 跳过品种数 / 异常品种数
    - 更新前后对比明细

规则:
    1. 对每个品种，查询 fut_contracts 中 contract_type != 'CONTINUOUS' 的合约
    2. 按 delist_date DESC 取最新一条（即将到期的最新合约）
    3. 提取 symbol 字段（如 MA2706），去掉 .EXCHANGE 后缀
    4. 更新 varieties.contract_code = 提取的合约代码
    5. 若 symbol 为空（如仅存在 ts_code），则回退到 ts_code 去掉后缀
    6. 无法找到合约的品种标记为异常，需要人工检查
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from models import SessionLocal, FutContractDB, VarietyDB


def _resolve_latest_contract(db: Session, variety: VarietyDB) -> FutContractDB | None:
    """查询品种最新活跃具体合约（contract_type='NORMAL'，按 delist_date 倒序）。"""
    return (
        db.query(FutContractDB)
        .filter(
            FutContractDB.fut_code == variety.symbol,
            FutContractDB.contract_type == "NORMAL",
        )
        .order_by(FutContractDB.delist_date.desc())
        .first()
    )


def fix_varieties_contract_code(db: Session, dry_run: bool = False) -> dict:
    """执行修复，返回统计信息。"""
    varieties = db.query(VarietyDB).order_by(VarietyDB.id).all()

    updated = 0
    skipped = 0
    failed = 0
    details: list[dict] = []

    for v in varieties:
        old_code = v.contract_code

        latest_contract = _resolve_latest_contract(db, v)
        if not latest_contract:
            failed += 1
            details.append(
                {
                    "symbol": v.symbol,
                    "name": v.name,
                    "old_code": old_code,
                    "new_code": None,
                    "status": "FAILED",
                    "reason": "无 NORMAL 类型合约",
                }
            )
            continue

        # 提取合约代码：优先 ts_code 去掉后缀（通用格式），回退 symbol
        if latest_contract.ts_code and "." in latest_contract.ts_code:
            new_code = latest_contract.ts_code.split(".")[0]
        elif latest_contract.symbol:
            new_code = latest_contract.symbol
        else:
            failed += 1
            details.append(
                {
                    "symbol": v.symbol,
                    "name": v.name,
                    "old_code": old_code,
                    "new_code": None,
                    "status": "FAILED",
                    "reason": "无法解析合约代码",
                }
            )
            continue

        # 月份合法性校验（最后两位不能为 00）
        if len(new_code) >= 4:
            month_str = new_code[-2:]
            if month_str.isdigit() and month_str == "00":
                failed += 1
                details.append(
                    {
                        "symbol": v.symbol,
                        "name": v.name,
                        "old_code": old_code,
                        "new_code": new_code,
                        "status": "FAILED",
                        "reason": f"合约月份异常: {new_code}",
                    }
                )
                continue

        if old_code == new_code:
            skipped += 1
            details.append(
                {
                    "symbol": v.symbol,
                    "name": v.name,
                    "old_code": old_code,
                    "new_code": new_code,
                    "status": "SKIPPED",
                    "reason": "已是最新",
                }
            )
            continue

        if not dry_run:
            v.contract_code = new_code

        updated += 1
        details.append(
            {
                "symbol": v.symbol,
                "name": v.name,
                "old_code": old_code,
                "new_code": new_code,
                "status": "UPDATED",
                "reason": None,
            }
        )

    if not dry_run:
        db.commit()

    return {
        "total": len(varieties),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "details": details,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="修复 varieties.contract_code 同步问题")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不执行更新")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = fix_varieties_contract_code(db, dry_run=args.dry_run)

        mode = "[DRY RUN]" if args.dry_run else "[COMMIT]"
        print(f"\n{mode} 修复结果汇总")
        print("=" * 50)
        print(f"  总品种数: {result['total']}")
        print(f"  已更新:   {result['updated']}")
        print(f"  已跳过:   {result['skipped']}")
        print(f"  失败:     {result['failed']}")
        print()

        if result["updated"] > 0:
            print("更新明细:")
            print("-" * 50)
            for d in result["details"]:
                if d["status"] == "UPDATED":
                    print(f"  {d['symbol']:6} {d['old_code'] or 'None':10} -> {d['new_code']:10}  ({d['name']})")

        if result["failed"] > 0:
            print("\n失败明细:")
            print("-" * 50)
            for d in result["details"]:
                if d["status"] == "FAILED":
                    print(f"  {d['symbol']:6} {d['old_code'] or 'None':10} -> {d['new_code'] or 'N/A':10}  [{d['reason']}]  ({d['name']})")

        print()
        print(f"完成时间: {datetime.now(timezone.utc).isoformat()}")

    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
