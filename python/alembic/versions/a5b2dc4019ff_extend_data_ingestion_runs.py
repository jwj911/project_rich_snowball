"""extend_data_ingestion_runs

Revision ID: a5b2dc4019ff
Revises: 7a40b39893ea
Create Date: 2026-05-14 07:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5b2dc4019ff'
down_revision: Union[str, None] = '7a40b39893ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('data_ingestion_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('duration_ms', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('error_sample', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('window_start', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('window_end', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('data_ingestion_runs', schema=None) as batch_op:
        batch_op.drop_column('window_end')
        batch_op.drop_column('window_start')
        batch_op.drop_column('error_sample')
        batch_op.drop_column('duration_ms')
