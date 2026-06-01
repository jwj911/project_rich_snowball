"""add trade_records table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-01 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trade_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variety_id", sa.Integer(), sa.ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opinion_id", sa.Integer(), sa.ForeignKey("opinions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("exit_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(length=10), nullable=False, server_default=sa.text("'open'")),
        sa.Column("pnl", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("pnl_percent", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_trade_records_user_id", "user_id"),
        sa.Index("ix_trade_records_variety_id", "variety_id"),
        sa.Index("ix_trade_records_status", "status"),
    )


def downgrade() -> None:
    op.drop_table("trade_records")
