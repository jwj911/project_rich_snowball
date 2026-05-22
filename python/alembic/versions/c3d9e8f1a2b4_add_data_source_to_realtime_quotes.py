"""add data_source to realtime_quotes

Revision ID: c3d9e8f1a2b4
Revises: ab0c82d41a97
Create Date: 2026-05-22 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d9e8f1a2b4'
down_revision: Union[str, None] = '2f4b824f1162'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('realtime_quotes', sa.Column('data_source', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('realtime_quotes', 'data_source')
