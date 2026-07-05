"""add strategy evolution lifecycle tables

Revision ID: 0cdaf00da990
Revises: 4705760ae2a8
Create Date: 2026-07-05 09:04:59.765086

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0cdaf00da990'
down_revision: Union[str, None] = '4705760ae2a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'strategy_evolution_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('config_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('generations', sa.Integer(), nullable=True),
        sa.Column('population_size', sa.Integer(), nullable=True),
        sa.Column('best_strategy_id', sa.Integer(), nullable=True),
        sa.Column('summary_json', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['best_strategy_id'], ['strategies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('strategy_evolution_runs', schema=None) as batch_op:
        batch_op.create_index('idx_evo_runs_symbol', ['symbol', 'created_at'], unique=False)
        batch_op.create_index('idx_evo_runs_user_status', ['user_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_strategy_evolution_runs_best_strategy_id'), ['best_strategy_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_strategy_evolution_runs_symbol'), ['symbol'], unique=False)
        batch_op.create_index(batch_op.f('ix_strategy_evolution_runs_user_id'), ['user_id'], unique=False)

    op.create_table(
        'strategy_generations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('evolution_run_id', sa.Integer(), nullable=False),
        sa.Column('generation_number', sa.Integer(), nullable=False),
        sa.Column('population_json', sa.Text(), nullable=True),
        sa.Column('best_fitness', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('avg_fitness', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('diversity_score', sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['evolution_run_id'], ['strategy_evolution_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('evolution_run_id', 'generation_number', name='uix_evo_gen_number'),
    )
    with op.batch_alter_table('strategy_generations', schema=None) as batch_op:
        batch_op.create_index('idx_evo_gen_fitness', ['evolution_run_id', 'generation_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_strategy_generations_evolution_run_id'), ['evolution_run_id'], unique=False)

    op.create_table(
        'strategy_lifecycle',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('strategy_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('evolution_run_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('in_sample_metrics', sa.Text(), nullable=True),
        sa.Column('out_of_sample_metrics', sa.Text(), nullable=True),
        sa.Column('walk_forward_metrics', sa.Text(), nullable=True),
        sa.Column('last_evaluated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('performance_trend', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('decay_score', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['evolution_run_id'], ['strategy_evolution_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('strategy_lifecycle', schema=None) as batch_op:
        batch_op.create_index('idx_lifecycle_decay', ['decay_score', 'updated_at'], unique=False)
        batch_op.create_index('idx_lifecycle_status', ['status', 'last_evaluated_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_strategy_lifecycle_evolution_run_id'), ['evolution_run_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_strategy_lifecycle_strategy_id'), ['strategy_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('strategy_lifecycle', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_strategy_lifecycle_strategy_id'))
        batch_op.drop_index(batch_op.f('ix_strategy_lifecycle_evolution_run_id'))
        batch_op.drop_index('idx_lifecycle_status')
        batch_op.drop_index('idx_lifecycle_decay')
    op.drop_table('strategy_lifecycle')

    with op.batch_alter_table('strategy_generations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_strategy_generations_evolution_run_id'))
        batch_op.drop_index('idx_evo_gen_fitness')
    op.drop_table('strategy_generations')

    with op.batch_alter_table('strategy_evolution_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_strategy_evolution_runs_user_id'))
        batch_op.drop_index(batch_op.f('ix_strategy_evolution_runs_symbol'))
        batch_op.drop_index(batch_op.f('ix_strategy_evolution_runs_best_strategy_id'))
        batch_op.drop_index('idx_evo_runs_user_status')
        batch_op.drop_index('idx_evo_runs_symbol')
    op.drop_table('strategy_evolution_runs')
