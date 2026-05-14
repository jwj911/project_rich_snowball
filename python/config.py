import os
from pathlib import Path
from dotenv import load_dotenv

# .env is at project root, config.py is in python/ subdirectory
# Allow overriding via DOTENV_PATH for testing
env_path = Path(os.getenv("DOTENV_PATH", Path(__file__).parent.parent / ".env"))
load_dotenv(dotenv_path=env_path)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./futures_community.db")
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# 环境控制
ENV = os.getenv("ENV", "development")
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "0") == "1"

# SECRET_KEY 强度检查（必须在 ENV 定义之后）
if ENV == "production" and len(SECRET_KEY) < 32:
    raise ValueError("SECRET_KEY must be at least 32 characters in production")

# 生产环境禁止 SQLite
if ENV == "production" and DATABASE_URL.startswith("sqlite"):
    raise ValueError("SQLite is not allowed in production. Use PostgreSQL.")

# 数据源配置
DATA_SOURCE = os.getenv("DATA_SOURCE", "mock")
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")
