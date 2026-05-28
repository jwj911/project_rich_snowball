"""add frontend_logs table

Revision ID: 71cca1a466b4
Revises: 5b2bada50d93
Create Date: 2026-05-28 19:52:33.630671

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '71cca1a466b4'
down_revision: Union[str, None] = '5b2bada50d93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('frontend_logs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('level', sa.String(length=20), nullable=True),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('user_agent', sa.String(length=500), nullable=True),
    sa.Column('release', sa.String(length=50), nullable=True),
    sa.Column('environment', sa.String(length=20), nullable=True),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('frontend_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_frontend_logs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_frontend_logs_level'), ['level'], unique=False)
        batch_op.create_index(batch_op.f('ix_frontend_logs_type'), ['type'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('frontend_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_frontend_logs_type'))
        batch_op.drop_index(batch_op.f('ix_frontend_logs_level'))
        batch_op.drop_index(batch_op.f('ix_frontend_logs_created_at'))

    op.drop_table('frontend_logs')
