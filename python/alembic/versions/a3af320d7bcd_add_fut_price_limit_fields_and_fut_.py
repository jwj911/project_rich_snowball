"""add_fut_price_limit_fields_and_fut_mapping_support

Revision ID: a3af320d7bcd
Revises: 47441c736275
Create Date: 2026-05-05 12:49:00.834661

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3af320d7bcd'
down_revision: Union[str, None] = '47441c736275'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing columns to fut_price_limits per Tushare ft_limit doc
    with op.batch_alter_table('fut_price_limits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('m_ratio', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('cont', sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('fut_price_limits', schema=None) as batch_op:
        batch_op.drop_column('cont')
        batch_op.drop_column('m_ratio')
        batch_op.drop_column('name')
