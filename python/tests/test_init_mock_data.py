from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data_collector.init_mock_data import (
    _MOCK_COMMENTS,
    _MOCK_USER_SPECS,
    _ensure_mock_users_and_comments,
)
from models import Base, CommentDB, UserDB, VarietyDB


def test_mock_comments_resolve_users_without_assuming_primary_key_values():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        symbols = {comment["symbol"] for comment in _MOCK_COMMENTS}
        varieties = [
            VarietyDB(
                symbol=symbol,
                contract_code=f"{symbol}2406",
                name=f"test-{symbol}",
                exchange="SHFE",
                category="test",
            )
            for symbol in symbols
        ]
        session.add_all(varieties)
        session.add(
            UserDB(
                id=100,
                username="existing_user",
                email="existing@example.com",
                password_hash="test-only",
            )
        )
        session.commit()

        variety_map = {variety.symbol: variety for variety in varieties}
        _ensure_mock_users_and_comments(session, variety_map)
        _ensure_mock_users_and_comments(session, variety_map)

        expected_usernames = {user["username"] for user in _MOCK_USER_SPECS}
        mock_users = session.query(UserDB).filter(UserDB.username.in_(expected_usernames)).all()
        assert {user.username for user in mock_users} == expected_usernames
        assert all(user.id > 100 for user in mock_users)

        comments = session.query(CommentDB).all()
        assert len(comments) == len(_MOCK_COMMENTS)
        username_by_id = {user.id: user.username for user in mock_users}
        expected_username_by_content = {comment["content"]: comment["username"] for comment in _MOCK_COMMENTS}
        assert {
            comment.content: username_by_id[comment.user_id] for comment in comments
        } == expected_username_by_content
    finally:
        session.close()
        engine.dispose()
