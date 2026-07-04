"""add_agent_tasks_and_steps

Revision ID: c4f6a8b2d9e1
Revises: f2b3c4d5e6f7
Create Date: 2026-06-24 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c4f6a8b2d9e1"
down_revision: str | None = "f2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # agent_tasks
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("agent_type", sa.String(30), nullable=False, index=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_tasks_user_status", "agent_tasks", ["user_id", "status"])
    op.create_index("idx_agent_tasks_created", "agent_tasks", ["created_at"])

    # agent_task_steps
    op.create_table(
        "agent_task_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(50), nullable=True),
        sa.Column("tool_input_json", sa.Text(), nullable=True),
        sa.Column("tool_output_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "step_number", name="uix_agent_step_number"),
    )
    op.create_index("idx_agent_task_steps_task", "agent_task_steps", ["task_id", "step_number"])


def downgrade() -> None:
    op.drop_table("agent_task_steps")
    op.drop_table("agent_tasks")
