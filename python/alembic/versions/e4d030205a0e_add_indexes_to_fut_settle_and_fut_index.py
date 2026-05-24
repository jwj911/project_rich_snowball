"""add_indexes_to_fut_settle_and_fut_index

Revision ID: e4d030205a0e
Revises: e747b7cf7e09
Create Date: 2026-05-24 12:29:38.586864

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e4d030205a0e'
down_revision: Union[str, None] = 'e747b7cf7e09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('idx_fut_settle_ts_code', 'fut_settle', ['ts_code'], unique=False)
    op.create_index('idx_fut_settle_trade_date', 'fut_settle', ['trade_date'], unique=False)
    op.create_index('idx_fut_index_ts_code', 'fut_index', ['ts_code'], unique=False)
    op.create_index('idx_fut_index_trade_date', 'fut_index', ['trade_date'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_fut_index_trade_date', table_name='fut_index')
    op.drop_index('idx_fut_index_ts_code', table_name='fut_index')
    op.drop_index('idx_fut_settle_trade_date', table_name='fut_settle')
    op.drop_index('idx_fut_settle_ts_code', table_name='fut_settle')
