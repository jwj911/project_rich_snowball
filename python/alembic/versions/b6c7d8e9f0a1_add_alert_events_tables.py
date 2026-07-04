"""add alert events tables

Revision ID: b6c7d8e9f0a1
Revises: a473c8a0a63f
Create Date: 2026-07-04 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, None] = "a473c8a0a63f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("related_variety_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("target_scope", sa.String(length=20), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["related_variety_id"], ["varieties.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("alert_events", schema=None) as batch_op:
        batch_op.create_index("idx_alert_events_category", ["category", "severity", "created_at"], unique=False)
        batch_op.create_index("idx_alert_events_source", ["source_type", "source_id", "target_scope", "user_id"], unique=False)
        batch_op.create_index("idx_alert_events_visible", ["target_scope", "user_id", "created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_alert_events_related_variety_id"), ["related_variety_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_alert_events_user_id"), ["user_id"], unique=False)

    op.create_table(
        "alert_event_user_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["alert_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "user_id", name="uix_alert_event_state_event_user"),
    )
    with op.batch_alter_table("alert_event_user_states", schema=None) as batch_op:
        batch_op.create_index("idx_alert_event_states_user", ["user_id", "dismissed_at", "read_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_alert_event_user_states_event_id"), ["event_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_alert_event_user_states_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("alert_event_user_states", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_alert_event_user_states_user_id"))
        batch_op.drop_index(batch_op.f("ix_alert_event_user_states_event_id"))
        batch_op.drop_index("idx_alert_event_states_user")
    op.drop_table("alert_event_user_states")

    with op.batch_alter_table("alert_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_alert_events_user_id"))
        batch_op.drop_index(batch_op.f("ix_alert_events_related_variety_id"))
        batch_op.drop_index("idx_alert_events_visible")
        batch_op.drop_index("idx_alert_events_source")
        batch_op.drop_index("idx_alert_events_category")
    op.drop_table("alert_events")
