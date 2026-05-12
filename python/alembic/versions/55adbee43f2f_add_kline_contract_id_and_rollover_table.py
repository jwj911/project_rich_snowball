"""add_kline_contract_id_and_rollover_table

Revision ID: 55adbee43f2f
Revises: 1f20e54ea7c0
Create Date: 2026-05-12 16:03:32.617313

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55adbee43f2f'
down_revision: Union[str, None] = '1f20e54ea7c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('contract_rollovers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('variety_id', sa.Integer(), nullable=False),
        sa.Column('old_contract_id', sa.Integer(), nullable=True),
        sa.Column('new_contract_id', sa.Integer(), nullable=True),
        sa.Column('old_contract_code', sa.String(length=20), nullable=True),
        sa.Column('new_contract_code', sa.String(length=20), nullable=True),
        sa.Column('effective_date', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['new_contract_id'], ['fut_contracts.id'], ),
        sa.ForeignKeyConstraint(['old_contract_id'], ['fut_contracts.id'], ),
        sa.ForeignKeyConstraint(['variety_id'], ['varieties.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('contract_rollovers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_contract_rollovers_effective_date'), ['effective_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_contract_rollovers_variety_id'), ['variety_id'], unique=False)

    with op.batch_alter_table('kline_data', schema=None) as batch_op:
        batch_op.add_column(sa.Column('contract_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_kline_data_contract_id'), ['contract_id'], unique=False)
        batch_op.create_foreign_key('fk_kline_data_contract_id', 'fut_contracts', ['contract_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('kline_data', schema=None) as batch_op:
        batch_op.drop_constraint('fk_kline_data_contract_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_kline_data_contract_id'))
        batch_op.drop_column('contract_id')

    with op.batch_alter_table('contract_rollovers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_contract_rollovers_variety_id'))
        batch_op.drop_index(batch_op.f('ix_contract_rollovers_effective_date'))

    op.drop_table('contract_rollovers')
