# 后端功能开发路线图

> 基于 OpenAlice 功能映射与当前代码库差距分析制定。
> 原则：**质量是底线，简洁清晰，如无必要勿增实体。**
> 制定日期：2026-05-31

---

## 一、当前已实现功能清单（COMPLETE）

| 模块 | 后端文件 | 端点 | 状态 |
|------|----------|------|------|
| **认证 Auth** | `routers/auth.py`, `models.py` UserDB/RefreshTokenDB | register/login/refresh/logout/me | ✅ 完整 |
| **用户设置 Settings** | `routers/settings.py`, `models.py` UserPreferenceDB | GET/PUT /api/settings | ✅ 完整 |
| **前端监控 Logs** | `routers/frontend_logs.py`, `models.py` FrontendLogDB | POST/GET /api/log/frontend | ✅ 完整 |
| **新闻资讯 News** | `routers/news.py`, `services/news_fetcher.py`, `models.py` NewsSourceDB/NewsArticleDB | sources/articles/fetch CRUD | ✅ 完整 |
| **行情市场 Market** | `routers/market.py`, `routers/realtime.py`, `routers/varieties.py` | hot/leading/status/batch/SSE | ✅ 完整 |
| **K线 Charts** | `routers/kline.py`, `services/continuous_kline.py` | variety/continuous/main/contract kline | ✅ 完整 |
| **评论 Comments** | `routers/comments.py`, `services/domain/comment_service.py` | POST/GET /api/comments | ✅ 完整 |
| **价位标注 Price Levels** | `routers/price_levels.py`, `services/domain/price_level_service.py` | CRUD + batch | ✅ 完整 |
| **自选 Watchlists** | `routers/watchlists.py`, `services/domain/watchlist_service.py` | CRUD | ✅ 完整 |
| **工作区 Workspace** | `routers/workspace.py`, `services/domain/workspace_service.py` | GET /api/workspace/me | ✅ 完整 |
| **合约 Contracts** | `routers/contracts.py` | list/detail/kline/rollovers | ✅ 完整 |
| **Admin 监控** | `routers/metrics_dashboard.py`, `services/metrics.py` | /metrics/dashboard + Prometheus | ✅ 完整 |
| **健康检查** | `routers/health.py` | /health/ready/live/scheduler | ✅ 完整 |
| **数据采集** | `data_collector/scheduler.py`, `data_collector/pipeline.py` | realtime/kline/variety/Tushare扩展 | ✅ 完整 |

---

## 二、OpenAlice 功能映射与差距分析

### 2.1 映射总表

| OpenAlice 模块 | 对应后端能力 | 当前状态 | 差距说明 |
|----------------|-------------|----------|----------|
| **Chat** | 无 | ❌ 未开始 | 实时聊天/私信，需 WebSocket |
| **Portfolio** | 无 | ❌ 未开始 | 投资组合/持仓管理，需交易记录模型 |
| **Market** | Market + Realtime + Varieties | ✅ 已完成 | 功能对齐 |
| **News** | NewsSourceDB + NewsArticleDB | ✅ 已完成 | 功能对齐 |
| **Diary** | OpinionDB + Router + Frontend | ✅ 已完成 | 后端 CRUD + 前端页面 + 品种联动 |
| **Automation** | 无 | ❌ 未开始 | 事件流工作流引擎，复杂度高 |
| **MarketData** | Kline + Realtime | ✅ 已完成 | 功能对齐 |
| **NewsCollector** | News admin fetch API + scheduler | ✅ 已完成 | 手动触发 + 每30分钟自动抓取 |
| **Connectors** | 无 | ❌ 未开始 | 交易所API连接，偏离社区定位 |
| **Trading** | 无 | ❌ 未开始 | 真实交易下单，偏离社区定位 |
| **AIProvider** | 无 | ❌ 未开始 | 大模型接入，成本高 |
| **Logs** | FrontendLogDB | ✅ 已完成 | 功能对齐 |
| **Settings** | UserPreferenceDB | ✅ 已完成 | 功能对齐 |
| **Dev** | 无 | ❌ 未开始 | 开发者工具，非核心 |

### 2.2 关键发现

1. **`OpinionDB` 是隐藏资产**：`models.py` 中已存在 `opinions` 表（user_id/variety_id/type/reason/target_price/stop_loss），但**无任何路由、Schema、Service、API**。字段设计恰好匹配"交易观点/日记"需求，是零成本起步点。

2. **`WatchlistDB.is_notified` 是半成资产**：自选表有 `is_notified` 布尔字段和 `notification_price` 存储，但**无任何触发机制或通知投递逻辑**。

3. **News 缺定时调度**：当前新闻抓取只有 admin 手动触发（`POST /api/news/fetch`），未注册到 APScheduler。

---

## 三、推荐开发路线（按优先级排序）

### Phase 2（当前）：功能填充（低风险、高价值）

| 优先级 | 功能 | 理由 | 技术路径 | 预估工作量 |
|--------|------|------|----------|-----------|
| **P0** | **Opinions（交易观点/日记）** | `OpinionDB` 模型已存在，零迁移成本；与品种深度绑定，用户粘性高；填补 Diary 差距 | 复用 OpinionDB，补充 Schema + Router + Service，前端可做时间线视图 | 1 天 |
| **P1** | **News 定时抓取** | 已有 fetch 服务，只需注册到 scheduler；让 News 从 admin 玩具变成真正可用 | `data_collector/scheduler.py` 添加 `fetch_news` 任务，每 30min | 0.5 天 |
| **P2** | **Price Alert（价格预警）** | `WatchlistDB` 已有通知字段；与现有行情轮询结合即可实现 | 扩展 scheduler 的 realtime 任务：检查 watchlist 价格 crossing，写通知表 | 1-2 天 |

### Phase 3（未来）：可选扩展（评估后启动）

| 优先级 | 功能 | 理由 | 前置条件 |
|--------|------|------|----------|
| P3 | **Chat（评论实时化）** | 评论变实时聊天，需 WebSocket | SSE 已统一，可复用但需改数据模型 |
| P4 | **Portfolio（模拟持仓）** | ✅ 已完成 | 新表 trade_records，支持 Opinion 关联，盈亏自动计算 |
| P5 | **NewsCollector 增强** | RSS 源自动发现、内容摘要 AI 化 | 需外部 AI 服务，成本高 |

### 明确不做（偏离产品定位）

| 功能 | 不做理由 |
|------|----------|
| **Trading / Connectors** | 连接真实交易所进行交易执行，合规风险高，超出"交流社区"边界 |
| **Automation 工作流引擎** | 事件流图、Cron 编排复杂度极高，与社区核心无关 |
| **AI Provider** | 大模型接入成本高，且已有行情/评论/观点足够支撑用户决策 |

---

## 四、P0: Opinions（交易观点/日记）技术实现路径

### 4.1 数据库模型（已存在，无需迁移）

```python
# models.py — OpinionDB（已存在）
class OpinionDB(Base):
    __tablename__ = "opinions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(10), nullable=False)          # "long" | "short" | "neutral"
    reason = Column(Text)                               # 观点理由/日记内容
    target_price = Column(Numeric(15, 4))              # 目标价
    stop_loss = Column(Numeric(15, 4))                 # 止损价
    created_at = Column(DateTime(timezone=True), default=_utc_now)
```

**需要新增的字段**（Alembic 迁移）：
- `status`: `String(20)` — `"open" | "closed_profit" | "closed_loss" | "expired"`，默认 `"open"`
- `closed_at`: `DateTime(timezone=True), nullable=True` — 观点关闭时间
- `actual_outcome`: `String(20), nullable=True` — `"profit" | "loss" | "breakeven"`，用于复盘

### 4.2 Schema 设计

```python
class OpinionCreate(BaseModel):
    variety_id: int
    type: Literal["long", "short", "neutral"]
    reason: str = Field(..., max_length=2000)
    target_price: Decimal | None
    stop_loss: Decimal | None

class OpinionUpdate(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
    target_price: Decimal | None
    stop_loss: Decimal | None
    status: Literal["open", "closed_profit", "closed_loss", "expired"] | None
    actual_outcome: Literal["profit", "loss", "breakeven"] | None

class OpinionResponse(BaseModel):
    id: int
    user_id: int
    variety_id: int
    variety_symbol: str          # joinedload 预加载
    variety_name: str
    type: str
    reason: str | None
    target_price: Decimal | None
    stop_loss: Decimal | None
    status: str
    actual_outcome: str | None
    created_at: datetime
    closed_at: datetime | None
```

### 4.3 API 设计

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/opinions` | 登录用户 | 查询观点列表（支持 variety_id 筛选、status 筛选、分页） |
| GET | `/api/opinions/me` | 登录用户 | 当前用户的观点时间线 |
| POST | `/api/opinions` | 登录用户 | 创建观点 |
| PUT | `/api/opinions/{id}` | 登录用户 | 更新观点（仅 owner） |
| DELETE | `/api/opinions/{id}` | 登录用户 | 删除观点（仅 owner） |
| GET | `/api/opinions/{id}` | 登录用户 | 单条观点详情 |

### 4.4 与现有系统的复用点

- **用户隔离**：复用 `get_current_user_dependency`
- **品种关联**：复用 `VarietyDB`，`joinedload` 预加载 symbol/name
- **XSS 过滤**：复用 `html.escape()` + Pydantic validator（同 Comments）
- **ServiceError**：复用 `ServiceError` / `NotFoundError` / `ForbiddenError`
- **N+1 防护**：`joinedload(OpinionDB.user)` + `joinedload(OpinionDB.variety)`

### 4.5 前端映射（对应 OpenAlice Diary）

| OpenAlice Diary | 本系统实现 |
|-----------------|-----------|
| 时间线流 | `/api/opinions/me` 按 created_at 倒序 |
| 标签/分类 | `type` 字段（long/short/neutral） |
| 内容条目 | `reason` 字段 |
| 右侧洞察面板 | 可扩展：统计用户胜率、平均收益等（未来） |

---

## 五、P1: News 定时抓取技术实现路径

### 5.1 改动点

在 `python/data_collector/scheduler.py` 中注册新任务：

```python
from services.news_fetcher import fetch_all_enabled_sources

# 每 30 分钟抓取一次（仅在交易时段）
scheduler.add_job(
    _fetch_news_task,
    "cron",
    minute="0,30",
    id="fetch_news",
    replace_existing=True,
)

def _fetch_news_task():
    from dependencies import get_db
    db = next(get_db())
    try:
        fetch_all_enabled_sources(db)
    finally:
        db.close()
```

**注意**：需要处理 `get_db()` 在 scheduler 线程中的使用（现有 scheduler 已有类似模式）。

---

## 六、P2: Price Alert（价格预警）技术实现路径

### 6.1 数据库模型（利用现有字段）

`WatchlistDB` 已有：
- `notification_price: Numeric(15, 4), nullable=True`
- `is_notified: Boolean, default=False`

**新增表**：`PriceAlertDB`（更通用，不绑定自选）

```python
class PriceAlertDB(Base):
    __tablename__ = "price_alerts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    variety_id = Column(Integer, ForeignKey("varieties.id", ondelete="CASCADE"), nullable=False)
    alert_type = Column(String(10), nullable=False)   # "above" | "below"
    target_price = Column(Numeric(15, 4), nullable=False)
    is_triggered = Column(Boolean, default=False)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
```

### 6.2 触发逻辑

在 `data_collector/scheduler.py` 的 `refresh_realtime_quotes` 任务后，增加：

```python
# 检查所有未触发的预警
alerts = db.query(PriceAlertDB).filter(PriceAlertDB.is_triggered.is_(False)).all()
for alert in alerts:
    quote = db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == alert.variety_id).first()
    if not quote:
        continue
    current = quote.close or quote.pre_settlement
    if alert.alert_type == "above" and current >= alert.target_price:
        trigger_alert(alert, current)
    elif alert.alert_type == "below" and current <= alert.target_price:
        trigger_alert(alert, current)
```

### 6.3 通知投递（MVP）

- **V1（当前）**：仅写入 `PriceAlertDB.triggered_at`，前端轮询 `GET /api/alerts` 查询已触发预警
- **V2（未来）**：接入 WebSocket/SSE 推送，或接入第三方推送服务（邮件/短信）

---

## 七、执行记录

| 日期 | 完成项 | 状态 |
|------|--------|------|
| 2026-05-31 | Phase 1 完成：Settings + Logs + News 后端全部闭环 | ✅ |
| 2026-05-31 | 差距分析完成：OpenAlice 14 模块映射，确认 4 个已完成、2 个部分完成、8 个未开始 | ✅ |
| 2026-06-01 | Phase 2 P0：Opinions（交易观点/日记）后端实现 | ✅ |
| | 复用 `OpinionDB` 模型，新增 status/closed_at/actual_outcome 字段 + Alembic 迁移 `03748a4fc2a5` | ✅ |
| | 新增 `OpinionCreate`/`OpinionUpdate`/`OpinionResponse` schemas + 字段校验（long/short/neutral，status 流转） | ✅ |
| | 新增 `routers/opinions.py`：GET list/me/detail + POST + PUT（关闭自动记录 closed_at）+ DELETE | ✅ |
| | 新增 `test_opinions.py`：21 个测试覆盖鉴权/CRUD/筛选/状态流转/权限隔离 | ✅ |
| | **Opinions 后端闭环，前端可开始消费** | ✅ |
| 2026-06-01 | Phase 2 P1：News 定时抓取注册到 scheduler | ✅ |
| | `sync_news()` 添加到 `scheduler.py`，30 分钟间隔 IntervalTrigger | ✅ |
| | `job_registry.py` 注册 news job，`build_job_configs` 新增 `sync_news_func` | ✅ |
| 2026-06-01 | Phase 2 P0 前端：Opinions 交易观点页面 (`/opinions`) | ✅ |
| | 双标签页（全部观点 + 我的观点）+ 筛选 + 创建/编辑/关闭/删除 | ✅ |
| | `CreateOpinionModal` 提取为可复用组件 | ✅ |
| 2026-06-01 | Phase 2 P0 前端：Opinions-Product 品种联动 | ✅ |
| | 品种详情页右侧 aside 显示当前品种最近观点 + 一键创建（自动锁定品种） | ✅ |
| 2026-06-01 | Phase 2 P2：Price Alert 价格预警完整实现 | ✅ |
| | `PriceAlertDB` 模型 + Alembic 迁移 + Schema + Router + 15 tests | ✅ |
| | Scheduler 集成：实时行情刷新后自动检查并触发预警 | ✅ |
| | 前端品种详情页预警面板（创建/列表/删除） | ✅ |
| 2026-06-01 | Phase 3 P4：Portfolio 模拟持仓完整实现 | ✅ |
| | `TradeRecordDB` 模型 + Alembic 迁移 + Schema + Router + 15 tests | ✅ |
| | 盈亏计算：支持 long/short，使用 variety.multiplier | ✅ |
| | 前端 `/portfolio` 页面：统计面板 + 筛选 + 创建/平仓/删除 | ✅ |

---

## 八、文档索引

- `BACKEND_API_REFERENCE_FOR_FRONTEND.md` — 前端对接用的完整 API 参考
- `AGENTS.md` — 面向 AI 编程助手的权威上下文（含当前迭代状态）
- `BACKEND_ROADMAP_v2_20260529.md` — 后端迭代路线图 v2
- `DATA_PIPELINE_AND_POSTGRES_GUIDE.md` — PostgreSQL 与数据流水线运维
