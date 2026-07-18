"""add fut_main_daily_data table

Revision ID: f7a8b9c0d1e2
Revises: 0cdaf00da990
Create Date: 2026-07-19 03:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "0cdaf00da990"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fut_main_daily_data",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("variety_id", sa.Integer(), nullable=False),
        sa.Column("ts_code", sa.String(length=20), nullable=False),
        sa.Column("trade_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pre_close", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("pre_settle", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("open_price", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("high_price", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("low_price", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("close_price", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("settle", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("change1", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("change2", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("oi_chg", sa.Integer(), nullable=True),
        sa.Column("period", sa.String(length=5), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["variety_id"],
            ["varieties.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "variety_id",
            "ts_code",
            "period",
            "trade_date",
            name="uix_fut_main_daily",
        ),
    )
    with op.batch_alter_table("fut_main_daily_data", schema=None) as batch_op:
        batch_op.create_index(
            "idx_fut_main_daily_lookup",
            ["variety_id", "period", "trade_date"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("fut_main_daily_data", schema=None) as batch_op:
        batch_op.drop_index("idx_fut_main_daily_lookup")

    op.drop_table("fut_main_daily_data")
