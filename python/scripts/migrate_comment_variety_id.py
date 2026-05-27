"""迁移脚本：填充 CommentDB.variety_id

基于 ProductDB.symbol → VarietyDB.symbol 的映射，将现有评论的 product_id
转换为对应的 variety_id。脚本幂等，可重复执行。

用法：
    cd python
    python scripts/migrate_comment_variety_id.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from models import SessionLocal


def migrate():
    db = SessionLocal()
    try:
        # 1. 建立 product_id → variety_id 映射（通过 symbol 匹配）
        mapping_rows = db.execute(
            text("""
                SELECT p.id AS product_id, v.id AS variety_id
                FROM products p
                JOIN varieties v ON v.symbol = p.symbol
            """)
        ).fetchall()

        mapping = {row.product_id: row.variety_id for row in mapping_rows}
        print(f"找到 {len(mapping)} 个 product→variety 映射")

        if not mapping:
            print("无映射可填充，跳过")
            return

        # 2. 分批更新 comments.variety_id
        updated = 0
        for product_id, variety_id in mapping.items():
            result = db.execute(
                text("""
                    UPDATE comments
                    SET variety_id = :variety_id
                    WHERE product_id = :product_id
                      AND variety_id IS NULL
                """),
                {"product_id": product_id, "variety_id": variety_id},
            )
            updated += result.rowcount

        db.commit()
        print(f"成功更新 {updated} 条评论的 variety_id")

        # 3. 报告未匹配的评论
        unmatched = db.execute(
            text("""
                SELECT COUNT(*) FROM comments
                WHERE variety_id IS NULL
            """)
        ).scalar()
        if unmatched:
            print(f"警告：仍有 {unmatched} 条评论未找到对应 variety_id")

    finally:
        db.close()


if __name__ == "__main__":
    migrate()
