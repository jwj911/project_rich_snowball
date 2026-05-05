# 期货社区后端重构 — 质量评估报告

> 评估日期：2026-05-03  
> 评估范围：python/ 全部后端代码  
> 评估人：资深后端架构师（AI 辅助）

---

## 一、架构设计（权重 25%）

**评分**：7/10  
**结论**：需改进  

### 具体问题

1. **位置**：`python/routers/varieties.py:19-24`、`python/routers/kline.py:18-28`、`python/routers/products.py:12-16`  
   **问题描述**：**缺少 Service 层**，所有业务逻辑（查询条件组装、分页、排序）直接写在 Router（Controller）中。当业务规则复杂化（如加入权限过滤、缓存策略、数据脱敏）时，Router 会迅速膨胀。  
   **风险等级**：🟡 中  
   **修复建议**：引入 Service 层，Router 只负责 HTTP 协议转换和参数校验，业务逻辑下沉到 `services/varieties_service.py` 等模块。

2. **位置**：`python/data_collector/scheduler.py:16-33`、`python/data_collector/upsert.py:6-35`  
   **问题描述**：**采集器与入库逻辑紧耦合**。`scheduler.py` 直接调用 `clean_realtime` → `upsert_realtime`，没有独立的 Pipeline 或 ETL 编排层。如果未来需要接入 Kafka、替换 SQLite 为 ClickHouse，改动面会很大。  
   **风险等级**：🟡 中  
   **修复建议**：抽象 `Pipeline` 类：`extract(collector) → transform(cleaner) → load(upsert)`， scheduler 只负责任务调度。

3. **位置**：`python/data_collector/akshare_collector.py:1-62`  
   **问题描述**：**缺少防腐层（Anti-Corruption Layer）**。`akshare_collector.py` 直接调用 `ak.futures_zh_spot()` 和 `ak.futures_zh_minute_sina()`，akshare 的字段名（如 `"最新价"`）直接硬编码在采集器中。一旦 akshare 升级字段变更，需要改采集器代码。  
   **风险等级**：🟡 中  
   **修复建议**：增加 `AkshareAdapter` 中间层，将 akshare 原始响应映射到内部标准字段，采集器只依赖标准字段。

4. **位置**：`python/models.py:10-17`  
   **问题描述**：**数据库连接池配置对 SQLite 无效**。`pool_size=10, max_overflow=20` 在 SQLite 上不起作用（SQLite 不支持真正的连接池），配置具有误导性。  
   **风险等级**：🟢 低  
   **修复建议**：注释说明或根据数据库类型条件配置。

5. **位置**：全局  
   **问题描述**：**无 Repository/DAO 层**。`db.query(X).filter(...)` 直接散落在 routers、scheduler、upsert 等 10+ 处。当需要优化查询（如加 selectinload、批量查询）时，需要全局搜索替换。  
   **风险等级**：🟡 中  
   **修复建议**：为每个模型建立 Repository 类（如 `VarietyRepository`），封装 CRUD 和常用查询。

---

## 二、性能与并发（权重 20%）

**评分**：5/10  
**结论**：严重问题  

### 具体问题

1. **位置**：`python/services/cache.py:1-26`  
   **问题描述**：**内存缓存无并发锁保护**。`_cache` 和 `_cache_time` 是全局 dict，APScheduler 的 BackgroundScheduler（独立线程）和 FastAPI 主线程（可能是多进程/多线程）会同时读写。在并发场景下可能出现 `RuntimeError: dictionary changed size during iteration` 或脏读。  
   **风险等级**：🔴 高  
   **修复建议**：使用 `threading.RLock()` 保护读写操作，或改用 `cachetools.TTLCache`。

2. **位置**：`python/data_collector/scheduler.py:16-33`、`python/models.py:10-13`  
   **问题描述**：**SQLite 并发写入风险**。BackgroundScheduler 每 30 秒执行 `refresh_realtime_quotes`，同时 FastAPI 请求也可能写数据库（如发表评论、注册用户）。SQLite 的写锁是全局的，并发写入会出现 `database is locked` 错误。当前虽然设置了 `check_same_thread=False`，但并未设置 `timeout` 参数，锁等待超时后报错。  
   **风险等级**：🔴 高  
   **修复建议**：
   - 短期：`create_engine(..., connect_args={"check_same_thread": False, "timeout": 30})`
   - 长期：迁移到 PostgreSQL + 读写分离

3. **位置**：`python/routers/kline.py:22-28`  
   **问题描述**：**K 线查询无时间范围过滤**。当前只按 `variety_id + period` 过滤，然后 `ORDER BY trading_time DESC LIMIT 100`。当 K 线数据量达到百万级时，即使走了索引，`ORDER BY` + `LIMIT` 仍然需要扫描大量数据。  
   **风险等级**：🟡 中  
   **修复建议**：增加 `start_time` / `end_time` 查询参数，强制时间范围过滤。

4. **位置**：`python/routers/products.py:12`  
   **问题描述**：`GET /api/products` 全量返回，无分页。当前 10 条数据无感，但当品种扩展到 100+ 时，响应体和数据序列化开销会线性增长。  
   **风险等级**：🟡 中  
   **修复建议**：增加 `skip`/`limit` 参数，与 `/api/varieties` 保持一致。

5. **位置**：全局  
   **问题描述**：**无 WebSocket/SSE 实时推送**。前端每 30 秒轮询 `GET /api/realtime/{symbol}` 和 `GET /api/products`，对于 100 个并发用户，每分钟会产生 200 次 HTTP 请求。  
   **风险等级**：🟡 中  
   **修复建议**：引入 WebSocket（如 `python-socketio`）或 SSE，服务端有数据变更时主动推送给客户端，将轮询改为事件驱动。

6. **位置**：`python/routers/varieties.py:22-23`  
   **问题描述**：**搜索使用 `contains` 而非全文索引**。`VarietyDB.name.contains(search)` 在 SQLite 中生成 `LIKE '%search%'`，无法利用 B-Tree 索引，大数据量时全表扫描。  
   **风险等级**：🟢 低  
   **修复建议**：品种数据量小（< 1000）时无需优化；若扩展，改用 SQLite FTS 或 PostgreSQL `pg_trgm`。

---

## 三、安全与可靠性（权重 20%）

**评分**：7/10  
**结论**：需改进  

### 具体问题

1. **位置**：`python/routers/comments.py:13-20`  
   **问题描述**：**评论接口缺少操作日志和幂等性保护**。用户重复点击"发送"可能产生重复评论；删除评论、修改评论等操作无审计日志。  
   **风险等级**：🟡 中  
   **修复建议**：
   - 前端按钮加防抖；后端对 `(user_id, content_hash, created_at 最近1分钟)` 去重
   - 增加审计日志表 `audit_logs`

2. **位置**：`python/routers/auth.py:12-28`  
   **问题描述**：**注册接口无 rate limit**。恶意用户可暴力注册耗尽用户名/邮箱空间，或进行注册轰炸。  
   **风险等级**：🟡 中  
   **修复建议**：引入 `slowapi` 或自研基于内存/IP 的速率限制：`@limiter.limit("5/minute")`

3. **位置**：全局  
   **问题描述**：**无熔断/降级策略**。akshare 接口超时或限流时，scheduler 会持续抛出异常并记录 error 日志，但系统不会自动降级（如切换到 MockCollector 或延长采集间隔）。  
   **风险等级**：🟡 中  
   **修复建议**：增加熔断器（如 `pybreaker`），连续失败 N 次后自动切换到 MockCollector，并在 M 分钟后尝试恢复。

4. **位置**：`python/config.py:9-10`  
   **问题描述**：`SECRET_KEY` 缺失时抛 `ValueError`，但错误信息会出现在启动日志中。如果部署时忘记设置环境变量，日志可能暴露到外部监控系统。  
   **风险等级**：🟢 低  
   **修复建议**：在 `main.py` 启动前更早地校验，并在错误信息中不暴露配置项名称。

5. **位置**：`python/dependencies.py:22-34`  
   **问题描述**：**`get_current_user` 在 Exception 分支返回 `None`**。虽然这比抛异常更安全，但如果调用方没有正确处理 `None`，可能导致未授权访问。当前 `get_current_user_dependency` 做了二次校验，但直接调用 `get_current_user` 的地方（如测试代码）可能遗漏。  
   **风险等级**：🟢 低  
   **修复建议**：`get_current_user` 改为内部私有函数，对外只暴露 `get_current_user_dependency`。

---

## 四、可维护性与代码质量（权重 20%）

**评分**：8/10  
**结论**：通过  

### 具体问题

1. **位置**：`python/data_collector/mock_collector.py:11-17`  
   **问题描述**：`BASE_PRICES` 硬编码在 Python 源码中。当需要新增品种或调整基准价时，需要修改代码并重新部署。  
   **风险等级**：🟢 低  
   **修复建议**：从数据库 `products` 表或配置文件读取基准价。

2. **位置**：`python/data_collector/scheduler.py:59`、`python/routers/products.py:33`  
   **问题描述**：部分模块内存在延迟导入（`from models import RealtimeQuoteDB`），虽然避免了循环导入，但降低了代码可读性。  
   **风险等级**：🟢 低  
   **修复建议**：通过重构模型层消除循环依赖，或统一放在模块顶部导入。

3. **位置**：全局  
   **问题描述**：缺少统一的日志配置。当前各模块使用 `logging.getLogger(__name__)`，但没有配置 handler/formatter/level，启动后控制台无日志输出（除非显式配置）。  
   **风险等级**：🟢 低  
   **修复建议**：在 `main.py` 或 `config.py` 中配置 `logging.basicConfig(level=logging.INFO, format='...')`。

4. **位置**：`python/tests/`  
   **问题描述**：当前测试覆盖率未知。`test_p0_fixes.py` 14 个 case 覆盖安全修复，`test_phase1_3_integration.py` 25 个 case 覆盖 API 集成，但缺少：
   - 采集器/清洗器的单元测试
   - 缓存层的并发测试
   - 定时任务的集成测试  
   **风险等级**：🟡 中  
   **修复建议**：使用 `pytest-cov` 量化覆盖率，补充缺失的测试模块。

---

## 五、业务正确性与期货场景适配（权重 15%）

**评分**：5/10  
**结论**：严重问题  

### 具体问题

1. **位置**：`python/models.py:96`、`python/models.py:116`、`python/routers/realtime.py:27`  
   **问题描述**：**价格字段使用 `Float` 而非 `Decimal`**。金融场景中浮点数精度误差会导致资金计算不一致。例如：`0.1 + 0.2 != 0.3`，当价格精度要求到小数点后 4 位时，误差会累积。  
   **风险等级**：🔴 高  
   **修复建议**：将价格相关字段改为 `Numeric(precision=15, scale=4)`，Python 侧使用 `decimal.Decimal`。

2. **位置**：`python/data_collector/mock_collector.py:41-46`、`python/data_collector/cleaner.py:20-29`  
   **问题描述**：**涨跌幅计算未使用交易所标准的"昨结算价"**。当前 mock 数据用 `(price - base) / base * 100` 计算涨跌幅，但期货交易所的涨跌幅公式是 `(最新价 - 昨结算价) / 昨结算价 * 100`。基价（base）≠ 昨结算价。  
   **风险等级**：🔴 高  
   **修复建议**：在 `RealtimeQuoteDB` 中增加 `pre_settlement`（昨结算价）字段，涨跌幅统一基于此字段计算。

3. **位置**：全局  
   **问题描述**：**无交易时间判断和交易日历**。当前定时任务 `sync_daily_kline` 在每天 16:05 执行，但如果当天是周末或法定节假日，交易所无数据，采集器会抓取空数据或前一天数据。  
   **风险等级**：🟡 中  
   **修复建议**：引入交易日历库（如 `exchange_calendars` 或自建 `trading_calendar` 表），定时任务先判断是否为交易日再执行。

4. **位置**：`python/data_collector/mock_collector.py:52-67`  
   **问题描述**：**K 线时间戳未处理夜盘**。mock 数据按固定间隔（如 60 分钟）生成，但期货夜盘（如黄金 21:00-02:30）与白天交易时段不连续，K 线时间戳会出现 "白天收盘后到夜盘开盘前" 的空白 gap。  
   **风险等级**：🟡 中  
   **修复建议**：MockCollector 按交易所实际交易时段生成 K 线，或至少标注交易时段归属。

5. **位置**：`python/routers/kline.py:12-16`  
   **问题描述**：**无合约换月处理**。当前 K 线查询按 `symbol`（如 "AU"）查询，但实际期货交易中，AU2506 和 AU2508 是两个不同合约。当前设计中 `KlineDataDB` 关联的是 `variety_id`（品种级别），而非 `contract_code`（合约级别）。当主力合约从 AU2506 切换到 AU2508 时，K 线数据会出现 "跳空"。  
   **风险等级**：🟡 中  
   **修复建议**：
   - 短期：在 `KlineDataDB` 中增加 `contract_code` 字段，查询时默认查主力合约
   - 长期：K 线表按合约维度存储，品种维度做主力合约拼接

---

## 总结

**总体评分**：64/100

### 核心风险（3 条）

1. **🔴 SQLite 并发写入 + 缓存无锁**：BackgroundScheduler 与 FastAPI 主线程同时读写 SQLite 和内存缓存，生产环境大概率出现 `database is locked` 或缓存脏读。
2. **🔴 价格使用 Float 而非 Decimal**：金融系统资金计算精度误差是根本性缺陷，必须修复。
3. **🔴 涨跌幅计算未用昨结算价**：与交易所标准不一致，会导致前端展示的价格与真实行情偏差。

### 必须立即修复的问题

- [ ] `services/cache.py` 增加 `threading.RLock()`
- [ ] SQLite 连接增加 `timeout=30`
- [ ] 价格字段从 `Float` 改为 `Numeric(15, 4)`
- [ ] `RealtimeQuoteDB` 增加 `pre_settlement` 字段，修正涨跌幅计算逻辑

### 建议中长期优化

- [ ] 引入 Service 层，Router 只负责 HTTP 协议转换
- [ ] 迁移到 PostgreSQL（SQLite 并发写入是架构瓶颈）
- [ ] 增加 WebSocket/SSE 实时推送，替代前端轮询
- [ ] 引入交易日历，处理夜盘/节假日
- [ ] 增加合约换月支持，K 线按合约维度存储
- [ ] 增加 rate limit、熔断器、审计日志

### 一句话评价

> **架构拆分清晰、代码整洁度良好，但 SQLite 并发安全和金融精度问题是当前系统的生死线，必须在进入生产环境前修复。**
