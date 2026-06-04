"""add_price_levels_partial_unique_indexes

Revision ID: f2b3c4d5e6f7
Revises: e1a2b3c4d5e6
Create Date: 2026-06-04 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b3c4d5e6f7'
down_revision: Union[str, None] = 'e1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dialect = op.get_context().dialect.name

    if dialect == "postgresql":
        # contract_id IS NULL：continuous / main scope 的标注
        op.create_index(
            "uix_price_levels_null_contract",
            "price_levels",
            ["user_id", "variety_id", "type", "price", "scope"],
            unique=True,
            postgresql_where=sa.text("contract_id IS NULL"),
        )
        # contract_id IS NOT NULL：具体合约 scope 的标注
        op.create_index(
            "uix_price_levels_not_null_contract",
            "price_levels",
            ["user_id", "variety_id", "type", "price", "scope", "contract_id"],
            unique=True,
            postgresql_where=sa.text("contract_id IS NOT NULL"),
        )
    # SQLite 不支持 partial unique indexes，应用层 check_duplicate 作为兜底


def downgrade() -> None:
    dialect = op.get_context().dialect.name

    if dialect == "postgresql":
        op.drop_index("uix_price_levels_null_contract", table_name="price_levels")
        op.drop_index("uix_price_levels_not_null_contract", table_name="price_levels")
