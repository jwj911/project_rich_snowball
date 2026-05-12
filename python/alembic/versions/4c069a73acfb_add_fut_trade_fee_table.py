"""add_fut_trade_fee_table

Revision ID: 4c069a73acfb
Revises: 00da0b5a5a4a
Create Date: 2026-05-09 16:57:59.114153

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c069a73acfb'
down_revision: Union[str, None] = '00da0b5a5a4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('fut_trade_fee',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('exchange', sa.String(length=20), nullable=False),
    sa.Column('contract_name', sa.String(length=50), nullable=False),
    sa.Column('contract_code', sa.String(length=20), nullable=False),
    sa.Column('current_price', sa.Float(), nullable=True),
    sa.Column('up_limit', sa.Float(), nullable=True),
    sa.Column('down_limit', sa.Float(), nullable=True),
    sa.Column('margin_buy_open', sa.Float(), nullable=True),
    sa.Column('margin_sell_open', sa.Float(), nullable=True),
    sa.Column('margin_per_hand', sa.Numeric(precision=15, scale=2), nullable=True),
    sa.Column('fee_open_rate', sa.Float(), nullable=True),
    sa.Column('fee_open_fixed', sa.String(length=50), nullable=True),
    sa.Column('fee_close_yesterday_rate', sa.Float(), nullable=True),
    sa.Column('fee_close_yesterday_fixed', sa.String(length=50), nullable=True),
    sa.Column('fee_close_today_rate', sa.Float(), nullable=True),
    sa.Column('fee_close_today_fixed', sa.String(length=50), nullable=True),
    sa.Column('tick_profit_gross', sa.Integer(), nullable=True),
    sa.Column('fee_total', sa.Float(), nullable=True),
    sa.Column('tick_profit_net', sa.Float(), nullable=True),
    sa.Column('remark', sa.String(length=20), nullable=True),
    sa.Column('fee_updated_at', sa.DateTime(), nullable=True),
    sa.Column('price_updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('contract_code', 'fee_updated_at', name='uix_fut_trade_fee')
    )
    with op.batch_alter_table('fut_trade_fee', schema=None) as batch_op:
        batch_op.create_index('idx_fut_trade_fee_lookup', ['exchange', 'contract_code', 'fee_updated_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_fut_trade_fee_contract_code'), ['contract_code'], unique=False)
        batch_op.create_index(batch_op.f('ix_fut_trade_fee_exchange'), ['exchange'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('fut_trade_fee', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_fut_trade_fee_exchange'))
        batch_op.drop_index(batch_op.f('ix_fut_trade_fee_contract_code'))
        batch_op.drop_index('idx_fut_trade_fee_lookup')

    op.drop_table('fut_trade_fee')
