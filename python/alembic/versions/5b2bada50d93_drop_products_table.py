"""drop products table

Revision ID: 5b2bada50d93
Revises: 21238bb1117f
Create Date: 2026-05-28 16:14:42.050816

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5b2bada50d93'
down_revision: Union[str, None] = '21238bb1117f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_index('ix_products_name')
        batch_op.drop_index('ix_products_symbol')

    op.drop_table('products')


def downgrade() -> None:
    op.create_table('products',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('name', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('symbol', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('current_price', sa.NUMERIC(precision=19, scale=4), autoincrement=False, nullable=False),
    sa.Column('change_percent', sa.NUMERIC(precision=19, scale=4), autoincrement=False, nullable=True),
    sa.Column('pre_settlement', sa.NUMERIC(precision=15, scale=4), autoincrement=False, nullable=True),
    sa.Column('open_price', sa.NUMERIC(precision=19, scale=4), autoincrement=False, nullable=True),
    sa.Column('high', sa.NUMERIC(precision=19, scale=4), autoincrement=False, nullable=True),
    sa.Column('low', sa.NUMERIC(precision=19, scale=4), autoincrement=False, nullable=True),
    sa.Column('volume', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('category', sa.VARCHAR(length=20), autoincrement=False, nullable=True),
    sa.Column('margin', sa.NUMERIC(precision=10, scale=4), autoincrement=False, nullable=True),
    sa.Column('commission', sa.NUMERIC(precision=10, scale=4), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('limit_up', sa.NUMERIC(precision=19, scale=4), autoincrement=False, nullable=True),
    sa.Column('limit_down', sa.NUMERIC(precision=19, scale=4), autoincrement=False, nullable=True),
    sa.Column('price_precision', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='products_pkey'),
    sa.UniqueConstraint('symbol', name='products_symbol_key')
    )
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.create_index('ix_products_symbol', ['symbol'], unique=True)
        batch_op.create_index('ix_products_name', ['name'], unique=False)
