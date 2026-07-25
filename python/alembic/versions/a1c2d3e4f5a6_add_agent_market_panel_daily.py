"""add agent market panel daily

Revision ID: a1c2d3e4f5a6
Revises: f7a8b9c0d1e2
Create Date: 2026-07-24 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c2d3e4f5a6"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_market_panel_daily",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_view", sa.String(length=30), nullable=False, server_default="raw_contract"),
        sa.Column("variety_id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("contract_code", sa.String(length=30), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False, server_default="1d"),
        sa.Column("open_price", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("high_price", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("low_price", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("close_price", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("settlement", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("ret_1", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("ret_5", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("ret_20", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("gap", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("amplitude", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("intraday_range", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("volume_ratio_20", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("source_flags", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("quality_status", sa.String(length=10), nullable=False, server_default="good"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["fut_contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variety_id"], ["varieties.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_view",
            "variety_id",
            "contract_id",
            "period",
            "trading_date",
            name="uix_agent_market_panel_daily",
        ),
    )
    op.create_index(
        "idx_agent_panel_symbol_date",
        "agent_market_panel_daily",
        ["symbol", "trading_date"],
        unique=False,
    )
    op.create_index(
        "idx_agent_panel_period_symbol_date",
        "agent_market_panel_daily",
        ["period", "symbol", "trading_date"],
        unique=False,
    )
    op.create_index(
        "idx_agent_panel_view_symbol_date",
        "agent_market_panel_daily",
        ["data_view", "symbol", "trading_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_agent_panel_view_symbol_date", table_name="agent_market_panel_daily")
    op.drop_index("idx_agent_panel_period_symbol_date", table_name="agent_market_panel_daily")
    op.drop_index("idx_agent_panel_symbol_date", table_name="agent_market_panel_daily")
    op.drop_table("agent_market_panel_daily")
