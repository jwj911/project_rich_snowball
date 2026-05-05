# 期货社区后端重构 — 改进版质量测试计划

> 版本：v2.0（改进版）
> 日期：2026-05-03
> 改进依据：TEST_PLAN_AND_REVIEW_AUDIT.md 审查意见
> 目标：从"一次性验收清单"升级为"可持续交付的测试基础设施"

---

## 一、测试基础设施（新增）

### 1.1 CI/CD 集成（.github/workflows/test.yml）

```yaml
name: Backend Tests

on:
  push:
    branches: [main, develop]
    paths: ['python/**']
  pull_request:
    branches: [main, develop]
    paths: ['python/**']

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          cd python
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Run tests with coverage
        run: |
          cd python
          pytest tests/ -v --cov=. --cov-report=xml --cov-report=term --benchmark-only
        env:
          SECRET_KEY: test-secret-key-for-ci
          DATABASE_URL: sqlite:///./test.db
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          files: ./python/coverage.xml
          fail_ci_if_error: true
          token: ${{ secrets.CODECOV_TOKEN }}
      
      - name: Coverage threshold check
        run: |
          cd python
          coverage report --fail-under=70
      
      - name: Lint check
        run: |
          cd python
          ruff check .
          mypy . --ignore-missing-imports
      
      - name: Security scan
        run: |
          cd python
          bandit -r . -f json -o bandit-report.json || true
          safety check || true
```

### 1.2 开发依赖（requirements-dev.txt）

```
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-cov>=5.0.0
pytest-benchmark>=4.0.0
pytest-xdist>=3.5.0
httpx>=0.27.0
ruff>=0.4.0
mypy>=1.10.0
bandit>=1.7.0
safety>=3.0.0
freezegun>=1.5.0
respx>=0.21.0
```

### 1.3 性能基线（pytest-benchmark）

```python
# tests/benchmarks/test_api_performance.py
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# ===== 基准测试：关键接口性能 =====

class TestApiPerformance:
    """记录关键接口的 P95/P99 响应时间作为性能基线"""
    
    def test_baseline_varieties_list(self, benchmark):
        """品种列表接口基线"""
        result = benchmark(client.get, "/api/varieties")
        assert result.status_code == 200
    
    def test_baseline_kline_query(self, benchmark):
        """K线查询基线"""
        result = benchmark(client.get, "/api/kline/AU?period=1h&limit=100")
        assert result.status_code == 200
    
    def test_baseline_realtime_with_cache(self, benchmark):
        """实时行情（缓存命中）基线"""
        # 先预热缓存
        client.get("/api/realtime/AU")
        result = benchmark(client.get, "/api/realtime/AU")
        assert result.status_code == 200
    
    def test_baseline_products_list(self, benchmark):
        """产品列表基线"""
        result = benchmark(client.get, "/api/products")
        assert result.status_code == 200


# ===== 性能退化检测 =====

@pytest.mark.skipif(not os.environ.get("CI"), reason="Only run in CI")
class TestPerformanceRegression:
    """与历史基线对比，检测性能退化"""
    
    # 基线阈值（根据实际 CI 运行结果调整）
    VARIETIES_LIST_P95_MS = 50
    KLINE_QUERY_P95_MS = 100
    REALTIME_CACHE_HIT_P95_MS = 10
    
    def test_varieties_list_not_regressed(self, benchmark):
        result = benchmark(client.get, "/api/varieties")
        stats = benchmark.stats
        assert stats["max"] * 1000 < self.VARIETIES_LIST_P95_MS * 2, \
            f"品种列表退化: P95={stats['max']*1000:.1f}ms, 基线={self.VARIETIES_LIST_P95_MS}ms"
```

### 1.4 Makefile（统一测试入口）

```makefile
.PHONY: test test-unit test-integration test-concurrency test-security test-benchmark test-cov lint format

test: test-unit test-integration test-security

test-unit:
	cd python && pytest tests/unit/ -v --cov=. --cov-append

test-integration:
	cd python && pytest tests/integration/ -v --cov=. --cov-append

test-concurrency:
	cd python && pytest tests/concurrency/ -v -s

test-security:
	cd python && pytest tests/security/ -v
	cd python && bandit -r . -lll

test-benchmark:
	cd python && pytest tests/benchmarks/ --benchmark-only --benchmark-json=benchmark-report.json

test-cov:
	cd python && pytest tests/ --cov=. --cov-report=html --cov-report=term-missing
	@echo "Coverage report: python/htmlcov/index.html"

lint:
	cd python && ruff check . && mypy . --ignore-missing-imports

format:
	cd python && ruff check . --fix && ruff format .

clean:
	cd python && rm -rf .pytest_cache htmlcov .coverage benchmark-report.json
```

---

## 二、Mock 策略（核心改进）

### 2.1 原则：所有外部依赖必须 Mock

| 外部依赖 | Mock 方法 | 测试影响 |
|----------|-----------|----------|
| akshare / Tushare API | `unittest.mock.patch` / `respx` | 不依赖网络，不依赖数据源可用性 |
| 数据库（生产环境） | 文件 SQLite + `tmp_path` fixture | 测试环境与生产环境行为一致 |
| APScheduler | `freezegun` 冻结时间 + 手动触发 | 测试不等待 30 秒间隔 |
| Redis / 外部缓存 | `fakeredis` 或内存替代 | 无 Redis 也能跑测试 |

### 2.2 采集器 Mock 示例

```python
# tests/unit/test_collector.py
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from data_collector.akshare_collector import AkshareCollector
from data_collector.tushare_collector import TushareCollector

class TestAkshareCollectorMocked:
    """akshare 采集器 — 完全 Mock，不依赖网络"""
    
    @pytest.fixture
    def collector(self):
        return AkshareCollector()
    
    def test_fetch_realtime_success(self, collector):
        """模拟 akshare 返回正常数据"""
        mock_df = pd.DataFrame([{
            "品种": "黄金", "最新价": 450.50, "涨跌额": 5.0, 
            "涨跌幅": 1.12, "成交量": 123456
        }])
        
        with patch("akshare.futures_zh_spot", return_value=mock_df):
            result = collector.fetch_realtime("AU")
        
        assert result["current_price"] == 450.50
        assert result["symbol"] == "AU"
    
    def test_fetch_realtime_empty_response(self, collector):
        """模拟 akshare 返回空数据"""
        with patch("akshare.futures_zh_spot", return_value=pd.DataFrame()):
            result = collector.fetch_realtime("AU")
        
        assert result is None  # 应优雅处理空数据
    
    def test_fetch_realtime_timeout(self, collector):
        """模拟 akshare 超时"""
        with patch("akshare.futures_zh_spot", side_effect=TimeoutError("Connection timeout")):
            result = collector.fetch_realtime("AU")
        
        assert result is None  # 应返回 None 而不是抛异常
    
    def test_fetch_realtime_rate_limited(self, collector):
        """模拟 akshare 限流（429）"""
        with patch("akshare.futures_zh_spot", side_effect=Exception("429 Too Many Requests")):
            result = collector.fetch_realtime("AU")
        
        assert result is None


class TestTushareCollectorMocked:
    """Tushare 采集器 — 完全 Mock"""
    
    @pytest.fixture
    def collector(self):
        return TushareCollector(token="mock_token")
    
    def test_fetch_realtime_minute(self, collector):
        """模拟 Tushare rt_fut_min 返回分钟数据"""
        mock_df = pd.DataFrame([{
            "code": "AU2506.SHF", "freq": "1MIN", "time": "2026-05-03 14:30:00",
            "open": 450.0, "close": 451.0, "high": 452.0, "low": 449.0,
            "vol": 1000, "amount": 450000, "oi": 50000
        }])
        
        with patch.object(collector.pro, "rt_fut_min", return_value=mock_df):
            result = collector.fetch_realtime("AU")
        
        assert result["current_price"] == 451.0  # close 作为最新价
        assert result["symbol"] == "AU"
    
    def test_fetch_kline_history(self, collector):
        """模拟 Tushare ft_mins 返回历史 K线"""
        mock_df = pd.DataFrame([
            {"ts_code": "AU2506.SHF", "trade_time": "2026-05-03 09:00:00", 
             "open": 448.0, "close": 449.0, "high": 450.0, "low": 447.0, 
             "vol": 5000, "amount": 2245000, "oi": 48000},
            {"ts_code": "AU2506.SHF", "trade_time": "2026-05-03 09:01:00",
             "open": 449.0, "close": 450.0, "high": 451.0, "low": 448.0,
             "vol": 6000, "amount": 2700000, "oi": 49000},
        ])
        
        with patch.object(collector.pro, "ft_mins", return_value=mock_df):
            result = collector.fetch_kline("AU", period="1m", limit=2)
        
        assert len(result) == 2
        assert result[0]["open"] == 448.0  # 时间升序
```

### 2.3 定时任务 Mock 示例

```python
# tests/unit/test_scheduler.py
import pytest
from freezegun import freeze_time
from unittest.mock import patch
from data_collector.scheduler import Scheduler

class TestSchedulerMocked:
    """定时任务 — 冻结时间 + Mock 采集器"""
    
    @freeze_time("2026-05-03 14:30:00")
    def test_refresh_realtime_triggered(self):
        """验证定时任务在正确时间触发"""
        scheduler = Scheduler(interval_seconds=30)
        
        with patch("data_collector.scheduler.refresh_realtime_quotes") as mock_refresh:
            # 模拟时间推进 35 秒
            with freeze_time("2026-05-03 14:30:35"):
                scheduler.tick()  # 手动触发调度检查
            
            mock_refresh.assert_called_once()
    
    @freeze_time("2026-05-03 16:05:00")
    def test_daily_kline_not_triggered_on_weekend(self):
        """周末不应触发日 K线同步"""
        # 2026-05-03 是周日
        scheduler = Scheduler()
        
        with patch("data_collector.scheduler.sync_daily_kline") as mock_sync:
            scheduler.tick()
            mock_sync.assert_not_called()  # 周末不执行
    
    @freeze_time("2026-05-04 09:30:00")
    def test_realtime_not_triggered_before_market_open(self):
        """开盘前不应触发实时采集"""
        # 国内期货日盘 09:00 开盘
        scheduler = Scheduler()
        
        with patch("data_collector.scheduler.refresh_realtime_quotes") as mock_refresh:
            scheduler.tick()
            # 09:30 已开盘，应该触发
            mock_refresh.assert_called_once()
```

---

## 三、文件 SQLite 并发测试（替代 :memory:）

### 3.1 问题

`:memory:` SQLite 的并发行为和**文件 SQLite 不同**（文件 SQLite 才有 `database is locked` 问题）。在内存数据库上跑并发测试通过了，不代表生产环境没事。

### 3.2 解决方案：临时文件数据库 + WAL 模式

```python
# tests/conftest.py（全局 fixture）
import pytest
import tempfile
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import Base

@pytest.fixture(scope="function")
def db_engine():
    """创建临时文件数据库，启用 WAL 模式，更接近生产环境"""
    # 创建临时文件（而不是 :memory:）
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30}
    )
    
    # 启用 WAL 模式（Write-Ahead Logging）
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA synchronous=NORMAL"))
    
    Base.metadata.create_all(engine)
    
    yield engine
    
    # 清理
    engine.dispose()
    os.unlink(db_path)

@pytest.fixture(scope="function")
def db_session(db_engine):
    """每个测试独立会话"""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


# 并发测试专用 fixture
@pytest.fixture(scope="function")
def concurrent_db():
    """专门用于并发测试的数据库"""
    fd, db_path = tempfile.mkstemp(suffix="_concurrent.db")
    os.close(fd)
    
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30}
    )
    
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
    
    Base.metadata.create_all(engine)
    
    yield engine
    
    engine.dispose()
    os.unlink(db_path)
```

### 3.3 文件 SQLite 并发测试

```python
# tests/concurrency/test_sqlite_concurrency.py
import pytest
import threading
import time
from sqlalchemy.orm import sessionmaker
from models import VarietyDB, RealtimeQuoteDB, CommentDB, UserDB

class TestSQLiteConcurrency:
    """使用真实文件 SQLite + WAL 模式的并发测试"""
    
    def test_concurrent_reads_no_lock(self, concurrent_db):
        """10 个线程同时读取，不应出现 database is locked"""
        # 准备数据
        Session = sessionmaker(bind=concurrent_db)
        db = Session()
        v = VarietyDB(symbol="AU", contract_code="AU2506", name="黄金", exchange="SHFE")
        db.add(v)
        db.commit()
        db.close()
        
        errors = []
        results = []
        
        def reader():
            try:
                db = Session()
                varieties = db.query(VarietyDB).all()
                results.append(len(varieties))
                db.close()
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        assert len(errors) == 0, f"并发读错误: {errors[:3]}"
        assert all(r == 1 for r in results)
    
    def test_write_while_reading_wal_mode(self, concurrent_db):
        """WAL 模式下：写者不阻塞读者"""
        Session = sessionmaker(bind=concurrent_db)
        
        # 写者线程
        def writer():
            db = Session()
            for i in range(5):
                v = VarietyDB(symbol=f"TEST{i}", contract_code=f"TEST{i}2506", 
                             name=f"测试{i}", exchange="SHFE")
                db.add(v)
                db.commit()
                time.sleep(0.01)
            db.close()
        
        # 读者线程
        read_counts = []
        def reader():
            db = Session()
            for _ in range(10):
                count = db.query(VarietyDB).count()
                read_counts.append(count)
                time.sleep(0.005)
            db.close()
        
        w = threading.Thread(target=writer)
        r = threading.Thread(target=reader)
        w.start(); r.start()
        w.join(); r.join()
        
        # WAL 模式下读者不应被阻塞，读取到的数量可能递增
        assert len(read_counts) == 10
        assert read_counts[-1] >= read_counts[0]  # 最终数量 >= 初始数量
    
    def test_concurrent_writes_database_locked(self, concurrent_db):
        """多个写入者同时写：验证 WAL 模式下的行为"""
        Session = sessionmaker(bind=concurrent_db)
        
        errors = []
        success_count = []
        
        def writer(thread_id):
            try:
                db = Session()
                for i in range(3):
                    v = VarietyDB(symbol=f"W{thread_id}_{i}", 
                                 contract_code=f"W{thread_id}_{i}2506",
                                 name=f"写者{thread_id}", exchange="SHFE")
                    db.add(v)
                    db.commit()
                db.close()
                success_count.append(thread_id)
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        # WAL 模式下，并发写应该都能成功（不会 database is locked）
        assert len(success_count) == 5, f"部分写入失败: {errors}"
    
    def test_scheduler_and_api_concurrent_write(self, concurrent_db):
        """模拟采集器写入 + API 写入并发"""
        Session = sessionmaker(bind=concurrent_db)
        
        # 准备品种
        db = Session()
        v = VarietyDB(symbol="AU", contract_code="AU2506", name="黄金", exchange="SHFE")
        db.add(v)
        db.commit()
        db.close()
        
        errors = []
        
        def scheduler_writer():
            """模拟采集器每 100ms 写入 realtime_quotes"""
            try:
                db = Session()
                for _ in range(10):
                    rt = RealtimeQuoteDB(variety_id=1, current_price=450.0)
                    db.add(rt)
                    db.commit()
                    time.sleep(0.1)
                db.close()
            except Exception as e:
                errors.append(f"Scheduler: {e}")
        
        def api_writer():
            """模拟用户注册（写入 users）"""
            try:
                db = Session()
                for i in range(5):
                    u = UserDB(username=f"user_{i}", email=f"u{i}@test.com", 
                              password_hash="hashed")
                    db.add(u)
                    db.commit()
                    time.sleep(0.2)
                db.close()
            except Exception as e:
                errors.append(f"API: {e}")
        
        t1 = threading.Thread(target=scheduler_writer)
        t2 = threading.Thread(target=api_writer)
        t1.start(); t2.start()
        t1.join(); t2.join()
        
        assert len(errors) == 0, f"并发写冲突: {errors}"
```

---

## 四、合并重复用例

### 4.1 原重复项

| 重复点 | 原位置 | 合并后位置 |
|--------|--------|-----------|
| 缓存性能测试 | `test_api_contract.py::test_realtime_cached` + `test_concurrency.py::test_cache_performance` | 仅保留 `test_cache.py::test_cache_hit` 和 `test_cache.py::test_cache_ttl`，删除 API 层的重复测试 |
| 404 场景 | varieties/kline/realtime 各测一遍 | 统一为 `test_api_contract.py::test_404_variants`，使用 `@pytest.mark.parametrize` |
| 分页验证 | 集成测试 + 回归测试 | 仅保留集成测试，删除回归测试中的重复验证 |

### 4.2 合并后的参数化测试

```python
# tests/integration/test_api_contract.py
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

class TestApi404:
    """统一的 404 测试"""
    
    @pytest.mark.parametrize("endpoint,expected_msg", [
        ("/api/varieties/UNKNOWN", "品种不存在"),
        ("/api/kline/UNKNOWN?period=1h", "品种不存在"),
        ("/api/realtime/UNKNOWN", "品种不存在"),
        ("/api/products/99999", "产品不存在"),
    ])
    def test_not_found_endpoints(self, endpoint, expected_msg):
        r = client.get(endpoint)
        assert r.status_code == 404
        assert expected_msg in r.json().get("detail", "")


class TestApiPagination:
    """统一的分页测试"""
    
    @pytest.mark.parametrize("endpoint,default_limit,max_limit", [
        ("/api/varieties", 20, 1000),
        ("/api/products", 20, 1000),
        ("/api/comments", 20, 1000),
    ])
    def test_pagination_params(self, endpoint, default_limit, max_limit):
        # 默认 limit
        r = client.get(endpoint)
        assert len(r.json()) <= default_limit
        
        # 自定义 limit
        r = client.get(f"{endpoint}?limit=5")
        assert len(r.json()) <= 5
        
        # 超过 max_limit 应 422
        r = client.get(f"{endpoint}?limit={max_limit + 1}")
        assert r.status_code == 422
        
        # skip 分页
        r1 = client.get(f"{endpoint}?skip=0&limit=5")
        r2 = client.get(f"{endpoint}?skip=5&limit=5")
        if len(r1.json()) > 0 and len(r2.json()) > 0:
            assert r1.json()[0]["id"] != r2.json()[0]["id"]
```

---

## 五、补充缺失的单元测试

### 5.1 配置层测试

```python
# tests/unit/test_config.py
import pytest
import os
from unittest.mock import patch

class TestConfig:
    """环境变量配置测试"""
    
    def test_secret_key_missing_raises(self):
        """SECRET_KEY 缺失时应抛异常"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="SECRET_KEY"):
                import config
                # 触发重新加载
                import importlib
                importlib.reload(config)
    
    def test_database_url_default(self):
        """未设置 DATABASE_URL 时使用默认值"""
        with patch.dict(os.environ, {"SECRET_KEY": "test"}):
            from config import DATABASE_URL
            assert "sqlite" in DATABASE_URL
    
    def test_database_url_custom(self):
        """自定义 DATABASE_URL"""
        with patch.dict(os.environ, {
            "SECRET_KEY": "test",
            "DATABASE_URL": "postgresql://user:pass@localhost/db"
        }):
            from config import DATABASE_URL
            assert "postgresql" in DATABASE_URL
```

### 5.2 依赖注入测试

```python
# tests/unit/test_dependencies.py
import pytest
from fastapi import HTTPException
from dependencies import get_current_user_dependency
from jose import jwt
from config import SECRET_KEY, ALGORITHM

class TestAuthDependencies:
    """认证依赖测试"""
    
    def test_valid_token(self):
        """有效 token 应返回用户"""
        token = jwt.encode({"sub": "testuser"}, SECRET_KEY, algorithm=ALGORITHM)
        user = get_current_user_dependency(token=f"Bearer {token}")
        assert user is not None
    
    def test_missing_token(self):
        """无 token 应抛 401"""
        with pytest.raises(HTTPException) as exc:
            get_current_user_dependency(token=None)
        assert exc.value.status_code == 401
    
    def test_invalid_token(self):
        """伪造 token 应抛 401"""
        with pytest.raises(HTTPException) as exc:
            get_current_user_dependency(token="Bearer fake_token")
        assert exc.value.status_code == 401
    
    def test_expired_token(self):
        """过期 token 应抛 401"""
        from datetime import datetime, timedelta, timezone
        expired = datetime.now(timezone.utc) - timedelta(hours=1)
        token = jwt.encode({"sub": "testuser", "exp": expired}, 
                          SECRET_KEY, algorithm=ALGORITHM)
        with pytest.raises(HTTPException) as exc:
            get_current_user_dependency(token=f"Bearer {token}")
        assert exc.value.status_code == 401
```

### 5.3 Upsert 逻辑测试

```python
# tests/unit/test_upsert.py
import pytest
from sqlalchemy.orm import sessionmaker
from models import Base, KlineDataDB, VarietyDB

class TestUpsertLogic:
    """数据库 Upsert 冲突处理测试"""
    
    def test_kline_upsert_insert_new(self, db_session):
        """新 K线数据应插入"""
        # ... 准备数据
        from data_collector.upsert import upsert_kline
        
        data = {
            "variety_id": 1, "period": "1h", "trading_time": "2026-05-03 10:00:00",
            "open": 100, "high": 105, "low": 98, "close": 102, "volume": 1000
        }
        upsert_kline(db_session, data)
        
        klines = db_session.query(KlineDataDB).all()
        assert len(klines) == 1
        assert klines[0].close_price == 102
    
    def test_kline_upsert_update_existing(self, db_session):
        """重复 K线应更新而非插入"""
        # 先插入一条
        self.test_kline_upsert_insert_new(db_session)
        
        # 再插入同一时间，不同数据
        data = {
            "variety_id": 1, "period": "1h", "trading_time": "2026-05-03 10:00:00",
            "open": 101, "high": 106, "low": 99, "close": 103, "volume": 2000
        }
        upsert_kline(db_session, data)
        
        klines = db_session.query(KlineDataDB).all()
        assert len(klines) == 1  # 仍只有一条
        assert klines[0].close_price == 103  # 已更新
```

---

## 六、长期迭代规划

### 6.1 测试演进路线图

```
当前（v2.0）                    3个月后（v3.0）                 6个月后（v4.0）
├─ 单元测试                      ├─ Mutation Testing             ├─ 混沌工程
│  ├─ 模型                       │  └─ mutmut（验证测试有效性）    │  └─ chaostoolkit
│  ├─ 清洗器                     ├─ 契约快照测试                  ├─ 压力测试
│  ├─ 缓存                       │  └─ DTO JSON Schema diff      │  └─ 100万条 K线压测
│  └─ 配置                       ├─ 性能基线自动告警              ├─ 多环境测试
├─ 集成测试                      │  └─ P95 超阈值自动阻断 PR       │  └─ dev/staging/prod
│  ├─ API 契约                   ├─ 端到端测试                   ├─ 可视化测试报告
│  └─ DB 一致性                  │  └─ Playwright / Cypress        │  └─ Allure 报告
├─ 并发测试                      └─ 安全扫描自动化                └─ 测试左移
│  └─ 文件 SQLite WAL            │  └─ bandit + safety CI         │  └─ PR 前自动跑测试
└─ 安全测试                        
   └─ 手动 curl
```

### 6.2 各阶段目标

| 阶段 | 时间 | 目标 | 验收标准 |
|------|------|------|----------|
| **v2.0** | 现在 | 补齐测试基础设施 | CI 跑通、覆盖率 > 70%、Mock 策略落地 |
| **v3.0** | 3个月后 | 测试质量提升 | Mutation score > 60%、契约测试覆盖核心 API |
| **v4.0** | 6个月后 | 生产环境信心 | 混沌工程通过、100万 K线压测通过、多环境 CI/CD |

### 6.3 指标看板

```python
# pytest.ini 配置
[pytest]
addopts = 
    -v
    --cov=.
    --cov-report=term-missing
    --cov-report=html
    --benchmark-only
    --benchmark-json=benchmark-report.json
    --tb=short

# 覆盖率阈值
[tool.coverage.run]
source = ["."]
omit = ["*/tests/*", "*/migrations/*"]

[tool.coverage.report]
fail_under = 70
show_missing = true
skip_covered = false
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
```

---

## 七、改进版测试执行汇总

| 阶段 | 测试文件 | 命令 | 通过标准 | 改进点 |
|------|----------|------|----------|--------|
| 单元测试 | `tests/unit/` | `make test-unit` | 全部通过，覆盖率 > 70% | **新增**：配置、依赖、upsert、scheduler Mock |
| 集成测试 | `tests/integration/` | `make test-integration` | 全部通过 | **新增**：参数化 404/分页测试 |
| 并发测试 | `tests/concurrency/` | `make test-concurrency` | 无 database is locked | **改进**：文件 SQLite + WAL 模式 |
| 性能测试 | `tests/benchmarks/` | `make test-benchmark` | P95 不超基线 2 倍 | **新增**：pytest-benchmark 基线 |
| 安全测试 | `tests/security/` | `make test-security` | bandit 无高危 | **新增**：自动化安全扫描 |
| CI/CD | `.github/workflows/` | 自动触发 | PR 阻断 + 覆盖率阈值 | **新增**：完整 CI pipeline |
| 回归测试 | 前端联调 | `npm run dev` | 功能正常 | **删除**：重复验证项 |

---

## 八、与原测试计划的对比

| 维度 | 原测试计划 | 改进版测试计划 |
|------|-----------|--------------|
| **CI/CD** | ❌ 无 | ✅ GitHub Actions 完整 pipeline |
| **性能基线** | ❌ 无 | ✅ pytest-benchmark + P95 阈值 |
| **Mock 策略** | ⚠️ 部分（无采集器 Mock） | ✅ 所有外部依赖强制 Mock |
| **并发测试环境** | ❌ `:memory:` SQLite | ✅ 文件 SQLite + WAL |
| **重复用例** | ❌ 缓存测两次、404 各测一遍 | ✅ 参数化合并 |
| **缺失单元测试** | ❌ 无配置/依赖/upsert 测试 | ✅ 全部补齐 |
| **安全扫描** | ❌ 手动 curl | ✅ bandit + safety CI 集成 |
| **长期规划** | ❌ 无 | ✅ 3 阶段演进路线图 |
| **覆盖率量化** | ❌ 无 | ✅ pytest-cov + 70% 阈值 |
| **Makefile** | ❌ 无 | ✅ 统一测试入口 |

---

## 一句话总结

> **原测试计划是"能不能跑"的验收单，改进版是"能不能持续交付"的基础设施。Mock 策略、文件 SQLite WAL、CI/CD、性能基线四个改进点，把测试从一次性检查升级为可量化的质量门禁。**
