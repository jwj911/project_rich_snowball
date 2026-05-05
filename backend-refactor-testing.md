# 期货社区后端重构质量测试 Prompt

## 角色
你是一位拥有 10 年以上金融系统测试经验的 QA 架构师，擅长后端 API 测试、数据库一致性验证、并发压力测试和交易系统边界条件测试。你对"看似能跑"的代码保持怀疑，能设计出让系统暴露真实问题的测试场景。

## 任务
请对以下已完成的期货社区后端重构代码进行全面质量测试。测试覆盖**单元测试、集成测试、API 契约测试、并发测试、数据一致性测试、安全测试**六个层面。不要只跑 happy path，要构造异常输入、边界条件和并发冲突场景。

## 测试环境要求（先确认）

测试前请先确认：
1. **技术栈**：Python 版本？FastAPI？SQLAlchemy？数据库是 SQLite 还是 PostgreSQL？
2. **依赖安装**：`requirements.txt` 是否完整？akshare/APScheduler/alembic 是否已装？
3. **数据库状态**：当前数据库是否已迁移？是否有种子数据？
4. **环境变量**：`.env` 中 `SECRET_KEY` / `DATABASE_URL` 是否配置？
5. **运行方式**：`python main.py` 还是 `uvicorn`？采集器是独立进程还是内嵌？

确认后执行测试，缺失环境先报告，不硬跑。

---

## 一、单元测试（Unit Tests）

### 1.1 模型层测试

**测试目标**：`models.py` 中所有模型的创建、关系和约束

| 测试项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| VarietyDB 创建 | 新建品种，所有字段赋值 | 成功插入，id 自增 |
| VarietyDB 唯一约束 | 插入相同 symbol | IntegrityError，不重复 |
| RealtimeQuoteDB 关联 | 为品种创建行情，查询 `variety.realtime` | 双向关系正常 |
| KlineDataDB 复合唯一 | 同一品种+周期+时间插入两次 | 第二次失败或被覆盖（取决于 upsert 策略） |
| UserDB 密码哈希 | 创建用户，检查 password_hash 是否为明文 | 必须是哈希值，不是明文密码 |
| CommentDB 级联删除 | 删除 User，关联的 Comment 是否处理 | 根据 cascade 设置，明确行为 |

**测试代码模板**：
```python
# 需要 pytest + pytest-asyncio + 内存数据库 fixture
@pytest.fixture
def db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()

def test_variety_unique_symbol(db):
    v1 = VarietyDB(symbol="AU", name="黄金", exchange="SHFE")
    db.add(v1); db.commit()
    v2 = VarietyDB(symbol="AU", name="黄金2", exchange="SHFE")
    db.add(v2)
    with pytest.raises(IntegrityError):
        db.commit()
```

### 1.2 数据清洗器测试

**测试目标**：`cleaner.py` 对各种脏输入的处理

| 输入 | 预期行为 |
|------|----------|
| `current_price = -100` | 返回 None，记录 warning |
| `high = 500, low = 600` | 返回 None（high < low） |
| `volume = "abc"` | 不崩溃，返回 None 或 0 |
| `change_percent = None` | 默认 0，不报错 |
| 空列表 `[]` | `clean_kline` 返回 `[]`，不崩溃 |
| 包含重复时间戳的列表 | 去重后保留第一条 |

### 1.3 缓存层测试

**测试目标**：`cache.py` 的并发安全和 TTL 逻辑

| 测试项 | 方法 |
|--------|------|
| 单线程读写 | 写入后立即读取，应命中 |
| TTL 过期 | 写入后等待5秒再读，应走 db_fetch |
| 并发读写 | 10个线程同时读写同一 symbol，不抛异常、数据一致 |
| 内存泄漏 | 写入1000个不同 symbol，检查 dict 长度是否受控 |

---

## 二、集成测试（Integration Tests）

### 2.1 API 契约测试

使用 `TestClient` 对每个路由做完整测试：

#### `/api/varieties`
- [ ] `GET /api/varieties` → 返回品种列表，格式匹配 `VarietyResponse`
- [ ] `?category=贵金属` → 只返回黄金、白银等
- [ ] `?search=黄金` → 返回包含"黄金"的品种
- [ ] `?skip=10&limit=20` → 分页正确，返回 20 条，第 11-30 条
- [ ] `?limit=1001` → 422 验证错误（超过 max=1000）
- [ ] 空表时 → 返回 `[]`，不是 null 或 500

#### `/api/kline/{symbol}`
- [ ] `GET /api/kline/AU?period=1h&limit=100` → 返回 OHLCV 数组，时间升序
- [ ] 不存在的 symbol → 404，错误信息明确
- [ ] `?period=1x` → 422 验证错误（period 不在枚举中）
- [ ] `limit=0` → 422 验证错误
- [ ] K线数据为空 → 返回 `[]`
- [ ] 返回数据的 `time` 字段是否为 ISO 格式字符串？

#### `/api/realtime/{symbol}`
- [ ] 正常 symbol → 返回价格快照，字段完整
- [ ] 不存在的 symbol → 404
- [ ] 5秒内重复请求 → 走缓存（响应时间 < 10ms vs 第一次 > 50ms）

#### `/api/auth`（如有）
- [ ] 注册用户 → 201，返回用户信息（不含密码）
- [ ] 重复注册 → 409 或 400，明确提示
- [ ] 登录正确密码 → 200，返回 token
- [ ] 登录错误密码 → 401
- [ ] 无 token 访问受保护接口 → 401/403

#### `/api/comments`（如有）
- [ ] CRUD 完整流程
- [ ] XSS 注入：`content = "<script>alert(1)</script>"` → 存储时转义，返回时无害
- [ ] 超长内容（>2000字）→ 422
- [ ] 空内容 → 422

### 2.2 数据库一致性测试

| 测试场景 | 验证方法 |
|----------|----------|
| 采集器写入 realtime_quotes 后 | 查 `variety.realtime` 能读到最新数据 |
| 定时任务 sync_prices_to_products 后 | `products.current_price` 与 `realtime_quotes.current_price` 一致 |
| 删除 Variety 时 | 关联的 Kline/Comment/Watchlist 按 cascade 设置处理，不抛外键错误 |
| Alembic 迁移后 | 旧数据仍在，新字段有默认值或 nullable |

### 2.3 采集器集成测试

**测试目标**：`data_collector/` 完整链路

```python
# 伪代码：模拟测试
def test_collector_pipeline():
    # 1. 运行 init_varieties.py，确认品种表有数据
    # 2. 启动 scheduler，mock akshare 返回固定数据
    # 3. 等待 35 秒，确认 realtime_quotes 有 Upsert 数据
    # 4. 确认 products 表被同步更新
    # 5. 停止 scheduler，确认无残留线程
```

---

## 三、并发与性能测试

### 3.1 SQLite 并发测试（致命级）

这是最重要的测试。SQLite 在并发写入时会出现 `database is locked`。

| 并发场景 | 测试方法 | 通过标准 |
|----------|----------|----------|
| 采集器写入 + API 同时读 | locust/threading 模拟 10 并发读，采集器持续写入 | 无 `database is locked`，读取延迟 < 200ms |
| 采集器写入 + 同步任务写入 | 两个写入源同时运行 | 无死锁，数据最终一致 |
| 大量 Kline 写入 + 查询 | 插入 1 万条 Kline，同时查询 | 查询不被阻塞或超时 |

**测试脚本模板**：
```python
import threading, time, requests

def test_concurrent_read_while_write():
    def writer():
        while True:
            # 模拟采集器 upsert
            time.sleep(30)
    
    def reader():
        for _ in range(100):
            r = requests.get("http://localhost:8000/api/varieties")
            assert r.status_code == 200
            assert r.elapsed.total_seconds() < 0.2
    
    threading.Thread(target=writer, daemon=True).start()
    threads = [threading.Thread(target=reader) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
```

### 3.2 缓存性能测试

| 场景 | 指标 |
|------|------|
| 首次请求 `/api/realtime/AU` | 响应时间 |
| 5秒内重复请求 | 响应时间应下降 80%+ |
| 缓存 TTL 过期后 | 响应时间恢复首次水平 |

### 3.3 内存测试

- 采集器运行 1 小时后，进程 RSS 内存是否持续增长？
- `python -m memory_profiler` 或 `tracemalloc` 检查泄漏点

---

## 四、安全测试

### 4.1 注入攻击

| 攻击向量 | 测试输入 | 预期结果 |
|----------|----------|----------|
| SQL 注入 | `?search=' OR 1=1 --` | 正常搜索，不暴露所有数据 |
| SQL 注入 | `?category='; DROP TABLE varieties; --` | 被转义或 422 |
| NoSQL 注入 | 如有 MongoDB，测试 `$ne` 操作符 | 被过滤 |

### 4.2 认证绕过

| 测试 | 方法 |
|------|------|
| 无 token 访问 POST/DELETE | 应返回 401/403 |
| 伪造 token | 用错误密钥签名，应 401 |
| token 过期 | 等待过期时间后请求，应 401 |
| 越权访问 | 用户A的 token 操作用户B的数据，应 403 |

### 4.3 输入校验

| 字段 | 异常输入 | 预期 |
|------|----------|------|
| `username` | `<script>alert(1)</script>` | 被过滤或拒绝 |
| `email` | `not-an-email` | 422 |
| `password` | 空字符串 / 7个字符 | 422（要求 >=8） |
| `content` | 5000字 | 422（要求 <=2000） |
| `period` | `1x` | 422（正则校验） |
| `symbol` | 超长字符串（>50字符） | 截断或 422 |

### 4.4 敏感信息泄漏

- [ ] 错误响应中是否包含 SQL 语句、堆栈跟踪、内部路径？
- [ ] 日志中是否打印了密码、token、数据库 URL？
- [ ] Swagger `/docs` 在生产环境是否关闭或加认证？

---

## 五、期货业务场景测试

这是区别于普通后端的核心测试。

### 5.1 合约换月测试

| 场景 | 测试方法 | 通过标准 |
|------|----------|----------|
| 主力合约切换 | 模拟 AU2506 即将到期，AU2508 成为新主力 | K线查询 `?contract=main` 自动指向新主力 |
| 新旧合约 K线拼接 | AU2506 和 AU2508 的日 K 是否有重叠日期 | 重叠日期取主力合约数据，不重复 |
| 合约下架 | AU2506 到期后 | 仍可查询历史，但实时行情返回 404 |

### 5.2 夜盘数据处理测试

| 场景 | 测试方法 |
|------|----------|
| 夜盘时间采集 | 模拟 21:30 采集黄金行情 | trading_time 应为 21:30，不是 09:30 |
| 交易日归属 | 5月6日 21:30 的夜盘 K线 | 归属交易日应为 5月7日（交易所规则） |
| 跨午夜 K线 | 23:00-01:00 的 1小时 K线 | 时间戳连续，无跳跃 |
| 夏令时 | 如有外盘数据 | 时间处理正确 |

### 5.3 数据精度测试

| 场景 | 测试 | 通过标准 |
|------|------|----------|
| 价格精度 | 黄金价格 1050.50 | 存储和返回都是 1050.50，不是 1050.5 或 1050.5000001 |
| 涨跌幅计算 | `(current - pre_close) / pre_close * 100` | 与交易所显示一致，精度 2 位小数 |
| 大成交量 | `volume = 9999999999` | 不溢出，不截断 |
| 零成交量 | `volume = 0` | 正常显示，不抛 ZeroDivisionError |

### 5.4 数据源降级测试

| 场景 | 测试方法 |
|------|----------|
| akshare 接口 502 | mock 返回 502，系统是否用缓存数据？是否记录 error？ |
| akshare 返回空 DataFrame | `df.empty = True`，系统是否保留上一次有效数据？ |
| 网络超时 | 请求 30 秒无响应，scheduler 是否继续下一轮？ |

---

## 六、回归测试（Regression）

### 6.1 旧接口兼容

| 旧接口 | 验证 |
|--------|------|
| `GET /api/products` | 返回数据格式与重构前一致 |
| `GET /api/products/{id}` | 字段名、类型不变 |
| 前端页面 | 不修改前端代码，功能正常 |

### 6.2 数据迁移验证

- [ ] 旧 `users` 表数据迁移后，登录正常
- [ ] 旧 `comments` 数据迁移后，评论显示正常
- [ ] 旧 `products` 数据是否被正确映射到新 varieties + realtime_quotes？

---

## 七、测试输出格式

对每个测试模块给出：

### [测试模块名]

**总体状态**：✅ 通过 / ⚠️ 部分通过 / ❌ 未通过 / ⏭️ 未执行  
**测试覆盖率**：X%  
**关键发现**：

1. **严重问题** 🔴
   - 描述：...
   - 复现步骤：...
   - 影响：...
   - 建议：...

2. **需改进** 🟡
   - ...

3. **通过项** 🟢
   - ...

---

## 八、测试执行 Checklist

### 环境准备
- [ ] Python 3.10+，虚拟环境激活
- [ ] `pip install -r requirements.txt`
- [ ] `pip install pytest pytest-asyncio httpx memory_profiler locust`（测试依赖）
- [ ] `.env` 配置正确，`SECRET_KEY` 已设置
- [ ] 数据库已迁移：`alembic upgrade head`
- [ ] 种子数据已灌入：`python data_collector/init_varieties.py`

### 执行顺序
1. [ ] 单元测试：`pytest tests/ -v`
2. [ ] API 测试：`pytest tests/test_api.py -v`
3. [ ] 并发测试：运行并发脚本，观察日志
4. [ ] 安全测试：用 Burp Suite 或手动构造异常输入
5. [ ] 性能测试：`locust -f locustfile.py --host=http://localhost:8000`
6. [ ] 业务场景测试：模拟合约换月、夜盘数据
7. [ ] 回归测试：前端对接，确认旧功能正常

---

## 使用说明

1. 先确认测试环境，缺失的依赖和配置先补齐
2. 按"单元→集成→并发→安全→业务→回归"顺序执行
3. 🔴 级问题必须修复后才能进入下一阶段
4. 测试代码应保留在 `tests/` 目录，作为持续集成的一部分
5. 所有测试应在 CI 中自动运行（GitHub Actions / GitLab CI）

---

## 一句话总结

> 能跑 ≠ 能上线。SQLite 并发、合约换月、实时推送是期货系统的生死线，必须用测试证明它们扛得住真实场景，而不是只在 localhost 上"看起来正常"。
