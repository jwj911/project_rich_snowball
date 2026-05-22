"""add_missing_indexes

Revision ID: 2f4b824f1162
Revises: bd656c03f8dc
Create Date: 2026-05-21 20:03:02.319395

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2f4b824f1162'
down_revision: Union[str, None] = 'bd656c03f8dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 仅添加缺失的索引，不修改列类型或约束
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.create_index('idx_comments_created_at', ['created_at'], unique=False)

    with op.batch_alter_table('kline_data', schema=None) as batch_op:
        batch_op.create_index('idx_kline_contract_period_time', ['contract_id', 'period', 'trading_time'], unique=False)

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.create_index('ix_products_name', ['name'], unique=False)

    with op.batch_alter_table('varieties', schema=None) as batch_op:
        batch_op.create_index('ix_varieties_contract_code', ['contract_code'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('varieties', schema=None) as batch_op:
        batch_op.drop_index('ix_varieties_contract_code')

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_index('ix_products_name')

    with op.batch_alter_table('kline_data', schema=None) as batch_op:
        batch_op.drop_index('idx_kline_contract_period_time')

    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_index('idx_comments_created_at')
