# 期货社区后端重构 — 质量测试计划

> 测试日期：2026-05-03  
> 测试范围：python/ 全部后端代码  
> 执行顺序：单元 → 集成 → 并发 → 安全 → 业务 → 回归

---

## 环境确认 Checklist

- [ ] Python 3.12+，`python --version`
- [ ] 依赖已安装：`pip install -r requirements.txt`
- [ ] 测试依赖已安装：`pip install pytest pytest-asyncio httpx`
- [ ] `.env` 中 `SECRET_KEY` 已设置
- [ ] 数据库已迁移：`cd python && alembic upgrade head`
- [ ] 种子数据已灌入：`python data_collector/init_varieties.py`
- [ ] 后端可启动：`python main.py` → `http://localhost:8000/docs` 可访问

---

## 一、单元测试（Unit Tests）

### 1.1 模型层测试

**目标文件**：`python/models.py`  
**测试文件**：`python/tests/test_models.py`

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, VarietyDB, RealtimeQuoteDB, KlineDataDB, UserDB, CommentDB
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_variety_create(db):
    v = VarietyDB(symbol="TEST", contract_code="TEST2506", name="测试", exchange="SHFE")
    db.add(v)
    db.commit()
    assert v.id is not None
    assert v.symbol == "TEST"


def test_variety_unique_symbol(db):
    v1 = VarietyDB(symbol="DUP", contract_code="DUP2506", name="重复1", exchange="SHFE")
    db.add(v1)
    db.commit()
    v2 = VarietyDB(symbol="DUP", contract_code="DUP2507", name="重复2", exchange="SHFE")
    db.add(v2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_realtime_quote_relation(db):
    v = VarietyDB(symbol="AU", contract_code="AU2506", name="黄金", exchange="SHFE")
    db.add(v)
    db.commit()

    rt = RealtimeQuoteDB(variety_id=v.id, current_price=450.0, updated_at=__import__('datetime').datetime.now())
    db.add(rt)
    db.commit()

    assert v.realtime.current_price == 450.0


def test_kline_unique_constraint(db):
    v = VarietyDB(symbol="AU", contract_code="AU2506", name="黄金", exchange="SHFE")
    db.add(v)
    db.commit()

    from datetime import datetime
    k1 = KlineDataDB(variety_id=v.id, period="1h", trading_time=datetime(2024, 1, 1, 10, 0), open_price=100, high_price=105, low_price=98, close_price=102, volume=1000)
    db.add(k1)
    db.commit()

    k2 = KlineDataDB(variety_id=v.id, period="1h", trading_time=datetime(2024, 1, 1, 10, 0), open_price=101, high_price=106, low_price=99, close_price=103, volume=2000)
    db.add(k2)
    with pytest.raises(IntegrityError):
        db.commit()


def test_user_password_not_plaintext(db):
    from utils import hash_password
    u = UserDB(username="test", email="test@test.com", password_hash=hash_password("password123"))
    db.add(u)
    db.commit()
    assert u.password_hash != "password123"
    assert u.password_hash.startswith("$2b$")
```

**执行命令**：
```bash
cd python
pytest tests/test_models.py -v
```

---

### 1.2 数据清洗器测试

**目标文件**：`python/data_collector/cleaner.py`  
**测试文件**：`python/tests/test_cleaner.py`

```python
import pytest
from data_collector.cleaner import clean_realtime, clean_kline
from datetime import datetime


def test_clean_realtime_valid():
    raw = {"current_price": 450.0, "high": 455.0, "low": 448.0, "volume": 1000, "change_percent": 1.5}
    result = clean_realtime(raw, "AU")
    assert result is not None
    assert result["current_price"] == 450.0


def test_clean_realtime_negative_price():
    raw = {"current_price": -100, "high": 455.0, "low": 448.0, "volume": 1000}
    assert clean_realtime(raw, "AU") is None


def test_clean_realtime_high_less_than_low():
    raw = {"current_price": 450.0, "high": 440.0, "low": 448.0, "volume": 1000}
    assert clean_realtime(raw, "AU") is None


def test_clean_realtime_invalid_volume_type():
    raw = {"current_price": 450.0, "high": 455.0, "low": 448.0, "volume": "abc"}
    # 应不崩溃，返回 None 或处理为 0
    result = clean_realtime(raw, "AU")
    assert result is None  # int("abc") 会抛 ValueError，被 except 捕获


def test_clean_kline_dedup():
    ts = datetime(2024, 1, 1, 10, 0)
    raw_list = [
        {"symbol": "AU", "trading_time": ts, "open_price": 100, "high_price": 105, "low_price": 98, "close_price": 102, "volume": 1000},
        {"symbol": "AU", "trading_time": ts, "open_price": 101, "high_price": 106, "low_price": 99, "close_price": 103, "volume": 2000},
    ]
    result = clean_kline(raw_list, "AU")
    assert len(result) == 1
    assert result[0]["open_price"] == 100


def test_clean_kline_empty():
    assert clean_kline([], "AU") == []
```

**执行命令**：
```bash
cd python
pytest tests/test_cleaner.py -v
```

---

### 1.3 缓存层测试

**目标文件**：`python/services/cache.py`  
**测试文件**：`python/tests/test_cache.py`

```python
import pytest
import threading
import time
from services.cache import get_cached, invalidate_cache


def test_cache_hit():
    call_count = 0
    def fetch():
        nonlocal call_count
        call_count += 1
        return "data"

    r1 = get_cached("test:hit", fetch, ttl=5)
    r2 = get_cached("test:hit", fetch, ttl=5)
    assert r1 == "data"
    assert r2 == "data"
    assert call_count == 1  # 第二次走缓存


def test_cache_ttl_expired():
    call_count = 0
    def fetch():
        nonlocal call_count
        call_count += 1
        return f"data_{call_count}"

    r1 = get_cached("test:ttl", fetch, ttl=1)
    time.sleep(1.1)
    r2 = get_cached("test:ttl", fetch, ttl=1)
    assert r1 != r2  # TTL 过期后重新获取
    assert call_count == 2


def test_cache_concurrent_access():
    results = []
    def worker():
        def fetch():
            return "safe"
        r = get_cached("test:concurrent", fetch, ttl=5)
        results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r == "safe" for r in results)


def test_cache_memory_leak():
    for i in range(1000):
        get_cached(f"key:{i}", lambda: "x", ttl=3600)
    # 当前实现无自动淘汰，1000 个 key 后 dict 长度为 1000+
    # 通过测试说明需要增加淘汰机制
```

**执行命令**：
```bash
cd python
pytest tests/test_cache.py -v
```

---

## 二、集成测试（Integration Tests）

### 2.1 API 契约测试

**测试文件**：`python/tests/test_api_contract.py`

```python
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestVarietiesApi:
    def test_list_varieties(self):
        r = client.get("/api/varieties")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            assert "symbol" in data[0]
            assert "name" in data[0]

    def test_varieties_category_filter(self):
        r = client.get("/api/varieties?category=贵金属")
        assert r.status_code == 200
        for v in r.json():
            assert v["category"] == "贵金属"

    def test_varieties_search(self):
        r = client.get("/api/varieties?search=黄金")
        assert r.status_code == 200
        assert any("黄金" in v["name"] for v in r.json())

    def test_varieties_pagination(self):
        r = client.get("/api/varieties?skip=0&limit=5")
        assert len(r.json()) == 5

    def test_varieties_invalid_limit(self):
        r = client.get("/api/varieties?limit=1001")
        assert r.status_code == 422

    def test_variety_detail(self):
        r = client.get("/api/varieties/AU")
        assert r.status_code == 200
        assert r.json()["symbol"] == "AU"

    def test_variety_not_found(self):
        r = client.get("/api/varieties/UNKNOWN")
        assert r.status_code == 404


class TestKlineApi:
    def test_kline_success(self):
        r = client.get("/api/kline/AU?period=1h&limit=10")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            assert "time" in data[0]
            assert "open" in data[0]
            assert "close" in data[0]

    def test_kline_invalid_period(self):
        r = client.get("/api/kline/AU?period=1x")
        assert r.status_code == 422

    def test_kline_variety_not_found(self):
        r = client.get("/api/kline/UNKNOWN?period=1h")
        assert r.status_code == 404

    def test_kline_limit_zero(self):
        r = client.get("/api/kline/AU?period=1h&limit=0")
        assert r.status_code == 422


class TestRealtimeApi:
    def test_realtime_success(self):
        r = client.get("/api/realtime/AU")
        assert r.status_code == 200
        data = r.json()
        assert "current_price" in data
        assert "change_percent" in data

    def test_realtime_cached(self):
        import time
        t1 = time.time()
        r1 = client.get("/api/realtime/AU")
        t2 = time.time()
        r2 = client.get("/api/realtime/AU")
        t3 = time.time()

        first_ms = (t2 - t1) * 1000
        second_ms = (t3 - t2) * 1000
        assert r1.json()["current_price"] == r2.json()["current_price"]
        assert second_ms < first_ms * 0.5  # 缓存响应应明显更快

    def test_realtime_not_found(self):
        r = client.get("/api/realtime/UNKNOWN")
        assert r.status_code == 404


class TestAuthApi:
    def test_register_and_login(self):
        # 注册
        r = client.post("/api/auth/register", json={
            "username": "test_auth_user",
            "email": "auth@test.com",
            "password": "password123"
        })
        assert r.status_code == 200
        assert "password" not in r.json()

        # 登录
        r = client.post("/api/auth/login", data={
            "username": "test_auth_user",
            "password": "password123"
        })
        assert r.status_code == 200
        token = r.json()["access_token"]
        assert token is not None

        # Me
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["username"] == "test_auth_user"

        # 清理
        from models import SessionLocal, UserDB
        db = SessionLocal()
        db.query(UserDB).filter(UserDB.username == "test_auth_user").delete()
        db.commit()
        db.close()

    def test_login_wrong_password(self):
        r = client.post("/api/auth/login", data={
            "username": "trader001",
            "password": "wrong_password"
        })
        assert r.status_code == 401


class TestCommentsApi:
    def test_xss_escaped(self):
        # 先登录
        r = client.post("/api/auth/login", data={
            "username": "trader001",
            "password": "password123"
        })
        token = r.json()["access_token"]

        r = client.post("/api/comments", json={
            "product_id": 1,
            "content": "<script>alert(1)</script>"
        }, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert "<script>" not in r.json()["content"]
        assert "&lt;script&gt;" in r.json()["content"]

    def test_comment_too_long(self):
        r = client.post("/api/auth/login", data={
            "username": "trader001",
            "password": "password123"
        })
        token = r.json()["access_token"]

        r = client.post("/api/comments", json={
            "product_id": 1,
            "content": "x" * 2001
        }, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 422
```

**执行命令**：
```bash
cd python
pytest tests/test_api_contract.py -v
```

---

### 2.2 数据库一致性测试

**测试文件**：`python/tests/test_db_consistency.py`

```python
import pytest
from models import SessionLocal, VarietyDB, RealtimeQuoteDB, ProductDB
from data_collector.scheduler import refresh_realtime_quotes, sync_prices_to_products


def test_realtime_to_products_sync():
    """定时任务同步后，products.current_price 应与 realtime_quotes 一致"""
    refresh_realtime_quotes()
    sync_prices_to_products()

    db = SessionLocal()
    try:
        au_variety = db.query(VarietyDB).filter(VarietyDB.symbol == "AU").first()
        rt = db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == au_variety.id).first()
        product = db.query(ProductDB).filter(ProductDB.symbol == "AU").first()

        assert rt is not None
        assert product is not None
        assert product.current_price == rt.current_price
        assert product.change_percent == rt.change_percent
    finally:
        db.close()
```

---

## 三、并发与性能测试

### 3.1 SQLite 并发测试

**测试文件**：`python/tests/test_concurrency.py`

```python
import threading
import time
import requests

BASE_URL = "http://localhost:8000"


def test_concurrent_read_while_scheduler_running():
    """
    前提：后端已启动（python main.py）
    10 个线程同时读取 /api/varieties，观察是否有 database is locked
    """
    errors = []
    latencies = []

    def reader():
        for _ in range(20):
            try:
                start = time.time()
                r = requests.get(f"{BASE_URL}/api/varieties", timeout=5)
                latencies.append(time.time() - start)
                if r.status_code != 200:
                    errors.append(f"Status {r.status_code}: {r.text}")
            except Exception as e:
                errors.append(str(e))

    threads = [threading.Thread(target=reader) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"并发读取出现错误: {errors[:5]}"
    avg_latency = sum(latencies) / len(latencies)
    assert avg_latency < 0.2, f"平均延迟 {avg_latency}s 超过 200ms"


def test_cache_performance():
    """验证缓存是否生效"""
    import time

    # 首次请求
    t1 = time.time()
    r1 = requests.get(f"{BASE_URL}/api/realtime/AU")
    first_ms = (time.time() - t1) * 1000

    # 5 秒内第二次请求
    t2 = time.time()
    r2 = requests.get(f"{BASE_URL}/api/realtime/AU")
    second_ms = (time.time() - t2) * 1000

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert second_ms < first_ms * 0.5, f"缓存未生效: 首次 {first_ms:.1f}ms, 二次 {second_ms:.1f}ms"
    print(f"Cache performance: first={first_ms:.1f}ms, second={second_ms:.1f}ms")
```

**执行命令**：
```bash
# 终端 1：启动后端
python main.py

# 终端 2：执行并发测试
cd python
pytest tests/test_concurrency.py -v -s
```

---

## 四、安全测试

### 4.1 注入攻击

```bash
# SQL 注入测试
curl "http://localhost:8000/api/varieties?search=' OR 1=1 --"
# 预期：返回空列表或正常搜索结果，不暴露全部数据

curl "http://localhost:8000/api/varieties?category='; DROP TABLE varieties; --"
# 预期：422 或返回空列表，表不被删除
```

### 4.2 认证绕过

```bash
# 无 token 访问受保护接口
curl -X POST http://localhost:8000/api/comments -H "Content-Type: application/json" -d '{"product_id":1,"content":"test"}'
# 预期：401

# 伪造 token
curl http://localhost:8000/api/auth/me -H "Authorization: Bearer fake_token_123"
# 预期：401
```

### 4.3 输入校验

```bash
# 超长评论（需先登录获取 token）
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -d "username=trader001&password=password123" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
curl -X POST http://localhost:8000/api/comments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"product_id\":1,\"content\":\"$(python -c 'print("x"*2001)')\"}"
# 预期：422

# 非法 period
curl "http://localhost:8000/api/kline/AU?period=1x"
# 预期：422
```

### 4.4 敏感信息泄漏

```bash
# 检查错误响应是否包含堆栈
curl "http://localhost:8000/api/varieties/UNKNOWN"
# 预期：{"detail":"品种不存在"}，不包含 SQL 语句或文件路径

# 检查 Swagger 是否可访问（生产环境应关闭）
curl http://localhost:8000/docs
# 当前：200（开发环境可接受，生产环境需加认证或关闭）
```

---

## 五、期货业务场景测试

### 5.1 数据精度测试

```python
def test_price_precision():
    """价格存储和返回精度应为 2 位小数"""
    from data_collector.mock_collector import MockCollector
    c = MockCollector()
    data = c.fetch_realtime("AU")
    price_str = str(data["current_price"])
    # 检查是否最多 2 位小数
    if '.' in price_str:
        assert len(price_str.split('.')[1]) <= 2
```

### 5.2 数据源降级测试

```python
def test_collector_failure_fallback():
    """模拟 akshare 失败时，scheduler 应继续运行不崩溃"""
    from data_collector.scheduler import refresh_realtime_quotes
    # 当前使用 MockCollector，默认不会失败
    # 如切换到 AkshareCollector，可用 monkeypatch 模拟异常
    refresh_realtime_quotes()  # 应正常完成
```

---

## 六、回归测试

### 6.1 旧接口兼容

```bash
# 旧品种列表接口
curl http://localhost:8000/api/products | python -m json.tool
# 验证字段：id, name, symbol, current_price, change_percent, open_price, high, low, volume, category, margin, commission, updated_at

# 旧品种详情接口
curl http://localhost:8000/api/products/1 | python -m json.tool
# 验证：product + comments 结构

# 旧评论接口
curl http://localhost:8000/api/comments/user/trader001 | python -m json.tool
# 验证：返回列表，包含 id, product_id, user_id, username, content, created_at
```

### 6.2 前端联调验证

```bash
# 启动前端
cd frontend && npm run dev

# 验证点：
# 1. 首页热门品种卡片价格正确显示
# 2. 品种列表页可排序、价格自动刷新
# 3. 品种详情页 K 线图展示真实数据（非固定种子 mock）
# 4. 详情页价格每 30 秒自动更新
# 5. 评论区正常显示、可发表评论
```

---

## 七、测试执行汇总

| 阶段 | 测试文件 | 命令 | 通过标准 |
|------|----------|------|----------|
| 单元测试 | `test_models.py` | `pytest tests/test_models.py -v` | 全部通过 |
| 单元测试 | `test_cleaner.py` | `pytest tests/test_cleaner.py -v` | 全部通过 |
| 单元测试 | `test_cache.py` | `pytest tests/test_cache.py -v` | 全部通过，并发无异常 |
| 集成测试 | `test_api_contract.py` | `pytest tests/test_api_contract.py -v` | 全部通过 |
| 集成测试 | `test_db_consistency.py` | `pytest tests/test_db_consistency.py -v` | 全部通过 |
| 并发测试 | `test_concurrency.py` | `pytest tests/test_concurrency.py -v -s` | 无 database is locked，延迟 < 200ms |
| 安全测试 | 手动/Burp | 见第四节命令 | 无注入、无信息泄漏 |
| 回归测试 | 前端联调 | `npm run dev` + 人工验证 | 功能正常 |

---

## 八、测试后发现问题的处理流程

1. **🔴 严重问题**：立即停止后续测试，修复后重新执行全部测试
2. **🟡 中等问题**：记录问题，完成本轮测试后统一修复
3. **🟢 低优先级**：记录问题，进入 backlog，后续迭代处理

---

## 一句话总结

> **按"单元→集成→并发→安全→业务→回归"顺序执行，🔴 级问题必须修复后才能合并到主分支。所有测试代码保留在 `tests/` 目录，作为 CI 持续集成的一部分。**
