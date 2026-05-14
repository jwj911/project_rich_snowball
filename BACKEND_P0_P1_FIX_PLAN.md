# 后端 P0/P1 问题修复方案

> 基于 Phase 3 完成后综合审查发现的 5 个 P0/P1 级别问题。
> 修复目标：消除阻塞性缺陷、消除技术债务、保证前后端一致性。

---

## 问题清单总览

| 优先级 | 编号 | 问题 | 文件 | 预计改动行数 |
|--------|------|------|------|-------------|
| P0 | 1 | CORS `allow_methods` 缺少 PUT/DELETE | `python/main.py` | 1 行 |
| P1 | 2 | `ACCESS_TOKEN_EXPIRE_MINUTES` 硬编码 | `python/config.py` | 1 行 |
| P1 | 3 | Pydantic `class Config` 弃用警告 | `python/schemas.py` | 4 处 |
| P1 | 4 | `.env.example` PostgreSQL 端口与 docker-compose 不一致 | `.env.example` | 1 行 |
| P1 | 5 | 熔断器未覆盖扩展 Pipeline | `python/data_collector/pipeline.py` | 7 处 |
| P2 | 6 | 前端缺少连续 K 线 API 封装 | `frontend/lib/api.ts` | 新增 2 个方法 |

---

## 问题 1：CORS allow_methods 缺少 PUT/DELETE [P0]

### 根因

`main.py:77` 的 CORS 中间件配置仅允许 `GET` 和 `POST`：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],      # ← 缺 PUT/DELETE
    allow_headers=["Authorization", "Content-Type"],
)
```

前端 `watchlists` 和 `price_levels` 功能调用了以下非 GET/POST 方法：
- `PUT /api/watchlists/{id}` — 更新自选备注
- `DELETE /api/watchlists/{id}` — 删除自选
- `PUT /api/price-levels/{id}` — 更新价位标注
- `DELETE /api/price-levels/{id}` — 删除价位标注

浏览器在跨域请求时会先发送 OPTIONS 预检请求（preflight）。若 CORS 中间件未声明 `PUT`/`DELETE`，浏览器会拒绝实际请求，导致上述操作在前端无法完成。

### 影响范围

- **开发环境**：前端 `npm run dev` 实际端口 3200，后端 8200，属于跨域，受影响。
- **生产环境**：必须配置 `CORS_ORIGINS`，跨域场景下受影响。
- **测试环境**：pytest 使用 `TestClient` 不走浏览器 CORS，测试不受影响。

### 修复方案

**方案 A（精确方法列表）—— 推荐**
```python
allow_methods=["GET", "POST", "PUT", "DELETE"],
```

**方案 B（通配符）**
```python
allow_methods=["*"],
```
不推荐，过于宽泛，且 `allow_credentials=True` 时 `"*"` 在部分浏览器中行为不一致。

### 验证方式
1. 启动后端：`cd python && python main.py`
2. 前端页面登录后，尝试：
   - 在品种详情页添加价位标注 → 删除价位标注（DELETE）
   - 在品种详情页加入自选 → 在工作区删除自选（DELETE）
   - 在工作区修改自选备注（PUT）
3. 浏览器 DevTools Network 面板确认 OPTIONS 预检返回 `200`，且 `Access-Control-Allow-Methods` 包含 `PUT, DELETE`。

---

## 问题 2：ACCESS_TOKEN_EXPIRE_MINUTES 硬编码 [P1]

### 根因

`config.py:16` 写死为 24 小时（1440 分钟）：
```python
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
```

`.env.example` 中已定义 `ACCESS_TOKEN_EXPIRE_MINUTES=1440`，但代码从未读取。

### 影响范围

- 无法通过环境变量调整 token 有效期，运维灵活性受限。
- 测试时若希望缩短 token 过期时间以验证刷新逻辑，无法做到。

### 修复方案

```python
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
```

**向后兼容**：默认值仍为 1440（24 小时），不影响现有行为。

### 验证方式
1. 新增测试：`test_access_token_expire_from_env`（验证环境变量可被读取）
2. 运行完整测试套件确认无回归：`pytest tests -v`

---

## 问题 3：Pydantic class Config 弃用警告 [P1]

### 根因

Pydantic v2.0 起，`class Config:` 语法已标记为 deprecated，将在 v3.0 移除。当前代码中 4 个 schema 使用该语法：

```python
class PriceLevelResponse(BaseModel):
    ...
    class Config:
        from_attributes = True
```

同类问题还存在于 `WatchlistResponse`、`ContractResponse`、`ContractRolloverResponse`。

### 影响范围

- pytest 输出 4 条 `PydanticDeprecatedSince20` 警告。
- Pydantic v3 发布后将导致运行错误。

### 修复方案

从 `pydantic` 导入 `ConfigDict`，统一替换：

```python
from pydantic import BaseModel, Field, field_validator, EmailStr, ConfigDict

class PriceLevelResponse(BaseModel):
    ...
    model_config = ConfigDict(from_attributes=True)
```

### 验证方式
1. `pytest tests -v` — 确认 4 条 Pydantic 警告消失。
2. 前端类型检查 `npx tsc --noEmit` — 确认无类型回归。

---

## 问题 4：.env.example PostgreSQL 端口不一致 [P1]

### 根因

`.env.example:14`：
```env
DATABASE_URL=postgresql://futures:futures123@localhost:5432/futures_community
```

`docker-compose.yml` 映射：`15432:5432`。

新用户直接复制 `.env.example` 为 `.env` 后，`python main.py` 会因连接不到 5432 端口而启动失败。

### 修复方案

```env
DATABASE_URL=postgresql://futures:futures123@localhost:15432/futures_community
```

### 验证方式
1. 文件级确认：与 `docker-compose.yml` 中的端口映射核对。

---

## 问题 5：熔断器未覆盖扩展 Pipeline [P1]

### 根因

`pipeline.py` 中，`run_realtime` 和 `run_kline` 在异常时调用了 `record_failure(source_name)`：

```python
except Exception as e:
    db.rollback()
    exc = e
    record_failure(source_name)   # ← 存在
    raise
```

但以下 7 个扩展 pipeline 方法在异常时**仅 raise，不记录熔断器**：
- `run_fut_daily`
- `run_fut_settle`
- `run_fut_weekly_detail`
- `run_fut_wsr`
- `run_fut_holding`
- `run_fut_price_limit`
- `run_fut_mapping`

**影响**：Tushare 扩展任务（日线、结算、仓单、持仓、涨跌停、主力映射）持续失败时，熔断器不会计数、不会打开，每次调度周期仍会重试，浪费 Tushare API 配额（免费版有日调用上限）。

### 修复方案

在每个扩展方法的 `except` 块中，追加 `record_failure(...)`：

```python
except Exception as e:
    db.rollback()
    exc = e
    record_failure(self.collector.__class__.__name__)   # ← 新增
    logger.critical(f"FutDaily pipeline aborted: {e}", exc_info=True)
    raise
```

同时，在 `finally` 块的 `_record_run` 之后，如果无异常也应追加 `record_success(...)`（`run_fut_mapping` 已有此逻辑，但其他方法没有显式调用）。

**注意**：`run_fut_mapping` 的 `finally` 块中已有 `if not exc: record_success(...)` 的等价逻辑吗？—— 检查现有代码：`run_fut_mapping` 没有显式调用 `record_success`，但 `run_realtime` 和 `run_kline` 在 `finally` 中有。为保证一致性，所有扩展方法都应在 `finally` 中：

```python
if not exc:
    record_success(self.collector.__class__.__name__)
```

### 验证方式
1. 新增/扩展 `test_circuit_breaker.py`：模拟某个扩展 pipeline（如 `run_fut_settle`）连续失败 5 次，验证熔断器打开。
2. 运行完整测试：`pytest tests -v`。

---

## 问题 6：前端缺少连续 K 线 API 封装 [P2]

### 根因

Phase 2 后端已提供连续 K 线 API：
- `GET /api/kline/{symbol}/continuous?period=D&limit=500`
- `GET /api/kline/{symbol}/main?period=D&limit=500`

但 `frontend/lib/api.ts` 中仅有旧版 `getKline(symbol, period, limit)`，未暴露上述接口。

### 影响范围

- 前端品种详情页目前只能查看单品种/单合约 K 线，无法查看主力连续 K 线。
- Phase 2 的合约语义功能无法被前端消费。

### 修复方案

在 `frontend/lib/api.ts` 的 `ApiService` 中新增：

```typescript
async getContinuousKline(
  symbol: string,
  period: string = 'D',
  start?: string,
  end?: string,
  limit: number = 500
): Promise<KlineData[]> {
  const params = new URLSearchParams()
  params.append('period', period)
  params.append('limit', String(limit))
  if (start) params.append('start', start)
  if (end) params.append('end', end)
  return this.request<KlineData[]>(`/api/kline/${symbol}/continuous?${params.toString()}`)
}

async getMainContractKline(
  symbol: string,
  period: string = 'D',
  start?: string,
  end?: string,
  limit: number = 500
): Promise<KlineData[]> {
  const params = new URLSearchParams()
  params.append('period', period)
  params.append('limit', String(limit))
  if (start) params.append('start', start)
  if (end) params.append('end', end)
  return this.request<KlineData[]>(`/api/kline/${symbol}/main?${params.toString()}`)
}
```

### 验证方式
1. `npx tsc --noEmit` — 确认类型无错误。
2. 浏览器中调用 `api.getContinuousKline('AU', 'D')`，确认返回数据格式与 `KlineData` 接口匹配。

---

## 实施计划

| 步骤 | 内容 | 预计时间 |
|------|------|----------|
| 1 | 修复 `main.py` CORS allow_methods | 5 分钟 |
| 2 | 修复 `config.py` ACCESS_TOKEN_EXPIRE_MINUTES | 5 分钟 |
| 3 | 修复 `schemas.py` Pydantic ConfigDict | 10 分钟 |
| 4 | 修复 `.env.example` PostgreSQL 端口 | 2 分钟 |
| 5 | 修复 `pipeline.py` 熔断器覆盖 | 15 分钟 |
| 6 | 新增 `api.ts` 连续 K 线方法 | 10 分钟 |
| 7 | 运行后端测试 + 前端类型检查 | 5 分钟 |
| 8 | 浏览器手动验证 CORS PUT/DELETE | 10 分钟 |
| **总计** | | **~1 小时** |

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| CORS 修改过宽引入安全隐患 | 低 | 中 | 精确列出方法，不使用 `"*"` |
| ConfigDict 替换导致序列化行为变化 | 低 | 中 | 跑完整测试套件验证 |
| pipeline 熔断器修改影响现有调度逻辑 | 低 | 低 | 修改仅追加 `record_failure`，不改变控制流 |
| 前端 api.ts 新增方法导致类型不匹配 | 低 | 低 | `tsc --noEmit` 验证 |

---

## 迭代建议

完成本方案修复后，建议进入 **Phase 4：前端 K 线图表深度集成**，具体包括：
1. 在品种详情页 `products/[id]/page.tsx` 中增加「连续 K 线 / 主力合约 / 单合约」切换器。
2. 将 `KlineChart.tsx` 的数据源从 `getKline` 切换为 `getContinuousKline`（作为默认视图）。
3. 在工作区增加「我的自选」实时行情卡片（利用现有 `/api/realtime/{symbol}` 轮询）。
