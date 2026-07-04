# Phase 5 迭代跟踪文档

> 创建时间：2026-07-04
> 当前状态：Phase 5-1 已完成，Phase 5-2 已完成，Phase 5-3 已完成，进入 Phase 5-4 性能优化

---

## 一、Phase 5 总体目标

在 Phase 4 策略系统（StrategyCompilerAgent + 回测引擎 + 前端面板）基础上，完成：

1. **策略优化引擎**（参数网格搜索 + 最优参数推荐）
2. **策略信号可视化**（K 线叠加买卖信号标记）
3. **性能优化**（数据库索引 + 缓存优化）
4. **监控告警与日志增强**（策略运行监控 + 告警事件）
5. **全量测试 + 提交到 master**

---

## 二、Phase 5-1：系统现状检查（已完成）

### 2.1 未提交修改（18 个文件）

| 类别 | 文件 | 说明 |
|------|------|------|
| 前端页面 | `frontend/app/strategies/page.tsx` | 策略面板大幅扩展 |
| 前端 API | `frontend/lib/api/{client,strategies,types}.ts` | 新增 API 类型和接口 |
| 后端路由 | `python/routers/strategies.py` | 新增 `portfolio-plan` 端点 |
| 后端路由 | `python/routers/portfolio.py` | 修改 |
| 后端 Schema | `python/schemas.py` | 新增 `StrategyPortfolioPlan*` schema |
| 后端模型 | `python/models.py` | 修改 |
| 测试 | `python/tests/test_strategies.py` | 新增（4 个测试） |
| 测试基建 | `python/tests/conftest.py` | 事务隔离优化（`flush` 替代 `commit`） |
| 迁移 | `python/alembic/versions/c7d8e9f0a1b2...` | 新增（TradeRecords 策略持仓扩展） |

### 2.2 测试状态

- `test_strategies.py`：4 个测试中 **2 通过，2 失败**
  - `test_generate_plan_strategy_not_found` ✅
  - `test_generate_plan_rejects_non_owner` ✅
  - `test_generate_plan_success` ❌（SQLite 隔离问题， UNIQUE constraint）
  - `test_generate_plan_requires_price_when_quote_missing` ❌（同上，返回 200 而非 400）
- **根因**：`conftest.py` 的 `drop_all` 在 SQLite 中跨测试清理不彻底，导致数据残留
- **处理策略**：**暂不修复**，进入 5-2 后继续推进。5-6 阶段统一回归测试时修复。

### 2.3 已完成的修复

- `routers/strategies.py`：权限拒绝统一使用 `ForbiddenError`（返回 403）
- `test_strategies.py`：对齐 `auth_headers` 的注册用户，避免 fixture 间用户不一致

---

## 三、Phase 5-2：策略优化引擎（已完成）

### 3.1 目标

对已有策略的关键参数（如均线窗口、RSI 阈值、布林带周期等）做网格搜索，自动运行多组合回测，输出最优参数和敏感性分析。

### 3.2 设计

**输入**：
- 策略 ID（已有 DSL）
- 参数搜索空间（如 `{"short": [5,10,20,30], "long": [20,30,40]}`）
- 评估指标权重（默认夏普比率优先，兼顾总收益、最大回撤）

**流程**：
1. 读取策略 DSL，提取可变参数（`{param_name}` 占位符）
2. 生成参数网格，枚举所有组合（上限 1000 防过拟合）
3. 对每个组合：编译 DSL → 运行回测 → 记录指标
4. 按综合评分排序（Sharpe 40% + 总收益 30% - 回撤 20% + 胜率 10%）
5. 输出最优参数 + 敏感性矩阵

**输出**：
- 最优参数组合
- 综合评分最高的 Top-N 组合
- 敏感性矩阵（参数变动对评分的平均影响）

### 3.3 新增文件

| 文件 | 说明 |
|------|------|
| `python/services/backtest/optimization_engine.py` | 网格搜索核心：参数替换、组合枚举、综合评分、敏感性矩阵 |
| `python/tests/test_optimization.py` | 9 个测试全部通过（单元 + 集成 Mock） |

### 3.4 修改文件

| 文件 | 说明 |
|------|------|
| `python/routers/strategies.py` | 新增 `POST /{id}/optimize` 端点 |
| `python/schemas.py` | 新增 `StrategyOptimizationRequest/Response/RunItem` |

### 3.5 提交记录

- `f5f0b230` feat(backend): 策略工作台与持仓扩展（optimization_engine.py 核心）
- `1d0fdb62` feat(backend): 策略参数优化 API 端点（routers/strategies.py）
- `d2f65651` test(optimization): 策略参数网格搜索引擎测试（9 passed）

---

## 四、Phase 5-3：策略信号可视化（已完成）

### 4.1 目标
在 K 线图上叠加策略回测的买卖信号标记（entry/exit），使用户直观看到进出场点位。

### 4.2 实现

**后端**：
- 新增 `GET /api/strategies/{strategy_id}/backtests/{backtest_id}/signals` 端点
- 返回 `BacktestSignalsResponse`：策略 ID + 回测 ID + 信号列表（time, type, price）+ 交易记录
- 从 `BacktestRunDB.result_json` 中解析已有的 `signals` 字段

**前端**：
- `KlineChart` 组件新增 `signals` prop：接收 `Array<{time: string, type: 'entry'|'exit', price: number}>`
- `useKlineChart` hook 新增 `setMarkers` 方法：通过 lightweight-charts `series.setMarkers()` 添加标记
- 信号标记：
  - `entry`（买入/做多）：红色箭头向上（`arrowUp`），位置 `belowBar`
  - `exit`（卖出/平多）：绿色箭头向下（`arrowDown`），位置 `aboveBar`
- 时间戳转换：ISO 字符串 → `Date.parse` → 秒级时间戳，与 K 线数据对齐

### 4.3 新增/修改文件

| 文件 | 说明 |
|------|------|
| `python/routers/strategies.py` | 新增 `GET /{id}/backtests/{bid}/signals` 端点 |
| `python/schemas.py` | 新增 `BacktestSignal` + `BacktestSignalsResponse` |
| `frontend/components/KlineChart.tsx` | 新增 `signals` prop，同步 markers |
| `frontend/hooks/useKlineChart.ts` | 新增 `setMarkers` 方法（lightweight-charts v5 类型断言） |

### 4.4 提交记录

- `3edb7215` feat(frontend+backend): 策略回测信号 K 线叠加可视化（Phase 5-3）

---

## 五、Phase 5-4 ~ 5-6 规划（待启动）

### 5-4：性能优化（进行中）
- 数据库索引：策略表、回测记录表、价格预警表加索引
- 缓存：回测结果 LRU 缓存，避免重复计算
- 批量回测：支持异步任务队列

### 5-5：监控告警与日志增强
- 策略运行监控：心跳检测、异常告警
- 告警事件系统：策略回测失败、参数异常等
- 结构化日志：策略优化全流程追踪

### 5-6：全量测试 + 提交到 master
- 修复 `test_strategies.py` 的 SQLite 隔离问题
- 全量 pytest 回归（目标 400+ 测试全绿）
- 前端 `tsc --noEmit` + `npm run lint` 通过
- 更新 AGENTS.md

---

## 五、已知阻塞项与风险

| 问题 | 影响 | 状态 |
|------|------|------|
| SQLite 测试隔离 | `test_strategies.py` 2 个失败 | 延后到 5-6 修复 |
| `portfolio/page.tsx` 曾被误删 | 已恢复，需确认恢复完整 | 已恢复，待验证 |
| `agents/detail/` 新增目录 | 可能是未完成的 Agent 详情页重构 | 暂不处理，关注是否有冲突 |

---

## 六、版本跟踪

| 日期 | 更新内容 | 负责人 |
|------|----------|--------|
| 2026-07-04 | 创建文档，完成 5-1 检查 | AI Assistant |
| 2026-07-04 | 完成 5-2 策略优化引擎（9 测试通过，3 次提交到 master） | AI Assistant |
| 2026-07-04 | 完成 5-3 策略信号可视化（K 线叠加买卖标记，前后端 5 文件修改） | AI Assistant |
| | | |
