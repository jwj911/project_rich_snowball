"""Add strategies and backtest_runs tables

Revision ID: a473c8a0a63f
Revises: d5e6f7a8b9c0
Create Date: 2026-07-04 13:19:10.705859

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a473c8a0a63f'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('strategies',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('dsl_json', sa.Text(), nullable=False),
    sa.Column('timeframe', sa.String(length=10), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('strategies', schema=None) as batch_op:
        batch_op.create_index('idx_strategies_created', ['created_at'], unique=False)
        batch_op.create_index('idx_strategies_user_symbol', ['user_id', 'symbol'], unique=False)
        batch_op.create_index(batch_op.f('ix_strategies_symbol'), ['symbol'], unique=False)
        batch_op.create_index(batch_op.f('ix_strategies_user_id'), ['user_id'], unique=False)

    op.create_table('backtest_runs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('strategy_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('query', sa.Text(), nullable=True),
    sa.Column('result_json', sa.Text(), nullable=True),
    sa.Column('metrics_score', sa.Integer(), nullable=True),
    sa.Column('trade_count', sa.Integer(), nullable=True),
    sa.Column('total_return_pct', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('max_drawdown_pct', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('backtest_runs', schema=None) as batch_op:
        batch_op.create_index('idx_backtest_runs_strategy', ['strategy_id', 'created_at'], unique=False)
        batch_op.create_index('idx_backtest_runs_user_status', ['user_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_backtest_runs_strategy_id'), ['strategy_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_backtest_runs_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('backtest_runs')
    op.drop_table('strategies')
