"""
Pytest fixtures：提供隔离 SQLite 数据库 + TestClient，实现测试隔离。
"""

import os
import sys
import tempfile
import atexit
from typing import Generator

# 确保在导入任何项目模块前设置测试环境变量
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-local-development")
os.environ["ENABLE_SCHEDULER"] = "0"
os.environ["DOTENV_PATH"] = "/nonexistent/.env"

# 创建临时数据库文件，确保所有测试共享同一个物理数据库（避免 :memory: 多连接隔离问题）
_TEST_DB_FILE = tempfile.mktemp(suffix="_test.db")
# 保存原始 DATABASE_URL，供 PostgreSQL 专属测试读取
os.environ["_PYTEST_ORIGINAL_DATABASE_URL"] = os.environ.get("DATABASE_URL", "")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_FILE}"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

# 必须先导入 models 让全局 engine 指向临时库，然后再导入 main
import models as _models_module
from main import app
from dependencies import get_db
from models import Base

# 使用 models 的全局 engine（已绑定到临时文件数据库），所有测试共享同一连接池
engine = _models_module.engine
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session() -> Generator:
    """每次测试函数独立创建表，函数结束后回滚并丢弃。"""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    # 创建所有表
    Base.metadata.create_all(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session):
    """返回覆盖 get_db 依赖的 TestClient。"""
    from fastapi.testclient import TestClient
    from routers.auth import clear_rate_limit_store

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    clear_rate_limit_store()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_headers(client):
    """注册并登录测试用户，返回包含 Bearer token 的请求头。"""
    client.post("/api/auth/register", json={
        "username": "integration_tester",
        "email": "integration@test.com",
        "password": "password123"
    })
    r = client.post("/api/auth/login", data={
        "username": "integration_tester",
        "password": "password123"
    })
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def seed_varieties(db_session):
    """在内存库中初始化 10 个品种数据（如 lifespan 已初始化则复用）。"""
    from models import VarietyDB

    specs = [
        ("AU", "AU2406", "黄金", "SHFE", "贵金属"),
        ("AG", "AG2406", "白银", "SHFE", "贵金属"),
        ("CU", "CU2406", "铜", "SHFE", "有色金属"),
        ("RB", "RB2406", "螺纹钢", "SHFE", "黑色系"),
        ("I", "I2406", "铁矿石", "DCE", "黑色系"),
        ("SC", "SC2406", "原油", "INE", "能源化工"),
        ("MA", "MA2406", "甲醇", "ZCE", "能源化工"),
        ("M", "M2406", "豆粕", "DCE", "农产品"),
        ("C", "C2406", "玉米", "DCE", "农产品"),
        ("CF", "CF2406", "棉花", "ZCE", "农产品"),
    ]

    existing = {v.symbol: v for v in db_session.query(VarietyDB).filter(VarietyDB.symbol.in_([s[0] for s in specs])).all()}
    varieties = []
    for sym, contract, name, exchange, category in specs:
        if sym in existing:
            varieties.append(existing[sym])
        else:
            v = VarietyDB(symbol=sym, contract_code=contract, name=name, exchange=exchange, category=category)
            db_session.add(v)
            db_session.flush()
            varieties.append(v)
    db_session.commit()
    return varieties


def _cleanup_test_db():
    """测试进程退出时删除临时数据库文件。"""
    import os as _os
    if _os.path.exists(_TEST_DB_FILE):
        try:
            _os.remove(_TEST_DB_FILE)
        except OSError:
            pass


atexit.register(_cleanup_test_db)
