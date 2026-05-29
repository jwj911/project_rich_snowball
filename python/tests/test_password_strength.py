"""密码强度测试

验证：密码最小长度 8、必须包含字母和数字。
运行方式：
    cd python
    pytest tests/test_password_strength.py -v
"""

import pytest
from pydantic import ValidationError

from schemas import UserCreate


class TestPasswordStrength:
    def test_password_too_short_rejected(self):
        """密码长度 < 8 应被拒绝"""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(username="testuser", email="test@example.com", password="short1")
        assert "String should have at least 8 characters" in str(exc_info.value)

    def test_password_no_digit_rejected(self):
        """密码不含数字应被拒绝"""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(username="testuser", email="test@example.com", password="onlyletters")
        assert "密码必须包含至少一个数字" in str(exc_info.value)

    def test_password_no_letter_rejected(self):
        """密码不含字母应被拒绝"""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(username="testuser", email="test@example.com", password="12345678")
        assert "密码必须包含至少一个字母" in str(exc_info.value)

    def test_password_valid_accepted(self):
        """符合要求的密码应被接受"""
        user = UserCreate(username="testuser", email="test@example.com", password="password123")
        assert user.password == "password123"

    def test_password_with_special_chars_accepted(self):
        """含特殊字符的强密码应被接受"""
        user = UserCreate(username="testuser", email="test@example.com", password="MyP@ssw0rd!")
        assert user.password == "MyP@ssw0rd!"
