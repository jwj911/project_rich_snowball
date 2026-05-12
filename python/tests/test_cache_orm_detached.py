"""
缓存 DTO 化测试
===============
验证：实时行情缓存返回 dict 而非 ORM 实例，无 DetachedInstanceError

运行方式：
    cd python
    pytest tests/test_cache_orm_detached.py -v
"""

import os
import sys
import threading

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_realtime_returns_dict_not_orm():
    """实时行情接口应返回 plain dict，不含 ORM 属性如 _sa_instance_state"""
    r = client.get("/api/realtime/AU")
    # AU 可能没有实时数据，404 也是可接受的；若存在数据则检查结构
    if r.status_code == 200:
        data = r.json()
        assert "symbol" in data
        assert "current_price" in data
        # 不应包含 SQLAlchemy ORM 内部属性
        assert "_sa_instance_state" not in data


def test_realtime_concurrent_no_exception():
    """并发请求实时行情不应抛出 DetachedInstanceError"""
    errors = []

    def worker():
        try:
            for _ in range(20):
                r = client.get("/api/realtime/AU")
                # 200 或 404 都是正常响应
                assert r.status_code in (200, 404)
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发请求出错: {errors}"
