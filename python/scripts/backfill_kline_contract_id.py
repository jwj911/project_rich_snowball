"""
回填 K 线合约归属脚本（历史语义正确化）
============================================
将 kline_data 表中 contract_id 为 null 的记录，按历史换月时段（contract_rollovers）
匹配具体合约进行回填；无历史换月记录时回退到当前 variety.contract_code。

运行方式：
    cd python
    python scripts/backfill_kline_contract_id.py

输出：
    - 回填成功条数（按品种/合约/时段细分）
    - 无法匹配的品种列表
    - 回填后的 null 计数
    - CSV 明细报告（默认输出到 backfill_report.csv）

语义约定：
    - rollover.effective_date 为切换日期；该日期之前归属 old_contract，之后归属 new_contract
    - 首个 rollover 之前的时段：若 old_contract_id 存在则使用，否则 fallback 到当前主力合约
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from models import SessionLocal, KlineDataDB, VarietyDB, ContractRolloverDB


def _resolve_contract_id(db: Session, contract_code: str) -> int | None:
    """将 contract_code（如 AU2506, MA2506）解析为 fut_contracts.id。"""
    if not contract_code:
        return None

    from models import FutContractDB

    c = db.query(FutContractDB).filter(FutContractDB.symbol == contract_code).first()
    if c:
        return c.id

    c = db.query(FutContractDB).filter(FutContractDB.ts_code == contract_code).first()
    if c:
        return c.id

    if len(contract_code) > 4 and contract_code[-4:].isdigit():
        zce_symbol = contract_code[:-4] + contract_code[-3:]
        c = db.query(FutContractDB).filter(FutContractDB.symbol == zce_symbol).first()
        if c:
            return c.id
        for suffix in (".ZCE", ".DCE", ".SHF", ".SHFE", ".INE", ".CFFEX"):
            c = db.query(FutContractDB).filter(FutContractDB.ts_code == contract_code + suffix).first()
            if c:
                return c.id

    return None


def _build_segments(
    db: Session,
    variety_id: int,
    rollovers: list[ContractRolloverDB],
    default_code: str | None,
) -> list[dict[str, Any]]:
    """根据 rollover 记录构建 [start, end) -> contract_id 的时段列表。"""
    segments: list[dict[str, Any]] = []

    if not rollovers:
        # 优先查找品种的所有历史合约，按生命周期构建时段
        from models import VarietyDB, FutContractDB

        variety = db.query(VarietyDB).filter(VarietyDB.id == variety_id).first()
        if variety:
            contracts = (
                db.query(FutContractDB)
                .filter(FutContractDB.fut_code == variety.symbol)
                .order_by(FutContractDB.list_date)
                .all()
            )
            for c in contracts:
                if c.id:
                    segments.append({
                        "start": c.list_date or datetime.min,
                        "end": c.delist_date or datetime.max,
                        "contract_id": c.id,
                        "contract_code": c.symbol,
                        "note": "contract_lifecycle",
                    })
            # 合并连续或重叠的时段
            if len(segments) > 1:
                merged = [segments[0]]
                for seg in segments[1:]:
                    last = merged[-1]
                    if last["contract_id"] == seg["contract_id"] or last["end"] >= seg["start"]:
                        last["end"] = max(last["end"], seg["end"])
                        last["note"] = f"{last['note']}+{seg['note']}"
                    else:
                        merged.append(seg)
                segments = merged

        # 如果仍无时段，fallback 到当前主力合约（限制在合约生命周期内）
        if not segments and default_code:
            cid = _resolve_contract_id(db, default_code)
            if cid:
                contract = db.query(FutContractDB).filter(FutContractDB.id == cid).first()
                start = datetime.min
                end = datetime.max
                note = "fallback_current_main"
                if contract:
                    if contract.list_date:
                        start = contract.list_date
                        note = "fallback_current_main_lifecycle"
                    if contract.delist_date:
                        end = contract.delist_date
                segments.append({
                    "start": start,
                    "end": end,
                    "contract_id": cid,
                    "contract_code": default_code,
                    "note": note,
                })
        return segments

    rollovers = sorted(rollovers, key=lambda r: r.effective_date)

    first = rollovers[0]
    if first.old_contract_id:
        segments.append({
            "start": datetime.min,
            "end": first.effective_date,
            "contract_id": first.old_contract_id,
            "contract_code": first.old_contract_code,
            "note": "pre_first_rollover_old",
        })
    elif default_code:
        cid = _resolve_contract_id(db, default_code)
        if cid:
            segments.append({
                "start": datetime.min,
                "end": first.effective_date,
                "contract_id": cid,
                "contract_code": default_code,
                "note": "pre_first_rollover_fallback",
            })

    for i, r in enumerate(rollovers):
        start = r.effective_date
        end = rollovers[i + 1].effective_date if i + 1 < len(rollovers) else datetime.max
        cid = r.new_contract_id
        code = r.new_contract_code
        if cid:
            segments.append({
                "start": start,
                "end": end,
                "contract_id": cid,
                "contract_code": code,
                "note": f"rollover_{i+1}",
            })

    if len(segments) <= 1:
        return segments

    merged: list[dict[str, Any]] = [segments[0]]
    for seg in segments[1:]:
        last = merged[-1]
        if last["contract_id"] == seg["contract_id"] and last["end"] == seg["start"]:
            last["end"] = seg["end"]
            last["note"] = f"{last['note']}+{seg['note']}"
        else:
            merged.append(seg)

    return merged


def _backfill_segments(
    db: Session,
    variety_id: int,
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """对单个品种按时段批量更新 K 线 contract_id。返回更新明细列表。"""
    rows: list[dict[str, Any]] = []
    for seg in segments:
        q = (
            db.query(KlineDataDB)
            .filter(
                KlineDataDB.variety_id == variety_id,
                KlineDataDB.contract_id.is_(None),
                KlineDataDB.trading_time >= seg["start"],
                KlineDataDB.trading_time < seg["end"],
            )
        )
        count = q.update(
            {"contract_id": seg["contract_id"]},
            synchronize_session=False,
        )
        if count:
            rows.append({
                "variety_id": variety_id,
                "contract_id": seg["contract_id"],
                "contract_code": seg["contract_code"],
                "start": seg["start"].isoformat() if seg["start"] != datetime.min else "-inf",
                "end": seg["end"].isoformat() if seg["end"] != datetime.max else "+inf",
                "updated": count,
                "note": seg["note"],
            })
    return rows


def backfill(dry_run: bool = False, report_csv: str = "backfill_report.csv", db: Session | None = None) -> dict[str, Any]:
    should_close = db is None
    db = db or SessionLocal()
    report_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "total_null_before": 0,
        "total_matched": 0,
        "total_null_after": 0,
        "varieties_processed": 0,
        "unmatched_varieties": [],
        "csv_path": report_csv,
    }

    try:
        total_null = db.query(KlineDataDB).filter(KlineDataDB.contract_id.is_(None)).count()
        summary["total_null_before"] = total_null
        print(f"回填前 contract_id 为 null 的记录: {total_null}")
        if total_null == 0:
            print("无需回填")
            return summary

        variety_ids = (
            db.query(KlineDataDB.variety_id)
            .filter(KlineDataDB.contract_id.is_(None))
            .distinct()
            .all()
        )
        variety_ids = sorted([v[0] for v in variety_ids])
        summary["varieties_processed"] = len(variety_ids)
        print(f"涉及品种数: {len(variety_ids)}")

        varieties = db.query(VarietyDB).filter(VarietyDB.id.in_(variety_ids)).all()
        variety_map = {v.id: v for v in varieties}

        rollovers_all = (
            db.query(ContractRolloverDB)
            .filter(ContractRolloverDB.variety_id.in_(variety_ids))
            .order_by(ContractRolloverDB.variety_id, ContractRolloverDB.effective_date)
            .all()
        )
        rollover_map: dict[int, list[ContractRolloverDB]] = {}
        for r in rollovers_all:
            rollover_map.setdefault(r.variety_id, []).append(r)

        for vid in variety_ids:
            v = variety_map.get(vid)
            default_code = v.contract_code if v else None
            rollovers = rollover_map.get(vid, [])

            segments = _build_segments(db, vid, rollovers, default_code)
            if not segments:
                summary["unmatched_varieties"].append({
                    "variety_id": vid,
                    "default_code": default_code,
                    "reason": "no_segments_built",
                })
                print(f"  Variety {vid}: 无法构建任何时段 (default_code={default_code})")
                continue

            rows = _backfill_segments(db, vid, segments)
            for r in rows:
                report_rows.append(r)
                summary["total_matched"] += r["updated"]
                print(f"  Variety {vid} -> Contract {r['contract_code']} ({r['contract_id']}): "
                      f"时段 [{r['start']}, {r['end']}) 回填 {r['updated']} 条")

        if dry_run:
            db.rollback()
            print("\n[DRY RUN] 已回滚，未实际写入")
        else:
            db.commit()
            print("\n已提交")

        remaining_null = db.query(KlineDataDB).filter(KlineDataDB.contract_id.is_(None)).count()
        summary["total_null_after"] = remaining_null

        _print_report(summary)
        _write_csv(report_csv, report_rows, summary)

    finally:
        if should_close:
            db.close()

    return summary


def _print_report(summary: dict[str, Any]) -> None:
    print("\n========== 回填报告 ==========")
    print(f"回填前 null 数: {summary['total_null_before']}")
    print(f"回填成功:       {summary['total_matched']}")
    print(f"回填后 null 数: {summary['total_null_after']}")
    print(f"处理品种数:     {summary['varieties_processed']}")
    if summary["unmatched_varieties"]:
        print(f"\n无法匹配的品种 ({len(summary['unmatched_varieties'])}):")
        for item in summary["unmatched_varieties"]:
            print(f"  variety_id={item['variety_id']}, default_code={item['default_code']}, reason={item['reason']}")
    print("==============================")


def _write_csv(path: str, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    if not rows:
        return
    fieldnames = ["variety_id", "contract_id", "contract_code", "start", "end", "updated", "note"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV 明细报告已写入: {path} ({len(rows)} 行)")


def main():
    parser = argparse.ArgumentParser(description="回填 K 线合约归属（历史语义正确化）")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际写入")
    parser.add_argument("--report", default="backfill_report.csv", help="CSV 报告路径")
    args = parser.parse_args()

    backfill(dry_run=args.dry_run, report_csv=args.report)


if __name__ == "__main__":
    main()
