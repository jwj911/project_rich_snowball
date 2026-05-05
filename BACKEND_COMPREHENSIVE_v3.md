# 期货社区后端重构 — 综合迭代与质量评估文档

> 版本：v3.0（终极综合版）
> 日期：2026-05-03
> 综合来源：
> - BACKEND_ITERATION_PLAN.md（原始迭代计划）
> - BACKEND_TEST_PLAN.md + BACKEND_TEST_PLAN_REVISED.md（测试计划原始+修订版）
> - BACKEND_REVIEW_REPORT.md + BACKEND_REVIEW_REPORT_REVISED.md（评审报告原始+修订版）
> - BACKEND_TEST_PLAN_V2.md（改进版测试计划）
> - BACKEND_REVIEW_SUPPLEMENT.md（多视角补充评审）
> - REVISED_DOCS_OPTIMIZATION.md（修订版优化建议）

---

## 一、项目背景与目标

### 1.1 原始状态（As-Is）

```
python/
├── main.py              # 316 行，含所有模型/路由/业务逻辑
├── init_data.py         # 引用不存在的模型，无法运行
├── requirements.txt     # 依赖列表
└── futures_community.db # SQLite 数据库（3 张表）
```

| 维度 | 现状 |
|------|------|
| 数据模型 | 仅 UserDB/ProductDB/CommentDB，init_data.py 引用不存在的 FuturesVarietyDB |
| K 线数据 | 无表、无 API、前端展示固定 mock 数据 |
| 实时行情 | 无表、无 API、ProductDB 价格是静态死数据 |
| 自选股/观点 | 无表、无 API |
| 数据采集 | 无采集器，数据手动录入 |

### 1.2 目标状态（To-Be）

```
python/
├── main.py                      # 仅启动/配置
├── models.py                    # 8 张表 SQLAlchemy 模型
├── schemas.py                   # Pydantic 校验层
├── dependencies.py              # 认证依赖
├── config.py                    # 环境配置
├── routers/
│   ├── auth.py                  # 注册/登录/Me
│   ├── varieties.py             # 品种列表/详情/搜索
│   ├── kline.py                 # K 线查询
│   ├── realtime.py              # 实时行情
│   ├── comments.py              # 评论 CRUD
│   └── products.py              # 旧接口兼容层
├── services/
│   └── cache.py                 # 内存缓存
├── data_collector/
│   ├── mock_collector.py        # 开发期 Mock 数据源
│   ├── tushare_collector.py     # Tushare Pro 主采集器
│   ├── akshare_collector.py     # akshare 备用采集器
│   ├── cleaner.py               # 数据清洗与标准化
│   ├── scheduler.py             # APScheduler 定时任务
│   └── init_varieties.py        # 品种元数据初始化
├── alembic/                     # 数据库迁移
└── tests/                       # 全量测试
```

| 维度 | 目标 |
|------|------|
| 数据模型 | 8 张表：users/varieties/realtime_quotes/kline_data/comments/watchlists/opinions/products(兼容视图) |
| K 线数据 | 支持 1m/5m/15m/30m/1h/1d/1w 查询，按品种+周期+时间索引 |
| 实时行情 | 每 30s 采集，内存缓存 5s，Upsert 到 realtime_quotes |
| 数据采集 | Tushare Pro 主 + akshare 备 + Mock 兜底 |

---

## 二、架构设计评估（多视角综合）

### 2.1 后端架构师视角

**评分：7/10**

| 问题 | 位置 | 风险 | 修复建议 |
|------|------|------|----------|
| 缺少 Service 层 | routers/*.py | 🟢 低 | 当前 8 表 5 路由规模，Router 偏薄，暂不需要大规模分层；等业务复杂后抽取 |
| 采集器与入库紧耦合 | scheduler.py | 🟡 中 | 抽象 Pipeline：extract→transform→load |
| 缺少防腐层 | akshare_collector.py | 🟡 中 | 增加 AkshareAdapter，字段映射集中化 |
| 连接池配置误导 | models.py | 🟢 低 | SQLite 不支持连接池，注释说明或条件配置 |
| 无 Repository/DAO | 全局 | 🟢 低 | 同类查询重复 3 次以上时再引入 |

### 2.2 安全工程师视角

**评分：7.5/10**

| 问题 | 位置 | 风险 | 修复建议 |
|------|------|------|----------|
| JWT 永不过期 | dependencies.py | 🟡 中 | 增加 `exp` 声明，token 24h 过期 |
| CORS 配置风险 | 全局 | 🔴 高 | 生产环境禁止 `allow_origins=["*"]`，只允许前端域名 |
| 注册无 rate limit | auth.py | 🟡 中 | 引入 `slowapi`，`@limiter.limit("5/minute")` |
| 登录爆破 | auth.py | 🟡 中 | 按 username+IP 限制失败次数 |
| 评论接口手动解析 token | comments.py | 🟡 中 | 统一使用 `Depends(get_current_user_dependency)` |
| XSS 策略不清 | comments.py | 🟡 中 | 明确存储时转义还是展示时转义 |
| 密码错误日志脱敏 | 全局 | 🟡 中 | 日志中不记录明文密码或 token |

### 2.3 运维工程师视角

**评分：5/10**

| 问题 | 风险 | 修复建议 |
|------|------|----------|
| 无 Dockerfile | 🟡 中 | 编写多阶段构建 Dockerfile |
| 无 `/health` 端点 | 🟡 中 | 增加 `/health` 返回 db/缓存状态 |
| 无 Prometheus 指标 | 🟡 中 | 增加 `/metrics`，暴露 QPS/延迟/错误率 |
| 无 Sentry 错误追踪 | 🟡 中 | 集成 Sentry SDK |
| 无结构化日志 | 🟡 中 | 日志输出 JSON，接入 ELK/Loki |
| 无自动备份 | 🟡 中 | 编写备份脚本，每日备份 SQLite |
| 采集器存活监控 | 🟡 中 | 心跳检测，挂掉 5 分钟告警 |
| 生产 docs 暴露 | 全局 | 🟢 低 | 生产环境关闭 `/docs` 或加认证 |

### 2.4 前端工程师视角

**评分：6/10**

| 问题 | 风险 | 修复建议 |
|------|------|----------|
| CORS 未配置 | 🔴 高 | FastAPI CORSMiddleware，允许前端域名 |
| 字段命名不一致 | 🟡 中 | `/api/varieties` 和 `/api/products` 统一字段名 |
| 分页缺少 total/has_more | 🟡 中 | 返回 `{data: [], total: N, has_more: bool}` |
| 错误响应格式不统一 | 🟢 低 | 统一错误结构 `{code, message, detail}` |
| 30 秒轮询体验差 | 🟡 中 | 短期优化 HTTP 缓存，长期引入 SSE |
| 首次加载无 loading | 🟢 低 | K线加载时展示 skeleton/loading |

### 2.5 交叉风险矩阵（多视角共识）

| 问题 | 后端 | 安全 | 运维 | 前端 | **最终** |
|------|------|------|------|------|---------|
| SQLite 并发写入 | 🔴 | 🟡 | 🟡 | 🟢 | **🔴** |
| 缓存 ORM 对象 | 🔴 | 🟡 | 🟢 | 🟢 | **🔴** |
| CORS 未配置 | 未评 | 🔴 | 🟢 | 🔴 | **🔴** *(新增)* |
| Float 价格 | 🔴 | 🟢 | 🟢 | 🟢 | **🟡** *(降)* |
| 涨跌幅计算 | 🔴 | 🟢 | 🟢 | 🟡 | **🟡** |
| 测试隔离不足 | 🔴 | 🟢 | 🔴 | 🟢 | **🔴** *(新增)* |
| Service 层缺失 | 🟡 | 🟢 | 🟢 | 🟢 | **🟢** *(降)* |
| JWT 永不过期 | 未评 | 🟡 | 🟢 | 🟢 | **🟡** *(新增)* |
| 无 /health | 未评 | 🟢 | 🟡 | 🟢 | **🟡** *(新增)* |
| 无监控指标 | 未评 | 🟢 | 🟡 | 🟢 | **🟡** *(新增)* |

---

## 三、质量测试计划（终极版）

### 3.1 测试基础设施

#### 3.1.1 CI/CD 配置（`.github/workflows/test.yml`）

```yaml
name: Backend Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-asyncio httpx pytest-cov pytest-benchmark
    
    - name: Run tests
      run: |
        cd python
        pytest -m "not slow" --cov=. --cov-report=xml --cov-fail-under=60
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./python/coverage.xml
    
    - name: Type check
      run: |
        pip install mypy
        cd python
        mypy routers/ models/ services/ --ignore-missing-imports
    
    - name: Lint check
      run: |
        pip install ruff
        cd python
        ruff check . --select E,W,F,I
```

#### 3.1.2 测试分组

```ini
# pytest.ini
[pytest]
markers =
    unit: fast unit tests
    integration: API and database integration tests
    concurrency: thread/process contention tests
    security: security boundary tests
    business: futures-domain correctness tests
    slow: slow tests excluded from default CI
    perf: performance baseline tests
```

**执行策略**：
```bash
# 默认 CI（快速）
pytest -m "not slow" --cov=. --cov-report=xml --cov-fail-under=60

# 专项测试
pytest -m "concurrency" -v -s
pytest -m "slow" -v -s
pytest -m "perf" --benchmark-compare=baseline.json
```

#### 3.1.3 独立测试数据库

```python
# tests/conftest.py
import pytest
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

@pytest.fixture(scope="function")
def db_engine():
    """每个测试用例独立临时文件数据库（非 :memory:）"""
    fd, path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": 30}
    )
    Base.metadata.create_all(engine)
    yield engine
    import os
    os.close(fd)
    os.unlink(path)

@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def client(db_engine):
    """FastAPI TestClient with overridden DB"""
    from main import app, get_db
    from fastapi.testclient import TestClient
    
    def override_get_db():
        Session = sessionmaker(bind=db_engine)
        db = Session()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    del app.dependency_overrides[get_db]
```

### 3.2 P0 测试：必须先补齐

#### 3.2.1 测试隔离与可重复性

**验收标准**：
- 连续执行 3 次 `pytest` 结果一致
- 单独执行任意一个测试文件也能通过
- 打乱测试顺序后仍能通过

**禁止事项**：
- 依赖真实数据库 `futures_community.db`
- 依赖固定用户（`trader001`）
- 依赖固定产品 id（`product_id=1`）
- 依赖固定品种（`AU`）

```python
def test_register_repeatable(client):
    """重复运行不会因为用户已存在而失败"""
    import uuid
    username = f"test_{uuid.uuid4().hex[:8]}"
    
    r1 = client.post("/api/auth/register", json={
        "username": username, "email": f"{username}@test.com", "password": "password123"
    })
    assert r1.status_code == 200
    
    # 同一用户名再次注册应返回 400
    r2 = client.post("/api/auth/register", json={
        "username": username, "email": f"{username}2@test.com", "password": "password123"
    })
    assert r2.status_code == 400
```

#### 3.2.2 缓存层正确性测试

```python
def test_cache_should_not_store_orm_object():
    """缓存 ORM 对象会导致跨 session detached instance"""
    value = get_cached("x", lambda: {"current_price": 1.23})
    assert isinstance(value, dict)
    assert not hasattr(value, '__mapper__')  # 不是 SQLAlchemy 对象

def test_cache_hit_only_calls_fetch_once():
    call_count = 0
    def fetch():
        nonlocal call_count
        call_count += 1
        return "data"
    
    r1 = get_cached("test:hit", fetch, ttl=5)
    r2 = get_cached("test:hit", fetch, ttl=5)
    assert call_count == 1

def test_cache_ttl_expired():
    call_count = 0
    def fetch():
        nonlocal call_count
        call_count += 1
        return f"data_{call_count}"
    
    r1 = get_cached("test:ttl", fetch, ttl=1)
    time.sleep(1.1)
    r2 = get_cached("test:ttl", fetch, ttl=1)
    assert call_count == 2

def test_cache_concurrent_safety():
    """并发访问同一个 key 不应抛异常"""
    import threading
    errors = []
    
    def worker():
        try:
            get_cached("test:concurrent", lambda: "safe", ttl=5)
        except Exception as e:
            errors.append(str(e))
    
    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(errors) == 0
```

#### 3.2.3 SQLite 并发写入测试（文件数据库 + WAL）

```python
def test_wal_mode_enabled():
    """确认数据库使用 WAL 模式"""
    fd, path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        result = conn.execute(text("PRAGMA journal_mode")).fetchone()
        assert result[0] == "wal"
    import os
    os.close(fd)
    os.unlink(path)

def test_concurrent_write_mixed_load():
    """混合读写：scheduler + 注册用户 + 发表评论 + API 读取"""
    fd, path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": 30}
    )
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
    
    errors = []
    
    def scheduler_worker():
        """模拟 scheduler 写入"""
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            for i in range(30):
                v = VarietyDB(symbol=f"SCH{i}", contract_code=f"SCH{i}2506", name=f"调度{i}", exchange="SHFE")
                db.add(v)
                db.commit()
        except Exception as e:
            errors.append(f"scheduler: {e}")
        finally:
            db.close()
    
    def api_writer():
        """模拟 API 注册用户"""
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            for i in range(30):
                u = UserDB(username=f"user{i}", email=f"u{i}@t.com", password_hash="hash")
                db.add(u)
                db.commit()
        except Exception as e:
            errors.append(f"api_writer: {e}")
        finally:
            db.close()
    
    def api_reader():
        """模拟 API 读取"""
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            for _ in range(60):
                db.query(VarietyDB).all()
        except Exception as e:
            errors.append(f"api_reader: {e}")
        finally:
            db.close()
    
    threads = [
        threading.Thread(target=scheduler_worker),
        threading.Thread(target=api_writer),
        threading.Thread(target=api_reader),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(errors) == 0, f"并发错误: {errors[:5]}"
    
    import os
    os.close(fd)
    os.unlink(path)
```

#### 3.2.4 API 鉴权与权限边界

```python
def test_auth_no_token_returns_401(client):
    r = client.post("/api/comments", json={"product_id": 1, "content": "test"})
    assert r.status_code == 401

def test_auth_fake_token_returns_401(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer fake_token"})
    assert r.status_code == 401

def test_auth_expired_token_returns_401(client):
    from jose import jwt
    from config import settings
    from datetime import datetime, timedelta
    
    expired_token = jwt.encode(
        {"sub": "nonexistent", "exp": datetime.utcnow() - timedelta(hours=1)},
        settings.SECRET_KEY,
        algorithm="HS256"
    )
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert r.status_code == 401

def test_comment_empty_content_returns_422(client, auth_headers):
    r = client.post("/api/comments", json={"product_id": 1, "content": ""}, headers=auth_headers)
    assert r.status_code == 422

def test_comment_whitespace_content_returns_422(client, auth_headers):
    r = client.post("/api/comments", json={"product_id": 1, "content": "   "}, headers=auth_headers)
    assert r.status_code == 422

def test_comment_too_long_returns_422(client, auth_headers):
    r = client.post("/api/comments", json={"product_id": 1, "content": "x" * 2001}, headers=auth_headers)
    assert r.status_code == 422

def test_comment_nonexistent_product_returns_404(client, auth_headers):
    r = client.post("/api/comments", json={"product_id": 99999, "content": "test"}, headers=auth_headers)
    assert r.status_code == 404

def test_login_wrong_password_no_user_enum(client):
    """错误密码返回 401，不泄露用户是否存在"""
    r = client.post("/api/auth/login", data={"username": "nonexistent_user_12345", "password": "wrong"})
    assert r.status_code == 401
    # 错误信息不应包含 "user not found" 或 "password incorrect" 的区分
```

#### 3.2.5 数据库迁移与 Schema 契约

```python
def test_alembic_migrate_from_empty():
    """从空库迁移到 head 成功"""
    import subprocess
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd="python",
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, result.stderr

def test_unique_constraints_exist(db_engine):
    """关键唯一约束存在"""
    from sqlalchemy import inspect
    inspector = inspect(db_engine)
    
    varieties_constraints = inspector.get_unique_constraints("varieties")
    constraint_names = [c["name"] for c in varieties_constraints]
    assert any("symbol" in str(c).lower() for c in varieties_constraints)

def test_kline_index_exists(db_engine):
    """K线索引存在"""
    from sqlalchemy import inspect
    inspector = inspect(db_engine)
    indexes = inspector.get_indexes("kline_data")
    index_names = [i["name"] for i in indexes]
    assert any("variety" in n and "period" in n for n in index_names)
```

### 3.3 P1 测试：近期补齐

#### 3.3.1 数据清洗器测试

```python
def test_clean_realtime_negative_price():
    assert clean_realtime({"current_price": -100, "high": 455, "low": 448, "volume": 1000}, "AU") is None

def test_clean_realtime_high_less_than_low():
    assert clean_realtime({"current_price": 450, "high": 440, "low": 448, "volume": 1000}, "AU") is None

def test_clean_realtime_invalid_volume():
    assert clean_realtime({"current_price": 450, "high": 455, "low": 448, "volume": "abc"}, "AU") is None

def test_clean_kline_ohlc_integrity():
    """high 必须 >= open/close/low，low 必须 <= open/close/high"""
    raw = [{"symbol": "AU", "trading_time": datetime.now(), "open_price": 100, "high_price": 95, "low_price": 98, "close_price": 102, "volume": 1000}]
    result = clean_kline(raw, "AU")
    assert len(result) == 0  # high < low，丢弃
```

#### 3.3.2 API 契约测试（快照）

```python
# tests/contract/test_api_snapshots.py
def test_varieties_list_snapshot(snapshot, client):
    r = client.get("/api/varieties")
    assert r.status_code == 200
    snapshot.assert_match(r.json())

def test_kline_structure_snapshot(snapshot, client):
    r = client.get("/api/kline/AU?period=1h&limit=3")
    assert r.status_code == 200
    snapshot.assert_match(r.json())
```

**工具**：`pip install pytest-snapshot`

#### 3.3.3 性能基线测试

```python
# tests/perf/test_api_latency.py
class TestLatencyBaseline:
    def test_kline_query_p95(self, benchmark, client):
        result = benchmark(client.get, "/api/kline/AU?period=1h&limit=100")
        assert result.status_code == 200
        # 首次运行记录基线，后续对比
    
    def test_realtime_cached_latency(self, benchmark, client):
        client.get("/api/realtime/AU")  # 预热
        result = benchmark(client.get, "/api/realtime/AU")
        assert result.status_code == 200
        assert benchmark.stats["median"] < 0.01  # 10ms
```

**基线管理**：
```bash
# 首次生成基线
pytest tests/perf/ --benchmark-json=baseline.json
# 后续对比（退化超 15% 失败）
pytest tests/perf/ --benchmark-compare=baseline.json --benchmark-compare-fail=median:15%
```

### 3.4 P2 测试：中长期

#### 3.4.1 容量测试

```python
def test_kline_query_1m_records():
    """100 万条 K线数据查询性能"""
    # 灌入 100 万条测试数据
    # 验证查询延迟 < 200ms
    # 验证索引被使用（EXPLAIN QUERY PLAN）
    pass
```

#### 3.4.2 轮询压力测试（Locust）

```python
# tests/perf/locustfile.py
from locust import HttpUser, task, between

class ApiUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def get_varieties(self):
        self.client.get("/api/varieties")
    
    @task(2)
    def get_kline(self):
        self.client.get("/api/kline/AU?period=1h&limit=100")
    
    @task(1)
    def get_realtime(self):
        self.client.get("/api/realtime/AU")
```

**执行**：
```bash
locust -f tests/perf/locustfile.py --host=http://localhost:8000 -u 50 -r 5 --run-time 5m
```

#### 3.4.3 混沌测试

```python
def test_collector_failure_fallback(monkeypatch):
    """模拟 akshare 502 降级到 MockCollector"""
    monkeypatch.setattr("akshare.futures_zh_spot", lambda: (_ for _ in ()).throw(ConnectionError("502")))
    # 验证 scheduler 继续运行，使用 MockCollector 数据

def test_disk_full_graceful_failure(monkeypatch):
    """模拟磁盘满 graceful 失败"""
    # 验证不崩溃，返回 503 或跳过写入
```

### 3.5 测试金字塔比例

```
tests/
├── conftest.py              # 全局 fixtures
├── unit/                    # 70%+ 数量（快速、隔离、Mock）
│   ├── test_models.py
│   ├── test_cleaner.py
│   ├── test_cache.py
│   ├── test_config.py
│   ├── test_dependencies.py
│   ├── test_upsert.py
│   └── test_scheduler.py
├── integration/             # 20% 数量（API + DB）
│   ├── test_api_contract.py
│   ├── test_db_consistency.py
│   └── test_collector_pipeline.py
├── perf/                    # 5% 数量（基准 + 压测）
│   ├── test_api_latency.py
│   └── locustfile.py
├── contract/                # 3% 数量（快照）
│   └── test_api_snapshots.py
└── e2e/                     # 2% 数量（人工 smoke）
    └── test_frontend_smoke.md
```

### 3.6 Mock 策略

```python
# Tushare Mock
@pytest.fixture
def mock_tushare_pro():
    mock_pro = Mock()
    mock_pro.rt_fut_min.return_value = pd.DataFrame({
        "code": ["AU2506.SHF"], "freq": ["1MIN"],
        "time": ["2026-05-03 09:31:00"],
        "open": [450.00], "close": [451.00],
        "high": [452.00], "low": [449.00],
        "vol": [1000], "amount": [450500.0],
        "oi": [50000]
    })
    return mock_pro

def test_tushare_collector_fetch(mock_tushare_pro):
    with patch("tushare.pro_api", return_value=mock_tushare_pro):
        collector = TushareCollector(token="fake_token")
        result = collector.fetch_realtime(["AU"])
    assert result[0]["current_price"] == 451.00
```

---

## 四、修复路线图

### 4.1 P0 阶段（本周内）

| 优先级 | 问题 | 工作量 | 验收标准 |
|--------|------|--------|----------|
| 1 | **CORS 配置** | 5 分钟 | 前端可跨域调用 |
| 2 | **SQLite WAL + timeout=30** | 2 行代码 | 并发写入无 `database is locked` |
| 3 | **缓存加锁（RLock）** | 10 行代码 | 并发读缓存无异常 |
| 4 | **缓存不存 ORM 对象** | 30 分钟 | 缓存返回 dict/DTO |
| 5 | **JWT 过期时间** | 5 分钟 | token 24h 过期 |
| 6 | **测试隔离（独立 DB）** | 2 小时 | 测试不依赖真实库，3 次运行结果一致 |
| 7 | **scheduler 防重入** | 10 分钟 | `max_instances=1` |
| 8 | **评论接口统一鉴权** | 15 分钟 | 使用 `Depends(get_current_user_dependency)` |
| 9 | **注册/登录限流** | 30 分钟 | 6 次/分钟返回 429 |
| 10 | **Float→Decimal** | 2 小时 | 价格字段 `Numeric(15,4)` |
| 11 | **昨结算价 + 涨跌幅修正** | 1 小时 | `RealtimeQuoteDB.pre_settlement` |
| 12 | **清洗器 OHLC 校验** | 30 分钟 | high >= open/close/low |

### 4.2 P1 阶段（第 2-3 周）

| 问题 | 工作量 |
|------|--------|
| 增加 `contract_code` 到 K线 | 2 小时 |
| API 返回 `total`/`has_more` | 1 小时 |
| 字段命名统一 | 1 小时 |
| 错误响应格式统一 | 30 分钟 |
| `/health` 端点 | 10 分钟 |
| 结构化日志（JSON） | 2 小时 |
| 备份脚本 | 1 小时 |
| Dockerfile | 2 小时 |
| CI/CD 接入 | 2 小时 |

### 4.3 P2 阶段（第 4-6 周）

| 问题 | 工作量 |
|------|--------|
| Service 层抽取（行情/K线/评论） | 1 天 |
| 性能基线追踪 | 2 小时 |
| 100 万条 K线容量测试 | 4 小时 |
| 契约快照测试 | 1 小时 |
| Prometheus 指标 | 2 小时 |
| Sentry 集成 | 1 小时 |
| 采集器存活监控 | 2 小时 |

### 4.4 P3 阶段（第 7-8 周）

| 问题 | 工作量 |
|------|--------|
| PostgreSQL 迁移 | 2 天 |
| scheduler 独立 worker | 1 天 |
| Redis 缓存 | 4 小时 |
| 交易日历 | 4 小时 |
| 夜盘处理 | 4 小时 |

### 4.5 P4 阶段（第 9-12 周）

| 问题 | 工作量 |
|------|--------|
| SSE/WebSocket 实时推送 | 2 天 |
| 合约换月自动处理 | 2 天 |
| 主连 K线拼接 | 1 天 |
| 混沌测试 | 4 小时 |
| 审计日志 | 4 小时 |

---

## 五、评分与验收标准

### 5.1 多维度评分

| 维度 | 权重 | 当前 | 目标 |
|------|------|------|------|
| 架构设计 | 20% | 7/10 | 8/10 |
| 性能与并发 | 20% | 5/10 | 8/10 |
| 安全与可靠性 | 20% | 7.5/10 | 9/10 |
| 可维护性与测试 | 15% | 6/10 | 9/10 |
| 业务正确性 | 15% | 5/10 | 8/10 |
| 运维就绪度 | 10% | 5/10 | 8/10 |
| **总体** | **100%** | **58/100** | **83/100** |

### 5.2 验收标准

**P0 完成标准**：
- `pytest -m "not slow"` 全部通过
- 覆盖率 > 60%
- 无测试依赖开发数据库
- SQLite 并发写入 3 线程混合负载无错误
- CORS 配置完成，前端可调用

**上线标准**：
- 全部 P0 完成
- 并发写入测试通过
- 旧接口兼容测试通过
- 安全测试通过（注入/XSS/限流）
- 业务正确性测试通过（精度/涨跌幅/合约维度）

**生产级标准**：
- 全部 P1 完成
- PostgreSQL 迁移完成
- `/health` + Prometheus + Sentry 接入
- 100 万条 K线查询 < 200ms
- 50 并发 Locust 压测错误率 0%

---

## 六、一句话总结

> **当前系统适合作为 MVP，但生产上线前必须修复 SQLite 并发安全、缓存 ORM 对象、CORS 配置、价格精度四大致命问题。测试不是一次性清单，而是持续守护系统的基础设施——从独立测试数据库起步，逐步接入 CI/CD、性能基线、契约快照和混沌工程。**
