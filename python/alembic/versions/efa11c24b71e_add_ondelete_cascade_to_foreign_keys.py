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


def _pg_fk_names(table_name: str) -> set[str]:
    """查询 PostgreSQL 中某表当前所有外键约束名。SQLite 返回空集合。"""
    dialect = op.get_context().dialect.name
    if dialect == "sqlite":
        return set()
    conn = op.get_bind()
    result = conn.execute(
        sa.text(f"SELECT conname FROM pg_constraint WHERE conrelid = '{table_name}'::regclass AND contype = 'f'")
    )
    return {row[0] for row in result}


def _pg_drop_fk_if_exists(table_name: str, *names: str) -> None:
    """PostgreSQL 下：仅当约束实际存在时才执行 DROP，避免事务进入 aborted 状态。"""
    existing = _pg_fk_names(table_name)
    for name in names:
        if name in existing:
            op.drop_constraint(name, table_name, type_='foreignkey')


def upgrade() -> None:
    dialect = op.get_context().dialect.name

    if dialect == "sqlite":
        # comments
        with op.batch_alter_table('comments', schema=None) as batch_op:
            batch_op.create_foreign_key("fk_comments_user_id_users", "users", ['user_id'], ["id"], ondelete='CASCADE')
            batch_op.create_foreign_key("fk_comments_product_id_products", "products", ['product_id'], ["id"], ondelete='CASCADE')
            batch_op.create_foreign_key("fk_comments_price_level_id_price_levels", "price_levels", ['price_level_id'], ["id"], ondelete='SET NULL')

        # contract_rollovers
        with op.batch_alter_table('contract_rollovers', schema=None) as batch_op:
            batch_op.create_foreign_key("fk_contract_rollovers_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')
            batch_op.create_foreign_key("fk_contract_rollovers_new_contract_id_fut_contracts", "fut_contracts", ['new_contract_id'], ["id"], ondelete='SET NULL')
            batch_op.create_foreign_key("fk_contract_rollovers_old_contract_id_fut_contracts", "fut_contracts", ['old_contract_id'], ["id"], ondelete='SET NULL')

        # fut_daily_data
        with op.batch_alter_table('fut_daily_data', schema=None) as batch_op:
            batch_op.create_foreign_key("fk_fut_daily_data_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')

        # kline_data
        with op.batch_alter_table('kline_data', schema=None) as batch_op:
            batch_op.create_foreign_key("fk_kline_data_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')
            batch_op.create_foreign_key("fk_kline_data_contract_id_fut_contracts", "fut_contracts", ['contract_id'], ["id"], ondelete='CASCADE')

        # opinions
        with op.batch_alter_table('opinions', schema=None) as batch_op:
            batch_op.create_foreign_key("fk_opinions_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')
            batch_op.create_foreign_key("fk_opinions_user_id_users", "users", ['user_id'], ["id"], ondelete='CASCADE')

        # price_levels
        with op.batch_alter_table('price_levels', schema=None) as batch_op:
            batch_op.create_foreign_key("fk_price_levels_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')
            batch_op.create_foreign_key("fk_price_levels_user_id_users", "users", ['user_id'], ["id"], ondelete='CASCADE')

        # realtime_quotes
        with op.batch_alter_table('realtime_quotes', schema=None) as batch_op:
            batch_op.create_foreign_key("fk_realtime_quotes_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')

        # refresh_tokens
        with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
            batch_op.create_foreign_key("fk_refresh_tokens_user_id_users", "users", ['user_id'], ["id"], ondelete='CASCADE')

        # watchlists
        with op.batch_alter_table('watchlists', schema=None) as batch_op:
            batch_op.create_foreign_key("fk_watchlists_variety_id_varieties", "varieties", ['variety_id'], ["id"], ondelete='CASCADE')
            batch_op.create_foreign_key("fk_watchlists_user_id_users", "users", ['user_id'], ["id"], ondelete='CASCADE')
    else:
        # comments
        _pg_drop_fk_if_exists('comments', 'comments_user_id_fkey', 'fk_comments_user_id_users')
        _pg_drop_fk_if_exists('comments', 'comments_product_id_fkey', 'fk_comments_product_id_products')
        _pg_drop_fk_if_exists('comments', 'comments_price_level_id_fkey', 'fk_comments_price_level_id', 'fk_comments_price_level_id_price_levels')
        op.create_foreign_key('fk_comments_user_id_users', 'comments', 'users', ['user_id'], ['id'], ondelete='CASCADE')
        op.create_foreign_key('fk_comments_product_id_products', 'comments', 'products', ['product_id'], ['id'], ondelete='CASCADE')
        op.create_foreign_key('fk_comments_price_level_id_price_levels', 'comments', 'price_levels', ['price_level_id'], ['id'], ondelete='SET NULL')

        # contract_rollovers
        _pg_drop_fk_if_exists('contract_rollovers', 'contract_rollovers_variety_id_fkey', 'fk_contract_rollovers_variety_id_varieties')
        _pg_drop_fk_if_exists('contract_rollovers', 'contract_rollovers_old_contract_id_fkey', 'fk_contract_rollovers_old_contract_id_fut_contracts')
        _pg_drop_fk_if_exists('contract_rollovers', 'contract_rollovers_new_contract_id_fkey', 'fk_contract_rollovers_new_contract_id_fut_contracts')
        op.create_foreign_key('fk_contract_rollovers_variety_id_varieties', 'contract_rollovers', 'varieties', ['variety_id'], ['id'], ondelete='CASCADE')
        op.create_foreign_key('fk_contract_rollovers_new_contract_id_fut_contracts', 'contract_rollovers', 'fut_contracts', ['new_contract_id'], ['id'], ondelete='SET NULL')
        op.create_foreign_key('fk_contract_rollovers_old_contract_id_fut_contracts', 'contract_rollovers', 'fut_contracts', ['old_contract_id'], ['id'], ondelete='SET NULL')

        # fut_daily_data
        _pg_drop_fk_if_exists('fut_daily_data', 'fut_daily_data_variety_id_fkey', 'fk_fut_daily_data_variety_id_varieties')
        op.create_foreign_key('fk_fut_daily_data_variety_id_varieties', 'fut_daily_data', 'varieties', ['variety_id'], ['id'], ondelete='CASCADE')

        # kline_data
        _pg_drop_fk_if_exists('kline_data', 'kline_data_variety_id_fkey', 'fk_kline_data_variety_id_varieties')
        _pg_drop_fk_if_exists('kline_data', 'kline_data_contract_id_fkey', 'fk_kline_data_contract_id', 'fk_kline_data_contract_id_fut_contracts')
        op.create_foreign_key('fk_kline_data_variety_id_varieties', 'kline_data', 'varieties', ['variety_id'], ['id'], ondelete='CASCADE')
        op.create_foreign_key('fk_kline_data_contract_id_fut_contracts', 'kline_data', 'fut_contracts', ['contract_id'], ['id'], ondelete='CASCADE')

        # opinions
        _pg_drop_fk_if_exists('opinions', 'opinions_variety_id_fkey', 'fk_opinions_variety_id_varieties')
        _pg_drop_fk_if_exists('opinions', 'opinions_user_id_fkey', 'fk_opinions_user_id_users')
        op.create_foreign_key('fk_opinions_variety_id_varieties', 'opinions', 'varieties', ['variety_id'], ['id'], ondelete='CASCADE')
        op.create_foreign_key('fk_opinions_user_id_users', 'opinions', 'users', ['user_id'], ['id'], ondelete='CASCADE')

        # price_levels
        _pg_drop_fk_if_exists('price_levels', 'price_levels_variety_id_fkey', 'fk_price_levels_variety_id_varieties')
        _pg_drop_fk_if_exists('price_levels', 'price_levels_user_id_fkey', 'fk_price_levels_user_id_users')
        op.create_foreign_key('fk_price_levels_variety_id_varieties', 'price_levels', 'varieties', ['variety_id'], ['id'], ondelete='CASCADE')
        op.create_foreign_key('fk_price_levels_user_id_users', 'price_levels', 'users', ['user_id'], ['id'], ondelete='CASCADE')

        # realtime_quotes
        _pg_drop_fk_if_exists('realtime_quotes', 'realtime_quotes_variety_id_fkey', 'fk_realtime_quotes_variety_id_varieties')
        op.create_foreign_key('fk_realtime_quotes_variety_id_varieties', 'realtime_quotes', 'varieties', ['variety_id'], ['id'], ondelete='CASCADE')

        # refresh_tokens
        _pg_drop_fk_if_exists('refresh_tokens', 'refresh_tokens_user_id_fkey', 'fk_refresh_tokens_user_id_users')
        op.create_foreign_key('fk_refresh_tokens_user_id_users', 'refresh_tokens', 'users', ['user_id'], ['id'], ondelete='CASCADE')

        # watchlists
        _pg_drop_fk_if_exists('watchlists', 'watchlists_variety_id_fkey', 'fk_watchlists_variety_id_varieties')
        _pg_drop_fk_if_exists('watchlists', 'watchlists_user_id_fkey', 'fk_watchlists_user_id_users')
        op.create_foreign_key('fk_watchlists_variety_id_varieties', 'watchlists', 'varieties', ['variety_id'], ['id'], ondelete='CASCADE')
        op.create_foreign_key('fk_watchlists_user_id_users', 'watchlists', 'users', ['user_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # 重要：downgrade 需兼容两种场景：
    # 1) 数据库通过 init_db() 创建（旧约束名，无 CASCADE）
    # 2) 数据库通过 alembic upgrade 创建（新约束名，有 CASCADE）
    #
    # PostgreSQL 中，失败的 DROP CONSTRAINT 会导致当前事务进入 aborted 状态，
    # 后续命令都会被拒绝。因此不能依赖 try/except 来尝试删除可能不存在的约束。
    # 策略：先查询 pg_constraint 获取实际存在的约束名，只删除存在的。

    dialect = op.get_context().dialect.name

    if dialect == "sqlite":
        # SQLite 使用 batch_alter_table，重建表时旧外键自然消失。
        # create_foreign_key 负责创建新的（旧定义）约束。

        # watchlists
        with op.batch_alter_table('watchlists', schema=None) as batch_op:
            batch_op.create_foreign_key('watchlists_variety_id_fkey', 'varieties', ['variety_id'], ['id'])
            batch_op.create_foreign_key('watchlists_user_id_fkey', 'users', ['user_id'], ['id'])

        # refresh_tokens
        with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
            batch_op.create_foreign_key('refresh_tokens_user_id_fkey', 'users', ['user_id'], ['id'])

        # realtime_quotes
        with op.batch_alter_table('realtime_quotes', schema=None) as batch_op:
            batch_op.create_foreign_key('realtime_quotes_variety_id_fkey', 'varieties', ['variety_id'], ['id'])

        # price_levels
        with op.batch_alter_table('price_levels', schema=None) as batch_op:
            batch_op.create_foreign_key('price_levels_variety_id_fkey', 'varieties', ['variety_id'], ['id'])
            batch_op.create_foreign_key('price_levels_user_id_fkey', 'users', ['user_id'], ['id'])

        # opinions
        with op.batch_alter_table('opinions', schema=None) as batch_op:
            batch_op.create_foreign_key('opinions_variety_id_fkey', 'varieties', ['variety_id'], ['id'])
            batch_op.create_foreign_key('opinions_user_id_fkey', 'users', ['user_id'], ['id'])

        # kline_data
        with op.batch_alter_table('kline_data', schema=None) as batch_op:
            batch_op.create_foreign_key('kline_data_variety_id_fkey', 'varieties', ['variety_id'], ['id'])
            batch_op.create_foreign_key('kline_data_contract_id_fkey', 'fut_contracts', ['contract_id'], ['id'])

        # fut_daily_data
        with op.batch_alter_table('fut_daily_data', schema=None) as batch_op:
            batch_op.create_foreign_key('fut_daily_data_variety_id_fkey', 'varieties', ['variety_id'], ['id'])

        # contract_rollovers
        with op.batch_alter_table('contract_rollovers', schema=None) as batch_op:
            batch_op.create_foreign_key('contract_rollovers_variety_id_fkey', 'varieties', ['variety_id'], ['id'])
            batch_op.create_foreign_key('contract_rollovers_new_contract_id_fkey', 'fut_contracts', ['new_contract_id'], ['id'])
            batch_op.create_foreign_key('contract_rollovers_old_contract_id_fkey', 'fut_contracts', ['old_contract_id'], ['id'])

        # comments
        with op.batch_alter_table('comments', schema=None) as batch_op:
            batch_op.create_foreign_key('comments_user_id_fkey', 'users', ['user_id'], ['id'])
            batch_op.create_foreign_key('comments_product_id_fkey', 'products', ['product_id'], ['id'])
            batch_op.create_foreign_key('comments_price_level_id_fkey', 'price_levels', ['price_level_id'], ['id'])
    else:
        # watchlists
        _pg_drop_fk_if_exists('watchlists', 'fk_watchlists_variety_id_varieties', 'watchlists_variety_id_fkey')
        _pg_drop_fk_if_exists('watchlists', 'fk_watchlists_user_id_users', 'watchlists_user_id_fkey')
        op.create_foreign_key('watchlists_variety_id_fkey', 'watchlists', 'varieties', ['variety_id'], ['id'])
        op.create_foreign_key('watchlists_user_id_fkey', 'watchlists', 'users', ['user_id'], ['id'])

        # refresh_tokens
        _pg_drop_fk_if_exists('refresh_tokens', 'fk_refresh_tokens_user_id_users', 'refresh_tokens_user_id_fkey')
        op.create_foreign_key('refresh_tokens_user_id_fkey', 'refresh_tokens', 'users', ['user_id'], ['id'])

        # realtime_quotes
        _pg_drop_fk_if_exists('realtime_quotes', 'fk_realtime_quotes_variety_id_varieties', 'realtime_quotes_variety_id_fkey')
        op.create_foreign_key('realtime_quotes_variety_id_fkey', 'realtime_quotes', 'varieties', ['variety_id'], ['id'])

        # price_levels
        _pg_drop_fk_if_exists('price_levels', 'fk_price_levels_variety_id_varieties', 'price_levels_variety_id_fkey')
        _pg_drop_fk_if_exists('price_levels', 'fk_price_levels_user_id_users', 'price_levels_user_id_fkey')
        op.create_foreign_key('price_levels_variety_id_fkey', 'price_levels', 'varieties', ['variety_id'], ['id'])
        op.create_foreign_key('price_levels_user_id_fkey', 'price_levels', 'users', ['user_id'], ['id'])

        # opinions
        _pg_drop_fk_if_exists('opinions', 'fk_opinions_variety_id_varieties', 'opinions_variety_id_fkey')
        _pg_drop_fk_if_exists('opinions', 'fk_opinions_user_id_users', 'opinions_user_id_fkey')
        op.create_foreign_key('opinions_variety_id_fkey', 'opinions', 'varieties', ['variety_id'], ['id'])
        op.create_foreign_key('opinions_user_id_fkey', 'opinions', 'users', ['user_id'], ['id'])

        # kline_data
        _pg_drop_fk_if_exists('kline_data', 'fk_kline_data_variety_id_varieties', 'kline_data_variety_id_fkey')
        _pg_drop_fk_if_exists('kline_data', 'fk_kline_data_contract_id_fut_contracts', 'kline_data_contract_id_fkey')
        op.create_foreign_key('kline_data_variety_id_fkey', 'kline_data', 'varieties', ['variety_id'], ['id'])
        op.create_foreign_key('kline_data_contract_id_fkey', 'kline_data', 'fut_contracts', ['contract_id'], ['id'])

        # fut_daily_data
        _pg_drop_fk_if_exists('fut_daily_data', 'fk_fut_daily_data_variety_id_varieties', 'fut_daily_data_variety_id_fkey')
        op.create_foreign_key('fut_daily_data_variety_id_fkey', 'fut_daily_data', 'varieties', ['variety_id'], ['id'])

        # contract_rollovers
        _pg_drop_fk_if_exists('contract_rollovers', 'fk_contract_rollovers_variety_id_varieties', 'contract_rollovers_variety_id_fkey')
        _pg_drop_fk_if_exists('contract_rollovers', 'fk_contract_rollovers_new_contract_id_fut_contracts', 'contract_rollovers_new_contract_id_fkey')
        _pg_drop_fk_if_exists('contract_rollovers', 'fk_contract_rollovers_old_contract_id_fut_contracts', 'contract_rollovers_old_contract_id_fkey')
        op.create_foreign_key('contract_rollovers_variety_id_fkey', 'contract_rollovers', 'varieties', ['variety_id'], ['id'])
        op.create_foreign_key('contract_rollovers_new_contract_id_fkey', 'contract_rollovers', 'fut_contracts', ['new_contract_id'], ['id'])
        op.create_foreign_key('contract_rollovers_old_contract_id_fkey', 'contract_rollovers', 'fut_contracts', ['old_contract_id'], ['id'])

        # comments
        _pg_drop_fk_if_exists('comments', 'fk_comments_user_id_users', 'comments_user_id_fkey')
        _pg_drop_fk_if_exists('comments', 'fk_comments_product_id_products', 'comments_product_id_fkey')
        _pg_drop_fk_if_exists('comments', 'fk_comments_price_level_id_price_levels', 'comments_price_level_id_fkey')
        op.create_foreign_key('comments_user_id_fkey', 'comments', 'users', ['user_id'], ['id'])
        op.create_foreign_key('comments_product_id_fkey', 'comments', 'products', ['product_id'], ['id'])
        op.create_foreign_key('comments_price_level_id_fkey', 'comments', 'price_levels', ['price_level_id'], ['id'])
