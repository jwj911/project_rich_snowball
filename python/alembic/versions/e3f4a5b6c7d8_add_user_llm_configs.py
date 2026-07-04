"""add_user_llm_configs

Revision ID: e3f4a5b6c7d8
Revises: c2adb95b3aba
Create Date: 2026-07-04 18:05:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e3f4a5b6c7d8"
down_revision: str | None = "c2adb95b3aba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_llm_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_llm_configs_is_active"), "user_llm_configs", ["is_active"], unique=False)
    op.create_index(op.f("ix_user_llm_configs_user_id"), "user_llm_configs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_llm_configs_user_id"), table_name="user_llm_configs")
    op.drop_index(op.f("ix_user_llm_configs_is_active"), table_name="user_llm_configs")
    op.drop_table("user_llm_configs")
