"""add_limit_price_precision_and_trading_calendar

Revision ID: 06867a613480
Revises: c3d9e8f1a2b4
Create Date: 2026-05-22 20:17:54.582335

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06867a613480'
down_revision: Union[str, None] = 'c3d9e8f1a2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('trading_calendar',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('trade_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_trading_day', sa.Boolean(), nullable=False),
    sa.Column('day_session_start', sa.String(length=5), nullable=True),
    sa.Column('day_session_end', sa.String(length=5), nullable=True),
    sa.Column('night_session_start', sa.String(length=5), nullable=True),
    sa.Column('night_session_end', sa.String(length=5), nullable=True),
    sa.Column('exchange', sa.String(length=10), nullable=True),
    sa.Column('remark', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trade_date', 'exchange', name='uix_calendar_date_exchange')
    )
    with op.batch_alter_table('trading_calendar', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_trading_calendar_trade_date'), ['trade_date'], unique=False)

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('limit_up', sa.Numeric(precision=19, scale=4), nullable=True))
        batch_op.add_column(sa.Column('limit_down', sa.Numeric(precision=19, scale=4), nullable=True))
        batch_op.add_column(sa.Column('price_precision', sa.Integer(), nullable=True))

    with op.batch_alter_table('realtime_quotes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('limit_up', sa.Numeric(precision=19, scale=4), nullable=True))
        batch_op.add_column(sa.Column('limit_down', sa.Numeric(precision=19, scale=4), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('realtime_quotes', schema=None) as batch_op:
        batch_op.drop_column('limit_down')
        batch_op.drop_column('limit_up')

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('price_precision')
        batch_op.drop_column('limit_down')
        batch_op.drop_column('limit_up')

    with op.batch_alter_table('trading_calendar', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_trading_calendar_trade_date'))

    op.drop_table('trading_calendar')
