# 后端迭代计划 v8（2026-05-09）

> 版本：v8
> 日期：2026-05-09
> 依据：`FULLSTACK_REVIEW_AND_ITERATION_PLAN_20260509.md` 后端部分 + 当前代码实际状态
> 定位：把后端从"新旧数据层并存"推进到"工作区闭环 + 合约语义贯通 + 生产可运行"

---

## 0. 当前代码基线速览

| 模块 | 已有 | 缺失 |
|------|------|------|
| 用户/认证 | `UserDB`、`auth.py`、JWT、bcrypt、限流 | — |
| 评论 | `CommentDB`、`comments.py`、分页、XSS 过滤 | 与 price_level / kline 时间点的关联 |
| 旧兼容层 | `ProductDB`、`products.py` | 应逐步收敛，新功能不走这里 |
| 品种/行情 | `VarietyDB`、`RealtimeQuoteDB`、`KlineDataDB` | `KlineDataDB` 缺 `contract_id` |
| 合约元数据 | `FutContractDB`（含 `ts_code`, `list_date`, `delist_date`, `contract_type`） | 无 `contracts.py` 路由；无 rollover 历史表 |
| 自选 | `WatchlistDB`（`user_id`, `variety_id`, `resistance_level`, `support_level`, `notes`） | 无 `watchlists.py` 路由；无 schema；无测试 |
| 价位标注 | — | 无模型、无表、无 API |
| 工作区聚合 | — | 无 `workspace.py` 路由 |
| 采集调度 | `scheduler.py` + APScheduler；`DataIngestionRunDB` | worker 未拆分；任务状态只写不读；无熔断 |
| 数据质量 | `upsert.py` 已兼容 PG/SQLite | 无统一质量报告；无缺失/异常检测 |
| Tushare 回填 | `tushare_pg_ingest/` 14 个脚本 | 缺统一 CLI 入口、dry-run、resume |

---

## 1. 迭代原则

1. **模型先行**：每个阶段先做表/字段迁移，再写 API，最后补测试。
2. **兼容层只缩不扩**：新 API 优先走 `/api/varieties`、`/api/contracts`、`/api/workspace`，旧 `/api/products` 只做维护。
3. **migration 分四步**：expand → backfill → switch → contract，绝不一次性破坏已有 K 线数据。
4. **进程边界清晰**：Phase 3 之前允许 scheduler 与 API 同进程，但代码上要预留拆分接口。

---

## 2. Phase 1：用户研究工作区闭环（建议优先）

**目标**：让用户的自选、价位标注、评论真正可沉淀、可查询、跨设备保留。

**周期预估**：5–7 天

### 2.1 任务清单

| 编号 | 任务 | 改动文件 | 说明 | 验收标准 |
|------|------|----------|------|----------|
| P1-1 | 新增 `price_levels` 表 | `models.py` + Alembic 迁移 | 支撑/阻力位独立成表，不再塞 `WatchlistDB` 单字段 | 迁移可 `upgrade/downgrade` |
| P1-2 | 新增 `PriceLevel` schema | `schemas.py` | 含 `type: support\|resistance`、`price: Decimal`、`note`、`source` | Pydantic v2 校验通过 |
| P1-3 | 新增 `watchlists.py` 路由 | `routers/watchlists.py` | 基于已有 `WatchlistDB` 做 CRUD；用户只能操作自己的数据 | 403 越权测试通过 |
| P1-4 | 新增 `price_levels.py` 路由 | `routers/price_levels.py` | 增删查改；同一用户同一品种同一价格同一类型去重 | 重复创建返回 409 或覆盖 |
| P1-5 | 新增 `workspace.py` 聚合路由 | `routers/workspace.py` | `/api/workspace/me` 返回：评论列表、标注列表、自选列表、最近访问品种 | 单请求驱动工作区首页 |
| P1-6 | 评论模型扩展 | `models.py` + 迁移、`schemas.py` | 评论可选关联 `price_level_id`（nullable）；兼容旧数据 | 旧评论不报错 |
| P1-7 | 后端测试 | `tests/test_watchlists.py`、`test_price_levels.py`、`test_workspace.py` | CRUD、越权、重复、聚合查询 | pytest 全绿 |
| P1-8 | 文档更新 | `AGENTS.md` | 新增 router 挂载点、端口、测试命令 | 与代码一致 |

### 2.2 `price_levels` 模型设计

```python
class PriceLevelDB(Base):
    __tablename__ = "price_levels"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    variety_id = Column(Integer, ForeignKey("varieties.id"), nullable=False, index=True)
    # 迁移期兼容：也可支持 product_id nullable，但最终以 variety_id 为准
    type = Column(String(20), nullable=False)  # support | resistance
    price = Column(Numeric(15, 4), nullable=False)
    note = Column(Text, nullable=True)
    source = Column(String(30), nullable=False, default="manual")  # manual | chart_context_menu | imported
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 同一用户同一品种同类型同价格唯一
    __table_args__ = (
        UniqueConstraint("user_id", "variety_id", "type", "price", name="uix_user_variety_type_price"),
    )
```

### 2.3 关键决策

- **WatchlistDB 的 `resistance_level`/`support_level` 字段**：不删除，留作兼容；新逻辑全走 `price_levels` 表。
- **Variety vs Product 关联**：`price_levels` 和 `watchlists` 都优先挂 `variety_id`；前端若仍传旧 `product_id`，在 router 里做映射转换。
- **localStorage 迁移**：前端首次加载时检测 localStorage 标注，提供"导入到云端"按钮；后端不感知迁移逻辑。

---

## 3. Phase 2：合约语义与 K 线归属（核心风险）

**目标**：解决期货业务最核心的问题 — K 线数据必须明确归属到具体合约，否则主力换月后历史数据语义错误。

**周期预估**：7–10 天

### 3.1 任务清单

| 编号 | 任务 | 改动文件 | 说明 | 验收标准 |
|------|------|----------|------|----------|
| P2-1 | 迁移 expand：`kline_data` 增加 `contract_id` nullable | Alembic 迁移 | 只加字段，不改唯一键，不删旧数据 | 旧 API 返回不变 |
| P2-2 | 新增 `contract_rollovers` 表 | `models.py` + 迁移 | 记录主力换月事件 | 含 old/new contract_id + effective_date |
| P2-3 | 回填 `contract_id` | `scripts/backfill_kline_contract_id.py` | 按 `variety.contract_code` + `trading_time` 匹配 `fut_contracts.ts_code` | 生成回填报告，列出未匹配行 |
| P2-4 | 新 K 线写入绑定合约 | `data_collector/pipeline.py`、`upsert.py` | `insert_kline_bulk` 根据 contract_code 查 `fut_contracts.id` 后写入 | 新数据含 contract_id |
| P2-5 | 新增 `contracts.py` 路由 | `routers/contracts.py` | `/api/varieties/{symbol}/contracts`（列表）、`/api/contracts/{id}/kline` | 前端可切换合约 |
| P2-6 | 新增连续 K 线服务 | `services/continuous_kline.py` | 基于 rollover 表拼接多合约 K 线 | 返回点含 `contract_code` 元数据 |
| P2-7 | 连续 K 线 API | `routers/kline.py` 扩展 | `/api/varieties/{symbol}/continuous-kline?period=` | 默认主力断档时自动切下一合约 |
| P2-8 | 主力映射沉淀 rollover | `pipeline.py` `run_fut_mapping` | 检测到 `variety.contract_code` 变化时写 `contract_rollovers` | 测试覆盖 AU2506 → AU2512 |
| P2-9 | 后端测试 | `tests/test_contracts.py`、`test_continuous_kline.py`、`test_kline_contract_binding.py` | 查询、回填、双写、rollover 事件 | pytest 全绿 |
| P2-10 | 迁移演练 | 独立脚本 + 文档 | SQLite 和 PostgreSQL 双环境验证 | `BACKEND_RUNTIME_ISSUES.md` 记录 |

### 3.2 `kline_data` 变更策略（expand → backfill → switch）

```text
Step 1: expand
- kline_data 增加 contract_id (Integer, nullable=True, FK -> fut_contracts.id)
- 新建 contract_rollovers 表

Step 2: backfill
- 脚本按 variety.contract_code + trading_time 范围匹配 fut_contracts
- 无法匹配的行 contract_id 保持 null，报告列出

Step 3: switch（新写入）
- pipeline 采集时先查 fut_contracts.id，再写入 kline_data
- 旧数据查询继续用 variety_id（兼容）

Step 4: contract（未来）
- 前端全部切换到 contract_id 查询后，再考虑将 contract_id 改为 not null
- 旧 variety_id 查询保留适配器，不做删除
```

### 3.3 风险与缓解

| 风险 | 缓解 |
|------|------|
| 回填脚本误匹配合约 | 回填报告必须列出所有未匹配行；人工抽查后再运行 |
| 历史 K 线重复（同一品种同一时间点多条） | backfill 期间先查重，发现重复时暂停并告警 |
| 旧 API 行为改变 | `kline_data` 查询在 contract_id 为 null 时 fallback 到 variety_id 逻辑 |

---

## 4. Phase 3：生产运行边界（数据质量 + 独立 Worker）

**目标**：把采集从"应用内定时任务"升级为可独立运行、可观测、可熔断的生产任务。

**周期预估**：7–10 天

### 4.1 任务清单

| 编号 | 任务 | 改动文件 | 说明 | 验收标准 |
|------|------|----------|------|----------|
| P3-1 | 拆分 worker 入口 | `python/worker.py`（新文件） | 纯 CLI 入口，只启动 scheduler，不启动 FastAPI | `python worker.py` 可独立运行 |
| P3-2 | API 进程禁用 scheduler | `main.py` | `ENABLE_SCHEDULER=0` 时完全不初始化 scheduler；默认值改为 0 | 多实例 API 不会重复采集 |
| P3-3 | 任务状态表扩展 | `models.py` + 迁移 | `data_ingestion_runs` 增加 `duration_ms`、`source`、`window_start`、`window_end`、`error_sample` | `/health/scheduler` 可读 |
| P3-4 | `/health/scheduler` 增强 | `routers/health.py` | 返回最近 N 次任务状态、成功率、最近成功时间 | 前端/运维可消费 |
| P3-5 | 数据源熔断 | `data_collector/pipeline.py` | 连续失败超过阈值（如 5 次/10 分钟）暂停该源并记录状态 | 不连续打爆外部 API |
| P3-6 | 数据质量检查脚本 | `scripts/data_quality_report.py` | 检测缺失日期、重复键、OHLC 异常（high < low）、成交量为负 | 输出 JSON/CSV 报告 |
| P3-7 | 质量检查 API（可选） | `routers/health.py` 或新路由 | `/health/data-quality?symbol=&period=` | 返回最近检查时间和异常摘要 |
| P3-8 | 回填脚本统一入口 | `tushare_pg_ingest/cli.py` | 统一参数校验、dry-run、resume、任务记录 | `python -m tushare_pg_ingest --dry-run` 可用 |
| P3-9 | 手续费/保证金接入品种 API | `routers/varieties.py` 或 `realtime.py` | 从 `fut_trade_fee` 表读取并返回 | 前端可展示真实费率 |
| P3-10 | 后端测试 | `tests/test_scheduler_health.py`、`test_data_quality.py`、`test_circuit_breaker.py` | 熔断、健康检查、质量报告 | pytest 全绿 |

### 4.2 进程边界设计

```text
开发环境：
  python main.py              # API + scheduler（ENABLE_SCHEDULER=1）

生产环境：
  python main.py              # 纯 API（ENABLE_SCHEDULER=0，默认）
  python worker.py            # 纯 scheduler（可部署多个 worker 做分片，当前先做单实例）
```

### 4.3 熔断简单实现

```python
# 建议放在 services/cache.py 或新 services/circuit_breaker.py
# 内存实现即可，Phase 5 再考虑 Redis 持久化
_failure_counts: dict[str, int] = {}
_last_failure_time: dict[str, float] = {}

CIRCUIT_THRESHOLD = 5
CIRCUIT_COOLDOWN_SECONDS = 600

def is_circuit_open(source: str) -> bool:
    if _failure_counts.get(source, 0) >= CIRCUIT_THRESHOLD:
        if time.time() - _last_failure_time.get(source, 0) < CIRCUIT_COOLDOWN_SECONDS:
            return True
        # 冷却结束，重置
        _failure_counts[source] = 0
    return False
```

---

## 5. Phase 4：可观测性与实时推送（后置）

**目标**：在数据语义和生产边界稳定后，补充实时监控和更优的实时行情体验。

**周期预估**：7–10 天
**前置条件**：Phase 1–3 完成且稳定运行 1 周以上。

### 5.1 任务清单

| 编号 | 任务 | 改动文件 | 说明 | 验收标准 |
|------|------|----------|------|----------|
| P4-1 | SSE 实时推送端点 | `routers/realtime.py` 扩展 | `/api/stream/quotes` 返回自选/热门品种行情流 | 前端可接收 |
| P4-2 | Redis Pub/Sub（可选） | worker → Redis → API | worker 更新行情后发布事件；API SSE 端点订阅 | 不依赖进程内广播 |
| P4-3 | Prometheus 指标 | `main.py` middleware + `data_collector/metrics.py` | 请求延迟、错误率、采集成功率、缓存命中 | `/metrics` 可抓 |
| P4-4 | 请求 ID 中间件 | `main.py` | 每个请求生成 `X-Request-ID`，日志可串联 | 日志含 request_id |
| P4-5 | 慢查询日志 | `dependencies.py` 或 SQLAlchemy event | 执行时间超过阈值的 SQL 打印 warning | 可配置阈值 |
| P4-6 | `ACCESS_TOKEN_EXPIRE_MINUTES` 环境变量化 | `config.py` | 当前写死 24h，应从 `.env` 读取 | `.env.example` 同步更新 |

### 5.2 关于 Redis 的说明

当前 `docker-compose.yml` 已包含 Redis，但应用代码未接入。Phase 4 之前：
- 限流、缓存、任务状态、熔断全部用内存实现即可。
- Redis 只在引入 SSE 广播或多实例共享状态时才必须接入，不要提前引入复杂度。

---

## 6. 执行顺序与依赖

```
Phase 1 (工作区闭环)
  ├── P1-1 ~ P1-4: 表 + schema + router（可并行）
  ├── P1-5: 聚合 API（依赖 P1-3/P1-4）
  ├── P1-6: 评论扩展（独立，可与前端并行）
  └── P1-7: 测试（依赖前面全部）

Phase 2 (合约语义)
  ├── P2-1 ~ P2-2: 迁移 expand（必须先做）
  ├── P2-3: 回填（可独立运行，需人工确认报告）
  ├── P2-4: 新写入绑定合约（依赖 P2-1）
  ├── P2-5: contracts API（独立）
  ├── P2-6 ~ P2-7: 连续 K 线（依赖 P2-2/P2-3）
  ├── P2-8: rollover 沉淀（依赖 P2-2）
  └── P2-9 ~ P2-10: 测试与演练（依赖前面全部）

Phase 3 (生产边界)
  ├── P3-1 ~ P3-2: worker 拆分（独立）
  ├── P3-3 ~ P3-4: 任务状态与健康检查（独立）
  ├── P3-5: 熔断（独立）
  ├── P3-6 ~ P3-7: 数据质量（独立）
  ├── P3-8: 回填 CLI（独立）
  └── P3-9 ~ P3-10: 费率 API + 测试（独立）

Phase 4 (可观测性)
  └── 全部后置，按需执行
```

---

## 7. 与既有后端文档的关系

- `BACKEND_ITERATION_PLAN_v7_COMPREHENSIVE.md`：已有许多 P0/P1 已完成（CORS、upsert、生产配置、ORM 缓存等），本计划承接其未完成项。
- `DATA_PIPELINE_AND_POSTGRES_GUIDE.md`：继续作为数据流水线和 PG 运维细节文档；Phase 2/3 的迁移和回填脚本应补充到该文档。
- `TUSHARE_POSTGRES_VERIFICATION.md`：回填验证记录；Phase 2 回填 `contract_id` 后应更新验证范围。

---

## 8. 即刻可启动的任务

如果你现在就想开始，推荐按以下顺序：

1. **今天**：运行 `pytest tests -v` 确认基线全绿；运行 `alembic upgrade head` 确认迁移状态。
2. **第 1 天**：P1-1（`price_levels` 迁移）+ P1-2（schema）。
3. **第 2 天**：P1-3（watchlists router）+ P1-4（price_levels router）。
4. **第 3 天**：P1-5（workspace 聚合）+ P1-6（评论扩展）。
5. **第 4 天**：P1-7（测试）+ P1-8（文档）。
6. **第 5 天**：人工验收前端接入（由前端同步进行）。

Phase 1 完成后，项目即可从"展示型"升级为"用户可沉淀研究数据"的形态。
