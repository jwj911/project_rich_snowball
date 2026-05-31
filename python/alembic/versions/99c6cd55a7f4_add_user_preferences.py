"""add_user_preferences

Revision ID: 99c6cd55a7f4
Revises: b057bf013236
Create Date: 2026-05-31 21:06:56.081420

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '99c6cd55a7f4'
down_revision: Union[str, None] = 'b057bf013236'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 user_preferences 表，存储用户级偏好设置。"""
    op.create_table(
        'user_preferences',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('theme', sa.String(length=20), nullable=False),
        sa.Column('polling_interval_seconds', sa.Integer(), nullable=False),
        sa.Column('notifications_enabled', sa.Boolean(), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('user_preferences', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_preferences_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_preferences_user_id'), ['user_id'], unique=True)


def downgrade() -> None:
    """删除 user_preferences 表。"""
    with op.batch_alter_table('user_preferences', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_preferences_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_preferences_id'))
    op.drop_table('user_preferences')
