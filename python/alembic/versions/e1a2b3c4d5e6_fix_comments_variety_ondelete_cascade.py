"""fix_comments_variety_ondelete_cascade

Revision ID: e1a2b3c4d5e6
Revises: d4e5f6a7b8c9
Create Date: 2026-06-04 14:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5e6'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dialect = op.get_context().dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table('comments', schema=None) as batch_op:
            # SQLite batch_alter_table 重建表时自动处理外键变更
            batch_op.drop_constraint('fk_comments_variety_id_varieties', type_='foreignkey')
            batch_op.create_foreign_key(
                'fk_comments_variety_id_varieties',
                'varieties',
                ['variety_id'],
                ['id'],
                ondelete='CASCADE'
            )
    else:
        # PostgreSQL: 先查询现有约束名，再删除并重建
        conn = op.get_bind()
        result = conn.execute(
            sa.text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'comments'::regclass AND contype = 'f' "
                "AND confrelid = 'varieties'::regclass"
            )
        )
        existing = {row[0] for row in result}

        for name in existing:
            op.drop_constraint(name, 'comments', type_='foreignkey')

        op.create_foreign_key(
            'fk_comments_variety_id_varieties',
            'comments',
            'varieties',
            ['variety_id'],
            ['id'],
            ondelete='CASCADE'
        )


def downgrade() -> None:
    dialect = op.get_context().dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table('comments', schema=None) as batch_op:
            batch_op.drop_constraint('fk_comments_variety_id_varieties', type_='foreignkey')
            batch_op.create_foreign_key(
                'fk_comments_variety_id_varieties',
                'varieties',
                ['variety_id'],
                ['id'],
                ondelete='SET NULL'
            )
    else:
        conn = op.get_bind()
        result = conn.execute(
            sa.text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'comments'::regclass AND contype = 'f' "
                "AND confrelid = 'varieties'::regclass"
            )
        )
        existing = {row[0] for row in result}

        for name in existing:
            op.drop_constraint(name, 'comments', type_='foreignkey')

        op.create_foreign_key(
            'fk_comments_variety_id_varieties',
            'comments',
            'varieties',
            ['variety_id'],
            ['id'],
            ondelete='SET NULL'
        )
