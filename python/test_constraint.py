import os
import sys
import tempfile

os.environ.setdefault("SECRET_KEY", "test")
os.environ["ENABLE_SCHEDULER"] = "0"
_TEST_DB_FILE = tempfile.mktemp(suffix="_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_FILE}"
sys.path.insert(0, ".")

from models import init_db, engine
init_db()
from sqlalchemy import text

with engine.begin() as conn:
    conn.execute(text("INSERT INTO users (username, email, password_hash) VALUES ('u1', 'u1@test.com', 'hash')"))
    conn.execute(text("INSERT INTO varieties (symbol, contract_code, name, exchange, category) VALUES ('AU', 'AU2406', '黄金', 'SHFE', '贵金属')"))
    conn.execute(text("INSERT INTO price_levels (user_id, variety_id, type, price, scope, source) VALUES (1, 1, 'support', 450, 'continuous', 'manual')"))
    try:
        conn.execute(text("INSERT INTO price_levels (user_id, variety_id, type, price, scope, source) VALUES (1, 1, 'support', 450, 'continuous', 'manual')"))
        print("Second insert succeeded - constraint NOT enforced!")
    except Exception as e:
        print("Second insert failed:", type(e).__name__, e)
