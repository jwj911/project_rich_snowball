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
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
