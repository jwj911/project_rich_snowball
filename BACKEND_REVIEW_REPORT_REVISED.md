# 期货社区后端重构 - 修订版审查报告

> 修订日期：2026-05-03  
> 审查范围：`python/` 后端、数据模型、API、缓存、scheduler、数据采集与测试现状  
> 审查目标：校准原评审的评分与优先级，指出漏审点，并给出更适合长期演进的修复路线。

---

## 一、总体结论

原评审报告抓到了几个重要方向：SQLite 并发写入、缓存无锁、价格字段使用 Float、涨跌幅缺少昨结算价、合约换月缺失。这些确实是后端进入更严肃使用场景前必须面对的问题。

但原报告也存在三类偏差：

1. 把部分长期架构优化当成当前高优先级问题，例如 Service 层、Repository 层、WebSocket/SSE。
2. 对部分问题的技术判断不够精确，例如 K 线索引查询、缓存并发错误类型、SECRET_KEY 风险。
3. 漏掉了一些更现实的发布风险，例如测试隔离不足、缓存 ORM 对象、scheduler 重入、真实外部数据源不可控、配置与环境边界。

修订后的总体评分：**68/100**

该分数略高于原报告的 64/100。理由是当前系统作为 MVP/重构阶段并非不可用，已有基础模型、接口、迁移、测试和兼容层；但若按生产级金融行情社区系统要求，仍有明显地基问题。

---

## 二、评分校准

| 维度 | 原评分 | 修订评分 | 说明 |
|---|---:|---:|---|
| 架构设计 | 7/10 | 7/10 | Router 偏薄，暂不需要大规模分层；采集链路确实需要更清晰边界。 |
| 性能与并发 | 5/10 | 5/10 | SQLite 写锁、缓存对象生命周期、scheduler 并发是实质风险。 |
| 安全与可靠性 | 7/10 | 6/10 | 原报告漏掉登录/注册限流、token 边界、生产 docs/config 策略，需下调。 |
| 可维护性与测试 | 8/10 | 6/10 | 代码不算混乱，但测试隔离性和可重复性不足，不能给 8 分。 |
| 业务正确性 | 5/10 | 5/10 | 期货领域关键能力不足，评分合理。 |

加权总分约为：**68/100**。

---

## 三、P0 问题：必须优先处理

### 3.1 测试隔离不足

**位置**：`python/tests/`、现有测试计划  
**风险等级**：高  

当前测试依赖真实数据库、固定种子数据、固定用户和固定产品 id。这样的测试不能稳定进入 CI，也无法证明系统在干净环境下可启动、可迁移、可运行。

**具体风险**：

- 测试重复执行失败。
- 测试顺序变化后失败。
- 开发数据库被测试污染。
- CI 空库环境无法通过。
- 测试失败无法定位是代码问题还是数据状态问题。

**更合适的方案**：

- 建立独立 test DB。
- 使用 `conftest.py` override `get_db`。
- 每个测试通过 fixture 创建数据。
- 测试后事务回滚或重建 schema。
- 禁止自动化测试依赖 `trader001`、`AU`、`product_id=1` 这类隐式数据。

### 3.2 缓存 ORM 对象

**位置**：`python/routers/realtime.py`、`python/services/cache.py`  
**风险等级**：高  

当前实时行情接口通过 `get_cached()` 缓存 `RealtimeQuoteDB` ORM 对象。这个问题比“dict 无锁”更隐蔽。

**具体风险**：

- ORM 对象绑定到某个请求的 SQLAlchemy session。
- 跨请求复用时可能出现 detached instance。
- 缓存对象可能陈旧。
- 多线程读取 ORM 对象不安全。
- 未来字段懒加载时风险更高。

**更合适的方案**：

- 缓存纯 dict、Pydantic DTO 或不可变 dataclass。
- 缓存写入时完成序列化，不把 DB session 生命周期带入缓存。
- 行情 upsert 成功后主动 invalidate 对应 symbol。
- 如继续使用内存缓存，增加锁和容量/TTL 清理策略。

### 3.3 SQLite 并发写入与 scheduler 任务重入

**位置**：`python/models.py`、`python/data_collector/scheduler.py`  
**风险等级**：高  

原报告指出 SQLite 写锁风险是对的，但修复建议需要更具体。

**当前风险**：

- `refresh_realtime_quotes`、`sync_prices_to_products` 每 30 秒执行。
- 注册、评论也会写库。
- SQLite 写锁全局，容易 `database is locked`。
- APScheduler 如果任务执行超过间隔，可能重入或积压。
- 当前没有显式 `timeout`，也没有 WAL mode。

**短期方案**：

- SQLite `connect_args` 增加 `timeout`。
- 启动时启用 WAL mode。
- scheduler job 设置 `max_instances=1`、`coalesce=True`、`misfire_grace_time`。
- 将行情刷新和 products 同步合并或串行化，减少写锁竞争。
- 写入失败时记录明确指标，不吞掉异常后继续假装成功。

**长期方案**：

- 迁移 PostgreSQL。
- scheduler 从 Web 进程中拆出，作为独立 worker。
- 对行情写入采用批量 upsert。

### 3.4 金融/期货数据精度策略不清

**位置**：`python/models.py`、`python/schemas.py`  
**风险等级**：高  

原报告认为所有价格 Float 都必须立刻改 Decimal，这个方向需要细分。

如果当前系统只展示 mock 行情，Float 是短期可接受的。但如果涉及：

- 保证金
- 手续费
- 盈亏
- 报价合法性
- tick size 校验
- 交易建议价格

则必须使用 Decimal/Numeric。

**更合适的方案**：

- 行情展示字段可短期保留 Float，但建立迁移计划。
- 资金计算、保证金、手续费、目标价、止损价应改为 `Numeric`。
- Pydantic 输出层统一格式化，避免浮点尾差暴露给前端。
- 每个品种按 `tick_size` 校验价格合法性，而不是统一保留 2 位小数。

### 3.5 涨跌幅缺少昨结算价

**位置**：`python/data_collector/mock_collector.py`、`python/data_collector/cleaner.py`、`python/models.py`  
**风险等级**：高  

原报告判断正确。期货涨跌幅应基于昨结算价，而不是 mock base price。

**更合适的方案**：

- `RealtimeQuoteDB` 增加 `pre_settlement`。
- 清洗器统一计算或校验 `change_percent`。
- Akshare 数据映射层保留昨结算价字段。
- MockCollector 明确生成 `pre_settlement`，不要将 `BASE_PRICES` 当作昨结算价。

---

## 四、P1 问题：近期处理

### 4.1 鉴权实现风格不一致

**位置**：`python/routers/comments.py`、`python/dependencies.py`、`python/routers/auth.py`  
**风险等级**：中  

评论接口手动解析 Authorization header，而 `/auth/me` 使用依赖注入。这会导致认证行为分叉。

**更合适的方案**：

- 评论接口统一使用 `Depends(get_current_user_dependency)`。
- `get_current_user` 改为私有辅助函数，避免被绕过式调用。
- 增加 token 过期、伪造 token、不存在用户 id 的测试。

### 4.2 注册和登录缺少限流

**位置**：`python/routers/auth.py`  
**风险等级**：中偏高  

原报告只提到注册 rate limit，漏掉登录爆破。

**更合适的方案**：

- 注册接口限制 IP 频率。
- 登录失败按 username + IP 限制。
- 错误信息保持一致，不泄露用户名是否存在。
- MVP 阶段可先用内存限流，生产阶段迁移 Redis。

### 4.3 数据采集边界不清

**位置**：`python/data_collector/akshare_collector.py`、`python/data_collector/cleaner.py`、`python/data_collector/scheduler.py`  
**风险等级**：中  

原报告提出 Anti-Corruption Layer 是合理的，但当前更直接的问题是字段映射、失败策略和观测性。

**更合适的方案**：

- 建立 Akshare 字段映射函数，集中处理中文字段。
- 清洗器只处理内部标准字段。
- collector 负责外部 API 调用和重试。
- scheduler 负责调度，不直接吞掉所有异常。
- 记录每次采集的成功数、失败数、耗时和最后成功时间。

### 4.4 K 线模型缺少合约维度

**位置**：`python/models.py`、`python/routers/kline.py`  
**风险等级**：中偏高  

原报告提出合约换月是合理的。当前 `KlineDataDB` 只关联 `variety_id`，长期会混淆不同合约。

**更合适的方案**：

- 短期增加 `contract_code` 字段。
- API 支持可选 `contract_code`。
- 默认返回当前主力合约。
- 长期区分“单合约 K 线”和“主连 K 线”。

### 4.5 K 线查询优化表述需要修正

**位置**：`python/routers/kline.py`、`python/models.py`  
**风险等级**：中  

原报告说 `ORDER BY trading_time DESC LIMIT 100` 即使有索引也会扫描大量数据，这个判断过于绝对。当前存在 `(variety_id, period, trading_time)` 复合索引，查询条件匹配前缀，数据库通常可以利用索引处理倒序 limit。

真正需要改进的是：

- 增加 `start_time` / `end_time`。
- 增加游标分页。
- 明确数据保留策略。
- 为百万级数据做 explain/query plan 验证。

### 4.6 错误处理与日志配置不足

**位置**：全局  
**风险等级**：中  

当前模块里有 logger，但缺少统一配置和结构化上下文。

**更合适的方案**：

- 在 app 启动时配置 logging。
- scheduler 每个 job 记录 job id、耗时、成功数、失败数。
- API 异常不泄露堆栈。
- 生产环境关闭 debug docs 或加访问控制。

---

## 五、P2 问题：中长期演进

### 5.1 Service 层

**原报告评价**：中风险  
**修订评价**：低到中风险，按复杂度逐步引入  

当前 router 查询逻辑还薄，不建议一次性重构所有模块。更适合的策略是：

- 先抽复杂逻辑：行情同步、K 线查询、评论创建。
- Router 保持参数校验和 response model。
- Service 管业务规则。
- Repository 只在查询复用或性能优化需要时引入。

### 5.2 Repository/DAO 层

**原报告评价**：中风险  
**修订评价**：低风险  

现在强行给每个模型建立 Repository 会增加样板代码。建议等到出现以下情况再引入：

- 同类查询重复 3 次以上。
- 需要统一 eager loading。
- 需要替换数据库。
- 需要复杂事务边界。

### 5.3 WebSocket/SSE

**原报告评价**：中风险  
**修订评价**：低到中风险  

100 用户每 30 秒轮询不是当前最紧急瓶颈。先做缓存、DB 写锁、接口压测，再决定是否引入 SSE/WebSocket。

更合适的路径：

1. 优化 HTTP 缓存和批量行情接口。
2. 记录实际 QPS、延迟、缓存命中率。
3. 用户量上来后引入 SSE。
4. 需要双向互动时再考虑 WebSocket。

### 5.4 PostgreSQL 迁移

**原报告评价**：中长期优化  
**修订评价**：正确，但要配合 worker 拆分  

仅迁移 PostgreSQL 不能解决所有问题。如果 scheduler 仍跑在 Web 进程里，仍会有任务重入、部署多副本重复执行的问题。

长期方案应包括：

- PostgreSQL。
- 独立 worker。
- 分布式锁或任务队列。
- 数据采集状态表。

---

## 六、原报告漏审点汇总

1. **测试不可重复**：现有测试依赖真实数据和固定 id，这是发布质量的基础缺口。
2. **缓存 ORM 对象**：比单纯 dict 无锁更危险。
3. **scheduler 重入**：没有 `max_instances=1` 等保护。
4. **Web 进程内 scheduler**：多 worker 部署时可能重复采集。
5. **认证风格不一致**：comments 手动解析 token，auth 使用依赖。
6. **登录爆破**：只提注册限流，不够。
7. **Pydantic 输入校验不足**：用户名、邮箱、密码复杂度没有明确策略。
8. **XSS 策略不清**：当前是存储时 escape，可能带来二次转义问题。
9. **Akshare 合约硬编码**：`f"{symbol}2506"` 会很快失效。
10. **产品兼容层数据一致性**：`products` 与 `realtime_quotes` 同步没有强一致保证。
11. **生产配置策略不足**：docs、CORS、SECRET_KEY、DATABASE_URL、日志级别需要环境化。
12. **业务字段缺失**：昨结算价、合约代码、交易时段、主力合约状态、数据来源时间。

---

## 七、修订后的推荐路线

### 阶段 1：质量地基

- 建立独立测试数据库和 fixture。
- 修复缓存，不缓存 ORM 对象。
- SQLite 增加 timeout/WAL。
- scheduler job 防重入。
- 评论接口统一鉴权依赖。
- 注册/登录增加基础限流。

### 阶段 2：行情与业务正确性

- 增加 `pre_settlement`。
- 明确涨跌幅计算策略。
- 增加 `contract_code` 到 K 线。
- 清洗器强化 OHLC、tick size 校验。
- Akshare 字段映射集中化。

### 阶段 3：可维护性与容量

- 抽取行情 service、K 线 service、评论 service。
- 根据重复查询引入 Repository。
- K 线增加时间范围和游标分页。
- 建立慢速容量测试。

### 阶段 4：生产化

- 迁移 PostgreSQL。
- scheduler 独立 worker 化。
- 引入 Redis 缓存/限流。
- 根据压测结果决定 SSE/WebSocket。
- 增加审计日志、监控和告警。

---

## 八、最终评价

当前后端适合作为重构阶段的 MVP，但还不适合直接按生产级行情系统发布。最需要优先修的不是“有没有 Service 层”，而是：

1. 测试是否能稳定证明系统正确。
2. 缓存是否跨请求安全。
3. SQLite 和 scheduler 是否会在并发写入下失效。
4. 价格、涨跌幅、合约维度是否符合期货业务基本语义。

把这四件事处理好以后，再推进分层、PostgreSQL、SSE/WebSocket，系统会走得更稳。
