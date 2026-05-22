"""make_kline_contract_id_not_nullable

Revision ID: 8188beb6eba0
Revises: a97d7113bdec
Create Date: 2026-05-16 18:36:23.682197

警告：本迁移包含破坏性 DELETE 操作，会永久删除 kline_data 表中 contract_id 为 NULL 的历史数据。
在生产环境执行前，务必先备份 kline_data 表！
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8188beb6eba0'
down_revision: Union[str, None] = 'a97d7113bdec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 清理无法归属到具体合约的 K 线数据，避免非空约束失败
    op.execute("DELETE FROM kline_data WHERE contract_id IS NULL")

    with op.batch_alter_table('kline_data', schema=None) as batch_op:
        batch_op.alter_column('contract_id', existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('kline_data', schema=None) as batch_op:
        batch_op.alter_column('contract_id', existing_type=sa.Integer(), nullable=True)
