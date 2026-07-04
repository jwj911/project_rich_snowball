"""add_factor_definitions_table

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-07-04 16:20:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "factor_definitions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("package_id", sa.String(length=80), nullable=False),
        sa.Column("factor_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=True),
        sa.Column("cluster_id", sa.String(length=80), nullable=True),
        sa.Column("is_cluster_rep", sa.Boolean(), nullable=False),
        sa.Column("q_score", sa.Numeric(12, 6), nullable=True),
        sa.Column("rankic", sa.Numeric(18, 10), nullable=True),
        sa.Column("rankicir", sa.Numeric(18, 10), nullable=True),
        sa.Column("test_rankicir", sa.Numeric(18, 10), nullable=True),
        sa.Column("monotonicity", sa.Numeric(18, 10), nullable=True),
        sa.Column("ls_sharpe", sa.Numeric(18, 10), nullable=True),
        sa.Column("size_corr", sa.Numeric(18, 10), nullable=True),
        sa.Column("coverage", sa.Numeric(18, 10), nullable=True),
        sa.Column("source_expression", sa.Text(), nullable=False),
        sa.Column("converted_formula", sa.Text(), nullable=True),
        sa.Column("conversion_status", sa.String(length=30), nullable=False),
        sa.Column("conversion_error", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=60), nullable=True),
        sa.Column("fields_json", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("watermark_sig", sa.String(length=200), nullable=True),
        sa.Column("source_file", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_id", "factor_id", name="uix_factor_definitions_package_factor"),
    )
    op.create_index("ix_factor_definitions_package_id", "factor_definitions", ["package_id"], unique=False)
    op.create_index("ix_factor_definitions_factor_id", "factor_definitions", ["factor_id"], unique=False)
    op.create_index("ix_factor_definitions_name", "factor_definitions", ["name"], unique=False)
    op.create_index("ix_factor_definitions_source", "factor_definitions", ["source"], unique=False)
    op.create_index("ix_factor_definitions_cluster_id", "factor_definitions", ["cluster_id"], unique=False)
    op.create_index("ix_factor_definitions_conversion_status", "factor_definitions", ["conversion_status"], unique=False)
    op.create_index("ix_factor_definitions_category", "factor_definitions", ["category"], unique=False)
    op.create_index("ix_factor_definitions_is_active", "factor_definitions", ["is_active"], unique=False)
    op.create_index(
        "idx_factor_definitions_quality",
        "factor_definitions",
        ["conversion_status", "q_score"],
        unique=False,
    )
    op.create_index(
        "idx_factor_definitions_source_category",
        "factor_definitions",
        ["source", "category"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_factor_definitions_source_category", table_name="factor_definitions")
    op.drop_index("idx_factor_definitions_quality", table_name="factor_definitions")
    op.drop_index("ix_factor_definitions_is_active", table_name="factor_definitions")
    op.drop_index("ix_factor_definitions_category", table_name="factor_definitions")
    op.drop_index("ix_factor_definitions_conversion_status", table_name="factor_definitions")
    op.drop_index("ix_factor_definitions_cluster_id", table_name="factor_definitions")
    op.drop_index("ix_factor_definitions_source", table_name="factor_definitions")
    op.drop_index("ix_factor_definitions_name", table_name="factor_definitions")
    op.drop_index("ix_factor_definitions_factor_id", table_name="factor_definitions")
    op.drop_index("ix_factor_definitions_package_id", table_name="factor_definitions")
    op.drop_table("factor_definitions")
