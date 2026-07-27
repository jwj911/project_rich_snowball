from data_collector.init_mock_data import (
    _MOCK_COMMENTS,
    _MOCK_USER_SPECS,
    _ensure_mock_users_and_comments,
)
from models import CommentDB, UserDB
from utils import hash_password


def test_mock_comments_resolve_users_without_assuming_primary_key_values(db_session, seed_varieties):
    db_session.add(
        UserDB(
            username="existing_user",
            email="existing@example.com",
            password_hash=hash_password("password123"),
        )
    )
    db_session.commit()

    variety_map = {variety.symbol: variety for variety in seed_varieties}
    _ensure_mock_users_and_comments(db_session, variety_map)
    _ensure_mock_users_and_comments(db_session, variety_map)

    expected_usernames = {user["username"] for user in _MOCK_USER_SPECS}
    mock_users = db_session.query(UserDB).filter(UserDB.username.in_(expected_usernames)).all()
    assert {user.username for user in mock_users} == expected_usernames
    assert all(user.id != 1 for user in mock_users)

    comments = db_session.query(CommentDB).all()
    assert len(comments) == len(_MOCK_COMMENTS)
    username_by_id = {user.id: user.username for user in mock_users}
    expected_username_by_content = {comment["content"]: comment["username"] for comment in _MOCK_COMMENTS}
    assert {comment.content: username_by_id[comment.user_id] for comment in comments} == expected_username_by_content
