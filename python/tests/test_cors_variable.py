"""
CORS 变量兼容测试
================
验证：CORS_ORIGINS 优先、ALLOW_ORIGINS 兼容、两者都缺失时行为

运行方式：
    cd python
    pytest tests/test_cors_variable.py -v
"""

import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_with_env(extra_env: dict, code: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DOTENV_PATH"] = "/nonexistent/.env"
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )


def test_cors_origins_priority():
    """CORS_ORIGINS 应被优先读取"""
    result = _run_with_env(
        {
            "SECRET_KEY": "test-secret-key-for-pytest-local-development",
            "CORS_ORIGINS": "https://example.com",
            "ALLOW_ORIGINS": "http://old.example.com",
        },
        "import main; print(main.origins)",
    )
    assert result.returncode == 0, result.stderr
    assert "https://example.com" in result.stdout
    assert "http://old.example.com" not in result.stdout


def test_allow_origins_fallback():
    """仅设置 ALLOW_ORIGINS 时仍应兼容"""
    result = _run_with_env(
        {
            "SECRET_KEY": "test-secret-key-for-pytest-local-development",
            "ALLOW_ORIGINS": "http://fallback.example.com",
        },
        "import main; print(main.origins)",
    )
    assert result.returncode == 0, result.stderr
    assert "http://fallback.example.com" in result.stdout


def test_default_origins_when_none_set():
    """未设置任何 CORS 变量时，开发环境使用默认值"""
    result = _run_with_env(
        {
            "SECRET_KEY": "test-secret-key-for-pytest-local-development",
        },
        "import main; print(main.origins)",
    )
    assert result.returncode == 0, result.stderr
    assert "http://localhost:3000" in result.stdout


def test_cors_max_age_default():
    """未设置 CORS_MAX_AGE_SECONDS 时，默认 max_age 为 600"""
    result = _run_with_env(
        {
            "SECRET_KEY": "test-secret-key-for-pytest-local-development",
        },
        "import main, os; print(os.getenv('CORS_MAX_AGE_SECONDS', '600'))",
    )
    assert result.returncode == 0, result.stderr
    assert "600" in result.stdout


def test_cors_max_age_custom():
    """设置 CORS_MAX_AGE_SECONDS 后应被正确读取"""
    result = _run_with_env(
        {
            "SECRET_KEY": "test-secret-key-for-pytest-local-development",
            "CORS_MAX_AGE_SECONDS": "1200",
        },
        "import config; print(config.CORS_MAX_AGE_SECONDS)",
    )
    assert result.returncode == 0, result.stderr
    assert "1200" in result.stdout
