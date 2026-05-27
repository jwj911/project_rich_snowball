"""add_variety_id_to_comments

Revision ID: 7e710d06887b
Revises: ff017239116d
Create Date: 2026-05-27 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e710d06887b'
down_revision: Union[str, None] = 'ff017239116d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('variety_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_comments_variety_id'), ['variety_id'], unique=False)
        batch_op.create_foreign_key('fk_comments_variety_id', 'varieties', ['variety_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_comments_variety_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_comments_variety_id'))
        batch_op.drop_column('variety_id')
