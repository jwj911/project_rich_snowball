"""add_price_levels_and_watchlist_unique

Revision ID: b2178b180093
Revises: 47441c736275
Create Date: 2026-05-14 20:58:01.432973

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2178b180093'
down_revision: Union[str, None] = '47441c736275'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建 price_levels 表
    op.create_table(
        'price_levels',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('variety_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('price', sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['variety_id'], ['varieties.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'variety_id', 'type', 'price', name='uix_price_level')
    )
    op.create_index(op.f('ix_price_levels_id'), 'price_levels', ['id'], unique=False)

    # 在 comments 表添加 price_level_id 列（SQLite batch mode 外键需单独处理）
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('price_level_id', sa.Integer(), nullable=True))

    # 单独创建外键约束
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_comments_price_level', 'price_levels', ['price_level_id'], ['id'])

    # 在 watchlists 表添加唯一约束
    with op.batch_alter_table('watchlists', schema=None) as batch_op:
        batch_op.create_unique_constraint('uix_watchlist_user_variety', ['user_id', 'variety_id'])


def downgrade() -> None:
    # 移除 watchlists 唯一约束
    with op.batch_alter_table('watchlists', schema=None) as batch_op:
        batch_op.drop_constraint('uix_watchlist_user_variety', type_='unique')

    # 移除 comments 的外键和列
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_comments_price_level', type_='foreignkey')
        batch_op.drop_column('price_level_id')

    # 删除 price_levels 表
    op.drop_index(op.f('ix_price_levels_id'), table_name='price_levels')
    op.drop_table('price_levels')
