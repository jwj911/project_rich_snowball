# Deep Code Review Findings

> Date: 2026-05-03  
> Scope: backend deep review, plus frontend-facing contract risks inferred from API behavior  
> Purpose: prioritized issue backlog for follow-up fixes

---

## Backend

### P0 - Must Fix Immediately

#### 1. Database engine uses SQLite-only options for every database

**File:** `python/models.py:10-17`

**Problem:** `check_same_thread=False` is passed unconditionally through `connect_args`. This is SQLite-specific and will break PostgreSQL connections.

**Risk:** Setting `DATABASE_URL=postgresql://...` can make the service fail at startup.

**Suggested fix:**

```python
engine_kwargs = {"pool_pre_ping": True, "pool_recycle": 3600}

if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_engine(DATABASE_URL, **engine_kwargs)
```

#### 2. Application startup creates fixed-password demo users

**File:** `python/main.py:12-16`, `python/data_collector/init_mock_data.py:25-29`

**Problem:** Startup calls `init_mock_data()`, which creates users with `password123`.

**Risk:** A fresh production database can be initialized with known weak credentials.

**Suggested fix:**

```python
if ENV != "production" and os.getenv("INIT_MOCK_DATA", "false").lower() == "true":
    from data_collector.init_mock_data import init_mock_data
    init_mock_data()
```

#### 3. Scheduler starts automatically inside the web process

**File:** `python/main.py:15-19`, `python/data_collector/scheduler.py:78-85`

**Problem:** Every app process starts the scheduler during FastAPI lifespan.

**Risk:** Multi-worker deployments can run duplicate data collection jobs, causing duplicate writes, DB lock pressure, and inconsistent data.

**Suggested fix:**

```python
if os.getenv("ENABLE_SCHEDULER", "false").lower() == "true":
    from data_collector.scheduler import start_scheduler
    start_scheduler()
```

#### 4. Cache stores SQLAlchemy ORM objects and has no lock

**File:** `python/routers/realtime.py:17-20`, `python/services/cache.py:4-16`

**Problem:** `get_cached()` stores `RealtimeQuoteDB` ORM objects from a request-scoped session. The cache dictionaries are also globally mutable without synchronization.

**Risk:** Stale data, detached ORM instances, thread-safety bugs, and inconsistent cache reads under concurrency.

**Suggested fix:**

```python
def _fetch() -> dict | None:
    quote = db.query(RealtimeQuoteDB).filter(
        RealtimeQuoteDB.variety_id == variety.id
    ).first()
    if not quote:
        return None
    return {
        "symbol": variety.symbol,
        "current_price": quote.current_price,
        "change_percent": quote.change_percent or 0,
        "open_price": quote.open_price,
        "high": quote.high,
        "low": quote.low,
        "volume": quote.volume,
        "updated_at": quote.updated_at,
    }
```

Use a `threading.RLock` around cache reads/writes.

#### 5. Auth endpoints lack rate limiting

**File:** `python/routers/auth.py:12-39`

**Problem:** Register and login endpoints have no request throttling.

**Risk:** Brute-force login, mass registration, and bcrypt CPU exhaustion.

**Suggested fix:** Add `slowapi` or equivalent IP/user-based rate limiting for login and registration.

---

### P1 - Strongly Recommended

#### 6. Scheduler jobs have no re-entry protection

**File:** `python/data_collector/scheduler.py:81-85`

**Problem:** Jobs do not set `max_instances`, `coalesce`, or `misfire_grace_time`.

**Risk:** Long-running jobs can overlap with the next interval and increase write contention.

**Suggested fix:**

```python
scheduler = BackgroundScheduler(job_defaults={
    "max_instances": 1,
    "coalesce": True,
    "misfire_grace_time": 10,
})
```

#### 7. `sync_prices_to_products()` has N+1 queries

**File:** `python/data_collector/scheduler.py:60-70`

**Problem:** It loads all quotes, lazily reads `q.variety`, then queries `ProductDB` once per quote.

**Risk:** Query count grows linearly with quote count and can become slow under more symbols.

**Suggested fix:** Eager-load varieties and batch-load products into a symbol map.

#### 8. `insert_kline_bulk()` queries varieties inside a loop

**File:** `python/data_collector/upsert.py:38-65`

**Problem:** Each row performs its own `VarietyDB` query before batch insert.

**Risk:** Large K-line batches produce many unnecessary DB round trips.

**Suggested fix:** Query all symbols once and build a `symbol -> variety_id` map.

#### 9. Product detail comments have N+1 user loading

**File:** `python/routers/products.py:23-36`

**Problem:** `c.user.username` can trigger one query per comment.

**Risk:** Product detail latency grows with comment count.

**Suggested fix:**

```python
comments = (
    db.query(CommentDB)
    .options(selectinload(CommentDB.user))
    .filter(CommentDB.product_id == product_id)
    .order_by(CommentDB.created_at.desc())
    .limit(100)
    .all()
)
```

#### 10. `/api/products` returns all rows without pagination

**File:** `python/routers/products.py:11-14`

**Problem:** The compatibility product list has no `skip` / `limit`.

**Risk:** Response size and serialization cost grow without bound.

**Suggested fix:** Add `skip` and `limit` query params matching `/api/varieties`.

#### 11. User registration input validation is too weak

**File:** `python/schemas.py:7-10`

**Problem:** `username`, `email`, and `password` are unconstrained strings.

**Risk:** Bad emails, extremely weak passwords, oversized input, and inconsistent usernames.

**Suggested fix:**

```python
from pydantic import EmailStr, Field

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
```

#### 12. Blank comments can pass validation after stripping

**File:** `python/schemas.py:41-48`

**Problem:** `"   "` passes `min_length=1`, then validator strips it to an empty string.

**Risk:** Empty comments can be stored.

**Suggested fix:** Use a `mode="before"` validator and raise on empty stripped content.

#### 13. JWT helper swallows too many exceptions

**File:** `python/dependencies.py:22-34`

**Problem:** `except Exception` catches database errors and programming errors, returning `None`.

**Risk:** Real operational errors are hidden as auth failures.

**Suggested fix:** Catch `PyJWTError` and `ValueError`, but log and re-raise SQLAlchemy errors.

#### 14. OHLC validation is incomplete

**File:** `python/data_collector/cleaner.py:16`, `python/data_collector/cleaner.py:55`

**Problem:** Cleaner only checks `high < low`; it does not enforce `high >= open/close` or `low <= open/close`.

**Risk:** Invalid market bars can enter the database.

**Suggested fix:** Add a shared `_valid_ohlc()` helper and use it for realtime and K-line rows.

#### 15. Akshare K-line collector hardcodes contract month

**File:** `python/data_collector/akshare_collector.py:52-55`

**Problem:** `contract = f"{symbol}2506"` will become stale, and `"1h"` is not mapped in `period_map`.

**Risk:** Data collection silently queries the wrong contract or wrong period.

**Suggested fix:** Resolve active/main contract from DB or config; map `"1h"` to `"60"`.

#### 16. Production docs are always exposed

**File:** `python/main.py:22`

**Problem:** `/docs` and `/redoc` are enabled regardless of environment.

**Risk:** Production API structure is exposed unnecessarily.

**Suggested fix:**

```python
app = FastAPI(
    title="期货交流社区 API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None if ENV == "production" else "/docs",
    redoc_url=None if ENV == "production" else "/redoc",
)
```

#### 17. Tests depend on real app database and fixed seed data

**File:** `python/tests/test_phase1_3_integration.py:20-25`, `python/tests/test_p0_fixes.py:197-254`

**Problem:** Tests import the real `app`, `engine`, and `SessionLocal`, then assume fixed users/products exist.

**Risk:** Tests are order-dependent, environment-dependent, and can pollute development data.

**Suggested fix:** Add `conftest.py` with a temporary SQLite file DB and override `get_db`.

---

### P2 - Optimization

#### 18. Import ordering is inconsistent

**File:** `python/main.py:1-4`

**Problem:** Standard library import `os` appears after third-party imports.

**Suggested fix:** Use PEP8 order: standard library, third-party, local.

#### 19. Return type hints are incomplete

**File:** Multiple, for example `python/routers/auth.py:13`, `python/routers/products.py:12`, `python/data_collector/scheduler.py:16`

**Problem:** Many functions have parameter hints but no return annotations.

**Suggested fix:** Add explicit return types such as `-> UserDB`, `-> list[ProductDB]`, `-> None`.

#### 20. Mock collector mutates global random state

**File:** `python/data_collector/mock_collector.py:16-18`

**Problem:** `random.seed(seed)` changes process-wide RNG state.

**Risk:** Tests or other modules using `random` become coupled to collector initialization.

**Suggested fix:** Use `self._random = random.Random(seed)`.

#### 21. Initialization scripts use `print()`

**File:** `python/data_collector/init_mock_data.py:46`, `python/data_collector/init_varieties.py:40`

**Problem:** Scripts print directly instead of using logging.

**Suggested fix:** Replace with module loggers.

#### 22. `init_varieties.py` creates a separate engine/session factory

**File:** `python/data_collector/init_varieties.py:8-16`

**Problem:** It duplicates data-layer setup instead of using `models.SessionLocal`.

**Suggested fix:** Reuse `SessionLocal` from `models`.

#### 23. `datetime as dt` reduces schema readability

**File:** `python/schemas.py:3`

**Problem:** The alias is unnecessary and less clear.

**Suggested fix:** Import `datetime` directly.

#### 24. Abstract methods use `pass`

**File:** `python/data_collector/base.py:6-19`

**Problem:** Abstract method bodies use `pass`.

**Suggested fix:** Use `...` and more precise nullable return types.

---

## Frontend / Frontend-Facing Contract Risks

> Note: The frontend was not reviewed with the same depth in this pass. These are issues inferred from backend API behavior and frontend integration risk.

### P0 - Must Fix Immediately

No confirmed frontend P0 issues were identified in this backend-focused pass.

---

### P1 - Strongly Recommended

#### 1. API error response shape is not normalized

**File:** Backend affects frontend globally; examples in `python/routers/*.py` and FastAPI validation responses.

**Problem:** Custom errors return `{"detail": "..."}`, while validation errors return FastAPI's list-shaped `detail`.

**Frontend risk:** Error handling becomes inconsistent and brittle.

**Suggested backend contract:**

```json
{
  "code": "VALIDATION_ERROR",
  "message": "请求参数校验失败",
  "errors": [],
  "timestamp": "2026-05-03T00:00:00Z"
}
```

#### 2. `/api/products` pagination change needs frontend compatibility handling

**File:** `python/routers/products.py:11-14`

**Problem:** Backend should add pagination, but current frontend may expect an array of all products.

**Frontend risk:** A response shape change could break existing pages.

**Suggested approach:** Keep response as array for now, add optional `skip`/`limit`, and only introduce envelope pagination in a versioned endpoint.

#### 3. Production docs and CORS behavior should be environment-specific

**File:** `python/main.py:22-31`

**Problem:** Backend docs exposure and CORS origins are backend-owned but affect frontend deployment.

**Frontend risk:** Staging/production frontend origins may fail or docs may be exposed unintentionally.

**Suggested fix:** Define `ENV` and `CORS_ORIGINS` per environment, and document required origins.

---

### P2 - Optimization

#### 4. Time format consistency should be formalized

**File:** `python/routers/kline.py:32`, `python/schemas.py:13-93`

**Problem:** K-line manually serializes `time`, while other schemas return datetime fields through Pydantic.

**Frontend risk:** Date parsing rules can diverge across components.

**Suggested fix:** Standardize on ISO 8601 UTC strings in API schema.

#### 5. Realtime updates still rely on polling

**File:** Backend API design, no specific frontend file reviewed.

**Problem:** Existing API design encourages polling `/api/realtime/{symbol}` and `/api/products`.

**Frontend risk:** More open tabs or watched symbols increase duplicate requests.

**Suggested path:** Keep polling for MVP, but define a later SSE endpoint for batched realtime quotes.

---

## Top 10 Fix Order

1. Fix database engine creation for SQLite vs PostgreSQL.
2. Disable automatic production mock users and fixed passwords.
3. Gate scheduler startup with `ENABLE_SCHEDULER`.
4. Stop caching ORM objects; cache DTO/dict values and add cache locking.
5. Add rate limiting to register/login.
6. Add scheduler re-entry protection.
7. Fix N+1 queries in product detail and price sync.
8. Batch variety lookup in K-line bulk insert.
9. Strengthen user/comment input validation.
10. Replace real DB-dependent tests with isolated test fixtures.

