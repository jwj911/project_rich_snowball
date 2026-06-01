"""add user_id to frontend_logs

Revision ID: c3968099fa3e
Revises: 99c6cd55a7f4
Create Date: 2026-05-31 22:02:07.653345

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3968099fa3e"
down_revision: Union[str, None] = "99c6cd55a7f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("frontend_logs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_frontend_logs_user_id"), ["user_id"], unique=False
        )
        batch_op.create_foreign_key(
            None, "users", ["user_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("frontend_logs", schema=None) as batch_op:
        batch_op.drop_constraint(None, type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_frontend_logs_user_id"))
        batch_op.drop_column("user_id")
