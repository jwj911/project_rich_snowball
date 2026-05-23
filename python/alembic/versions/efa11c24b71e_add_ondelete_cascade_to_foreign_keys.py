"""add_ondelete_cascade_to_foreign_keys

Revision ID: efa11c24b71e
Revises: 1120a1ca174c
Create Date: 2026-05-21 08:56:30.304601

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'efa11c24b71e'
down_revision: Union[str, None] = '1120a1ca174c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fk(batch_op, table_name, column_name, known_name=None):
    """尝试删除外键约束；名称可能因方言而异，捕获异常忽略不存在的情况。"""
    dialect = op.get_context().dialect.name
    if dialect == "sqlite":
        # SQLite batch_alter_table 通过重建表实现变更，
        # 匿名外键约束无需显式 drop，旧表删除时自然消失。
        return
    candidates = []
    if known_name:
        candidates.append(known_name)
    candidates.extend([
        f"{table_name}_{column_name}_fkey",
        f"fk_{table_name}_{column_name}",
        column_name,
    ])
    for name in candidates:
        try:
            batch_op.drop_constraint(name, type_="foreignkey")
            return
        except Exception:
            pass


def upgrade() -> None:
    # comments
    with op.batch_alter_table('comments', schema=None) as batch_op:
        _drop_fk(batch_op, 'comments', 'user_id', 'comments_user_id_fkey')
        _drop_fk(batch_op, 'comments', 'product_id', 'comments_product_id_fkey')
        _drop_fk(batch_op, 'comments', 'price_level_id', 'fk_comments_price_level_id')
        batch_op.create_foreign_key("fk_comments_user_id_users", "users", ['user_id'], ["id"], ondelete='CASCADE')
        batch_op.create_foreign_key("fk_comments_product_id_products", "products", ['product_id'], ["id"], ondelete='CASCADE')
        batch_op.create_foreign_key("fk_comments_price_level_id_price_levels", "price_levels", ['price_level_id'], ["id"], ondelete='SET NULL')

    # contract_rollovers
    with op.batch_alter_table('contract_rollovers', schema=None) as batch_op:
        _drop_fk(batch_op, 'contract_rollovers', 'variety_id', 'contract_rollovers_variety_id_fkey')
        _drop_fk(batch_op, 'contract_rollovers', 'old_contract_id', 'contract_rollovers_old_contract_id_fkey')
        _drop_fk(batch_op, 'contract_rollovers', 'new_contract_id', 'contract_rollovers_new_contract_id_fkey')
        batch_op.create_foreign_key("fk_contract_rollovers_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')
        batch_op.create_foreign_key("fk_contract_rollovers_new_contract_id_fut_contracts", "fut_contracts", ['new_contract_id'], ["id"], ondelete='SET NULL')
        batch_op.create_foreign_key("fk_contract_rollovers_old_contract_id_fut_contracts", "fut_contracts", ['old_contract_id'], ["id"], ondelete='SET NULL')

    # fut_daily_data
    with op.batch_alter_table('fut_daily_data', schema=None) as batch_op:
        _drop_fk(batch_op, 'fut_daily_data', 'variety_id', 'fut_daily_data_variety_id_fkey')
        batch_op.create_foreign_key("fk_fut_daily_data_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')

    # kline_data
    with op.batch_alter_table('kline_data', schema=None) as batch_op:
        _drop_fk(batch_op, 'kline_data', 'variety_id', 'kline_data_variety_id_fkey')
        _drop_fk(batch_op, 'kline_data', 'contract_id', 'fk_kline_data_contract_id')
        batch_op.create_foreign_key("fk_kline_data_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')
        batch_op.create_foreign_key("fk_kline_data_contract_id_fut_contracts", "fut_contracts", ['contract_id'], ["id"], ondelete='CASCADE')

    # opinions
    with op.batch_alter_table('opinions', schema=None) as batch_op:
        _drop_fk(batch_op, 'opinions', 'variety_id', 'opinions_variety_id_fkey')
        _drop_fk(batch_op, 'opinions', 'user_id', 'opinions_user_id_fkey')
        batch_op.create_foreign_key("fk_opinions_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')
        batch_op.create_foreign_key("fk_opinions_user_id_users", "users", ['user_id'], ["id"], ondelete='CASCADE')

    # price_levels
    with op.batch_alter_table('price_levels', schema=None) as batch_op:
        _drop_fk(batch_op, 'price_levels', 'user_id', 'price_levels_user_id_fkey')
        _drop_fk(batch_op, 'price_levels', 'variety_id', 'price_levels_variety_id_fkey')
        batch_op.create_foreign_key("fk_price_levels_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')
        batch_op.create_foreign_key("fk_price_levels_user_id_users", "users", ['user_id'], ["id"], ondelete='CASCADE')

    # realtime_quotes
    with op.batch_alter_table('realtime_quotes', schema=None) as batch_op:
        _drop_fk(batch_op, 'realtime_quotes', 'variety_id', 'realtime_quotes_variety_id_fkey')
        batch_op.create_foreign_key("fk_realtime_quotes_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')

    # refresh_tokens
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        _drop_fk(batch_op, 'refresh_tokens', 'user_id', 'refresh_tokens_user_id_fkey')
        batch_op.create_foreign_key("fk_refresh_tokens_user_id_users", "users", ['user_id'], ["id"], ondelete='CASCADE')

    # watchlists
    with op.batch_alter_table('watchlists', schema=None) as batch_op:
        _drop_fk(batch_op, 'watchlists', 'user_id', 'watchlists_user_id_fkey')
        _drop_fk(batch_op, 'watchlists', 'variety_id', 'watchlists_variety_id_fkey')
        batch_op.create_foreign_key("fk_watchlists_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')
        batch_op.create_foreign_key("fk_watchlists_user_id_users", "users", ['user_id'], ["id"], ondelete='CASCADE')


def downgrade() -> None:
    # watchlists
    with op.batch_alter_table('watchlists', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('watchlists_variety_id_fkey', 'varieties', ['variety_id'], ['id'])
        batch_op.create_foreign_key('watchlists_user_id_fkey', 'users', ['user_id'], ['id'])

    # refresh_tokens
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('refresh_tokens_user_id_fkey', 'users', ['user_id'], ['id'])

    # realtime_quotes
    with op.batch_alter_table('realtime_quotes', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('realtime_quotes_variety_id_fkey', 'varieties', ['variety_id'], ['id'])

    # price_levels
    with op.batch_alter_table('price_levels', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('price_levels_variety_id_fkey', 'varieties', ['variety_id'], ['id'])
        batch_op.create_foreign_key('price_levels_user_id_fkey', 'users', ['user_id'], ['id'])

    # opinions
    with op.batch_alter_table('opinions', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('opinions_user_id_fkey', 'users', ['user_id'], ['id'])
        batch_op.create_foreign_key('opinions_variety_id_fkey', 'varieties', ['variety_id'], ['id'])

    # kline_data
    with op.batch_alter_table('kline_data', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('fk_kline_data_contract_id', 'fut_contracts', ['contract_id'], ['id'])
        batch_op.create_foreign_key('kline_data_variety_id_fkey', 'varieties', ['variety_id'], ['id'])

    # fut_daily_data
    with op.batch_alter_table('fut_daily_data', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('fut_daily_data_variety_id_fkey', 'varieties', ['variety_id'], ['id'])

    # contract_rollovers
    with op.batch_alter_table('contract_rollovers', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('contract_rollovers_variety_id_fkey', 'varieties', ['variety_id'], ['id'])
        batch_op.create_foreign_key('contract_rollovers_new_contract_id_fkey', 'fut_contracts', ['new_contract_id'], ['id'])
        batch_op.create_foreign_key('contract_rollovers_old_contract_id_fkey', 'fut_contracts', ['old_contract_id'], ['id'])

    # comments
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('comments_user_id_fkey', 'users', ['user_id'], ['id'])
        batch_op.create_foreign_key('comments_product_id_fkey', 'products', ['product_id'], ['id'])
        batch_op.create_foreign_key('fk_comments_price_level_id', 'price_levels', ['price_level_id'], ['id'])
