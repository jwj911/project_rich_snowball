"""add_pre_settlement_to_realtime_quotes

Revision ID: 8027809b23b3
Revises: a3af320d7bcd
Create Date: 2026-05-05 13:02:07.942986

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8027809b23b3'
down_revision: Union[str, None] = 'a3af320d7bcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('realtime_quotes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pre_settlement', sa.Numeric(precision=15, scale=4), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('realtime_quotes', schema=None) as batch_op:
        batch_op.drop_column('pre_settlement')
