"""add_user_role

Revision ID: b057bf013236
Revises: 20260529_price_levels_scope
Create Date: 2026-05-30 21:39:17.490463

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b057bf013236'
down_revision: Union[str, None] = '20260529_price_levels_scope'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为 users 表添加 role 字段，默认值为 'user'。"""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('role', sa.String(length=20), nullable=False, server_default='user')
        )


def downgrade() -> None:
    """移除 users 表的 role 字段。"""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('role')
