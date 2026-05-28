"""merge_comment_variety_and_fut_indexes

Revision ID: 36075c47fab3
Revises: 7e710d06887b, e4d030205a0e
Create Date: 2026-05-28 15:40:28.317923

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36075c47fab3'
down_revision: Union[str, None] = ('7e710d06887b', 'e4d030205a0e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
