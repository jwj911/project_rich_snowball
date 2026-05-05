# 期货社区后端重构 - 修订版测试计划

> 修订日期：2026-05-03  
> 适用范围：`python/` 后端、数据采集、数据库迁移、API 兼容层  
> 核心目标：让测试能稳定复现问题、能进入 CI、能覆盖真实发布风险，而不是只形成一次性检查清单。

---

## 一、总体评价与修订原则

原测试计划覆盖了模型、清洗器、缓存、API、并发、安全、业务和回归场景，方向是完整的。但主要问题是：

1. 依赖真实开发数据库和固定种子数据，导致测试顺序敏感、重复运行不稳定。
2. 很多测试只验证“接口能返回”，没有验证数据隔离、幂等、权限边界和错误分支。
3. 并发测试主要是并发读，不能证明 SQLite 写锁、scheduler 写入和用户写入之间的真实风险。
4. 性能测试使用墙钟时间比例断言，容易受机器负载影响。
5. 业务测试停留在价格小数位，未覆盖期货系统真正关键的昨结算价、合约维度、交易日历、夜盘、tick size。

修订后的测试原则：

- 每个测试必须可重复运行，不能依赖上一次测试留下的数据。
- 快速单元测试和慢速集成/并发测试分层执行。
- 尽量通过 fixture、mock、独立 test DB、事务回滚控制测试边界。
- 对核心风险写“能失败”的测试，避免只有注释没有断言。
- 测试结果必须能进入 CI，慢测试可单独标记。

---

## 二、测试环境规范

### 2.1 独立测试数据库

禁止直接使用开发数据库 `futures_community.db` 执行自动化测试。测试环境应使用独立数据库，例如：

```bash
cd python
set DATABASE_URL=sqlite:///./test_futures_community.db
set SECRET_KEY=test-secret-key
pytest -p no:langsmith
```

建议在 `tests/conftest.py` 中提供：

- `test_engine`
- `TestingSessionLocal`
- `override_get_db`
- 每个测试前创建 schema
- 每个测试后回滚或删除测试库
- 自动禁用 scheduler 启动

### 2.2 测试分组

建议使用 pytest marker：

```ini
[pytest]
markers =
    unit: fast unit tests
    integration: API and database integration tests
    concurrency: thread/process contention tests
    security: security boundary tests
    business: futures-domain correctness tests
    slow: slow tests excluded from default CI
```

默认 CI 执行：

```bash
pytest -m "not slow" --cov=python --cov-report=term-missing
```

专项执行：

```bash
pytest -m "concurrency or slow" -v -s
```

---

## 三、P0 测试：必须先补齐

### 3.1 测试隔离与 fixture

目标：所有 API 测试不依赖真实 `trader001`、真实 `AU` 数据或开发库中的 10 条种子数据。

必须覆盖：

- 每个测试创建自己的用户、产品、品种、行情、K 线。
- 注册测试重复运行不会因为用户已存在而失败。
- 测试失败后不污染后续测试。
- scheduler 不会在导入 `main.app` 时自动写真实数据库。

验收标准：

- 连续执行 3 次 `pytest` 结果一致。
- 单独执行任意一个测试文件也能通过。
- 打乱测试顺序后仍能通过。

### 3.2 缓存层正确性测试

当前风险：`services/cache.py` 缓存全局 dict 无锁，并且 `realtime` 接口缓存 ORM 对象，可能出现跨 session、陈旧数据或线程安全问题。

必须覆盖：

- 缓存命中时 fetch 函数只调用一次。
- TTL 过期后重新调用 fetch。
- `invalidate_cache(key)` 只清理指定 key。
- `invalidate_cache()` 清理全部 key。
- 并发请求同一个 key 时不会抛异常。
- 不允许缓存 SQLAlchemy ORM 实例，推荐缓存 dict / DTO。

示例断言方向：

```python
def test_cache_should_not_store_orm_object():
    value = get_cached("x", lambda: {"current_price": 1.23})
    assert isinstance(value, dict)
```

如果暂时仍缓存 ORM 对象，应先加 `xfail` 标明这是已知缺陷。

### 3.3 SQLite 并发写入测试

原计划只并发读取 `/api/varieties`，不足以证明 `database is locked` 风险。新的并发测试必须混合读写。

场景：

- 线程 A：循环执行 `refresh_realtime_quotes()`
- 线程 B：循环注册用户
- 线程 C：循环发表评论
- 线程 D：循环读取 `/api/realtime/AU`
- 线程 E：循环读取 `/api/products`

验收标准：

- 不出现 `database is locked`
- 不出现 session closed / detached instance 错误
- 写入数据最终一致
- API 错误率为 0

短期如果仍使用 SQLite，建议同时验证：

- `connect_args.timeout`
- WAL mode
- scheduler job 不重入

### 3.4 API 鉴权与权限边界

必须覆盖：

- 无 token 访问评论创建返回 401。
- 伪造 token 返回 401。
- 过期 token 返回 401。
- 使用不存在用户 id 的 token 返回 401。
- 评论 product_id 不存在返回 404。
- 评论内容为空、全空格、超长均返回 422。
- 登录错误密码返回 401，且不泄露用户是否存在。
- 重复注册用户名/邮箱返回 400。

当前 `comments.py` 手动解析 Authorization header，`auth.py` 使用 FastAPI OAuth2 依赖，风格不一致。测试应覆盖两种认证路径行为一致。

### 3.5 数据库迁移与 schema 契约

必须覆盖：

- Alembic 从空库迁移到 head 成功。
- 所有业务表存在。
- 关键唯一约束存在：用户 username/email、品种 symbol/contract_code、K 线唯一键。
- 关键索引存在：品种 symbol/category、K 线 `(variety_id, period, trading_time)`。
- 外键关系存在。
- 如果引入 Decimal/Numeric，验证数据库字段类型和 Python 返回类型。

---

## 四、P1 测试：近期应补齐

### 4.1 数据清洗器测试

必须覆盖：

- 负价格丢弃。
- high < low 丢弃。
- volume 非数字不抛异常。
- open_interest 非数字不抛异常。
- 缺失 current_price 丢弃。
- `updated_at` 字符串、datetime、缺失值都能处理。
- K 线重复时间去重。
- K 线 OHLC 合法性：high 必须大于等于 open/close/low，low 必须小于等于 open/close/high。

原计划只检查 high 和 low，不足以发现 OHLC 内部矛盾。

### 4.2 实时行情 API 契约

必须覆盖：

- 返回字段完整。
- 返回字段类型稳定。
- 不存在品种返回 404。
- 存在品种但无行情返回 404。
- 缓存命中不返回陈旧 ORM 对象。
- 更新行情后，cache invalidation 生效。

### 4.3 K 线 API 契约

必须覆盖：

- period 合法值：`1m`、`5m`、`15m`、`30m`、`1h`、`1d`、`1w`。
- 非法 period 返回 422。
- limit 边界：0、1、1000、1001。
- 返回时间顺序为升序。
- 返回数据只属于请求 symbol。
- 未来加入 `start_time` / `end_time` 后，必须验证边界包含规则。

### 4.4 旧接口兼容

必须覆盖：

- `/api/products` 响应字段兼容旧前端。
- `/api/products/{id}` 返回 `product + comments`。
- `/api/comments/user/{username}` 返回结构稳定。
- 新旧行情同步后，`products.current_price` 与 `realtime_quotes.current_price` 一致。

这些测试应使用 fixture 数据，不应假设真实库里一定有 id=1。

---

## 五、P1 安全测试

### 5.1 注入与输入边界

必须覆盖：

- `search="' OR 1=1 --"` 不返回异常，不泄露 SQL。
- `category="'; DROP TABLE varieties; --"` 不破坏表。
- `skip=-1` 返回 422。
- `limit=0` 和 `limit=1001` 返回 422。
- symbol/path 参数包含特殊字符时不泄露堆栈。

### 5.2 XSS 策略

当前 `CommentCreate.sanitize_content` 在入库前 escape。测试需要明确策略：

- 如果选择“存储时转义”，则 API 返回应包含 `&lt;script&gt;`。
- 如果选择“展示时转义”，则数据库保存原文，前端负责 escape。

长期更推荐保存原始用户输入，输出层按场景 escape，避免重复转义和搜索体验问题。但如果当前系统短期采用存储时转义，测试必须防止二次 escape。

### 5.3 Rate Limit

当前注册和登录接口缺少 rate limit。测试应在实现后覆盖：

- 同 IP 1 分钟内超过注册次数返回 429。
- 登录失败次数过多返回 429 或临时锁定。
- 正常用户低频请求不受影响。

---

## 六、P1 业务正确性测试

### 6.1 价格精度

不要简单断言“最多 2 位小数”。不同期货品种 tick size 不同。

应验证：

- 价格符合品种 `tick_size`。
- 保证金、手续费、盈亏等资金计算使用 Decimal。
- API 输出格式稳定，避免浮点尾差。

### 6.2 涨跌幅计算

必须覆盖：

- 使用昨结算价 `pre_settlement` 计算涨跌幅。
- 昨结算价为 0 或缺失时不计算，返回 0 或 null，策略要明确。
- mock collector 不应把 base price 伪装成昨结算价。

### 6.3 合约维度与换月

必须覆盖：

- K 线数据至少能区分 `symbol` 和 `contract_code`。
- 同一品种不同合约的 K 线不会混写。
- 主力合约切换时，查询策略明确：查当前主力、查指定合约，或查拼接主连。

### 6.4 交易日历与夜盘

必须覆盖：

- 周末/节假日不执行日 K 补全，或执行后不写入错误数据。
- 夜盘时间戳归属正确。
- 日盘与夜盘之间允许 gap，但不能生成不存在交易时段的 K 线。

---

## 七、P2 性能与容量测试

### 7.1 K 线查询容量

准备至少 100 万条 K 线测试数据，验证：

- 指定 symbol + period + limit 查询延迟。
- 加入时间范围后的查询延迟。
- 索引是否被使用。
- 返回顺序是否稳定。

### 7.2 轮询压力

在引入 SSE/WebSocket 前，应先证明轮询是否真的成为瓶颈。

场景：

- 100、500、1000 并发用户。
- 每 30 秒请求 `/api/products` 和 `/api/realtime/{symbol}`。
- 记录 P50/P95/P99 延迟、错误率、DB 查询次数、缓存命中率。

只有当轮询成为明确瓶颈时，再推进 SSE/WebSocket。

---

## 八、推荐执行顺序

1. 建立 `conftest.py` 和独立测试数据库。
2. 修复现有测试对真实库、真实用户、固定 id 的依赖。
3. 补齐 P0：缓存、并发写入、鉴权、迁移。
4. 补齐 P1：清洗器、API 契约、安全、业务正确性。
5. 将 `not slow` 测试接入 CI。
6. 将并发、容量、交易日历等慢测试作为发布前专项。

---

## 九、通过标准

默认合并门槛：

- `pytest -m "not slow"` 全部通过。
- 覆盖率报告生成成功。
- P0 测试全部通过。
- 无测试依赖开发数据库。
- 无测试依赖固定用户、固定产品 id、固定执行顺序。

发布前门槛：

- 并发写入测试通过。
- scheduler 专项测试通过。
- 关键安全测试通过。
- 旧接口兼容测试通过。
- 业务正确性测试通过，尤其是价格精度、涨跌幅、合约维度。

---

## 十、一句话结论

测试计划的长期目标不是“写更多 case”，而是让每个核心风险都有一个稳定、隔离、能自动失败的测试来守住。当前最应该先补的是测试隔离、缓存对象生命周期、SQLite 并发写入、鉴权边界和期货业务正确性。
