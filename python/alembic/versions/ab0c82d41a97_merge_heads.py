"""merge heads

Revision ID: ab0c82d41a97
Revises: 2f4b824f1162, b2178b180093
Create Date: 2026-05-22 17:26:55.492735

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab0c82d41a97'
down_revision: Union[str, None] = ('2f4b824f1162', 'b2178b180093')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
