"""add market panel view lineage

Revision ID: c0d1e2f3a4b5
Revises: a1c2d3e4f5a6
Create Date: 2026-07-26 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0d1e2f3a4b5"
down_revision: str | None = "a1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_market_panel_daily") as batch_op:
        batch_op.add_column(sa.Column("rollover_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "adjustment_value",
                sa.Numeric(precision=20, scale=8),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "adjustment_method",
                sa.String(length=30),
                nullable=False,
                server_default="none",
            )
        )
        batch_op.add_column(sa.Column("lineage_json", sa.Text(), nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("build_trace_id", sa.String(length=32), nullable=True))
        batch_op.create_foreign_key(
            "fk_agent_market_panel_daily_rollover_id",
            "contract_rollovers",
            ["rollover_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_index("idx_agent_panel_view_rollover", "agent_market_panel_daily", ["data_view", "rollover_id"])
    op.create_index("ix_agent_market_panel_daily_build_trace_id", "agent_market_panel_daily", ["build_trace_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_market_panel_daily_build_trace_id", table_name="agent_market_panel_daily")
    op.drop_index("idx_agent_panel_view_rollover", table_name="agent_market_panel_daily")
    with op.batch_alter_table("agent_market_panel_daily") as batch_op:
        batch_op.drop_constraint("fk_agent_market_panel_daily_rollover_id", type_="foreignkey")
        batch_op.drop_column("build_trace_id")
        batch_op.drop_column("lineage_json")
        batch_op.drop_column("adjustment_method")
        batch_op.drop_column("adjustment_value")
        batch_op.drop_column("rollover_id")
