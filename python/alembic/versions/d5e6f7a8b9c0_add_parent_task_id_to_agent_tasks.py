"""add_parent_task_id_to_agent_tasks

Revision ID: d5e6f7a8b9c0
Revises: c4f6a8b2d9e1
Create Date: 2026-07-04 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4f6a8b2d9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_tasks",
        sa.Column(
            "parent_task_id",
            sa.Integer(),
            sa.ForeignKey("agent_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_agent_tasks_parent", "agent_tasks", ["parent_task_id"])


def downgrade() -> None:
    op.drop_index("idx_agent_tasks_parent", table_name="agent_tasks")
    op.drop_column("agent_tasks", "parent_task_id")
