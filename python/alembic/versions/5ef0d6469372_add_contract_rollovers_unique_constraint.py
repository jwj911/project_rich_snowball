"""add_contract_rollovers_unique_constraint

Revision ID: 5ef0d6469372
Revises: a5b2dc4019ff
Create Date: 2026-05-16 09:44:20.692275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ef0d6469372'
down_revision: Union[str, None] = 'a5b2dc4019ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('contract_rollovers', schema=None) as batch_op:
        batch_op.create_unique_constraint('uix_rollover_variety_date_new', ['variety_id', 'effective_date', 'new_contract_code'])


def downgrade() -> None:
    with op.batch_alter_table('contract_rollovers', schema=None) as batch_op:
        batch_op.drop_constraint('uix_rollover_variety_date_new', type_='unique')
