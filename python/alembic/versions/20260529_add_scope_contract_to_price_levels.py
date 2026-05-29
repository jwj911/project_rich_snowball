"""add scope and contract_id to price_levels

Revision ID: 20260529_price_levels_scope
Revises: 090b961056bb
Create Date: 2026-05-29 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260529_price_levels_scope'
down_revision: Union[str, None] = '090b961056bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('price_levels', sa.Column('contract_id', sa.Integer(), nullable=True))
    op.add_column('price_levels', sa.Column('scope', sa.String(length=20), nullable=False, server_default='continuous'))
    op.create_index(op.f('ix_price_levels_contract_id'), 'price_levels', ['contract_id'], unique=False)
    op.create_foreign_key(None, 'price_levels', 'fut_contracts', ['contract_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('uix_user_variety_type_price', 'price_levels', type_='unique')
    op.create_unique_constraint('uix_user_variety_type_price_scope_contract',
                                'price_levels',
                                ['user_id', 'variety_id', 'type', 'price', 'scope', 'contract_id'])


def downgrade() -> None:
    op.drop_constraint('uix_user_variety_type_price_scope_contract', 'price_levels', type_='unique')
    op.create_unique_constraint('uix_user_variety_type_price', 'price_levels',
                                ['user_id', 'variety_id', 'type', 'price'])
    op.drop_constraint(None, 'price_levels', type_='foreignkey')
    op.drop_index(op.f('ix_price_levels_contract_id'), table_name='price_levels')
    op.drop_column('price_levels', 'scope')
    op.drop_column('price_levels', 'contract_id')
