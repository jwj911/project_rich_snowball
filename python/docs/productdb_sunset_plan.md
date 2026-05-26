# ProductDB 兼容层退场计划

> 制定日期：2026-05-26
> 目标：消除 `ProductDB` 与新行情数据层（`VarietyDB`/`RealtimeQuoteDB`/`KlineDataDB`）长期并存造成的双写/双读债务。

---

## 一、当前状态

`ProductDB`（旧）与 `VarietyDB` + `RealtimeQuoteDB`（新）长期并存：

- **写路径**：scheduler 每 60 秒执行 `sync_prices_to_products()`，将 `RealtimeQuoteDB` 的价格复制回 `ProductDB`
- **读路径**：前端品种列表和详情页仍调用 `/api/products/*`，后端查询 `ProductDB`
- **评论关联**：`CommentDB.product_id` 外键指向 `ProductDB.id`

---

## 二、依赖清单

### 2.1 前端依赖

| 前端文件 | 使用方式 | 依赖的 API |
|----------|----------|------------|
| `app/products/page.tsx` | 行情中心页面 | `GET /api/products?search=&category=&direction=&sort_by=` |
| `app/products/[id]/page.tsx` | 品种详情页 | `GET /api/products/{id}` |
| `app/page.tsx` | 行情工作台（领涨卡片链接） | `GET /api/products` → 跳转 `/products/{id}` |
| `app/workspace/page.tsx` | 工作区（自选/标注/评论链接） | 跳转 `/products/{id}` |
| `app/my-comments/page.tsx` | 我的评论（跳转链接） | 跳转 `/products/{id}` |
| `lib/api/products.ts` | API 客户端封装 | `/api/products`, `/api/products/{id}`, `/api/comments` |
| `hooks/useProductListRealtime.ts` | 实时行情轮询 | `GET /api/products` + SWR |

### 2.2 后端依赖

| 后端模块 | 使用方式 |
|----------|----------|
| `routers/products.py` | `/api/products` 路由，调用 `ProductService` → `ProductRepository` → `ProductDB` |
| `services/domain/product_service.py` | 品种领域服务，依赖 `ProductRepository` |
| `services/domain/repositories/product_repository.py` | 直接查询 `ProductDB` |
| `models.py:ProductDB` | 旧品种表，22 个字段 |
| `data_collector/scheduler.py:sync_prices_to_products()` | 每 60 秒将 `RealtimeQuoteDB` 同步回 `ProductDB` |
| `models.py:CommentDB` | `product_id` 外键指向 `ProductDB.id` |
| `data_collector/init_mock_data.py` | 初始化 Mock 数据时写入 `ProductDB` |

---

## 三、新 API 替代路径

### 3.1 已有新接口（可直接复用或扩展）

| 旧接口 | 新接口 | 状态 |
|--------|--------|------|
| `GET /api/products` | `GET /api/varieties` | ❌ 新接口缺少搜索/筛选/排序/统计能力 |
| `GET /api/products/{id}` | `GET /api/varieties/{id}` + `GET /api/realtime/{symbol}` | ⚠️ 需前端组合调用 |
| `POST /api/comments` (product_id) | `POST /api/comments` (variety_id) | ❌ 需改外键和接口参数 |

### 3.2 需新建/扩展的接口

1. **`GET /api/varieties`** 增强
   - 添加 `search`, `category`, `direction`, `sort_by`, `sort_order` 参数
   - 响应头携带 `X-Total-Count`, `X-Total-Volume`, `X-Up-Count`, `X-Down-Count`, `X-Categories`
   - 后端实现：联合查询 `VarietyDB` + `RealtimeQuoteDB`

2. **`GET /api/varieties/{id}/detail`** 或增强现有 `GET /api/varieties/{id}`
   - 返回品种元数据 + 实时行情 + 评论列表
   - 替代 `GET /api/products/{id}`

3. **评论接口迁移**
   - `CommentDB` 增加 `variety_id` nullable 字段
   - `POST /api/comments` 支持 `variety_id` 参数
   - 读接口支持按 `variety_id` 查询评论
   - 数据迁移：将现有 `product_id` → `variety_id` 映射填充

---

## 四、迁移阶段

### Phase 1：新接口补齐（1 周）

- [ ] 扩展 `GET /api/varieties` 支持列表查询（搜索/筛选/排序/统计）
- [ ] 扩展 `GET /api/varieties/{id}` 返回评论列表
- [ ] 扩展评论 CRUD 支持 `variety_id`
- [ ] 数据迁移脚本：填充 `CommentDB.variety_id`
- [ ] 后端测试覆盖新接口

### Phase 2：前端切流（1 周）

- [ ] 新建 `lib/api/varieties.ts` 替代 `lib/api/products.ts`
- [ ] `app/products/page.tsx` 切换到 `/api/varieties`
- [ ] `app/products/[id]/page.tsx` 切换到 `/api/varieties/{id}`
- [ ] 所有 `/products/{id}` 链接改为 `/products/{symbol}` 或保持 ID（需确认路由策略）
- [ ] 工作区、评论页等链接更新
- [ ] 前端测试回归

### Phase 3：双写停止（1 天）

- [ ] 删除 `sync_prices_to_products()` 调度任务
- [ ] 删除 `scheduler.py` 中对 `ProductDB` 的导入
- [ ] 验证 `RealtimeQuoteDB` 写入不受影响

### Phase 4：兼容层删除（1 周）

- [ ] 删除 `routers/products.py`
- [ ] 删除 `services/domain/product_service.py`
- [ ] 删除 `services/domain/repositories/product_repository.py`
- [ ] 删除 `models.py:ProductDB`（Alembic 迁移删除表）
- [ ] 删除 `schemas.py` 中仅 ProductDB 使用的 schema
- [ ] 更新 `data_collector/init_mock_data.py`，不再写入 ProductDB
- [ ] 全量测试回归

---

## 五、删除 `sync_prices_to_products()` 的前置条件

| 前置条件 | 状态 |
|----------|------|
| 前端所有品种列表/详情页面已切换到新接口 | ⬜ |
| `CommentDB` 已完成 `variety_id` 迁移，且评论接口支持 `variety_id` | ⬜ |
| 工作区、自选、标注等模块不再依赖 `ProductDB.id` | ⬜ |
| 外部脚本/管理后台不再直接读写 `ProductDB` | ⬜ |
| 新接口性能不低于旧接口（列表查询 P95 < 200ms） | ⬜ |

---

## 六、风险与缓解

| 风险 | 缓解方案 |
|------|----------|
| 新接口联合查询性能下降 | 预先在 `RealtimeQuoteDB.variety_id` + `VarietyDB.symbol` 上加索引；必要时引入物化视图 |
| 评论数据迁移丢失 | 迁移脚本使用幂等键（`product_id` + `symbol` 映射），先 dry-run 再执行 |
| 前端路由 `/products/{id}` 变为 `/products/{symbol}` 导致外链失效 | 保留 `/products/{id}` 路由做 302 重定向到 `/products/{symbol}`，持续 1-2 个版本 |
| 第三方/移动客户端未同步更新 | 旧 `/api/products` 保留只读代理 1-2 个版本，返回 410 Gone + 新路径提示 |

---

## 七、验收标准

1. `grep -r "ProductDB" python/routers python/services --include="*.py"` 返回空（测试和 Alembic 除外）
2. `grep -r "/api/products" frontend/ --include="*.ts" --include="*.tsx"` 返回空
3. 数据库中 `products` 表已删除（Alembic 迁移完成）
4. 全量 pytest 通过，Playwright E2E 通过
5. `/health/scheduler` 不再包含 `sync_prices_to_products` 任务

---

*本计划随迭代进展更新。当前阶段：文档先行，尚未进入实施。*
