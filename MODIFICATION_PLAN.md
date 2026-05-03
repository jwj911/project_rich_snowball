# 期货交流社区 — 修改建议文档（迭代版）

> 基于两次全量代码审查（初版审查 + 2026-05-01 深度审查），按 **P0（必须立即修复）→ P1（强烈建议修复）→ P2（优化建议）** 分级。\
> **用户优先级**：安全与功能修复优先，数据层建设其次，架构与体验优化最后。

***

## 一、后端修改建议（python/）

### P0 — 必须立即修复（安全漏洞、崩溃风险、功能完全失效）

#### B-P0-01 硬编码 JWT SECRET\_KEY

- **文件**: `python/main.py:15`
- **问题**: `SECRET_KEY = "your-secret-key-change-in-production"` 直接写在源码中
- **风险**: 任何人拿到源码即可伪造 JWT，冒充任意用户登录、发帖、删数据
- **建议**: 改为从环境变量读取，并提供 `.env.example`

```python
import os
from dotenv import load_dotenv

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
```

依赖追加：`python-dotenv>=1.0.0`

***

#### B-P0-02 SHA256 无盐哈希存储密码

- **文件**: `python/main.py:78-82`
- **问题**: `hashlib.sha256(password.encode()).hexdigest()` 无随机盐，同等明文密码哈希结果永远相同
- **风险**: 数据库泄露后，所有用户密码可被彩虹表/哈希库瞬间反查
- **建议**: 使用 `passlib[bcrypt]`

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
```

依赖追加：`passlib[bcrypt]==1.7.4`

***

#### B-P0-03 数据模型严重分裂（init\_data.py 无法运行）

- **文件**: `python/init_data.py:4`
- **问题**: `from main import Base, FuturesVarietyDB, KlineDataDB, WatchlistDB, CommentDB, OpinionDB`，但 `main.py` 实际只有 `UserDB/ProductDB/CommentDB`，导致 `ImportError`
- **风险**: K 线数据、自选股、观点等核心数据表**完全不存在**；社区沦为只有静态品种卡片+评论的 Demo
- **建议**: 统一模型层，新建 `python/models.py` 补全缺失模型，并修改导入

```python
# python/models.py
class VarietyDB(Base): ...
class KlineDataDB(Base): ...
class WatchlistDB(Base): ...
class OpinionDB(Base): ...

# init_data.py 修改导入
from models import Base, VarietyDB, KlineDataDB, WatchlistDB, CommentDB, OpinionDB
```

***

#### B-P0-04 没有 K 线数据 API

- **文件**: `python/main.py`（全局缺失）
- **问题**: `main.py` 没有任何 K 线相关的 GET/POST 接口；品种详情页 `KlineChart` 永远只能展示基于固定值 450 生成的随机 mock 数据
- **风险**: 社区号称"数据驱动"，但用户看到的 K 线图与真实品种价格**完全脱节**
- **建议**: 新增 `/api/kline/{symbol}` 接口，支持按时间周期（1H/1D/1W）查询；数据库用 `KlineDataDB` 存储 OHLCV

```python
@app.get("/api/kline/{symbol}")
def get_kline(
    symbol: str,
    period: str = Query("1h", regex="^(1m|5m|15m|30m|1h|1d|1w)$"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if not variety:
        raise HTTPException(404, "品种不存在")
    klines = (
        db.query(KlineDataDB)
        .filter(KlineDataDB.variety_id == variety.id, KlineDataDB.period == period)
        .order_by(KlineDataDB.trading_time.desc())
        .limit(limit)
        .all()
    )
    return [{"time": k.trading_time.isoformat(), "open": k.open_price, ...} for k in reversed(klines)]
```

***

#### B-P0-05 品种价格是静态死数据

- **文件**: `python/main.py:270-311`
- **问题**: `init_mock_data()` 一次性写入 `ProductDB` 后，价格字段永远不会更新
- **风险**: 期货价格实时变动，用户每次刷新看到的都是同一组数字，失去社区价值
- **建议**: 增加定时任务（APScheduler / celery beat）或启动时轮询脚本，定期更新价格字段；如接入真实数据源（akshare/tushare），则对接外部 API

***

#### B-P0-06 评论无长度限制与 XSS 过滤缺失

- **文件**: `python/main.py:220-248`, `frontend/app/products/[id]/page.tsx:194`
- **问题**: `CommentCreate` 模型对 `content` 无任何长度校验；后端入库前不做过滤；前端直接 `<p>{comment.content}</p>` 渲染
- **风险**: 用户可写入超大文本撑爆数据库；可注入 `<script>` 执行 XSS 攻击其他用户
- **建议**: 后端加 Pydantic 校验与 HTML 转义

```python
from pydantic import BaseModel, Field, field_validator
import html

class CommentCreate(BaseModel):
    product_id: int
    content: str = Field(..., min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def sanitize_content(cls, v: str) -> str:
        return html.escape(v.strip())
```

***

#### B-P0-07 init\_data.py 全局数据库连接泄漏

- **文件**: `python/init_data.py:7-9`
- **问题**: 模块级创建 `db = SessionLocal()`，全生命周期不关闭；且缺少 `check_same_thread=False`
- **风险**: 进程退出前连接句柄持续占用；多线程访问 SQLite 时触发线程安全错误
- **建议**: 使用上下文管理器

```python
from contextlib import contextmanager

@contextmanager
def get_db_session():
    engine = create_engine(
        "sqlite:///./futures_community.db",
        connect_args={"check_same_thread": False}
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

***

#### B-P0-08 裸 except: 吞掉所有异常

- **文件**: `python/main.py:97-98`
- **问题**: `get_current_user` 中 `except:` 捕获全部异常且不记录，包括 JWT 过期、格式错误、甚至系统信号
- **风险**: 异常被静默吞掉，返回 `None` 导致后续逻辑给出误导性 401；调试时完全无日志可查
- **建议**: 精确捕获并记录

```python
import logging
from jwt.exceptions import PyJWTError

logger = logging.getLogger(__name__)

def get_current_user(token: str, db: Session) -> Optional[UserDB]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return db.query(UserDB).filter(UserDB.id == int(user_id)).first()
    except PyJWTError as e:
        logger.warning(f"JWT decode failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_current_user: {e}")
        return None
```

***

#### B-P0-09 模块级 Base.metadata.create\_all 导入即执行

- **文件**: `python/main.py:59`
- **问题**: `Base.metadata.create_all(bind=engine)` 在模块顶层执行，任何 `import main` 都会触发
- **风险**: 测试时导入主模块会意外修改数据库 schema；生产环境若权限不当可能覆盖已有表
- **建议**: 封装为显式初始化函数

```python
def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    init_mock_data()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

***

### P1 — 强烈建议修复（明显设计缺陷、性能瓶颈、错误处理缺失）

#### B-P1-01 所有代码堆砌在 main.py 单文件

- **文件**: `python/main.py`（316 行）
- **问题**: 模型、Schema、依赖、路由全部耦合在一起，无法单元测试、无法团队协作
- **建议**: 拆分为标准 FastAPI 项目结构

```
python/
├── models.py       # SQLAlchemy ORM
├── schemas.py      # Pydantic DTO
├── dependencies.py # get_db, get_current_user
├── routers/
│   ├── auth.py
│   ├── products.py
│   └── comments.py
└── main.py         # app = FastAPI() + include_router
```

***

#### B-P1-02 API 列表接口全量返回，无分页

- **文件**: `python/main.py:191-194`, `250-268`
- **问题**: `db.query(ProductDB).all()` 与 `db.query(CommentDB)...all()` 在数据增长后会拖垮内存与网络
- **建议**: 增加分页参数

```python
from fastapi import Query

@app.get("/api/products", response_model=List[ProductResponse])
def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    return db.query(ProductDB).offset(skip).limit(limit).all()
```

***

#### B-P1-03 CORS 配置过度开放

- **文件**: `python/main.py:63-69`
- **问题**: `allow_methods=["*"]`, `allow_headers=["*"]` 配合 localhost origin，若部署到公网会被恶意网站跨域调用
- **建议**: 生产环境收紧到实际域名

```python
import os

origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
```

***

#### B-P1-04 用户注册无密码强度与邮箱格式校验

- **文件**: `python/main.py:100-103`
- **问题**: `UserCreate` 仅声明类型，无长度/格式/强度限制
- **建议**: 增加 Pydantic v2 校验器

```python
from pydantic import BaseModel, Field, EmailStr, field_validator

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("密码必须包含至少一个数字")
        if not any(c.isalpha() for c in v):
            raise ValueError("密码必须包含至少一个字母")
        return v
```

***

#### B-P1-05 数据库连接缺少连接池配置

- **文件**: `python/main.py:19`
- **问题**: `create_engine(DATABASE_URL, connect_args={...})` 无 pool 参数
- **建议**: 增加连接池配置

```python
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True,
)
```

***

#### B-P1-06 SQLite 无迁移机制

- **文件**: `python/main.py:59`
- **问题**: 依赖 `create_all()` 自动建表，后续字段变更容易导致数据丢失
- **建议**: 引入 Alembic

```bash
pip install alembic
alembic init alembic
# 配置 alembic.ini 指向 models 的 Base.metadata
```

***

#### B-P1-07 缺少日志配置

- **文件**: `python/main.py`（全局缺失）
- **问题**: 无结构化日志，异常全靠 print
- **建议**: 增加 `logging` 配置，区分 access log 与 app log

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")
```

***

#### B-P1-08 缺少分类/搜索接口

- **文件**: `python/main.py:191-194`
- **问题**: 有 `category` 字段，但无按分类筛选或按名称搜索的 API
- **建议**: 新增查询参数支持

```python
@app.get("/api/products", response_model=List[ProductResponse])
def get_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(ProductDB)
    if category:
        q = q.filter(ProductDB.category == category)
    if search:
        q = q.filter(ProductDB.name.contains(search))
    return q.all()
```

***

### P2 — 优化建议（命名、注释、可读性、轻微性能）

#### B-P2-01 导入语句放在文件中部

- **文件**: `python/main.py:179`
- **问题**: `from fastapi import Header` 出现在路由定义中间，违反 PEP8
- **建议**: 所有 import 集中到文件顶部

***

#### B-P2-02 Pydantic 模型缺少 Field 约束

- **文件**: `python/main.py:115-128`
- **问题**: `ProductResponse` 等模型只声明类型，无 `Field(gt=0)` 等范围校验
- **建议**: 对价格、百分比等字段加约束

```python
class ProductResponse(BaseModel):
    id: int
    current_price: float = Field(..., gt=0)
    change_percent: float = Field(..., ge=-20, le=20)
    ...
```

***

#### B-P2-03 init\_mock\_data 硬编码测试账号弱密码

- **文件**: `python/main.py:290-294`
- **问题**: 初始化脚本创建 `trader001` / `password123` 等账号
- **建议**: 仅在 `DEBUG=True` 环境下初始化测试数据

```python
if __name__ == "__main__":
    init_db()
    if os.getenv("ENV", "dev") == "dev":
        init_mock_data()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

***

## 二、前端修改建议（frontend/）

### P0 — 必须立即修复（构建失败、功能完全失效、安全漏洞）

#### F-P0-01 Navbar 组件被传入未定义 props（TypeScript 构建失败）

- **文件**: `frontend/app/products/[id]/page.tsx:105,129`
- **问题**: `<Navbar user={user} onLogout={() => {}} setUser={setUser} />`，但 `Navbar.tsx:9` 定义 `export default function Navbar()` **不接受任何 props**
- **风险**: `next build` 时 TypeScript 编译报错；开发模式下类型系统已失效
- **建议**: 移除非法 props，保持与组件签名一致

```tsx
// frontend/app/products/[id]/page.tsx
<Navbar />
```

如需共享用户状态，应使用 React Context / Zustand，而非通过 props 强塞。

***

#### F-P0-02 KlineChart 组件 props 更新不响应（数据永远锁定 mock）

- **文件**: `frontend/components/KlineChart.tsx:62`
- **问题**: `const [data] = useState<KlineData[]>(() => externalData.length > 0 ? externalData : generateMockKline(450, 80))` 只读 state 不随 props 变化
- **风险**: 即使父组件后续传入真实 K 线数据，图表仍展示 mock 随机数据，属于严重数据绑定 bug
- **建议**: 改用 `useMemo` 响应 props

```typescript
const data = useMemo<KlineData[]>(() => {
    return externalData.length > 0 ? externalData : generateMockKline(450, 80)
}, [externalData])
```

***

#### F-P0-03 K 线图硬编码空数据且与品种价格脱节

- **文件**: `frontend/app/products/[id]/page.tsx:151`
- **问题**: `data={[]}` 传给 `KlineChart`，导致内部 fallback 到基于固定值 450 的随机数据，与品种无关
- **风险**: 用户看到的 K 线图与真实品种价格完全无关
- **建议**: 改为从后端 `/api/kline/{symbol}` 获取真实数据；在 API 未就绪前，可先用品种 `current_price` 作为 base 生成 mock

```typescript
const [klineData, setKlineData] = useState<KlineData[]>([])

useEffect(() => {
    if (product?.symbol) {
        api.getKline(product.symbol, '1h').then(setKlineData)
            .catch(() => setKlineData(generateMockKline(product.current_price || 450, 80)))
    }
}, [product?.symbol])

// 传入真实数据
<KlineChart data={klineData} symbol={product.symbol} ... />
```

***

#### F-P0-04 API 基地址硬编码 localhost

- **文件**: `frontend/lib/api.ts:1`
- **问题**: `const API_BASE = 'http://localhost:8000'`
- **风险**: 部署到测试/生产环境后前端无法连接后端
- **建议**: 使用环境变量

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'
```

***

#### F-P0-05 评论内容直接渲染无转义（XSS 风险）

- **文件**: `frontend/app/products/[id]/page.tsx:194`
- **问题**: `<p className="text-sm text-gray-300">{comment.content}</p>` 直接渲染用户输入
- **风险**: 虽然 React 默认转义文本节点，但不应依赖前端做安全；后端已转义则此处安全，需确保前后端双重保障
- **建议**: 确保后端已做 HTML escape（见 B-P0-06），前端保持文本渲染即可

***

### P1 — 强烈建议修复（明显设计缺陷、性能瓶颈、错误处理缺失）

#### F-P1-01 全客户端渲染，无 SSR

- **文件**: `frontend/app/page.tsx`, `frontend/app/products/page.tsx`, `frontend/app/products/[id]/page.tsx`, `frontend/app/my-comments/page.tsx`
- **问题**: 所有页面都是 `'use client'`，Next.js App Router 的 SSR 优势完全未利用
- **风险**: 首屏需要等 JS 加载、fetch 数据后才能渲染，SEO 极差
- **建议**: 列表页、详情页改为 Server Component 预取数据

```typescript
// app/products/page.tsx (Server Component)
import { api } from '@/lib/server-api'

export default async function ProductsPage() {
    const products = await api.getProducts()
    return <ProductsClient initialData={products} />
}
```

***

#### F-P1-02 API 错误对用户不可见（静默吞异常）

- **文件**: `frontend/app/page.tsx:14-18`, `frontend/app/products/page.tsx:15-20`, `frontend/app/products/[id]/page.tsx:25-35`
- **问题**: `.catch(() => setLoading(false))` 或 `console.error`，用户看不到失败原因
- **建议**: 增加错误状态并渲染提示

```typescript
const [error, setError] = useState<string | null>(null)

useEffect(() => {
    api.getProducts()
        .then(data => { setProducts(data); setLoading(false) })
        .catch((err) => { setError(err.message); setLoading(false) })
}, [])

if (error) return <div className="text-red-400">加载失败: {error}</div>
```

***

#### F-P1-03 fetch 无超时控制，可能永久挂起

- **文件**: `frontend/lib/api.ts:65-87`
- **问题**: `fetch` 默认无超时；网络抖动时页面会无限等待
- **建议**: 封装带超时的 fetch

```typescript
private async request<T>(url: string, options: RequestInit = {}): Promise<T> {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 10000)

    try {
        const response = await fetch(`${API_BASE}${url}`, {
            ...options,
            signal: controller.signal,
            headers: { 'Content-Type': 'application/json', ...options.headers },
        })
        clearTimeout(timeoutId)
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }))
            throw new Error(error.detail || 'Request failed')
        }
        return response.json()
    } catch (err) {
        clearTimeout(timeoutId)
        throw err
    }
}
```

***

#### F-P1-04 login 方法未复用 request 封装

- **文件**: `frontend/lib/api.ts:89-110`
- **问题**: `login` 手写 `fetch`、错误处理、JSON 解析，与第 65-87 行的 `request` 方法逻辑 80% 重复
- **建议**: 让 `login` 复用底层 `request`

```typescript
async login(username: string, password: string): Promise<{ access_token: string }> {
    const formData = new URLSearchParams()
    formData.append('username', username)
    formData.append('password', password)

    const data = await this.request<{ access_token: string }>('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData,
    })
    this.setToken(data.access_token)
    return data
}
```

***

#### F-P1-05 KlineChart 渲染循环中存在 O(n²) 重复计算

- **文件**: `frontend/components/KlineChart.tsx:208-217`
- **问题**: `data.map(...)` 内部每次迭代都执行 `Math.max(...data.map(d => d.volume))`
- **建议**: 提取到 map 外部

```typescript
const maxVol = useMemo(() => Math.max(...data.map(d => d.volume)), [data])

{data.map((candle, i) => {
    const h = (candle.volume / maxVol) * (volumeHeight - 20)
    return <rect key={`v-${i}`} x={x} y={height + volumeHeight - h} width={candleWidth} height={h} fill={color} opacity="0.4" rx="2" />
})}
```

***

#### F-P1-06 params.id 无合法性校验

- **文件**: `frontend/app/products/[id]/page.tsx:11,28`
- **问题**: `const { id } = params` 后直接 `parseInt(id)`，若传入非数字字符串会得到 `NaN`
- **建议**: 校验后再使用

```typescript
const rawId = params.id
const productId = parseInt(rawId, 10)
if (isNaN(productId) || productId <= 0) {
    return <div className="text-center py-20 text-red-400">无效的ID</div>
}
// 后续使用 productId
```

***

#### F-P1-07 价格不会自动刷新

- **文件**: `frontend/app/page.tsx`, `frontend/app/products/page.tsx`
- **问题**: 页面加载后价格定格，不会轮询更新
- **建议**: 增加轮询机制

```typescript
useEffect(() => {
    const interval = setInterval(() => {
        api.getProducts().then(setProducts).catch(console.error)
    }, 30000)
    return () => clearInterval(interval)
}, [])
```

***

#### F-P1-08 移动端布局可能溢出

- **文件**: `frontend/app/products/[id]/page.tsx:130`
- **问题**: `h-[calc(100vh-60px)]` 等固定高度在小屏上会导致内容被截断
- **建议**: 改用响应式布局

```tsx
<div className="flex flex-col lg:flex-row h-[calc(100vh-60px)]">
```

***

### P2 — 优化建议（命名、注释、可读性、轻微性能）

#### F-P2-01 useState<any> 破坏 TypeScript 类型安全

- **文件**: `frontend/app/products/[id]/page.tsx:15`
- **问题**: `const [user, setUser] = useState<any>(null)`
- **建议**: `const [user, setUser] = useState<User | null>(null)`

***

#### F-P2-02 使用数组索引作为 React key

- **文件**: `frontend/components/KlineChart.tsx:153,164,175,208`
- **问题**: `key={i}`、`key={`s-${i}`}`、`key={`v-${i}`}`，若数据顺序变化会导致 React 复用错误 DOM 节点
- **建议**: 使用时间戳或唯一标识

```typescript
{data.map((candle) => (
    <g key={candle.time}>...</g>
))}
```

***

#### F-P2-03 globals.css 使用 @import 引入外部字体，阻塞渲染

- **文件**: `frontend/app/globals.css:1`
- **问题**: `@import url('https://fonts.googleapis.com/...')` 是同步阻塞的 CSS 导入
- **建议**: 使用 `next/font` 优化

```typescript
// app/layout.tsx
import { JetBrains_Mono } from 'next/font/google'

const jetbrains = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono' })

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return <html lang="zh-CN" className={jetbrains.variable}><body>{children}</body></html>
}
```

***

#### F-P2-04 api.ts URL 拼接未 encodeURIComponent

- **文件**: `frontend/lib/api.ts:138-140`
- **问题**: `` `/api/comments/user/${username}` ``
- **建议**: 对路径参数编码

```typescript
async getUserComments(username: string): Promise<Comment[]> {
    return this.request<Comment[]>(`/api/comments/user/${encodeURIComponent(username)}`)
}
```

***

#### F-P2-05 组件文件过长未拆分

- **文件**: `frontend/components/Navbar.tsx`（255 行含 3 个组件）
- **问题**: Navbar + LoginModal + RegisterModal 全部耦合在一个文件
- **建议**: 拆分为 `components/modals/LoginModal.tsx` 和 `RegisterModal.tsx`

***

#### F-P2-06 loadData 与 checkAuth 串行执行

- **文件**: `frontend/app/products/[id]/page.tsx:25-51`
- **问题**: 两个无依赖关系的异步请求串行，延长首屏时间
- **建议**: 使用 `Promise.all` 并行

```typescript
useEffect(() => {
    const loadData = async () => { ... }
    const checkAuth = async () => { ... }
    Promise.all([loadData(), checkAuth()]).catch(console.error)
}, [id])
```

***

#### F-P2-07 涨跌幅颜色体系混乱

- **文件**: `frontend/app/globals.css:24-25`, `frontend/app/page.tsx:83`, `frontend/app/products/[id]/page.tsx:139`
- **问题**: `globals.css` 定义了 `.up`/`.down`，但部分页面直接混用 `text-red-400` / `text-green-400`
- **建议**: 统一使用 Tailwind 自定义颜色，删除 globals.css 中的硬编码类

```css
/* tailwind.config.js */
module.exports = {
  theme: {
    extend: {
      colors: {
        up: '#ef4444',
        down: '#22c55e',
      },
    },
  },
}
```

***

#### F-P2-08 缺少全局状态管理

- **文件**: `frontend/app/products/[id]/page.tsx`, `frontend/app/my-comments/page.tsx`
- **问题**: 用户登录状态在各页面重复 `api.getMe()` 调用
- **建议**: 可用 React Context 或 Zustand 做全局 auth store

***

#### F-P2-09 手写 SVG K 线图功能简陋

- **文件**: `frontend/components/KlineChart.tsx`
- **问题**: 无缩放、拖拽、技术指标（MA/MACD/KDJ）
- **建议**: 考虑引入 `lightweight-charts` 或 `echarts-for-react`

***

## 三、实施路线图（按优先级重排）

### 第一阶段：安全与功能修复（立即执行，预计 1\~2 天）

> **目标**：消除安全漏洞和功能崩溃风险，确保项目可编译、可运行、数据不泄露。

| 顺序 | 任务                                   | 涉及文件                                          | 优先级 |
| -- | ------------------------------------ | --------------------------------------------- | --- |
| 1  | 硬编码 SECRET\_KEY → 环境变量               | `python/main.py:15`                           | P0  |
| 2  | SHA256 → bcrypt 密码哈希                 | `python/main.py:78-82`                        | P0  |
| 3  | 评论增加长度限制与 XSS 过滤                     | `python/main.py:220-248`                      | P0  |
| 4  | Navbar 移除非法 props 传参                 | `frontend/app/products/[id]/page.tsx:105,129` | P0  |
| 5  | KlineChart 改用 useMemo 响应 props       | `frontend/components/KlineChart.tsx:62`       | P0  |
| 6  | init\_data.py 全局连接改为上下文管理器           | `python/init_data.py:7-9`                     | P0  |
| 7  | 裸 except: 改为精确捕获并记录                  | `python/main.py:97-98`                        | P0  |
| 8  | create\_all 从模块级移到显式初始化函数            | `python/main.py:59`                           | P0  |
| 9  | API\_BASE 改为读取环境变量                   | `frontend/lib/api.ts:1`                       | P0  |
| 10 | K 线图改为从 current\_price 生成 mock（临时方案） | `frontend/app/products/[id]/page.tsx:151`     | P0  |

**验收标准**：

- `next build` 前端编译通过，无 TypeScript 错误
- `python main.py` 后端启动正常，`init_data.py` 可独立运行
- 用户注册/登录/评论流程端到端通顺
- 浏览器控制台无 XSS 相关警告

***

### 第二阶段：数据层与 API 建设（预计 2\~3 天）

> **目标**：统一数据模型，补齐 K 线 API，解决模型分裂和静态数据问题。

| 顺序 | 任务                                                            | 涉及文件                                  | 优先级 |
| -- | ------------------------------------------------------------- | ------------------------------------- | --- |
| 1  | 新建 `models.py` 补全 VarietyDB/KlineDataDB/WatchlistDB/OpinionDB | 新建 `python/models.py`                 | P0  |
| 2  | 重写 `init_data.py` 使其与 models.py 兼容                            | `python/init_data.py`                 | P0  |
| 3  | 新增 `/api/kline/{symbol}` 接口                                   | `python/main.py` 或 `routers/kline.py` | P0  |
| 4  | 接入/模拟动态价格更新机制                                                 | 新建 `python/data_collector/`           | P0  |
| 5  | 后端 API 增加分页                                                   | `python/main.py:191-194,250-268`      | P1  |
| 6  | 增加分类/搜索查询参数                                                   | `python/main.py:191-194`              | P1  |
| 7  | 用户注册增加密码强度与邮箱校验                                               | `python/main.py:100-103`              | P1  |
| 8  | CORS 配置收紧                                                     | `python/main.py:63-69`                | P1  |

**验收标准**：

- `init_data.py` 运行后所有表正确创建并灌入数据
- `/api/kline/{symbol}?period=1h&limit=100` 返回正确 JSON
- 品种价格每 30 秒有变化（哪怕是模拟数据）
- 大数据量下 API 响应时间 < 200ms

***

### 第三阶段：架构拆分与体验优化（预计 3\~5 天）

> **目标**：后端模块化、前端 SSR 化、全局错误处理、性能优化。

| 顺序 | 任务                                              | 涉及文件                                                      | 优先级 |
| -- | ----------------------------------------------- | --------------------------------------------------------- | --- |
| 1  | main.py 拆分为 models/schemas/dependencies/routers | 新建多个文件                                                    | P1  |
| 2  | Alembic 迁移机制                                    | 新建 `alembic/`                                             | P1  |
| 3  | 增加结构化日志配置                                       | `python/main.py`                                          | P1  |
| 4  | 前端增加全局 Toast/Alert 错误提示                         | 新建 `components/Toast.tsx`                                 | P1  |
| 5  | 首页/列表页改为 Server Component                       | `frontend/app/page.tsx`, `frontend/app/products/page.tsx` | P1  |
| 6  | 增加价格自动轮询刷新                                      | `frontend/app/page.tsx`, `frontend/app/products/page.tsx` | P1  |
| 7  | fetch 增加 10s 超时控制                               | `frontend/lib/api.ts:65-87`                               | P1  |
| 8  | KlineChart 提取 maxVol 到 useMemo                  | `frontend/components/KlineChart.tsx:208-217`              | P1  |
| 9  | params.id 增加合法性校验                               | `frontend/app/products/[id]/page.tsx:11,28`               | P1  |
| 10 | 涨跌幅颜色体系统一                                       | `frontend/app/globals.css`, `tailwind.config.js`          | P2  |
| 11 | Navbar 拆分为独立组件                                  | `frontend/components/Navbar.tsx`                          | P2  |
| 12 | K 线图组件升级为 lightweight-charts                    | `frontend/components/KlineChart.tsx`                      | P2  |
| 13 | 引入全局 auth store（Zustand）                        | 新建 `frontend/store/auth.ts`                               | P2  |
| 14 | 使用 next/font 替代 @import                         | `frontend/app/layout.tsx`, `frontend/app/globals.css`     | P2  |

**验收标准**：

- 后端单文件行数 < 100 行（main.py 只做聚合）
- 首页首屏时间（FCP）< 1.5s
- 无内存泄漏（KlineChart 事件监听正确卸载）
- Lighthouse 性能评分 > 80

***

## 四、文件清单

### 后端关键文件

- `python/main.py` — 后端主入口（待拆分）
- `python/init_data.py` — 数据初始化脚本（与主模型不兼容，需重写）
- `python/requirements.txt` — 依赖（待追加 bcrypt/dotenv/apscheduler）
- `python/models.py` — **待新建**，统一 ORM 模型
- `python/routers/` — **待新建**，路由拆分
- `python/dependencies.py` — **待新建**，依赖注入
- `python/schemas.py` — **待新建**，Pydantic DTO

### 前端关键文件

- `frontend/app/page.tsx` — 首页（热门品种列表）
- `frontend/app/products/page.tsx` — 品种列表
- `frontend/app/products/[id]/page.tsx` — 品种详情（含评论、K线）
- `frontend/app/my-comments/page.tsx` — 我的评论
- `frontend/app/layout.tsx` — 根布局
- `frontend/app/globals.css` — 全局样式
- `frontend/components/Navbar.tsx` — 导航栏（待拆分）
- `frontend/components/KlineChart.tsx` — K 线图（数据绑定有 bug）
- `frontend/lib/api.ts` — API 客户端
- `frontend/next.config.js` — Next.js 配置
- `frontend/tailwind.config.js` — Tailwind 配置

***

## 五、Top 10 必须修复清单（速查表）

> 按紧急程度排序，建议按此顺序逐个击破。

| 排序 | 编号      | 问题简述                           | 文件                                        | 类别  |
| -- | ------- | ------------------------------ | ----------------------------------------- | --- |
| 1  | B-P0-01 | 硬编码 SECRET\_KEY，可伪造任意 Token    | `python/main.py:15`                       | 安全  |
| 2  | B-P0-02 | SHA256 无盐哈希，彩虹表秒破              | `python/main.py:78`                       | 安全  |
| 3  | B-P0-03 | init\_data.py 引用不存在模型，无法运行     | `python/init_data.py:4`                   | 功能  |
| 4  | F-P0-02 | KlineChart props 不响应，永远展示 mock | `frontend/components/KlineChart.tsx:62`   | 功能  |
| 5  | F-P0-01 | Navbar 被传入未定义 props，TS 构建失败    | `frontend/app/products/[id]/page.tsx:129` | 功能  |
| 6  | B-P0-06 | 评论无长度限制/XSS 过滤                 | `python/main.py:220`                      | 安全  |
| 7  | B-P0-07 | init\_data.py 全局连接泄漏           | `python/init_data.py:7`                   | 健壮性 |
| 8  | B-P0-08 | 裸 except: 吞掉所有异常               | `python/main.py:97`                       | 健壮性 |
| 9  | B-P0-09 | 模块级 create\_all 导入即执行          | `python/main.py:59`                       | 架构  |
| 10 | F-P0-04 | API\_BASE 硬编码 localhost        | `frontend/lib/api.ts:1`                   | 工程化 |

***

> **总结**：当前项目最紧迫的是 **安全层（密钥、密码哈希、XSS）** 与 **模型层分裂（init\_data.py 无法运行）**。修复 P0 后，按第二阶段补齐数据层 API，再按第三阶段做架构拆分与体验优化。`DATA_PIPELINE_DESIGN.md` 中的数据管道方案可作为第二阶段的技术参考，保持不变。

