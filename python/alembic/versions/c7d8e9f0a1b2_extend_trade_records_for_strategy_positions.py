"""Extend trade records for strategy-generated positions

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-07-04 18:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b6c7d8e9f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("trade_records") as batch_op:
        batch_op.add_column(sa.Column("strategy_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("backtest_run_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("account_balance", sa.Numeric(precision=15, scale=4), nullable=True))
        batch_op.add_column(sa.Column("stop_loss_price", sa.Numeric(precision=15, scale=4), nullable=True))
        batch_op.add_column(sa.Column("take_profit_price", sa.Numeric(precision=15, scale=4), nullable=True))
        batch_op.add_column(sa.Column("margin_required", sa.Numeric(precision=15, scale=4), nullable=True))
        batch_op.add_column(sa.Column("risk_amount", sa.Numeric(precision=15, scale=4), nullable=True))
        batch_op.add_column(sa.Column("risk_reward_ratio", sa.Numeric(precision=10, scale=4), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"))
        batch_op.create_index(batch_op.f("ix_trade_records_strategy_id"), ["strategy_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_trade_records_backtest_run_id"), ["backtest_run_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_trade_records_strategy_id_strategies",
            "strategies",
            ["strategy_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_trade_records_backtest_run_id_backtest_runs",
            "backtest_runs",
            ["backtest_run_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("trade_records") as batch_op:
        batch_op.drop_constraint("fk_trade_records_backtest_run_id_backtest_runs", type_="foreignkey")
        batch_op.drop_constraint("fk_trade_records_strategy_id_strategies", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_trade_records_backtest_run_id"))
        batch_op.drop_index(batch_op.f("ix_trade_records_strategy_id"))
        batch_op.drop_column("source")
        batch_op.drop_column("risk_reward_ratio")
        batch_op.drop_column("risk_amount")
        batch_op.drop_column("margin_required")
        batch_op.drop_column("take_profit_price")
        batch_op.drop_column("stop_loss_price")
        batch_op.drop_column("account_balance")
        batch_op.drop_column("backtest_run_id")
        batch_op.drop_column("strategy_id")
