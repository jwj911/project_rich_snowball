"""add_price_levels_table

Revision ID: 27e011e4aced
Revises: 4c069a73acfb
Create Date: 2026-05-11 18:10:13.829431

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '27e011e4aced'
down_revision: Union[str, None] = '4c069a73acfb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('price_levels',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('variety_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('price', sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['variety_id'], ['varieties.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'variety_id', 'type', 'price', name='uix_user_variety_type_price')
    )
    with op.batch_alter_table('price_levels', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_price_levels_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_price_levels_variety_id'), ['variety_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('price_levels', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_price_levels_variety_id'))
        batch_op.drop_index(batch_op.f('ix_price_levels_user_id'))

    op.drop_table('price_levels')
