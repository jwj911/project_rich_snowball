"""add news_sources and news_articles tables

Revision ID: 7663d085e48e
Revises: c3968099fa3e
Create Date: 2026-05-31 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7663d085e48e"
down_revision: Union[str, None] = "c3968099fa3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetch_error_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("news_sources", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_news_sources_id"), ["id"], unique=False)

    op.create_table(
        "news_articles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["news_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "url", name="uix_article_source_url"),
    )
    with op.batch_alter_table("news_articles", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_news_articles_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_news_articles_published_at"), ["published_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_news_articles_source_id"), ["source_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("news_articles", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_news_articles_source_id"))
        batch_op.drop_index(batch_op.f("ix_news_articles_published_at"))
        batch_op.drop_index(batch_op.f("ix_news_articles_id"))
    op.drop_table("news_articles")

    with op.batch_alter_table("news_sources", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_news_sources_id"))
    op.drop_table("news_sources")
