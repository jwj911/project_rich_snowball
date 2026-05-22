"""add_timezone_to_all_datetime_columns

Revision ID: bd656c03f8dc
Revises: efa11c24b71e
Create Date: 2026-05-21 10:17:46.605092

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'bd656c03f8dc'
down_revision: Union[str, None] = 'efa11c24b71e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 需要添加 timezone=True 的列映射：{table: [(column, nullable)]}
_COLUMNS_TO_ALTER = {
    "comments": [("created_at", True)],
    "contract_rollovers": [("effective_date", False), ("created_at", True)],
    "data_ingestion_runs": [
        ("started_at", False),
        ("finished_at", True),
        ("window_start", True),
        ("window_end", True),
    ],
    "fut_contracts": [
        ("list_date", True),
        ("delist_date", True),
        ("created_at", True),
        ("updated_at", True),
    ],
    "fut_daily_data": [("trade_date", False), ("created_at", True)],
    "fut_holding": [("trade_date", False), ("created_at", True)],
    "fut_index": [("trade_date", False), ("created_at", True)],
    "fut_price_limits": [("trade_date", False), ("created_at", True)],
    "fut_settle": [("trade_date", False), ("created_at", True)],
    "fut_trade_fee": [
        ("fee_updated_at", True),
        ("price_updated_at", True),
        ("created_at", True),
    ],
    "fut_weekly_detail": [("week_date", True), ("created_at", True)],
    "fut_wsr": [("trade_date", False), ("created_at", True)],
    "kline_data": [("trading_time", False), ("created_at", True)],
    "opinions": [("created_at", True)],
    "price_levels": [("created_at", True), ("updated_at", True)],
    "products": [("updated_at", True)],
    "realtime_quotes": [("updated_at", False)],
    "refresh_tokens": [("created_at", True)],
    "users": [("created_at", True)],
    "varieties": [
        ("listing_date", True),
        ("last_trading_date", True),
        ("created_at", True),
        ("updated_at", True),
    ],
    "watchlists": [("created_at", True)],
}


def upgrade() -> None:
    for table, columns in _COLUMNS_TO_ALTER.items():
        with op.batch_alter_table(table, schema=None) as batch_op:
            for col, nullable in columns:
                batch_op.alter_column(
                    col,
                    existing_type=postgresql.TIMESTAMP(),
                    type_=sa.DateTime(timezone=True),
                    existing_nullable=nullable,
                )


def downgrade() -> None:
    for table, columns in _COLUMNS_TO_ALTER.items():
        with op.batch_alter_table(table, schema=None) as batch_op:
            for col, nullable in columns:
                batch_op.alter_column(
                    col,
                    existing_type=sa.DateTime(timezone=True),
                    type_=postgresql.TIMESTAMP(),
                    existing_nullable=nullable,
                )
