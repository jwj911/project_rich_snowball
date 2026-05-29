# 前端迭代路线图 v7（还债 + 契约对齐迭代）

> 基于《前端深度审计报告 v5（前后端交叉验证版）》（评分 B，建议"需进行一次还债 + 契约对齐迭代"）制定。  
> 制定日期：2026-05-29  
> 原则：**先修复契约裂缝，再统一数据精度，最后验证性能基线。在评级推进到 A- 之前不开大功能。**

---

## 一、总体策略

当前前端已从"质量门禁不可证明"推进到"基础门禁可信"（tsc / Vitest / lint / build 全绿），但存在 4 个阻碍进入 A 档的契约级问题：

1. `/api/realtime/batch` 与单品种接口字段不一致 → 涨跌停标识在实时链路漂移
2. 价位标注只按 `variety_id` 存取 → 与 K 线的 continuous/main/single 口径未对齐
3. K 线图价格格式多处硬编码 `toFixed(2)` → 未使用品种级 `price_precision`
4. Playwright 性能 E2E 未跑通 → 性能基线未证明

**核心原则：契约对齐优先、精度统一跟进、标注改造兜底、性能闭环收尾。**

---

## 二、阶段规划

### Phase 1：实时行情 batch 契约修复（P0，1 天）

目标：`/api/realtime/{symbol}`、`/api/realtime/batch`、SSE payload 使用同一个 `RealtimeQuote` 形态。

| 行动项 | 关键动作 | 文件 | 验收标准 |
|--------|----------|------|----------|
| 后端 batch 补齐字段 | `_fetch_realtime_batch()` 的 `quotes.append()` 中补 `limit_up`、`limit_down` | `python/services/realtime.py` | batch 响应包含涨跌停字段 |
| 后端 batch 测试 | `test_realtime_batch.py` 增加 batch 返回涨跌停字段断言 | `python/tests/test_realtime_batch.py` | pytest 通过 |
| 前端 merge 补字段 | `useProductListRealtime` merge 逻辑补 `limit_up`、`limit_down` 覆盖 | `frontend/hooks/useProductListRealtime.ts:55-64` | 实时更新后涨跌停标签同步 |
| 前端类型校验 | 确认 `RealtimeQuote` 类型与所有实时接口响应一致 | `frontend/lib/api/types.ts:69-80` | tsc --noEmit 通过 |
| 组件验证 | `QuoteCard` / `QuoteTable` / `ProductHeader` 的 `LimitBadge` 在 SSE/polling 更新后仍正确 | 相关组件测试 | 测试通过 |

**产出物**：前后端实时契约一致，涨跌停标识在所有更新链路中不漂移。

**回归命令**：
```powershell
cd frontend && npx.cmd tsc --noEmit && npm.cmd run test && npm.cmd run lint && npm.cmd run build
cd python && $env:SECRET_KEY="test"; $env:ENABLE_SCHEDULER="0"; pytest tests/test_realtime_batch.py -q
```

---

### Phase 2：K 线图价格精度统一（P1，1~2 天）

目标：图表区和行情卡片使用同一套 `price_precision`，消除所有硬编码 `toFixed(2)`。

| 行动项 | 关键动作 | 文件 | 验收标准 |
|--------|----------|------|----------|
| 新增图表价格格式化工具 | `lib/format.ts` 新增 `formatChartPrice(value, precision)` | `frontend/lib/format.ts` | 工具函数有单测覆盖 |
| Header 精度替换 | `KlineChartHeader.tsx` 中所有 `toFixed(2)` 替换为 `formatChartPrice(..., pricePrecision)` | `frontend/components/kline/KlineChartHeader.tsx:24-28` | precision=0 不显示小数 |
| Tooltip 精度替换 | `CrosshairTooltip.tsx` 中 `toFixed(2)` 替换 | `frontend/components/kline/CrosshairTooltip.tsx:17` | tooltip 价格位数与品种一致 |
| Chart 配置精度替换 | `useKlineChart.ts` 中 `priceFormatter: (price) => price.toFixed(2)` 改为动态 precision | `frontend/hooks/useKlineChart.ts:75` | 右侧价格轴刻度精度正确 |
| Chart 配置精度替换（旧 hook） | `useLightweightChart.ts` 中同样替换 | `frontend/hooks/useLightweightChart.ts:90` | 同上 |
| KlineChart 透传 prop | `KlineChart` 增加 `pricePrecision` prop，`KlineSection` 从产品详情传入 `product.price_precision` | `frontend/components/KlineChart.tsx`、`frontend/components/product/KlineSection.tsx` | prop 正确透传 |
| aria-label 精度 | `KlineChart.tsx` 中 aria-label 的 `toFixed(2)` 替换 | `frontend/components/KlineChart.tsx` | 无障碍标签精度一致 |
| 单测覆盖 | 补 `formatChartPrice` 单测（precision=0/1/2） | `frontend/tests/lib/format.test.ts` | 3 种精度均通过 |

**产出物**：同一品种在 `ProductHeader`、K 线 header、tooltip、价格轴、aria-label 中价格位数完全一致。

**回归命令**：
```powershell
cd frontend && npx.cmd tsc --noEmit && npm.cmd run test && npm.cmd run lint && npm.cmd run build
```

---

### Phase 3：空值涨跌幅 neutral 态（P1，0.5 天）

目标：`null` 涨跌幅不再被视觉表达为上涨。

| 行动项 | 关键动作 | 文件 | 验收标准 |
|--------|----------|------|----------|
| 扩展 tone 语义 | `lib/format.ts` 中 `getChangeTone` 扩展为返回 `'up' \| 'down' \| 'neutral'`；`null/undefined` 返回 `neutral` | `frontend/lib/format.ts` | tsc 通过，现有调用兼容 |
| PriceChange 适配 | `PriceChange.tsx` 中 `value == null` 时不显示 TrendingUp/TrendingDown 图标，使用灰色 class | `frontend/components/market/PriceChange.tsx:11-16` | null 时无图标、灰色文案 |
| 单测覆盖 | `PriceChange.test.tsx` 补 `value=null` 场景 | `frontend/tests/components/PriceChange.test.tsx` | 断言 neutral 态 |
| value=0 确认 | 与产品确认 `value=0` 显示为持平还是上涨；默认按 neutral 处理 | — | 确认后调整 |

**产出物**：无涨跌幅数据时视觉上不再误导为上涨。

**回归命令**：
```powershell
cd frontend && npx.cmd tsc --noEmit && npm.cmd run test && npm.cmd run lint && npm.cmd run build
```

---

### Phase 4：KlineData 补齐 contract_id（P2，0.5 天）

目标：前端能精确知道每根 K 线 bar 属于哪个合约 id。

| 行动项 | 关键动作 | 文件 | 验收标准 |
|--------|----------|------|----------|
| 类型扩展 | `KlineData` 增加 `contract_id?: number \| null` | `frontend/lib/api/types.ts:82-90` | tsc 通过 |
| 数据归一化保留 | `normalizeKlineData` / `klineData.ts` 保留 `contractId` | `frontend/lib/klineData.ts` | contract_id 贯穿数据流 |
| CrosshairQuote 保留 | `CrosshairQuote` 类型增加 `contractId?: number \| null` | `frontend/lib/klineChart.ts` | tooltip 可拿到内部 id |
| useLightweightChart 透传 |  crosshair move 时把 `contractId` 一并设置 | `frontend/hooks/useLightweightChart.ts:140-148` | 数据结构完整 |
| 单测覆盖 | `klineData.test.ts` 补 `contract_id` 字段断言 | `frontend/tests/lib/klineData.test.ts` | 通过 |

**产出物**：K 线数据结构保留 `contract_id`，为后续"点击 bar 操作对应合约标注"等功能预留能力。

**回归命令**：
```powershell
cd frontend && npx.cmd tsc --noEmit && npm.cmd run test && npm.cmd run lint && npm.cmd run build
```

---

### Phase 5：标注 scope/contract 口径改造（P0，2~3 天）

目标：用户在什么 K 线口径下画线，就只在对应口径下展示。这是范围最大的改造，建议单独开小分支完成。

**后端变更（配合）**：

| 行动项 | 关键动作 | 验收标准 |
|--------|----------|----------|
| 表结构扩展 | `price_levels` 增加 `scope`（`'continuous' \| 'main' \| 'contract'`）和 `contract_id nullable` | Alembic 迁移通过 |
| 约束添加 | `scope='contract'` 时 `contract_id` 必填；其他 scope 时为空 | 数据库约束生效 |
| API 升级 | `list/create/update` batch 接口支持 scope + contract_id 参数 | pytest 通过 |
| 数据兼容 | 现有数据默认 scope='continuous'（与当前行为一致） | 旧标注不丢失 |

**前端变更**：

| 行动项 | 关键动作 | 文件 | 验收标准 |
|--------|----------|------|----------|
| 类型定义 | 新增 `PriceLevelScope = 'continuous' \| 'main' \| 'contract'` | `frontend/lib/api/types.ts` | tsc 通过 |
| Hook 接口改造 | `usePriceLevels` 入参从 `(varietyId, userId, symbol)` 改为对象形式，增加 `source` / `contractId` | `frontend/hooks/usePriceLevels.ts:5` | API 兼容过渡 |
| Hook 内部适配 | 根据 source 决定 scope；`source='single'` 时传入 `contractId`；API 调用带 scope/contract_id | `frontend/hooks/usePriceLevels.ts` | 请求参数正确 |
| localStorage key 升级 | key 从 `price-levels:v1:{userId}:{symbol}` 改为 `price-levels:v2:{userId}:{symbol}:{scope}:{contractIdOrAll}` | `frontend/hooks/usePriceLevels.ts:17-20` | 不同 scope 标注隔离 |
| 旧数据导入 | v1 数据导入时默认进入 `continuous` scope | `frontend/hooks/usePriceLevels.ts` | 旧数据不丢失 |
| KlineSection 传参 | 向 `usePriceLevels` 传入 `selectedKlineSource` 和 `selectedContractId` | `frontend/components/product/KlineSection.tsx` | 参数正确透传 |
| 切换重载 | 切换 K 线 source / contract 时重新加载对应标注 | `frontend/components/product/KlineSection.tsx` | 无残留标注 |
| 单测覆盖 | 切换 continuous/main/single 时分别加载不同标注；single 合约 A 标注不出现在合约 B | `frontend/tests/lib/priceLevels.test.ts` | 全部通过 |

**产出物**：合约切换时不再出现标注残留；主力/连续/具体合约三种 K 线的标注语义清晰。

**回归命令**：
```powershell
cd frontend && npx.cmd tsc --noEmit && npm.cmd run test && npm.cmd run lint && npm.cmd run build
cd python && $env:SECRET_KEY="test"; $env:ENABLE_SCHEDULER="0"; pytest tests/test_price_levels.py -q
```

---

### Phase 6：性能 E2E / Lighthouse 闭环（P2，1~2 天）

目标：Playwright 性能 E2E 能跑完，或提供可复现的替代方案。

| 行动项 | 关键动作 | 验收标准 |
|--------|----------|----------|
| 诊断 EPERM | 排查 Chromium 启动 `spawn EPERM` 根因：权限 / 防病毒软件 / Playwright 安装完整性 | 定位根因 |
| 修复启动 | 按根因修复：重装 Playwright browsers / 调整权限 / 换用 Chromium 路径 | `npx.cmd playwright test e2e/performance.spec.ts` 通过 |
| 或替代方案 | 若仍无法修复，提供 Lighthouse CI 配置作为替代基线 | `.github/workflows/frontend-ci.yml` 中包含 Lighthouse |
| 基线记录 | 记录并版本化：DOMContentLoaded、loadComplete、LCP、heap used | 写入 `frontend/docs/performance-baseline.md` |
| 登录态 setup | 验证 `auth.setup.ts` 在 E2E 中正确生成登录态 | setup 通过 |

**产出物**：性能 spec 能跑完，或有可复现的 Lighthouse 报告 + 基线文档。

**回归命令**：
```powershell
cd frontend
npx.cmd playwright test e2e/performance.spec.ts
# 或
npm.cmd run lighthouse
```

---

## 三、执行顺序与依赖

```
Phase 1 实时 batch 契约修复（P0，1d）
    ↓
Phase 2 K 线价格精度统一（P1，1~2d）
    ↓
Phase 3 空值涨跌幅 neutral 态（P1，0.5d）
    ↓
Phase 4 KlineData contract_id 补齐（P2，0.5d）
    ↓
Phase 5 标注 scope/contract 口径改造（P0，2~3d）← 建议独立分支
    ↓
Phase 6 性能 E2E 闭环（P2，1~2d）
```

**顺序理由**：
- Phase 1 是最小最明确的契约 bug，先做。
- Phase 2/3/4 是低风险 UI 语义修正，互相独立可并行，但按文件冲突顺序串行更稳妥。
- Phase 5 涉及后端表迁移和前端 hook 大改，范围最大，放在后面单独分支。
- Phase 6 是验证性质工作，放在最后。

---

## 四、明确冻结（暂不启动）

以下功能在综合健康度达到 A- 之前**坚决不开工**：

- ❌ 策略回测系统（阻塞点：K 线未形成回测级查询服务）
- ❌ 高级图表指标（MACD/KDJ/布林带等 overlay）（阻塞点：指标计算层未就绪）
- ❌ 多品种对比面板（阻塞点：需要稳定的实时批量订阅契约，Phase 1 后才可评估）
- ❌ 移动端 App / PWA（阻塞点：先保证 Web 端评级到 A-）

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
pytest tests/test_realtime_batch.py tests/test_price_levels.py -q
```

---

## 六、完成标准（评级推进到 A-）

本轮全部 Phase 完成后应满足：

- [x] `/api/realtime/batch` 与前端 `RealtimeQuote` 类型完全一致（Phase 1）
- [ ] 合约/连续/主力 K 线下的标注不会串口径（Phase 5）
- [x] K 线图所有价格展示尊重 `price_precision`（Phase 2）
- [x] 空涨跌幅不显示上涨/下跌倾向（Phase 3）
- [ ] `KlineData` 前端类型保留 `contract_id`（Phase 4）
- [x] `tsc/test/lint/build` 全绿
- [ ] Playwright 性能 E2E 或 Lighthouse 有一份可复现结果（Phase 6）

达到以上标准后，前端评级从 **B** 推进到 **A-**。

---

## 七、执行记录

| 日期 | 完成项 | 状态 |
|------|--------|------|
| 2026-05-29 | 路线图文档定稿 | ✅ |
| 2026-05-29 | Phase 1: 实时 batch 契约修复 — batch 补齐 limit_up/limit_down，前端 merge 同步，测试断言，合并 master | ✅ |
| 2026-05-29 | Phase 2: K 线价格精度统一 — 消灭 toFixed(2)，全链路透传 pricePrecision，合并 master | ✅ |
| 2026-05-29 | Phase 3: 空值涨跌幅 neutral 态 — getChangeTone 返回 neutral，PriceChange 不渲染上涨图标，合并 master | ✅ |

---

*文档随迭代进展更新。*
