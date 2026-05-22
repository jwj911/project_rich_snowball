"""
缓存 DTO 化测试
===============
验证：实时行情缓存返回 dict 而非 ORM 实例，无 DetachedInstanceError

运行方式：
    cd python
    pytest tests/test_cache_orm_detached.py -v
"""


def test_realtime_returns_dict_not_orm(client, auth_headers):
    """实时行情接口应返回 plain dict，不含 ORM 属性如 _sa_instance_state"""
    r = client.get("/api/realtime/AU", headers=auth_headers)
    # AU 可能没有实时数据，404 也是可接受的；若存在数据则检查结构
    if r.status_code == 200:
        data = r.json()
        assert "symbol" in data
        assert "current_price" in data
        # 不应包含 SQLAlchemy ORM 内部属性
        assert "_sa_instance_state" not in data


def test_realtime_rapid_requests_no_exception(client, auth_headers):
    """高频请求实时行情不应抛出 DetachedInstanceError。

    说明：当前 _fetch_realtime 已返回纯 dict（通过 get_cached 缓存），
    不存在 ORM session detached 风险。本测试通过高频顺序请求验证稳定性。
    由于 conftest.py 使用显式事务隔离，多线程并发会面临 SQLite 连接隔离问题，
    故采用单线程高频请求替代。
    """
    for _ in range(100):
        r = client.get("/api/realtime/AU", headers=auth_headers)
        # 200 或 404 都是正常响应
        assert r.status_code in (200, 404)
