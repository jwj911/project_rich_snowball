# ProductDB 兼容层退场计划

> 制定日期：2026-05-26
> 更新日期：2026-05-27（Phase 1-3 已完成，进入 Phase 4 准备）
> 目标：消除 `ProductDB` 与新行情数据层（`VarietyDB`/`RealtimeQuoteDB`/`KlineDataDB`）长期并存造成的双写/双读债务。

---

## 一、当前状态

`ProductDB`（旧）与 `VarietyDB` + `RealtimeQuoteDB`（新）长期并存：

- **写路径**：scheduler 每 60 秒执行 `sync_prices_to_products()`，将 `RealtimeQuoteDB` 的价格复制回 `ProductDB`
- **读路径**：前端品种列表和详情页仍调用 `/api/products/*`，后端查询 `ProductDB`
- **评论关联**：`CommentDB.product_id` 外键指向 `ProductDB.id`

---

## 二、依赖清单（精确到文件）

### 2.1 前端依赖

#### API 端点调用

| API 端点 | 前端封装文件 | 调用方 |
|----------|-------------|--------|
| `GET /api/products` | `frontend/lib/api/products.ts` | `useProductListRealtime`, `useProducts`, `Workspace`, `MyComments` |
| `GET /api/products?skip=&limit=&search=&category=&direction=&sort_by=&sort_order=` | `frontend/lib/api/products.ts:getProductsPage` | `app/products/page.tsx` |
| `GET /api/products/{id}` | `frontend/lib/api/products.ts:getProduct` | `useProductPolling`, `useProductDetail`, `app/products/[id]/page.tsx` |

#### 类型定义

| 类型 | 定义文件 | 使用场景 |
|------|----------|----------|
| `Product` | `frontend/lib/api/types.ts:1` | 所有行情卡片、表格、详情组件 |
| `ProductQuery` | `frontend/lib/api/types.ts:20` | 行情中心筛选参数 |
| `ProductListResponse` | `frontend/lib/api/types.ts:30` | 列表分页响应 |
| `ProductDetail` | `frontend/lib/api/types.ts:51` | 详情页响应 |

#### Hooks

| Hook | 文件 | API 方法 |
|------|------|----------|
| `useProducts` | `frontend/lib/swr-hooks.ts:10` | `api.getProducts()` |
| `useProduct` | `frontend/lib/swr-hooks.ts:14` | `api.getProduct(id)` |
| `useProductListRealtime` | `frontend/hooks/useProductListRealtime.ts:58` | `api.getProductsPage(query)` |
| `useProductPolling` | `frontend/hooks/useProductPolling.ts:49` | `api.getProduct(productId)` |
| `useProductDetail` | `frontend/hooks/useProductDetail.ts:37` | `api.getProduct(productId)` |

#### 页面

| 页面 | 文件 | 依赖说明 |
|------|------|----------|
| 行情工作台 | `frontend/app/page.tsx` | `Product` 类型、`useProductListRealtime`、领涨卡片链接 `/products/{id}` |
| 行情中心 | `frontend/app/products/page.tsx` | `Product` 类型、`useProductListRealtime`、路由 `/products` |
| 品种详情 | `frontend/app/products/[id]/page.tsx` | `useProductPolling`、`product` 对象 |
| 工作区 | `frontend/app/workspace/page.tsx` | `api.getProducts()`、`Product` 类型、链接 `/products/{id}` |
| 我的评论 | `frontend/app/my-comments/page.tsx` | `api.getProducts()`、`Product` 类型、链接 `/products/{id}` |

#### 组件

| 组件 | 文件 |
|------|------|
| `QuoteCard` | `frontend/components/market/QuoteCard.tsx` |
| `QuoteTable` | `frontend/components/market/QuoteTable.tsx` |
| `QuoteDesktopTable` | `frontend/components/market/QuoteDesktopTable.tsx` |
| `QuoteMobileList` | `frontend/components/market/QuoteMobileList.tsx` |
| `ProductHeader` | `frontend/components/product/ProductHeader.tsx` |
| `TradingInfoPanel` | `frontend/components/product/TradingInfoPanel.tsx` |
| `TradingInfo` | `frontend/components/product/TradingInfo.tsx` |
| `WatchlistPanel` | `frontend/components/workspace/WatchlistPanel.tsx` |
| `MyResearchTimeline` | `frontend/components/workspace/MyResearchTimeline.tsx` |

#### UI 路由链接（非 API，但需同步迁移）

所有指向品种详情的 Next.js Link 使用 `/products/{id}` 路由：
- `frontend/app/page.tsx:94`（领涨卡片）
- `frontend/app/products/page.tsx`（行情中心）
- `frontend/components/market/QuoteCard.tsx:18`
- `frontend/components/market/QuoteTable.tsx:100`
- `frontend/components/market/QuoteDesktopTable.tsx:116`
- `frontend/components/workspace/WatchlistPanel.tsx:55`
- `frontend/components/workspace/MyResearchTimeline.tsx:43`
- `frontend/components/workspace/MyAnnotationsPanel.tsx:38`
- `frontend/app/my-comments/page.tsx:129`

#### 前端测试

| 测试文件 | 依赖内容 |
|----------|----------|
| `frontend/tests/lib/api.test.ts` | `api.getProductsPage()`, `api.getProducts()`, `/api/products` 断言 |
| `frontend/tests/hooks/useProductDetail.test.tsx` | `api.getProduct`, `makeProduct` |
| `frontend/tests/components/QuoteTable.test.tsx` | `makeProduct`, `makeTestProduct`, `products` prop |
| `frontend/tests/components/QuoteCard.test.tsx` | `makeProduct`, `mockProduct` |
| `frontend/tests/fixtures/index.ts` | `Product` import, `makeProduct()` factory |

### 2.2 后端依赖

#### API 路由

| 路由文件 | 端点 | 说明 |
|----------|------|------|
| `routers/products.py` | `GET /api/products` | 列表查询（分页/搜索/分类/涨跌筛选/排序） |
| `routers/products.py` | `GET /api/products/{id}` | 详情查询（含评论分页） |

> 注：`routers/products.py` 自身不直接导入 `ProductDB`，而是通过 `ProductService` → `ProductRepository` 间接依赖。

#### 领域服务与仓储

| 文件 | 依赖方式 |
|------|----------|
| `services/domain/product_service.py` | 包装 `ProductRepository` 的业务层 |
| `services/domain/repositories/product_repository.py` | 直接查询 `ProductDB`（get/list/filter/stats/sort/pagination） |
| `services/domain/repositories/comment_repository.py` | `get_product(product_id)` 验证产品存在性 |

#### 数据采集与调度

| 文件 | 依赖方式 |
|------|----------|
| `data_collector/scheduler.py:195-246` | `sync_prices_to_products()` 定义：每 60 秒将 `RealtimeQuoteDB` 同步回 `ProductDB` |
| `data_collector/scheduler.py:249-259` | `refresh_and_sync()` 调用 `sync_prices_to_products()` |
| `data_collector/init_mock_data.py` | 初始化 Mock 数据时写入 `ProductDB`，并读取 `ProductDB` 初始化 `RealtimeQuoteDB`/`CommentDB` |

#### 模型定义

| 文件 | 依赖方式 |
|------|----------|
| `models.py:97-116` | `ProductDB` 表定义（22 个字段） |
| `models.py:122,129` | `CommentDB.product_id` 外键 + `product` relationship |

#### 脚本与运维

| 文件 | 依赖方式 |
|------|----------|
| `scripts/data_quality_report.py:31,214` | 数据质量检查包含 `ProductDB` |

#### 后端测试

| 测试文件 | 依赖方式 |
|----------|----------|
| `tests/test_products_query.py` | `ProductDB` fixture 设置 |
| `tests/test_workspace_api.py` | 动态创建 `ProductDB` 行 |
| `tests/test_phase1_3_integration.py` | 查询 `ProductDB` count |
| `tests/test_ondelete_cascade.py` | `ProductDB` fixture + 级联行为测试 |

---

## 三、新 API 替代路径

### 3.1 已有新接口（可直接复用或扩展）

| 旧接口 | 新接口 | 状态 |
|--------|--------|------|
| `GET /api/products` | `GET /api/varieties` | ✅ 已具备搜索/筛选/排序/统计能力 |
| `GET /api/products/{id}` | `GET /api/varieties/by-product-id/{id}` + `GET /api/varieties/{symbol}/detail` | ✅ 过渡 API 已就绪 |
| `POST /api/comments` (product_id) | `POST /api/comments` (variety_id 可选) | ✅ 已支持 variety_id |

### 3.2 需新建/扩展的接口

1. **`GET /api/varieties` 增强**
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

### Phase 1：新接口补齐 ✅

- [x] 扩展 `GET /api/varieties` 支持列表查询（搜索/筛选/排序/统计）
- [x] 扩展 `GET /api/varieties/{symbol}/detail` 返回评论列表
- [x] 扩展评论 CRUD 支持 `variety_id`
- [x] 数据迁移脚本：填充 `CommentDB.variety_id`
- [x] 后端测试覆盖新接口（7 个测试）

### Phase 2：前端切流 ✅

- [x] `lib/api/products.ts` 内部切换到 `/api/varieties`（保持对外接口不变）
- [x] `app/products/page.tsx` 间接切换到 `/api/varieties`（通过 `getProductsPage`）
- [x] `app/products/[id]/page.tsx` 切换到 `/api/varieties/by-product-id/{id}`
- [x] 所有 `/products/{id}` 链接保持路由不变，仅 API 调用切换
- [x] 工作区、评论页等引用更新（`getProducts` 已间接迁移）
- [x] 前端测试回归（167 passed）

### Phase 3：双写停止 ✅

- [x] 删除 `sync_prices_to_products()` 调度任务
- [x] 删除 `refresh_and_sync()` 组合任务
- [x] 删除 `scheduler.py` 中对 `ProductDB` 的导入
- [x] `init_mock_data.py` 不再以 ProductDB 作为 RealtimeQuoteDB 的数据源
- [x] `/api/products` 标记 `Deprecation` 响应头
- [x] 验证 `RealtimeQuoteDB` 写入不受影响（pytest 218 passed）

### Phase 4：兼容层删除（待开始）

- [ ] 删除 `routers/products.py`
- [ ] 删除 `services/domain/product_service.py`
- [ ] 删除 `services/domain/repositories/product_repository.py`
- [ ] `CommentDB.product_id` 外键改为 nullable 或删除（Alembic 迁移）
- [ ] 删除 `models.py:ProductDB`（Alembic 迁移删除表）
- [ ] 删除 `schemas.py` 中仅 ProductDB 使用的 schema
- [ ] 更新 `data_collector/init_mock_data.py`，不再写入 ProductDB
- [ ] 更新所有测试，移除 `/api/products` 和 `ProductDB` 引用
- [ ] 全量测试回归

---

## 五、删除 `sync_prices_to_products()` 的前置条件

| 前置条件 | 状态 |
|----------|------|
| 前端所有品种列表/详情页面已切换到新接口 | ✅ |
| `CommentDB` 已完成 `variety_id` 迁移，且评论接口支持 `variety_id` | ✅ |
| 工作区、自选、标注等模块不再依赖 `ProductDB.id` | ✅ |
| 外部脚本/管理后台不再直接读写 `ProductDB` | ✅ |
| 新接口性能不低于旧接口（列表查询 P95 < 200ms） | ⬜（未压测，需观测） |

---

## 六、风险与缓解

| 风险 | 缓解方案 |
|------|----------|
| 新接口联合查询性能下降 | 预先在 `RealtimeQuoteDB.variety_id` + `VarietyDB.symbol` 上加索引；必要时引入物化视图 |
| 评论数据迁移丢失 | 迁移脚本使用幂等键（`product_id` + `symbol` 映射），先 dry-run 再执行 |
| 前端路由 `/products/{id}` 变为 `/products/{symbol}` 导致外链失效 | **保持 `/products/{id}` 路由不变**，仅切换内部 API 调用源，避免外链和书签失效 |
| 第三方/移动客户端未同步更新 | 旧 `/api/products` 保留只读代理 1-2 个版本，返回 410 Gone + 新路径提示 |

---

## 七、验收标准

1. `grep -r "ProductDB" python/routers python/services --include="*.py"` 返回空（测试和 Alembic 除外）
2. `grep -r "/api/products" frontend/ --include="*.ts" --include="*.tsx"` 返回空
3. 数据库中 `products` 表已删除（Alembic 迁移完成）
4. 全量 pytest 通过，Playwright E2E 通过
5. `/health/scheduler` 不再包含 `sync_prices_to_products` 任务

---

## 八、本次 Step 6 更新说明

本次迭代对原退场计划进行了以下增强：

- **前端依赖精确到文件级**：补充了 hooks（`useProductPolling`、`useProductDetail`、`useProductListRealtime`）、类型定义（`lib/api/types.ts`）、测试 fixtures、UI 路由链接分布等细节。
- **后端依赖精确到文件级**：补充了 `comment_repository.py`、`scripts/data_quality_report.py`、以及所有引用 `ProductDB` 的测试文件。
- **修正路由策略**：明确前端 Next.js 路由 `/products/{id}` **保持不变**，仅 API 层从 `/api/products/*` 切换到 `/api/varieties/*`，降低外链/书签失效风险。

*当前阶段：Phase 1-3 已完成，Phase 4 待启动。Phase 4 涉及删除 ProductDB 表和大量测试更新，建议在独立的迭代窗口中执行。*
