"""fix_numeric_float_schema_drift

Revision ID: 52512a652797
Revises: 8188beb6eba0
Create Date: 2026-05-16 20:56:32.682292

修复 Numeric vs Float schema drift，将以下列从 FLOAT 统一为 Numeric：
- varieties.margin_rate / commission
- watchlists.resistance_level / support_level
- opinions.target_price / stop_loss

同时补充上一轮 models.py 中已添加但缺失的索引：
- comments.product_id / user_id
- data_ingestion_runs.started_at
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52512a652797'
down_revision: Union[str, None] = '8188beb6eba0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 补充高频查询索引（上一轮 models.py 已添加 index=True，但 Alembic 未同步）
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_comments_product_id'), ['product_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_comments_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('data_ingestion_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_data_ingestion_runs_started_at'), ['started_at'], unique=False)

    # 修复 Numeric vs Float schema drift
    with op.batch_alter_table('opinions', schema=None) as batch_op:
        batch_op.alter_column('target_price',
               existing_type=sa.FLOAT(),
               type_=sa.Numeric(precision=15, scale=4),
               existing_nullable=True)
        batch_op.alter_column('stop_loss',
               existing_type=sa.FLOAT(),
               type_=sa.Numeric(precision=15, scale=4),
               existing_nullable=True)

    with op.batch_alter_table('varieties', schema=None) as batch_op:
        batch_op.alter_column('margin_rate',
               existing_type=sa.FLOAT(),
               type_=sa.Numeric(precision=10, scale=4),
               existing_nullable=True)
        batch_op.alter_column('commission',
               existing_type=sa.FLOAT(),
               type_=sa.Numeric(precision=10, scale=4),
               existing_nullable=True)

    with op.batch_alter_table('watchlists', schema=None) as batch_op:
        batch_op.alter_column('resistance_level',
               existing_type=sa.FLOAT(),
               type_=sa.Numeric(precision=15, scale=4),
               existing_nullable=True)
        batch_op.alter_column('support_level',
               existing_type=sa.FLOAT(),
               type_=sa.Numeric(precision=15, scale=4),
               existing_nullable=True)


def downgrade() -> None:
    # 回滚 Numeric → Float
    with op.batch_alter_table('watchlists', schema=None) as batch_op:
        batch_op.alter_column('support_level',
               existing_type=sa.Numeric(precision=15, scale=4),
               type_=sa.FLOAT(),
               existing_nullable=True)
        batch_op.alter_column('resistance_level',
               existing_type=sa.Numeric(precision=15, scale=4),
               type_=sa.FLOAT(),
               existing_nullable=True)

    with op.batch_alter_table('varieties', schema=None) as batch_op:
        batch_op.alter_column('commission',
               existing_type=sa.Numeric(precision=10, scale=4),
               type_=sa.FLOAT(),
               existing_nullable=True)
        batch_op.alter_column('margin_rate',
               existing_type=sa.Numeric(precision=10, scale=4),
               type_=sa.FLOAT(),
               existing_nullable=True)

    with op.batch_alter_table('opinions', schema=None) as batch_op:
        batch_op.alter_column('stop_loss',
               existing_type=sa.Numeric(precision=15, scale=4),
               type_=sa.FLOAT(),
               existing_nullable=True)
        batch_op.alter_column('target_price',
               existing_type=sa.Numeric(precision=15, scale=4),
               type_=sa.FLOAT(),
               existing_nullable=True)

    # 回滚索引
    with op.batch_alter_table('data_ingestion_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_data_ingestion_runs_started_at'))

    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_comments_user_id'))
        batch_op.drop_index(batch_op.f('ix_comments_product_id'))
