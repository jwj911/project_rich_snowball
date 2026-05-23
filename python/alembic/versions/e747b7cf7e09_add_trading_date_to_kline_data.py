"""add_trading_date_to_kline_data

Revision ID: e747b7cf7e09
Revises: 06867a613480
Create Date: 2026-05-23 23:21:19.258162

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e747b7cf7e09'
down_revision: Union[str, None] = '06867a613480'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('kline_data', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trading_date', sa.Date(), nullable=True))
        batch_op.create_index(batch_op.f('ix_kline_data_trading_date'), ['trading_date'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('kline_data', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_kline_data_trading_date'))
        batch_op.drop_column('trading_date')
