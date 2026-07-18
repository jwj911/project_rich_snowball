"""enhance news with ai summary and user sources

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-01 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("news_sources", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True))
        batch_op.add_column(sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index(batch_op.f("ix_news_sources_user_id"), ["user_id"], unique=False)

    with op.batch_alter_table("news_articles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ai_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("news_articles", schema=None) as batch_op:
        batch_op.drop_column("ai_summary")

    with op.batch_alter_table("news_sources", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_news_sources_user_id"))
        batch_op.drop_column("is_builtin")
        batch_op.drop_column("user_id")
