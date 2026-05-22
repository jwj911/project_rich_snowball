"""add_watchlist_user_variety_unique_constraint

Revision ID: a97d7113bdec
Revises: 5ef0d6469372
Create Date: 2026-05-16 09:57:51.043854

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a97d7113bdec'
down_revision: Union[str, None] = '5ef0d6469372'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('watchlists', schema=None) as batch_op:
        batch_op.create_unique_constraint('uix_watchlist_user_variety', ['user_id', 'variety_id'])


def downgrade() -> None:
    with op.batch_alter_table('watchlists', schema=None) as batch_op:
        batch_op.drop_constraint('uix_watchlist_user_variety', type_='unique')
