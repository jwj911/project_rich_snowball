"""Add ts_code to fut_daily_data unique constraint

Revision ID: 4705760ae2a8
Revises: de2ecb908257
Create Date: 2026-07-05 07:47:22.699880

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4705760ae2a8"
down_revision: Union[str, None] = "de2ecb908257"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old unique constraint and recreate with ts_code included.
    with op.batch_alter_table("fut_daily_data", schema=None) as batch_op:
        batch_op.drop_constraint("uix_fut_daily", type_="unique")
        batch_op.create_unique_constraint(
            "uix_fut_daily", ["variety_id", "ts_code", "period", "trade_date"]
        )


def downgrade() -> None:
    # Restore old unique constraint without ts_code.
    with op.batch_alter_table("fut_daily_data", schema=None) as batch_op:
        batch_op.drop_constraint("uix_fut_daily", type_="unique")
        batch_op.create_unique_constraint(
            "uix_fut_daily", ["variety_id", "period", "trade_date"]
        )
