"""add user_id and is_builtin to factor_definitions

Revision ID: c2adb95b3aba
Revises: d8e9f0a1b2c3
Create Date: 2026-07-04 17:40:09.315791

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2adb95b3aba"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("factor_definitions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.create_index(batch_op.f("ix_factor_definitions_is_builtin"), ["is_builtin"], unique=False)
        batch_op.create_index(batch_op.f("ix_factor_definitions_user_id"), ["user_id"], unique=False)
        batch_op.create_foreign_key(None, "users", ["user_id"], ["id"], ondelete="SET NULL")

    # 将已有万因子记录标记为系统内置
    op.execute("UPDATE factor_definitions SET is_builtin = true WHERE user_id IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("factor_definitions", schema=None) as batch_op:
        batch_op.drop_constraint(None, type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_factor_definitions_user_id"))
        batch_op.drop_index(batch_op.f("ix_factor_definitions_is_builtin"))
        batch_op.drop_column("is_builtin")
        batch_op.drop_column("user_id")
