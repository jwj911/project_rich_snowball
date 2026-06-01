"""add price_alerts table

Revision ID: a1b2c3d4e5f6
Revises: 03748a4fc2a5
Create Date: 2026-06-01 17:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "03748a4fc2a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variety_id", sa.Integer(), sa.ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_type", sa.String(length=10), nullable=False),
        sa.Column("target_price", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("is_triggered", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_price_alerts_user_id", "user_id"),
        sa.Index("ix_price_alerts_variety_id", "variety_id"),
        sa.Index("ix_price_alerts_triggered", "is_triggered"),
    )


def downgrade() -> None:
    op.drop_table("price_alerts")
