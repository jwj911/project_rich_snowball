"""
检测并清理 kline_data 表中 contract_id 为 NULL 的重复记录。

问题背景：
- kline_data 的唯一约束为 (variety_id, contract_id, period, trading_time)
- SQL 标准中 NULL != NULL，因此 contract_id=NULL 的重复行不会被唯一约束阻止
- insert_kline_bulk 已在新写入时跳过 contract_id 无法解析的行
- 本脚本用于处理升级前已写入的重复历史数据

运行方式：
    cd python
    python scripts/dedup_kline_null_contract.py [--dry-run]

输出：
    - 重复组数量和重复行总数
    - 按品种/周期汇总
    - 实际删除条数（dry-run 时不删除）
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from models import SessionLocal, engine, _IS_SQLITE


def _find_duplicates(db):
    """查找 contract_id IS NULL 的重复记录。"""
    # 使用 SQL 窗口函数或子查询找出重复组
    if _IS_SQLITE:
        # SQLite 支持窗口函数（3.25+）
        sql = text("""
            SELECT variety_id, period, trading_time, COUNT(*) as cnt
            FROM kline_data
            WHERE contract_id IS NULL
            GROUP BY variety_id, period, trading_time
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
        """)
    else:
        sql = text("""
            SELECT variety_id, period, trading_time, COUNT(*) as cnt
            FROM kline_data
            WHERE contract_id IS NULL
            GROUP BY variety_id, period, trading_time
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
        """)
    return db.execute(sql).fetchall()


def _delete_duplicates_keep_first(db):
    """删除重复记录，每组保留 id 最小的一条。"""
    if _IS_SQLITE:
        # SQLite: 使用 DELETE with rowid 子查询
        sql = text("""
            DELETE FROM kline_data
            WHERE id IN (
                SELECT id FROM kline_data AS outer_table
                WHERE contract_id IS NULL
                  AND id > (
                      SELECT MIN(id) FROM kline_data
                      WHERE variety_id = outer_table.variety_id
                        AND period = outer_table.period
                        AND trading_time = outer_table.trading_time
                        AND contract_id IS NULL
                  )
            )
        """)
    else:
        # PostgreSQL: 使用 DELETE with CTE
        sql = text("""
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY variety_id, period, trading_time
                           ORDER BY id
                       ) AS rn
                FROM kline_data
                WHERE contract_id IS NULL
            )
            DELETE FROM kline_data
            WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """)
    result = db.execute(sql)
    return result.rowcount if hasattr(result, "rowcount") else 0


def main():
    parser = argparse.ArgumentParser(description="Dedup kline_data rows with NULL contract_id")
    parser.add_argument("--dry-run", action="store_true", help="只报告，不删除")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # 1. 统计 NULL contract_id 总数
        total_null = db.execute(
            text("SELECT COUNT(*) FROM kline_data WHERE contract_id IS NULL")
        ).scalar()
        print(f"contract_id 为 NULL 的总记录数: {total_null}")

        if total_null == 0:
            print("无需处理")
            return

        # 2. 查找重复组
        duplicates = _find_duplicates(db)
        if not duplicates:
            print("未发现重复记录（contract_id=NULL 的记录均唯一）")
            return

        total_dup_groups = len(duplicates)
        total_dup_rows = sum(row[3] for row in duplicates)
        print(f"\n发现 {total_dup_groups} 组重复，涉及 {total_dup_rows} 行记录")
        print("\n前 20 组重复详情:")
        for variety_id, period, trading_time, cnt in duplicates[:20]:
            print(f"  variety_id={variety_id}, period={period}, trading_time={trading_time}, 重复数={cnt}")

        if args.dry_run:
            print("\n[Dry-run] 未执行删除。如需清理，请去掉 --dry-run 重新运行。")
            return

        # 3. 执行去重
        print("\n正在删除重复记录（每组保留 id 最小的一条）...")
        deleted = _delete_duplicates_keep_first(db)
        db.commit()
        print(f"删除完成，共删除 {deleted} 行重复记录")

        # 4. 验证
        remaining_null = db.execute(
            text("SELECT COUNT(*) FROM kline_data WHERE contract_id IS NULL")
        ).scalar()
        remaining_dups = _find_duplicates(db)
        print(f"清理后 NULL contract_id 记录数: {remaining_null}")
        print(f"剩余重复组数: {len(remaining_dups)}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
