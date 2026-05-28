"""
验证外键 ondelete CASCADE / SET NULL 在 SQLite 和 SQLAlchemy ORM 层面的行为。
"""

import pytest
from sqlalchemy import text

from models import (
    UserDB,
    CommentDB,
    PriceLevelDB,
    WatchlistDB,
    RefreshTokenDB,
    ContractRolloverDB,
    FutContractDB,
    VarietyDB,
)


def test_sqlite_foreign_keys_enabled(db_session):
    """SQLite 连接已自动启用 PRAGMA foreign_keys=ON。"""
    result = db_session.execute(text("PRAGMA foreign_keys"))
    assert result.scalar() == 1


def test_user_delete_cascades_comments(db_session):
    """删除用户时，关联评论应被 CASCADE 删除。"""
    user = UserDB(username="cascade_user", email="c@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()

    variety = VarietyDB(symbol="TEST01", contract_code="TEST01", name="Test", exchange="SHFE")
    db_session.add(variety)
    db_session.flush()

    comment = CommentDB(variety_id=variety.id, user_id=user.id, content="hello")
    db_session.add(comment)
    db_session.commit()

    assert db_session.query(CommentDB).filter_by(user_id=user.id).count() == 1

    comment_id = comment.id
    db_session.delete(user)
    db_session.commit()

    assert db_session.query(CommentDB).filter_by(id=comment_id).first() is None


def test_user_delete_cascades_price_levels(db_session):
    """删除用户时，关联价位标注应被 CASCADE 删除。"""
    variety = VarietyDB(symbol="CU_CASCADE", contract_code="CU_CASCADE", name="铜", exchange="SHFE", category="有色")
    db_session.add(variety)
    db_session.flush()

    user = UserDB(username="pl_user", email="pl@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()

    pl = PriceLevelDB(user_id=user.id, variety_id=variety.id, type="support", price=50000)
    db_session.add(pl)
    db_session.commit()

    pl_id = pl.id
    db_session.delete(user)
    db_session.commit()

    assert db_session.query(PriceLevelDB).filter_by(id=pl_id).first() is None


def test_user_delete_cascades_watchlists(db_session):
    """删除用户时，关联自选应被 CASCADE 删除。"""
    variety = VarietyDB(symbol="AU_CASCADE", contract_code="AU_CASCADE", name="黄金", exchange="SHFE", category="贵金属")
    db_session.add(variety)
    db_session.flush()

    user = UserDB(username="wl_user", email="wl@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()

    wl = WatchlistDB(user_id=user.id, variety_id=variety.id)
    db_session.add(wl)
    db_session.commit()

    wl_id = wl.id
    db_session.delete(user)
    db_session.commit()

    assert db_session.query(WatchlistDB).filter_by(id=wl_id).first() is None


def test_user_delete_cascades_refresh_tokens(db_session):
    """删除用户时，关联 refresh token 应被 CASCADE 删除。"""
    from datetime import datetime, timedelta, timezone

    user = UserDB(username="rt_user", email="rt@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()

    rt = RefreshTokenDB(
        user_id=user.id,
        token_hash="abc123",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(rt)
    db_session.commit()

    rt_id = rt.id
    db_session.delete(user)
    db_session.commit()

    assert db_session.query(RefreshTokenDB).filter_by(id=rt_id).first() is None


def test_price_level_delete_sets_null_on_comments(db_session):
    """删除价位标注时，关联评论的 price_level_id 应被 SET NULL。"""
    variety = VarietyDB(symbol="RB_CASCADE", contract_code="RB_CASCADE", name="螺纹钢", exchange="SHFE", category="黑色")
    db_session.add(variety)
    db_session.flush()

    user = UserDB(username="pl_null_user", email="pn@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()

    pl = PriceLevelDB(user_id=user.id, variety_id=variety.id, type="resistance", price=3500)
    db_session.add(pl)
    db_session.flush()

    comment = CommentDB(variety_id=variety.id, user_id=user.id, price_level_id=pl.id, content="test")
    db_session.add(comment)
    db_session.commit()

    db_session.delete(pl)
    db_session.commit()

    comment_after = db_session.query(CommentDB).filter_by(id=comment.id).first()
    assert comment_after is not None
    assert comment_after.price_level_id is None


def test_contract_delete_sets_null_on_rollover(db_session):
    """删除合约时，换月记录的 old_contract_id 应被 SET NULL。"""
    variety = VarietyDB(symbol="AG_CASCADE", contract_code="AG_CASCADE", name="白银", exchange="SHFE", category="贵金属")
    db_session.add(variety)
    db_session.flush()

    old_contract = FutContractDB(ts_code="AG_CASCADE_06.SHFE", symbol="AG", name="白银2506", exchange="SHFE")
    new_contract = FutContractDB(ts_code="AG_CASCADE_07.SHFE", symbol="AG", name="白银2507", exchange="SHFE")
    db_session.add_all([old_contract, new_contract])
    db_session.flush()

    rollover = ContractRolloverDB(
        variety_id=variety.id,
        old_contract_id=old_contract.id,
        new_contract_id=new_contract.id,
        effective_date=variety.created_at,
    )
    db_session.add(rollover)
    db_session.commit()

    db_session.delete(old_contract)
    db_session.commit()

    rollover_after = db_session.query(ContractRolloverDB).filter_by(id=rollover.id).first()
    assert rollover_after is not None
    assert rollover_after.old_contract_id is None
    assert rollover_after.new_contract_id == new_contract.id
