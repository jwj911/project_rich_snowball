# 后端迭代方案 —— 支撑前端 FUT-07/08/10 修复

> 目标：为前端 3 个未完成项（涨跌停视觉标识、价格精度、节假日休市提示）提供后端数据支撑
> 技术栈：FastAPI + SQLAlchemy + Alembic
> 预估工期：1.5～2 小时

---

## 一、需求总览

| 前端编号 | 需求 | 需要后端做什么 | 影响面 |
|---|---|---|---|
| FUT-07 | 涨跌停视觉标识 | 实时行情接口返回 `limit_up` / `limit_down` | `RealtimeResponse`、`/api/realtime/*` |
| FUT-08 | 价格精度按品种区分 | `ProductResponse` / `VarietyResponse` 返回 `price_precision` | `ProductResponse`、`VarietyResponse`、品种表 |
| FUT-10 | 节假日/休市提示 | 提供交易日历查询接口或市场状态接口 | 新增表 + 新接口 |

---

## 二、FUT-07：涨跌停价格字段

### 现状分析

- 数据库已有 `fut_price_limits` 表（`FutPriceLimitDB`），存储每日涨跌停价格
- 但 `RealtimeQuoteDB` 没有 `limit_up` / `limit_down` 字段
- `/api/realtime/*` 接口的响应中也不包含涨跌停价

### 方案选择

**推荐方案 A：在实时行情采集时把涨跌停价写入 `RealtimeQuoteDB`**

优点：查询时无需 JOIN，性能最好，前端直接读取。

**备选方案 B：查询时 JOIN `fut_price_limits` 取最新记录**

优点：不改实时行情表结构。缺点：每次查询需要 JOIN，且需确定 "最新" 的 trade_date。

以下按 **方案 A** 给出具体步骤。

### 实施步骤

#### 2.1 模型层修改

文件：`python/models.py`

在 `RealtimeQuoteDB` 中新增两个字段：

```python
class RealtimeQuoteDB(Base):
    __tablename__ = "realtime_quotes"
    # ... 现有字段 ...
    limit_up = Column(Float, nullable=True)    # 涨停价
    limit_down = Column(Float, nullable=True)  # 跌停价
```

#### 2.2 Schema 层修改

文件：`python/schemas.py`

修改 `RealtimeResponse`，增加两个字段：

```python
class RealtimeResponse(BaseModel):
    symbol: str
    current_price: float
    change_percent: float
    open_price: Optional[float]
    high: Optional[float]
    low: Optional[float]
    volume: Optional[int]
    updated_at: dt
    limit_up: Optional[float] = None    # 新增
    limit_down: Optional[float] = None  # 新增
```

同时修改 `ProductResponse`，因为品种详情页也会展示价格：

```python
class ProductResponse(BaseModel):
    id: int
    name: str
    symbol: str
    current_price: float
    change_percent: float
    open_price: Optional[float]
    high: Optional[float]
    low: Optional[float]
    volume: Optional[float]
    category: Optional[str]
    margin: Optional[float]
    commission: Optional[float]
    updated_at: dt
    limit_up: Optional[float] = None    # 新增
    limit_down: Optional[float] = None  # 新增
```

#### 2.3 数据采集层修改

找到写入 `RealtimeQuoteDB` 的代码（通常在 `data_collector/` 或 `services/` 下的行情更新任务），在写入实时行情时同时填充 `limit_up` / `limit_down`：

```python
# 示例：更新实时行情时
limit_record = db.query(FutPriceLimitDB) \
    .filter(FutPriceLimitDB.ts_code == variety.contract_code) \
    .order_by(FutPriceLimitDB.trade_date.desc()) \
    .first()

if limit_record:
    quote.limit_up = limit_record.up_limit
    quote.limit_down = limit_record.down_limit
```

> 如果当前采集任务不更新 `RealtimeQuoteDB`（而是直接 INSERT 新记录），则确保 INSERT 时带上这两个字段。

#### 2.4 Router 层修改

文件：`python/routers/realtime.py`

修改 `_fetch_realtime` 的返回字典，增加两个字段：

```python
def _fetch_realtime(symbol: str, db: Session):
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        return None

    def _fetch():
        q = db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id == variety.id).first()
        if not q:
            return None
        return {
            "symbol": variety.symbol,
            "current_price": q.current_price,
            "change_percent": q.change_percent or 0,
            "open_price": q.open_price,
            "high": q.high,
            "low": q.low,
            "volume": q.volume,
            "updated_at": q.updated_at,
            "limit_up": q.limit_up,      # 新增
            "limit_down": q.limit_down,  # 新增
        }

    return get_cached(f"realtime:{symbol}", _fetch)
```

文件：`python/routers/products.py`

品种列表和详情接口需要把 `ProductDB` 的数据映射到 `ProductResponse`。由于 `ProductDB` 目前没有 `limit_up` / `limit_down`，有以下两种做法：

**做法 1（推荐）**：在 `ProductDB` 中也增加 `limit_up` / `limit_down`，由数据采集任务同步写入。

```python
# models.py ProductDB 新增
limit_up = Column(Float, nullable=True)
limit_down = Column(Float, nullable=True)
```

**做法 2**：在 `get_product` / `get_products` 中 JOIN `RealtimeQuoteDB` 获取。

推荐做法 1，因为品种列表页（`/api/products`）通常返回大量数据，JOIN 会影响性能。

#### 2.5 Alembic 迁移

```bash
cd python && alembic revision -m "add_limit_up_down_to_realtime_and_products"
```

生成的 migration 文件应包含：

```python
op.add_column('realtime_quotes', sa.Column('limit_up', sa.Float(), nullable=True))
op.add_column('realtime_quotes', sa.Column('limit_down', sa.Float(), nullable=True))
op.add_column('products', sa.Column('limit_up', sa.Float(), nullable=True))
op.add_column('products', sa.Column('limit_down', sa.Float(), nullable=True))
```

---

## 三、FUT-08：价格精度字段

### 现状分析

- `VarietyDB` 已有 `tick_size`（最小变动价位），例如 `0.5`、`1`、`0.01`
- 但前端需要 `price_precision`（小数位数）来决定格式化显示
- 例如：`tick_size=0.5` → `precision=1`；`tick_size=1` → `precision=0`

### 方案选择

**推荐方案：在 Schema 层从 `tick_size` 派生 `price_precision`**

无需修改数据库表，只需在 Pydantic schema 中增加计算字段。

### 实施步骤

#### 3.1 Schema 层修改

文件：`python/schemas.py`

修改 `VarietyResponse`，增加 `price_precision`：

```python
from pydantic import computed_field

class VarietyResponse(BaseModel):
    id: int
    symbol: str
    contract_code: str
    name: str
    exchange: str
    category: Optional[str]
    margin_rate: Optional[float]
    commission: Optional[float]
    tick_size: Optional[float] = None  # 如果数据库已有，确保暴露

    @computed_field
    @property
    def price_precision(self) -> int:
        """根据 tick_size 推导价格精度（小数位数）"""
        if not self.tick_size:
            return 2
        tick = self.tick_size
        # 处理 0.5 -> 1, 1 -> 0, 0.01 -> 2, 0.05 -> 2, 5 -> 0
        s = f"{tick:.10f}".rstrip('0')
        if '.' in s:
            return len(s.split('.')[1])
        return 0
```

> 注意：当前 `VarietyResponse` 没有 `tick_size` 字段，如果数据库有但 schema 没暴露，先加上 `tick_size: Optional[float] = None`。

#### 3.2 ProductResponse 也要暴露精度

前端品种列表和详情主要使用 `ProductResponse`，所以 `ProductResponse` 也需要 `price_precision`：

```python
class ProductResponse(BaseModel):
    # ... 现有字段 ...
    price_precision: Optional[int] = 2  # 新增，默认 2 位小数
```

由于 `ProductDB` 没有 `tick_size` 或 `price_precision` 字段，需要：

**做法 1（推荐）**：在 `ProductDB` 中增加 `price_precision` 字段，在初始化/同步时从对应 `VarietyDB.tick_size` 计算写入。

```python
# models.py ProductDB 新增
price_precision = Column(Integer, default=2)
```

**做法 2**：在 `get_products` / `get_product` 中 JOIN `VarietyDB` 计算。

推荐做法 1，避免列表查询时的大量 JOIN。

#### 3.3 Router 层修改

文件：`python/routers/products.py`

如果采用做法 1（`ProductDB` 增加字段），无需修改 router，ORM 自动映射。

如果采用做法 2，需要修改查询逻辑：

```python
from sqlalchemy.orm import joinedload

@router.get("", response_model=List[ProductResponse])
def get_products(...):
    products = db.query(ProductDB).options(joinedload(ProductDB.variety)).offset(skip).limit(limit).all()
    # 需要确保 ProductResponse 能处理 variety 关系
    return products
```

#### 3.4 Alembic 迁移

```bash
cd python && alembic revision -m "add_price_precision_to_products_and_varieties"
```

生成的 migration 文件应包含：

```python
op.add_column('products', sa.Column('price_precision', sa.Integer(), nullable=True, server_default='2'))
# 如果 VarietyDB 没有 tick_size 才需要加：
# op.add_column('varieties', sa.Column('tick_size', sa.Float(), nullable=True))
```

> 执行 migration 后，建议写一个数据修复脚本，遍历所有 `ProductDB` 记录，根据对应 `VarietyDB.tick_size` 回填 `price_precision`。

---

## 四、FUT-10：节假日/休市状态

### 现状分析

- 前端目前硬编码了 2025-2026 年中国期货节假日（`frontend/lib/trading-calendar.ts`）
- 缺点：每年需手动更新，且无法处理临时休市（如台风、突发事件）
- 需要后端提供动态的交易日历或市场状态查询

### 方案选择

**推荐方案：新增 `/api/market/status` 接口**

不修改现有接口的返回结构，通过独立接口提供市场状态，前端在页面加载时调用一次即可。

接口返回：
- 当前日期是否为交易日
- 当前交易时段（日盘/夜盘/休市）
- 如果是非交易日，返回下一交易日的日期

### 实施步骤

#### 4.1 新增数据模型

文件：`python/models.py`

新增交易日历表：

```python
class TradingCalendarDB(Base):
    __tablename__ = "trading_calendar"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(DateTime, nullable=False, index=True)  # 交易日日期（00:00:00）
    is_trading_day = Column(Boolean, default=True, nullable=False)  # 是否交易日
    day_session_start = Column(String(5), default="09:00")  # 日盘开始时间 HH:MM
    day_session_end = Column(String(5), default="15:00")    # 日盘结束时间 HH:MM
    night_session_start = Column(String(5), default="21:00")  # 夜盘开始时间，None 表示无夜盘
    night_session_end = Column(String(5), default="02:30")    # 夜盘结束时间
    exchange = Column(String(10), default="ALL")  # ALL 表示全市场通用，或 SHFE/DCE/CZCE/GFEX/INE/CFFEX
    remark = Column(String(100))  # 节假日名称或休市原因
    created_at = Column(DateTime, default=datetime.datetime.now)

    __table_args__ = (
        UniqueConstraint("trade_date", "exchange", name="uix_calendar_date_exchange"),
    )
```

#### 4.2 新增 Schema

文件：`python/schemas.py`

```python
class TradingCalendarEntry(BaseModel):
    trade_date: dt
    is_trading_day: bool
    day_session_start: str
    day_session_end: str
    night_session_start: Optional[str]
    night_session_end: Optional[str]
    exchange: str
    remark: Optional[str]

class MarketStatusResponse(BaseModel):
    date: str  # 当前日期 yyyy-MM-dd
    is_trading_day: bool
    current_session: str  # "day" | "night" | "closed"
    next_trade_date: Optional[str]
    remark: Optional[str]
```

#### 4.3 新增 Router

新建文件：`python/routers/market.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from models import TradingCalendarDB
from schemas import MarketStatusResponse
from dependencies import get_db

router = APIRouter(prefix="/api/market", tags=["市场状态"])

def _get_session_status(calendar_entry: TradingCalendarDB) -> str:
    """根据当前时间判断交易时段"""
    now = datetime.now()
    time_str = now.strftime("%H:%M")
    
    if not calendar_entry or not calendar_entry.is_trading_day:
        return "closed"
    
    # 日盘判断
    if calendar_entry.day_session_start <= time_str <= calendar_entry.day_session_end:
        return "day"
    
    # 夜盘判断（可能跨天）
    if calendar_entry.night_session_start and calendar_entry.night_session_end:
        night_start = calendar_entry.night_session_start
        night_end = calendar_entry.night_session_end
        
        if night_start < night_end:
            # 不跨天（如 21:00-23:00）
            if night_start <= time_str <= night_end:
                return "night"
        else:
            # 跨天（如 21:00-02:30）
            if time_str >= night_start or time_str <= night_end:
                return "night"
    
    return "closed"

@router.get("/status", response_model=MarketStatusResponse)
def get_market_status(db: Session = Depends(get_db)):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 查询今天的日历记录
    today_entry = db.query(TradingCalendarDB).filter(
        TradingCalendarDB.trade_date == today,
        TradingCalendarDB.exchange == "ALL"
    ).first()
    
    # 如果没数据，默认假设是交易日
    is_trading = today_entry.is_trading_day if today_entry else True
    session = _get_session_status(today_entry) if today_entry else "day"
    remark = today_entry.remark if today_entry else None
    
    # 查询下一交易日
    next_trade = db.query(TradingCalendarDB).filter(
        TradingCalendarDB.trade_date > today,
        TradingCalendarDB.is_trading_day == True,
        TradingCalendarDB.exchange == "ALL"
    ).order_by(TradingCalendarDB.trade_date.asc()).first()
    
    return MarketStatusResponse(
        date=today.strftime("%Y-%m-%d"),
        is_trading_day=is_trading,
        current_session=session,
        next_trade_date=next_trade.trade_date.strftime("%Y-%m-%d") if next_trade else None,
        remark=remark
    )
```

并在 `main.py` 中注册 router：

```python
from routers import market
app.include_router(market.router)
```

#### 4.4 数据初始化脚本

新建文件：`python/scripts/init_trading_calendar.py`

该脚本导入 2025-2026 年中国期货交易日历（前端已有硬编码数据，可移植过来）。

核心逻辑：
1. 生成 2025-01-01 到 2026-12-31 的所有日期
2. 标记周末为非交易日
3. 标记法定节假日为非交易日（元旦、春节、清明、劳动节、端午、中秋、国庆）
4. 插入 `TradingCalendarDB`

运行：
```bash
cd python && python scripts/init_trading_calendar.py
```

#### 4.5 Alembic 迁移

```bash
cd python && alembic revision -m "add_trading_calendar"
```

Migration 内容：

```python
def upgrade():
    op.create_table(
        'trading_calendar',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trade_date', sa.DateTime(), nullable=False),
        sa.Column('is_trading_day', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('day_session_start', sa.String(5), nullable=True, server_default='09:00'),
        sa.Column('day_session_end', sa.String(5), nullable=True, server_default='15:00'),
        sa.Column('night_session_start', sa.String(5), nullable=True, server_default='21:00'),
        sa.Column('night_session_end', sa.String(5), nullable=True, server_default='02:30'),
        sa.Column('exchange', sa.String(10), nullable=True, server_default='ALL'),
        sa.Column('remark', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trade_date', 'exchange', name='uix_calendar_date_exchange')
    )
    op.create_index('idx_trading_calendar_date', 'trading_calendar', ['trade_date'])
```

---

## 五、SEC-02（推荐同期完成）：Token 鉴权改为 httpOnly Cookie

> 此条虽不在 FUT 范畴，但属于安全 P0，且前端已做内存存储过渡，后端改为 Cookie 后可彻底闭环。

### 现状

- `login` 接口返回 JSON：`{"access_token": "...", "token_type": "bearer"}`
- 前端需手动在每次请求 Header 中携带 `Authorization: Bearer <token>`
- SSE `/api/realtime/stream` 被迫通过 URL query param 传 token（EventSource 不支持自定义 header）

### 目标

改为 httpOnly Cookie 鉴权，消除 URL 传 token 的安全隐患。

### 实施步骤

#### 5.1 修改登录接口返回 Cookie

文件：`python/routers/auth.py`

```python
from fastapi import Response

@router.post("/login")
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    # ... 原有验证逻辑 ...
    access_token = create_access_token(data={"sub": str(user.id)})
    
    # 设置 httpOnly Cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,  # 生产环境设为 True（HTTPS）
        samesite="lax",
        max_age=86400,  # 24 小时，与 token 过期时间一致
    )
    
    # 仍然返回 JSON，便于前端首次获取后存内存（过渡兼容）
    return {"access_token": access_token, "token_type": "bearer"}
```

#### 5.2 修改依赖函数读取 Cookie

文件：`python/dependencies.py`

```python
from fastapi import Cookie

def get_current_user_dependency(
    authorization: str = Header(None),
    access_token: str = Cookie(None),  # 新增：读取 Cookie
    db: Session = Depends(get_db)
) -> UserDB:
    # 优先从 Header 读取（兼容旧方式），否则从 Cookie 读取
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    elif access_token:
        token = access_token
    
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    
    user = get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="无效的 token")
    return user
```

#### 5.3 SSE 接口改为读取 Cookie

文件：`python/routers/realtime.py`

```python
from fastapi import Cookie

@router.get("/stream")
def get_realtime_stream(
    symbols: list[str] = Query(default=[]),
    token: str = Query(default=""),
    access_token: str = Cookie(None),  # 新增
):
    effective_token = token or access_token
    if not effective_token:
        raise HTTPException(status_code=401, detail="未登录")
    return StreamingResponse(
        _sse_realtime_generator(symbols, effective_token),
        media_type="text/event-stream",
        headers={...}
    )
```

> 前端已在前序迭代中移除了 SSE URL 中的 `token` query param，改为 Cookie 后 SSE 连接无需再传任何鉴权参数，浏览器会自动携带 Cookie。

---

## 六、前端对接说明

后端完成上述修改后，前端只需做以下调整（约 1 小时）：

### FUT-07

1. `frontend/lib/api/types.ts` — `Product` / `RealtimeQuote` 接口增加：
   ```typescript
   limit_up: number | null
   limit_down: number | null
   ```
2. `QuoteMetric` / `QuoteCard` 组件中增加涨停/跌停标签渲染

### FUT-08

1. `frontend/lib/api/types.ts` — `Product` / `Variety` 接口增加：
   ```typescript
   price_precision: number
   ```
2. `frontend/lib/format.ts` — `formatPrice(value, precision?)` 函数
3. 所有价格显示处改为 `formatPrice(price, product.price_precision)`

### FUT-10

1. 新增 API 调用：
   ```typescript
   async getMarketStatus(): Promise<MarketStatusResponse> {
     return this.request('/api/market/status')
   }
   ```
2. `RealtimeStatusBar` 组件中调用该接口，非交易日显示提示条
3. 可删除 `frontend/lib/trading-calendar.ts` 中的硬编码节假日（或保留作为 fallback）

---

## 七、执行 checklist

按以下顺序执行，避免遗漏依赖：

### Step 1：数据库迁移（30 分钟）
- [ ] `alembic revision` 生成 3 个 migration 文件
- [ ] `alembic upgrade head` 执行迁移
- [ ] 验证表结构正确

### Step 2：模型 + Schema 修改（20 分钟）
- [ ] `models.py`：RealTimeQuoteDB 加 limit_up/down；ProductDB 加 limit_up/down + price_precision；新增 TradingCalendarDB
- [ ] `schemas.py`：修改 RealtimeResponse / ProductResponse / VarietyResponse / 新增 MarketStatusResponse

### Step 3：Router 修改（20 分钟）
- [ ] `realtime.py`：`_fetch_realtime` 返回新增字段
- [ ] `products.py`：确保 ProductResponse 能正确序列化新增字段
- [ ] 新建 `market.py`：交易日历状态接口
- [ ] `main.py`：注册 market router

### Step 4：数据采集任务修改（20 分钟）
- [ ] 找到写入 RealtimeQuoteDB 的代码，增加 limit_up/down 写入逻辑
- [ ] 找到写入 ProductDB 的代码，增加 price_precision 写入逻辑（或从 VarietyDB 同步）

### Step 5：数据初始化（10 分钟）
- [ ] 运行 `init_trading_calendar.py` 导入 2025-2026 交易日历
- [ ] 检查 `RealtimeQuoteDB` / `ProductDB` 的 limit 和 precision 字段是否已回填

### Step 6：SEC-02 Cookie 鉴权（可选，20 分钟）
- [ ] 修改 `auth.py` login 返回 Set-Cookie
- [ ] 修改 `dependencies.py` 读取 Cookie
- [ ] 修改 `realtime.py` SSE 接口读取 Cookie

---

## 八、API 变更汇总

| 接口 | 变更 |
|---|---|
| `GET /api/products` | `ProductResponse` 增加 `limit_up`、`limit_down`、`price_precision` |
| `GET /api/products/{id}` | 同上 |
| `GET /api/realtime/{symbol}` | `RealtimeResponse` 增加 `limit_up`、`limit_down` |
| `GET /api/realtime/batch` | 同上 |
| `GET /api/realtime/stream` | SSE 返回数据增加 `limit_up`、`limit_down`；支持 Cookie 鉴权 |
| `GET /api/varieties/{symbol}` | `VarietyResponse` 增加 `price_precision` |
| **新增** `GET /api/market/status` | 返回市场整体状态 |
| `POST /api/auth/login` | 增加 `Set-Cookie: access_token=...; HttpOnly` |

---

> 后端完成上述修改后，告知前端，前端可在 1 小时内完成对接并关闭 FUT-07/08/10。
