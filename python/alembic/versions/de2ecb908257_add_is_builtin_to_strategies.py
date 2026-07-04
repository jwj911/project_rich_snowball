"""add is_builtin to strategies

Revision ID: de2ecb908257
Revises: 481fd8a02d05
Create Date: 2026-07-04 23:29:41.475087

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'de2ecb908257'
down_revision: Union[str, None] = '481fd8a02d05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('strategies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_builtin', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    with op.batch_alter_table('strategies', schema=None) as batch_op:
        batch_op.drop_column('is_builtin')
