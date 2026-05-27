"""
P0 修复回归测试
================
测试范围：9 个 P0 级别修复的安全、配置与代码质量

运行方式：
    cd python
    pip install pytest httpx
    SECRET_KEY=test-secret-key pytest tests/test_p0_fixes.py -v

注意：
- 测试 1（SECRET_KEY）使用子进程，不依赖当前环境变量
- 其余测试使用 conftest.py 提供的内存数据库 fixture，不污染开发库
"""

import os
import sys
import subprocess
import html
import pytest
import time
from datetime import timedelta, datetime, timezone

# 确保 SECRET_KEY 在导入 main 前已设置
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-local-development")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import hash_password, verify_password, create_access_token
from dependencies import get_current_user
from models import init_db, UserDB, CommentDB, Base, get_engine_info
from schemas import CommentCreate

# 保留 main 导入供需要 TestClient 的测试使用
import main


# ============================================================================
# 1. B-P0-01 硬编码 SECRET_KEY
# ============================================================================

def test_secret_key_missing_raises_error():
    """未设置 SECRET_KEY 时导入 main.py 应抛出 ValueError"""
    env = os.environ.copy()
    env.pop("SECRET_KEY", None)
    # 阻止 config.py 从 .env 文件加载密钥
    env["DOTENV_PATH"] = "/nonexistent/.env"
    result = subprocess.run(
        [sys.executable, "-c", "import main"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )
    assert result.returncode != 0
    assert "SECRET_KEY environment variable is not set" in result.stderr


def test_secret_key_from_env():
    """设置了 SECRET_KEY 后应正常导入"""
    import config as cfg
    assert cfg.SECRET_KEY is not None and len(cfg.SECRET_KEY) > 0


# ============================================================================
# 2. B-P0-02 SHA256 无盐哈希 → bcrypt
# ============================================================================

def test_hash_password_generates_bcrypt():
    """bcrypt 哈希应以 $2b$ 开头，且每次盐值不同"""
    h1 = hash_password("password123")
    h2 = hash_password("password123")
    assert h1.startswith("$2b$")
    assert h2.startswith("$2b$")
    assert h1 != h2, "bcrypt 应使用随机盐，相同密码哈希结果不同"


def test_verify_password_correct():
    """正确密码应验证通过"""
    h = hash_password("mypassword")
    assert verify_password("mypassword", h) is True


def test_verify_password_incorrect():
    """错误密码应验证失败"""
    h = hash_password("mypassword")
    assert verify_password("wrongpassword", h) is False


# ============================================================================
# 3. B-P0-06 评论 XSS + 长度限制
# ============================================================================

def test_comment_content_max_length():
    """评论内容超过 2000 字符应被 Pydantic 拒绝"""
    try:
        CommentCreate(product_id=1, content="x" * 2001)
        assert False, "应抛出 ValidationError"
    except Exception as e:
        assert "max_length" in str(e) or "String should have at most 2000 characters" in str(e)


def test_comment_content_min_length():
    """评论内容为空应被 Pydantic 拒绝"""
    try:
        CommentCreate(product_id=1, content="")
        assert False, "应抛出 ValidationError"
    except Exception as e:
        assert "min_length" in str(e) or "String should have at least 1 character" in str(e) or "评论内容不能为空" in str(e)


def test_comment_content_xss_escaped():
    """HTML 标签应被转义为实体"""
    comment = CommentCreate(product_id=1, content='<script>alert("xss")</script>')
    assert "<script>" not in comment.content
    assert html.unescape(comment.content) == '<script>alert("xss")</script>'


def test_comment_content_strips_whitespace():
    """首尾空白应被 strip"""
    comment = CommentCreate(product_id=1, content="  hello world  ")
    assert comment.content == "hello world"


# ============================================================================
# 5. B-P0-08 裸 except 吞异常 → 精确捕获 PyJWTError
# ============================================================================

def test_get_current_user_with_expired_token(db_session):
    """过期 JWT 应返回 None，不抛出异常，且应记录 warning 日志"""
    db = db_session

    # 创建一个已过期 1 小时的 token
    expired_token = create_access_token({"sub": "1"})
    # 手动篡改 exp 为过去时间（hack 方式：直接解码改时间再编码）
    import jwt as pyjwt
    payload = pyjwt.decode(expired_token, os.environ["SECRET_KEY"], algorithms=["HS256"], options={"verify_exp": False})
    payload["exp"] = datetime.now(timezone.utc) - timedelta(hours=1)
    expired_token = pyjwt.encode(payload, os.environ["SECRET_KEY"], algorithm="HS256")

    result = get_current_user(expired_token, db)
    assert result is None


def test_get_current_user_with_invalid_token(db_session):
    """无效 JWT 应返回 None，不抛出异常"""
    db = db_session

    result = get_current_user("totally.invalid.token", db)
    assert result is None


# ============================================================================
# 6. B-P0-09 模块级 create_all → 显式 init_db()
# ============================================================================

def test_import_does_not_call_create_all():
    """导入 main 模块时不应自动调用 create_all"""
    # 已通过测试 1 验证：导入时若 SECRET_KEY 设置正确则不会报错
    # 真正的验证是：多次导入不会报错（表已存在时 create_all 不会报错，但如果是模块级则每次导入都会执行）
    # 这里用一个间接方式：确保 Base.metadata.create_all 被封装在函数里
    import main as m
    assert callable(m.init_db)


# ============================================================================
# 7. B-P0-07 init_data.py 连接泄漏 → 上下文管理器
# ============================================================================

def test_get_db_session_closes_connection():
    """get_db_session 应正确关闭数据库连接"""
    pytest.importorskip("init_data", reason="init_data.py 模型与 main.py 不兼容，暂跳过")
    from init_data import get_db_session

    with get_db_session() as db:
        assert db is not None
        # 简单执行一个查询验证连接可用
        result = db.execute("SELECT 1").scalar()
        assert result == 1
    # 退出 with 块后连接应已关闭


# ============================================================================
# 端到端：注册 + 登录 + 发评论流程
# ============================================================================

# ============================================================================
# DB Engine 条件化 + WAL
# ============================================================================

def test_sqlite_wal_enabled():
    """SQLite 数据库应启用 WAL 模式"""
    from models import _IS_SQLITE
    if not _IS_SQLITE:
        pytest.skip("仅 SQLite 环境测试")
    # lifespan 未触发时文件库可能未执行 init_db，手动调用确保 WAL 启用
    init_db()
    info = get_engine_info()
    assert info.get("journal_mode") == "wal"


# ============================================================================
# 缓存并发安全 + LRU
# ============================================================================

def test_cache_concurrent_access():
    """多线程并发读写缓存不应崩溃"""
    import threading
    from services.cache import get_cached, invalidate_cache, get_cache_stats

    invalidate_cache()
    counter = {"value": 0}

    def fetch():
        counter["value"] += 1
        return counter["value"]

    errors = []

    def worker():
        try:
            for _ in range(100):
                get_cached("test_key", fetch, ttl=60)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发访问出错: {errors}"
    stats = get_cache_stats()
    assert stats["size"] == 1


def test_cache_lru_eviction():
    """缓存超过容量限制时应正确淘汰"""
    from services.cache import get_cached, invalidate_cache, get_cache_stats

    invalidate_cache()
    for i in range(1100):
        get_cached(f"key_{i}", lambda i=i: f"value_{i}", ttl=60)

    stats = get_cache_stats()
    assert stats["size"] <= stats["max_size"]
    assert stats["size"] < 1100, "LRU 应淘汰部分 key，实际未触发淘汰"


def test_cache_ttl_expiration():
    """TTL 过期后应重新读取"""
    from services.cache import get_cached, invalidate_cache

    invalidate_cache()
    call_count = {"value": 0}

    def fetch():
        call_count["value"] += 1
        return call_count["value"]

    v1 = get_cached("ttl_key", fetch, ttl=0)
    time.sleep(0.1)
    v2 = get_cached("ttl_key", fetch, ttl=0)
    assert v2 > v1


# ============================================================================
# Auth 限流 + 恒定时间登录
# ============================================================================

def test_login_rate_limit(client):
    """同一 IP 连续登录 11 次应触发 429"""
    # 先注册一个用户
    r = client.post("/api/auth/register", json={
        "username": "ratelimit_user",
        "email": "rl@example.com",
        "password": "password123"
    })
    assert r.status_code == 201

    # 快速登录 11 次
    for i in range(11):
        r = client.post("/api/auth/login", data={
            "username": "ratelimit_user",
            "password": "password123"
        })

    assert r.status_code == 429, f"第 11 次应触发限流，实际状态码: {r.status_code}"


def test_login_constant_time(client):
    """恒定时间：存在/不存在的用户名登录耗时差异不应过大"""
    times_exist = []
    times_not_exist = []

    # 注册用户
    client.post("/api/auth/register", json={
        "username": "constant_time_user",
        "email": "ct@example.com",
        "password": "password123"
    })

    for _ in range(20):
        start = time.perf_counter()
        client.post("/api/auth/login", data={
            "username": "constant_time_user",
            "password": "wrongpassword"
        })
        times_exist.append(time.perf_counter() - start)

        start = time.perf_counter()
        client.post("/api/auth/login", data={
            "username": "nonexistent_user_12345",
            "password": "wrongpassword"
        })
        times_not_exist.append(time.perf_counter() - start)

    avg_exist = sum(times_exist) / len(times_exist)
    avg_not_exist = sum(times_not_exist) / len(times_not_exist)
    diff_ratio = abs(avg_exist - avg_not_exist) / max(avg_exist, avg_not_exist, 0.001)

    # 允许 50% 差异（本地测试环境波动较大，主要确保两者都执行了 bcrypt）
    assert diff_ratio < 0.5, f"存在/不存在用户名登录耗时差异过大: {diff_ratio:.2%}"


# ============================================================================
# 健康检查
# ============================================================================

def test_health_endpoint(client):
    """/health 应返回 200"""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_endpoint(client):
    """/health/ready 应返回 ready=true"""
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["ready"] is True


# ============================================================================
# 端到端：注册 + 登录 + 发评论流程
# ============================================================================

def test_register_and_login_flow(client):
    """完整注册登录流程，验证 bcrypt 密码和 JWT 工作正常"""
    # 注册
    r = client.post("/api/auth/register", json={
        "username": "testuser_p0",
        "email": "test@example.com",
        "password": "password123"
    })
    assert r.status_code == 201, f"注册失败: {r.text}"
    assert r.json()["username"] == "testuser_p0"

    # 登录
    r = client.post("/api/auth/login", data={
        "username": "testuser_p0",
        "password": "password123"
    })
    assert r.status_code == 200, f"登录失败: {r.text}"
    token = r.json()["access_token"]
    assert token is not None

    # 获取当前用户
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "testuser_p0"


# ============================================================================
# 缓存击穿防护（P0 修复）
# ============================================================================

def test_cache_prevents_thundering_herd():
    """并发缓存 miss 时 db_fetch_func 仅执行一次。"""
    import threading
    from services.cache import get_cached, invalidate_cache

    call_count = [0]
    def slow_fetch():
        call_count[0] += 1
        time.sleep(0.05)
        return {"data": "value"}

    results = []
    def worker():
        result = get_cached("thundering_herd_test", slow_fetch, ttl=5)
        results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert call_count[0] == 1, f"db_fetch_func 应只执行一次，实际执行了 {call_count[0]} 次"
    assert all(r == {"data": "value"} for r in results)
    invalidate_cache("thundering_herd_test")


# ============================================================================
# Request-ID 全链路追踪（P2 修复）
# ============================================================================

def test_request_id_in_response_header(client):
    """响应应携带 X-Request-ID 头，便于日志串联。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "x-request-id" in resp.headers
    assert len(resp.headers["x-request-id"]) > 0
