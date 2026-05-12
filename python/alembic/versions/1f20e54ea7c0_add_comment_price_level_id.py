"""add_comment_price_level_id

Revision ID: 1f20e54ea7c0
Revises: 27e011e4aced
Create Date: 2026-05-11 18:16:16.054371

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f20e54ea7c0'
down_revision: Union[str, None] = '27e011e4aced'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('price_level_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_comments_price_level_id'), ['price_level_id'], unique=False)
        batch_op.create_foreign_key('fk_comments_price_level_id', 'price_levels', ['price_level_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_comments_price_level_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_comments_price_level_id'))
        batch_op.drop_column('price_level_id')
