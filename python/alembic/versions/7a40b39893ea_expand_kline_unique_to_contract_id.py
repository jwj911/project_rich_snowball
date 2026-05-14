"""expand_kline_unique_to_contract_id

Revision ID: 7a40b39893ea
Revises: 55adbee43f2f
Create Date: 2026-05-12 21:38:39.677938

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7a40b39893ea'
down_revision: Union[str, None] = '55adbee43f2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('kline_data', schema=None) as batch_op:
        batch_op.drop_constraint('uix_kline', type_='unique')
        batch_op.create_unique_constraint('uix_kline_contract', ['variety_id', 'contract_id', 'period', 'trading_time'])


def downgrade() -> None:
    with op.batch_alter_table('kline_data', schema=None) as batch_op:
        batch_op.drop_constraint('uix_kline_contract', type_='unique')
        batch_op.create_unique_constraint('uix_kline', ['variety_id', 'period', 'trading_time'])
