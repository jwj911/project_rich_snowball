"""drop comments product_id column

Revision ID: 090b961056bb
Revises: 71cca1a466b4
Create Date: 2026-05-28 20:06:31.436402

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '090b961056bb'
down_revision: Union[str, None] = '71cca1a466b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_column('product_id')


def downgrade() -> None:
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('product_id', sa.INTEGER(), autoincrement=False, nullable=True))
