# Phase 9 后端改造评审文档：价位标注 batch scope/contract 补齐

> 日期：2026-05-29  
> 背景：前端 v7 已完成标注 scope/contract 主链路改造（单条 create），但 batch 接口仍停留在旧契约  
> 目标：单条 create 与 batch create 在 `scope/contract_id` 语义上完全一致

---

## 一、当前问题

### 1. 前端 batch 类型缺少 scope/contract_id

`frontend/lib/api/workspace.ts:53-71` 的 `createPriceLevelsBatch()` item 类型：

```ts
items: Array<{
  variety_id: number
  type: 'support' | 'resistance'
  price: string
  note?: string | null
}>
```

缺少 `scope` 和 `contract_id` 字段。

### 2. 后端 batch 创建未写入 scope/contract_id

`python/services/domain/price_level_service.py:132-139`：

```python
pl = PriceLevelDB(
    user_id=user_id,
    variety_id=item.variety_id,
    type=item.type,
    price=item.price,
    note=item.note,
    source="manual",
)
```

未设置 `scope` 和 `contract_id`。

### 3. 重复检测 key 过窄

`python/services/domain/price_level_service.py:115-130`：

```python
existing_keys = {
    (pl.variety_id, pl.type, float(pl.price))
    for pl in self._repo.list_by_user_and_varieties(user_id, variety_ids)
}

key = (item.variety_id, item.type, float(item.price))
```

相同品种、类型、价格但不同 scope 的标注会被误判为重复。

---

## 二、建议改造方案

### 2.1 Schema 扩展

**前端**：`frontend/lib/api/workspace.ts`

```ts
type PriceLevelBatchItem = {
  variety_id: number
  type: 'support' | 'resistance'
  price: string
  note?: string | null
  scope?: 'continuous' | 'main' | 'contract'
  contract_id?: number | null
}
```

注意保持向后兼容：`scope` 默认为 `'continuous'`，`contract_id` 默认为 `null`。

**后端**：`python/schemas.py` 的 `PriceLevelBatchCreate` / `PriceLevelBatchItem`

```python
class PriceLevelBatchItem(BaseModel):
    variety_id: int
    type: Literal["support", "resistance"]
    price: str
    note: str | None = None
    scope: Literal["continuous", "main", "contract"] = "continuous"
    contract_id: int | None = None

class PriceLevelBatchCreate(BaseModel):
    items: list[PriceLevelBatchItem]
```

### 2.2 后端 batch 创建写入 scope/contract_id

`python/services/domain/price_level_service.py:132-139`：

```python
pl = PriceLevelDB(
    user_id=user_id,
    variety_id=item.variety_id,
    type=item.type,
    price=item.price,
    note=item.note,
    source="manual",
    scope=item.scope,
    contract_id=item.contract_id,
)
```

### 2.3 重复检测 key 扩展

`python/services/domain/price_level_service.py:115-130`：

```python
existing_keys = {
    (pl.variety_id, pl.type, float(pl.price), pl.scope, pl.contract_id)
    for pl in self._repo.list_by_user_and_varieties(user_id, variety_ids)
}

key = (item.variety_id, item.type, float(item.price), item.scope, item.contract_id)
```

### 2.4 校验规则

在 `create_price_levels_batch` 中增加：

```python
if item.scope == "contract" and item.contract_id is None:
    failed.append({"index": idx, "reason": "contract scope 必须指定 contract_id"})
    continue

if item.scope in ("continuous", "main") and item.contract_id is not None:
    item.contract_id = None  # 规范化
```

### 2.5 现有数据兼容

已通过 Alembic 迁移将现有数据默认 scope='continuous'（当前行为一致），无需再次迁移。

---

## 三、测试覆盖建议

### 后端测试（`python/tests/test_price_levels.py`）

1. **batch 创建 contract scope 标注可保留 contract_id**
   - POST `/api/price-levels/batch` 含 `scope='contract', contract_id=123`
   - 断言返回 success 中记录的 scope='contract', contract_id=123

2. **continuous/main/contract 同价位互不冲突**
   - 同一品种、类型、价格，分别用 continuous/main/contract scope batch 创建
   - 断言 3 条都成功

3. **contract scope 缺 contract_id 返回 422 或业务错误**
   - batch 含 `scope='contract', contract_id=null`
   - 断言 failed 中 reason 含"必须指定 contract_id"

4. **scope 默认值为 continuous**
   - batch item 不传 scope
   - 断言创建的记录 scope='continuous'

### 前端测试

1. `createPriceLevelsBatch` 调用时传入 `scope`/`contract_id` 参数正确
2. batch 返回结果处理正常（success/failed 结构不变）

---

## 四、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `python/schemas.py` | 修改 | `PriceLevelBatchItem` 增加 `scope`/`contract_id` |
| `python/services/domain/price_level_service.py` | 修改 | 写入 scope/contract_id；扩展重复 key；增加校验 |
| `python/tests/test_price_levels.py` | 新增 | batch scope 隔离测试 |
| `frontend/lib/api/workspace.ts` | 修改 | `createPriceLevelsBatch` item 类型补齐 |
| `frontend/lib/api/types.ts` | 无需修改 | `PriceLevelScope` 已存在 |

---

## 五、验收标准

- [x] 单条 create 与 batch create 在 `scope/contract_id` 语义上完全一致
- [x] batch 导入不会污染 continuous 标注口径
- [x] 不同 scope 下相同价位不冲突
- [x] contract scope 缺 contract_id 返回明确错误
- [x] 现有数据不受影响
- [x] 前后端测试全部通过

---

## 六、后端改造完成记录

**完成日期**：2026-05-29  
**合并分支**：`master`（`4172a2d3`）

### 实际变更

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `python/schemas.py` | 修改 | 新增 `PriceLevelBatchItem`，`PriceLevelBatchCreate` 改用 `list[PriceLevelBatchItem]`，与单条 `PriceLevelCreate` 在 scope/contract_id 语义上完全一致 |
| `python/services/domain/price_level_service.py` | 修改 | `create_price_levels_batch` 增加校验：① contract scope 必须指定 contract_id；② continuous/main 的 contract_id 自动规范化为 None |
| `python/tests/test_price_levels.py` | 修改 | 新增 4 个测试覆盖 batch scope 隔离、contract_id 必填、默认值、规范化场景 |
| `frontend/lib/api/workspace.ts` | 修改 | `createPriceLevelsBatch` item 类型补齐 `scope`/`contract_id` |

### 测试结论

- 后端 pytest：`233 passed, 6 skipped`（含 price_levels 14 个测试全部通过）
- 前端类型检查：`npx tsc --noEmit` 无错误

### 前端可开始迭代

Batch 接口已就绪：
- `POST /api/price-levels/batch` 接受 `scope`（默认 `"continuous"`）和 `contract_id`（默认 `null`）
- contract scope 必须传 `contract_id`，否则返回 `failed` 项 reason 含 `"contract scope 必须指定 contract_id"`
- continuous/main 下即使传了 `contract_id` 也会被后端规范化为 `null`，不污染合约层标注

---

*请后端 agent 评审后确认方案或提出修改意见。*
