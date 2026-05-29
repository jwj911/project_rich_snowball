# 前端迭代路线图 v8（P1/P2 收口轮）

> 基于《前端交叉审计进度复核报告 v5.1》（评级 B+）制定。  
> 制定日期：2026-05-29  
> 原则：**优先收口 P1 契约裂缝，补齐 P2 精度与基线证据，推进评级到 A-。**  
> 前置状态：路线图 v7 的 Phase 1~6 主干已完成，但复核发现 4 处遗漏/边缘未干净。

---

## 一、总体策略

路线图 v7 完成了实时 batch 契约、K 线精度、空值 neutral、contract_id、标注 scope/contract 主链路、Lighthouse 脚本与 CI 集成。v5.1 复核发现以下遗漏：

| 问题 | 优先级 | 遗漏位置 |
|------|--------|----------|
| SSE 鉴权同时存在 cookie-only + stream-token 两套语义 | P1 | `realtimeStore.ts` 未消费 `createRealtimeStreamToken()` |
| 价位标注 batch 接口仍为旧契约（无 scope/contract_id） | P1 | `workspace.ts` + 后端 `price_level_service.py` |
| 交易时段 badge 仍使用前端本地规则 | P1 | `MarketSessionBadge.tsx` 未调用 `/api/market/status` |
| 标注组件价格仍固定两位小数 | P2 | `LevelChips.tsx`、`LevelEditor.tsx`、`usePriceLevels.ts` |
| `useLightweightChart.ts` 价格轴 formatter 仍固定两位 | P2 | Phase 2 遗漏 |
| Lighthouse 缺少可复现的基线报告文件 | P2 | `.lighthouse/latest.json` 未生成/未提交 |
| 后端本地测试环境不可复现（阻塞交叉验证） | P2 | 文档与 venv 指导缺失 |

**核心原则：先闭合 P1 契约分叉（SSE、batch、时段），再补齐 P2 精度残留与基线证据。**

---

## 二、阶段规划

### Phase 7：SSE 鉴权契约二选一（P1，0.5~1 天）

目标：前后端只保留一个"一等公民"的 SSE 鉴权路径。

**方案 A（推荐）：前端消费 stream-token**

| 行动项 | 关键动作 | 文件 | 验收标准 |
|--------|----------|------|----------|
| 获取 token | `RealtimeStore.connect()` 先调用 `api.createRealtimeStreamToken()` | `frontend/lib/realtimeStore.ts:114` | token 获取成功 |
| URL 拼接 token | 修改 `buildSseUrl(symbols, token?)`，将 token 作为 `?token=` query param | `frontend/lib/realtimeStore.ts:103-112` | URL 包含 token |
| 兼容 fallback | 保留 `withCredentials: true`，token 获取失败时降级为 cookie-only | `frontend/lib/realtimeStore.ts:122-124` | 降级不报错 |
| reconnect 兼容 | reconnect 时复用或刷新 token | `frontend/lib/realtimeStore.ts:219-232` | 重连后 URL 仍含 token |
| 前端测试 | EventSource URL 包含 `token`；token 失败时降级 polling | `frontend/tests/lib/realtimeStore.test.ts` | 测试通过 |
| 后端/文档 | 访问日志对 `token=` query 做脱敏说明 | `AGENTS.md` 或后端日志配置 | 文档更新 |

**方案 B（备选）：废弃 stream-token**

- 前端标记 `createRealtimeStreamToken()` 为 `@deprecated`
- 后端将 `/api/realtime/stream-token` 标记 deprecated
- 文档写明 SSE 只支持 cookie 兼容路径

**产出物**：SSE 鉴权路径唯一，reconnect / fallback / cleanup 测试继续通过。

**回归命令**：
```powershell
cd frontend
npx.cmd tsc --noEmit
npm.cmd run test
npm.cmd run lint
npm.cmd run build
```

---

### Phase 8：交易时段 badge 后端权威化（P1，0.5 天）

目标：首页交易状态只以 `/api/market/status` 为权威来源，banner 与 badge 不再冲突。

| 行动项 | 关键动作 | 文件 | 验收标准 |
|--------|----------|------|----------|
| 新增/复用 hook | 新增 `useMarketStatus()` hook，调用 `api.getMarketStatus()` | `frontend/hooks/useMarketStatus.ts`（新建） | 返回 `current_session` |
| Badge 改造 | `MarketSessionBadge` 改用 hook 数据，不再直接调用 `getCurrentSession()` | `frontend/components/market/MarketSessionBadge.tsx` | 显示后端返回的 session |
| Banner 统一 | 确认 `MarketClosedBanner` 与 Badge 共用同一份 status | `frontend/components/market/MarketClosedBanner.tsx` | 无重复请求 |
| Fallback 标记 | 后端不可用时降级到 `getCurrentSession()`，并在 UI/telemetry 标记 | `frontend/hooks/useMarketStatus.ts` | fallback 不白屏 |
| 测试 | badge 显示 `day`/`night`/`closed`；API 失败时 fallback | `frontend/tests/components/MarketSessionBadge.test.tsx` | 测试通过 |
| 清理 | 若 `getCurrentSession()` 无其他消费者，评估是否保留为纯 fallback | `frontend/lib/trading-hours.ts` | 不影响其他调用方 |

**产出物**：`MarketSessionBadge` 与 `MarketClosedBanner` 同源，夜盘/节假日/临时休市时不出现分歧。

**回归命令**：
```powershell
cd frontend
npx.cmd tsc --noEmit
npm.cmd run test
npm.cmd run lint
npm.cmd run build
```

---

### Phase 9：价位标注 batch scope/contract 补齐（P1，1~1.5 天）

目标：单条 create 与 batch create 在 `scope/contract_id` 语义上完全一致。

**前端变更**：

| 行动项 | 关键动作 | 文件 | 验收标准 |
|--------|----------|------|----------|
| 类型补齐 | `createPriceLevelsBatch()` item 类型增加 `scope?: PriceLevelScope`、`contract_id?: number \| null` | `frontend/lib/api/workspace.ts:53-60` | tsc 通过 |
| 组件透传 | 批量导入入口（如有）传入当前 source 对应的 scope/contract_id | 调用方 | batch 参数正确 |
| 前端测试 | batch 创建 contract scope 标注可保留 contract_id | `frontend/tests/lib/api/workspace.test.ts` 或新增 | 测试通过 |

**后端变更（配合）**：

| 行动项 | 关键动作 | 文件 | 验收标准 |
|--------|----------|------|----------|
| 写入字段 | `create_price_levels_batch()` 创建 `PriceLevelDB` 时写入 `scope=item.scope`、`contract_id=item.contract_id` | `python/services/domain/price_level_service.py:132-139` | 数据库记录含 scope |
| 重复 key 扩展 | duplicate key 从 `(variety_id, type, price)` 扩展为 `(variety_id, type, price, scope, contract_id)` | `python/services/domain/price_level_service.py:115-130` | 不同 scope 同价位不冲突 |
| 校验规则 | `scope='contract'` 时 `contract_id` 必填；continuous/main 时 `contract_id` 规范化为空 | `python/services/domain/price_level_service.py` | 非法输入返回 422 |
| 后端测试 | batch 创建 contract scope 可保留 contract_id；continuous/main/contract 同价位互不冲突 | `python/tests/test_price_levels.py` | pytest 通过 |

**产出物**：批量导入不会污染 continuous 标注口径；重复检测在多 scope 下准确。

**回归命令**：
```powershell
cd frontend
npx.cmd tsc --noEmit && npm.cmd run test && npm.cmd run lint && npm.cmd run build

cd python
$env:SECRET_KEY="test-secret-key-for-frontend-contract-audit"
$env:ENABLE_SCHEDULER="0"
pytest tests/test_price_levels.py -q
```

---

### Phase 10：标注价格精度 + 图表 formatter 残留统一（P2，0.5~1 天）

目标：`ProductHeader`、K 线 header、tooltip、aria-label、`LevelChips`、`LevelEditor` 价格精度一致。

| 行动项 | 关键动作 | 文件 | 验收标准 |
|--------|----------|------|----------|
| 新增 payload 格式化 | 新增 `formatPricePayload(price, precision)`，避免展示函数与 API payload 语义混用 | `frontend/lib/format.ts` | 工具函数有单测 |
| LevelChips 精度 | `LevelChips` 增加 `pricePrecision?: number` prop，使用 `formatPrice()` | `frontend/components/kline/LevelChips.tsx:1,27` | precision=0 显示整数 |
| LevelEditor 精度 | `LevelEditor` 增加 `pricePrecision?: number` prop，展示和 aria-label 均使用 `formatPrice()` | `frontend/components/product/LevelEditor.tsx:6,73,75` | aria-label 精度一致 |
| usePriceLevels 提交 | 创建/迁移标注时使用 `formatPricePayload(price, pricePrecision)` 替代 `toFixed(2)` | `frontend/hooks/usePriceLevels.ts:132,137,173,210` | API payload 精度正确 |
| useLightweightChart 残留 | `priceFormatter` 从 `toFixed(2)` 改为 `formatPrice(price, pricePrecision)` | `frontend/hooks/useLightweightChart.ts:90` | 右侧价格轴精度正确 |
| 透传 prop | `KlineSection` → `LevelChips`/`LevelEditor` 传入 `product.price_precision` | `frontend/components/product/KlineSection.tsx` | prop 正确透传 |
| 单测覆盖 | `formatPricePayload` 单测（precision=0/1/2）；组件渲染断言 | `frontend/tests/lib/format.test.ts` 等 | 全部通过 |

**产出物**：同一品种在所有标注展示位价格位数一致；API payload 不再盲目截断为两位。

**回归命令**：
```powershell
cd frontend
npx.cmd tsc --noEmit
npm.cmd run test
npm.cmd run lint
npm.cmd run build
```

---

### Phase 11：Lighthouse 可复现基线证据（P2，0.5 天）

目标：本轮报告或 CI artifact 有一份可复现的 Lighthouse 数值。

| 行动项 | 关键动作 | 验收标准 |
|--------|----------|----------|
| 本地运行 | `npm run build && npm start`，另终端执行 `npm run lighthouse -- http://127.0.0.1:3000` | `.lighthouse/latest.json` 生成 |
| 指标检查 | Performance >= 85；LCP < 2.5s；CLS < 0.1；TBT < 300ms | 数值达标或记录偏差原因 |
| 提交/文档 | 将 `latest.json` 摘要粘贴到审计报告或提交文件；团队约定是否纳入版本控制 | 可复核 |
| CI 验证 | 确认 `.github/workflows/frontend-ci.yml` 中 Lighthouse 步骤能生成 artifact | PR check 中有 Lighthouse 输出 |

**产出物**：可复现的 Web Vitals 基线，支持后续趋势对比。

**回归命令**：
```powershell
cd frontend
npm.cmd run build
npm.cmd run lighthouse
```

---

### Phase 12：后端本地测试环境文档化（P2，0.5 天）

目标：前端 agent 能用同一命令复核接口契约，后端测试本地可复现。

| 行动项 | 关键动作 | 文件 | 验收标准 |
|--------|----------|------|----------|
| venv 指导 | README/AGENTS 明确使用独立 venv，不要用全局 Anaconda | `AGENTS.md`、`README.md` | 文档更新 |
| 命令模板 | 提供 Powershell 一键命令（创建 venv + 安装 lock + 运行测试） | `AGENTS.md` | 可复制执行 |
| 环境校验 | 建议增加 `python -c "import sqlalchemy; print(sqlalchemy.__version__)"` 快速检查 | `AGENTS.md` | 版本 >= 2.0 |

**产出物**：任何新进入的开发者或 AI agent 能按文档稳定跑通后端契约测试。

**回归命令**：
```powershell
cd python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
$env:SECRET_KEY="test-secret-key-for-frontend-contract-audit"
$env:ENABLE_SCHEDULER="0"
.\.venv\Scripts\python.exe -m pytest tests/test_realtime_batch.py tests/test_price_levels.py -q
```

---

## 三、执行顺序与依赖

```text
Phase 7  SSE 鉴权契约二选一（P1，0.5~1d）
    ↓
Phase 8  交易时段 badge 后端权威化（P1，0.5d）
    ↓
Phase 9  价位标注 batch scope/contract 补齐（P1，1~1.5d）← 建议独立分支，需后端配合
    ↓
Phase 10 标注价格精度 + 图表 formatter 残留统一（P2，0.5~1d）
    ↓
Phase 11 Lighthouse 可复现基线证据（P2，0.5d）
    ↓
Phase 12 后端本地测试环境文档化（P2，0.5d）
```

**顺序理由**：
- Phase 7/8 是 P1 契约/UI 修正，互相独立，可并行。
- Phase 9 涉及后端 batch 改造，范围最大，单独分支最稳妥。
- Phase 10 纯前端精度收尾，与 Phase 9 无文件冲突时可并行。
- Phase 11/12 是验证和文档，放在最后。

---

## 四、明确冻结（暂不启动）

以下功能在综合健康度达到 A- 之前**坚决不开工**：

- 策略回测系统（阻塞点：K 线未形成回测级查询服务）
- 高级图表指标（MACD/KDJ/布林带等 overlay）（阻塞点：指标计算层未就绪）
- 多品种对比面板（阻塞点：需要 SSE batch 稳定 + 鉴权闭环）
- 移动端 App / PWA（阻塞点：先保证 Web 端评级到 A-）

---

## 五、每阶段回归命令

每完成一个 Phase，至少执行：

```powershell
cd frontend
npx.cmd tsc --noEmit
npm.cmd run test
npm.cmd run lint
npm.cmd run build
```

涉及后端契约修改时追加：

```powershell
cd python
$env:SECRET_KEY="test-secret-key-for-frontend-contract-audit"
$env:ENABLE_SCHEDULER="0"
pytest tests/test_price_levels.py -q
```

---

## 六、完成标准（评级从 B+ 推进到 A-）

本轮全部 Phase 完成后应满足：

- [ ] SSE 鉴权路径唯一（cookie-only 或 stream-token 二选一，不并存）
- [ ] `MarketSessionBadge` 与 `MarketClosedBanner` 共用后端 `/api/market/status`
- [ ] 价位标注单条 create 与 batch create 在 `scope/contract_id` 语义完全一致
- [ ] `LevelChips`、`LevelEditor`、`usePriceLevels` 价格展示与 API payload 均尊重 `price_precision`
- [ ] `useLightweightChart.ts` 价格轴 formatter 不再硬编码 `toFixed(2)`
- [ ] `tsc/test/lint/build` 全绿
- [ ] Lighthouse 有一份可复现的基线报告（本地或 CI artifact）
- [ ] 后端契约测试能在本机稳定运行（venv + lock 文件）

达到以上标准后，前端评级从 **B+** 推进到 **A-**。

---

## 七、执行记录

| 日期 | 完成项 | 状态 |
|------|--------|------|
| 2026-05-29 | 路线图 v8 文档定稿 | 已完成 |
| 2026-05-29 | Phase 7: SSE 鉴权契约二选一（方案 B，废弃 stream-token） | 已完成 |
| 2026-05-29 | Phase 8: 交易时段 badge 后端权威化 | 已完成 |
| | Phase 9: 价位标注 batch scope/contract 补齐 | 待开始 |
| | Phase 9: 价位标注 batch scope/contract 补齐 | 待开始 |
| | Phase 10: 标注价格精度 + 图表 formatter 残留 | 待开始 |
| | Phase 11: Lighthouse 可复现基线证据 | 待开始 |
| | Phase 12: 后端本地测试环境文档化 | 待开始 |

---

*文档随迭代进展更新。*
