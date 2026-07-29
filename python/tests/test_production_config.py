"""
生产配置安全测试
================
验证：生产环境禁止 SQLite、SECRET_KEY 强度、CORS 配置必填、SSE 部署模式显式有效

运行方式：
    cd python
    pytest tests/test_production_config.py -v
"""

import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_production_sqlite_banned():
    """ENV=production + SQLite 导入 config 应失败"""
    env = os.environ.copy()
    env["ENV"] = "production"
    env["DATABASE_URL"] = "sqlite:///./test.db"
    env["SECRET_KEY"] = "this-is-a-very-long-secret-key-for-production-testing"
    env["SSE_DEPLOYMENT_MODE"] = "single"
    env["DOTENV_PATH"] = "/nonexistent/.env"
    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )
    assert result.returncode != 0
    assert "SQLite is not allowed in production" in result.stderr


def test_production_postgresql_allowed():
    """ENV=production + PostgreSQL 导入 config 应成功"""
    env = os.environ.copy()
    env["ENV"] = "production"
    env["DATABASE_URL"] = "postgresql://user:pass@localhost/db"
    env["SECRET_KEY"] = "this-is-a-very-long-secret-key-for-production-testing"
    env["SSE_DEPLOYMENT_MODE"] = "single"
    env["DOTENV_PATH"] = "/nonexistent/.env"
    result = subprocess.run(
        [sys.executable, "-c", "import config; print('OK')"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_production_secret_key_too_short():
    """ENV=production + SECRET_KEY < 32 应失败"""
    env = os.environ.copy()
    env["ENV"] = "production"
    env["DATABASE_URL"] = "postgresql://user:pass@localhost/db"
    env["SECRET_KEY"] = "short"
    env["SSE_DEPLOYMENT_MODE"] = "single"
    env["DOTENV_PATH"] = "/nonexistent/.env"
    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )
    assert result.returncode != 0
    assert "SECRET_KEY must be at least 32 characters" in result.stderr


def test_production_cors_missing():
    """ENV=production + CORS 缺失 应失败"""
    env = os.environ.copy()
    env["ENV"] = "production"
    env["DATABASE_URL"] = "postgresql://user:pass@localhost/db"
    env["SECRET_KEY"] = "this-is-a-very-long-secret-key-for-production-testing"
    env["SSE_DEPLOYMENT_MODE"] = "single"
    env.pop("CORS_ORIGINS", None)
    env.pop("ALLOW_ORIGINS", None)
    env["DOTENV_PATH"] = "/nonexistent/.env"
    result = subprocess.run(
        [sys.executable, "-c", "import main"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )
    assert result.returncode != 0
    assert "CORS_ORIGINS (or ALLOW_ORIGINS) is required in production" in result.stderr


def test_non_production_sse_deployment_mode_defaults_to_single():
    """非生产环境未配置 SSE_DEPLOYMENT_MODE 时应默认 single"""
    env = os.environ.copy()
    env["ENV"] = "development"
    env["SECRET_KEY"] = "test-secret-key-for-pytest-local-development"
    env.pop("SSE_DEPLOYMENT_MODE", None)
    env["DOTENV_PATH"] = "/nonexistent/.env"
    result = subprocess.run(
        [sys.executable, "-c", "import config; print(config.SSE_DEPLOYMENT_MODE)"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "single"


def test_production_sse_deployment_mode_is_required():
    """生产环境必须显式配置 SSE_DEPLOYMENT_MODE"""
    env = os.environ.copy()
    env["ENV"] = "production"
    env["DATABASE_URL"] = "postgresql://user:pass@localhost/db"
    env["SECRET_KEY"] = "this-is-a-very-long-secret-key-for-production-testing"
    env.pop("SSE_DEPLOYMENT_MODE", None)
    env["DOTENV_PATH"] = "/nonexistent/.env"
    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )
    assert result.returncode != 0
    assert "SSE_DEPLOYMENT_MODE must be explicitly set to single or sticky" in result.stderr


def test_production_sse_deployment_mode_rejects_unsupported_value():
    """生产环境仅接受 single 或 sticky"""
    env = os.environ.copy()
    env["ENV"] = "production"
    env["DATABASE_URL"] = "postgresql://user:pass@localhost/db"
    env["SECRET_KEY"] = "this-is-a-very-long-secret-key-for-production-testing"
    env["SSE_DEPLOYMENT_MODE"] = "multi"
    env["DOTENV_PATH"] = "/nonexistent/.env"
    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )
    assert result.returncode != 0
    assert "SSE_DEPLOYMENT_MODE must be single or sticky" in result.stderr


def test_production_sse_deployment_mode_normalizes_supported_value():
    """配置层与发布预检一致地规范化受支持模式"""
    env = os.environ.copy()
    env["ENV"] = "production"
    env["DATABASE_URL"] = "postgresql://user:pass@localhost/db"
    env["SECRET_KEY"] = "this-is-a-very-long-secret-key-for-production-testing"
    env["SSE_DEPLOYMENT_MODE"] = " STICKY "
    env["DOTENV_PATH"] = "/nonexistent/.env"
    result = subprocess.run(
        [sys.executable, "-c", "import config; print(config.SSE_DEPLOYMENT_MODE)"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "sticky"


def test_bcrypt_rounds_default():
    """默认 BCRYPT_ROUNDS 应为 12"""
    env = os.environ.copy()
    env["SECRET_KEY"] = "test-secret-key-for-pytest-local-development"
    env["DOTENV_PATH"] = "/nonexistent/.env"
    result = subprocess.run(
        [sys.executable, "-c", "import config; print(config.BCRYPT_ROUNDS)"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "12" in result.stdout


def test_bcrypt_rounds_configurable():
    """BCRYPT_ROUNDS 应可通过环境变量配置"""
    env = os.environ.copy()
    env["SECRET_KEY"] = "test-secret-key-for-pytest-local-development"
    env["BCRYPT_ROUNDS"] = "4"
    env["DOTENV_PATH"] = "/nonexistent/.env"
    result = subprocess.run(
        [sys.executable, "-c", "import config; print(config.BCRYPT_ROUNDS)"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "4" in result.stdout
