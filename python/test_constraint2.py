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

with engine.connect() as conn:
    indexes = conn.execute(text("PRAGMA index_list(price_levels)")).fetchall()
    for idx in indexes:
        print("index:", idx)
    print('---')
    for idx in indexes:
        info = conn.execute(text(f"PRAGMA index_info('{idx[1]}')")).fetchall()
        print("info for", idx[1], ":", info)
