"""
Pytest fixtures：提供隔离 SQLite 数据库 + TestClient，实现测试隔离。
"""

import os
import sys
import tempfile
import atexit
from typing import Generator

# 确保在导入任何项目模块前设置测试环境变量
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ["ENABLE_SCHEDULER"] = "0"
os.environ["DOTENV_PATH"] = "/nonexistent/.env"

# 创建临时数据库文件，确保所有测试共享同一个物理数据库（避免 :memory: 多连接隔离问题）
_TEST_DB_FILE = tempfile.mktemp(suffix="_test.db")
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
def seed_varieties(db_session):
    """在内存库中初始化 10 个品种数据。"""
    from models import VarietyDB

    varieties = [
        VarietyDB(symbol="AU", contract_code="AU2406", name="黄金", exchange="SHFE", category="贵金属"),
        VarietyDB(symbol="AG", contract_code="AG2406", name="白银", exchange="SHFE", category="贵金属"),
        VarietyDB(symbol="CU", contract_code="CU2406", name="铜", exchange="SHFE", category="有色金属"),
        VarietyDB(symbol="RB", contract_code="RB2406", name="螺纹钢", exchange="SHFE", category="黑色系"),
        VarietyDB(symbol="I", contract_code="I2406", name="铁矿石", exchange="DCE", category="黑色系"),
        VarietyDB(symbol="SC", contract_code="SC2406", name="原油", exchange="INE", category="能源化工"),
        VarietyDB(symbol="MA", contract_code="MA2406", name="甲醇", exchange="ZCE", category="能源化工"),
        VarietyDB(symbol="M", contract_code="M2406", name="豆粕", exchange="DCE", category="农产品"),
        VarietyDB(symbol="C", contract_code="C2406", name="玉米", exchange="DCE", category="农产品"),
        VarietyDB(symbol="CF", contract_code="CF2406", name="棉花", exchange="ZCE", category="农产品"),
    ]
    for v in varieties:
        db_session.add(v)
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
