"""add status closed_at actual_outcome to opinions

Revision ID: 03748a4fc2a5
Revises: 7663d085e48e
Create Date: 2026-06-01 07:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "03748a4fc2a5"
down_revision: str | None = "7663d085e48e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("opinions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'open'")))
        batch_op.add_column(sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("actual_outcome", sa.String(length=20), nullable=True))
        batch_op.create_index(batch_op.f("ix_opinions_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_opinions_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_opinions_variety_id"), ["variety_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("opinions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_opinions_variety_id"))
        batch_op.drop_index(batch_op.f("ix_opinions_user_id"))
        batch_op.drop_index(batch_op.f("ix_opinions_status"))
        batch_op.drop_column("actual_outcome")
        batch_op.drop_column("closed_at")
        batch_op.drop_column("status")
