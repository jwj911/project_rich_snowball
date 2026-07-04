# Phase 5 迭代跟踪文档

> 创建时间：2026-07-04
> 当前状态：Phase 5-1~5-4 已完成，Phase 5-5 已完成，进入 Phase 5-6 全量测试 + 提交到 master

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

## 五、Phase 5-4：性能优化（已完成）

### 5.1 目标
提升策略回测和网格搜索的性能，减少重复计算。

### 5.2 实现

**回测结果缓存**：
- `services/backtest/service.py` 中 `run_dsl_backtest` 接入 5 分钟 LRU 缓存（`services/cache.py`）
- 缓存 key 基于 `(symbol, period, direction, entry_conditions_hash, exit_conditions_hash, limit)` 生成
- 使用 `hashlib.md5` + `json.dumps(sort_keys=True)` 确保参数顺序无关性
- 缓存穿透防护：同 key 并发 miss 时仅一个线程回源（`cache.py` 内置）
- 缓存雪崩防护：TTL 附加 0~2 秒随机抖动（`cache.py` 内置）

**数据库索引现状**：
- 策略表 `strategies` 已有 `(user_id, symbol)` 和 `(created_at)` 复合索引
- 回测记录表 `backtest_runs` 已有 `(strategy_id, created_at)` 和 `(user_id, status)` 复合索引
- Agent 任务表已有完善索引
- **结论**：现有索引已覆盖主要查询路径，Phase 5-4 无需新增迁移

### 5.3 新增/修改文件

| 文件 | 说明 |
|------|------|
| `python/services/backtest/service.py` | 新增 `_backtest_cache_key` + `_run_dsl_backtest_inner` + 缓存包装 |
| `python/tests/test_performance.py` | 缓存 key 确定性测试（3 个测试全部通过） |

### 5.4 提交记录

- `0efe040d` perf(backtest): DSL 回测结果 5 分钟 LRU 缓存 + 性能测试

---

## 六、Phase 5-5：监控告警与日志增强（已完成）

### 6.1 目标
策略回测/优化失败时自动创建告警事件，并在关键流程中注入结构化日志。

### 6.2 实现

**告警事件系统扩展**：
- `services/alert_events.py` 新增：
  - `create_strategy_alert_for_backtest()`：回测失败时创建 `category="strategy"` 个人告警
  - `create_strategy_alert_for_optimization()`：优化失败时创建个人告警
  - 告警类型常量：`STRATEGY_BACKTEST_SOURCE_TYPE`、`STRATEGY_OPTIMIZATION_SOURCE_TYPE`

**回测/优化路由集成**：
- `routers/strategies.py` 回测端点 `POST /{id}/backtest`：
  - except 块中调用 `create_strategy_alert_for_backtest()`，失败静默（不阻塞主流程）
- `routers/strategies.py` 优化端点 `POST /{id}/optimize`：
  - 新增 try/except 块，失败时调用 `create_strategy_alert_for_optimization()` 后抛出 `ServiceError`

**结构化日志**：
- `optimization_engine.py`：
  - `strategy_optimization_start`：记录 symbol、period、组合数、参数空间
  - `strategy_optimization_complete`：记录组合数、耗时、最优评分、最优参数
- `service.py`（回测）：
  - `dsl_backtest_complete`：记录 symbol、period、bars、trade_count、score、cache_key

### 6.3 新增/修改文件

| 文件 | 说明 |
|------|------|
| `python/services/alert_events.py` | 新增策略告警创建函数 + 常量 |
| `python/routers/strategies.py` | 回测/优化失败时创建告警事件 |
| `python/services/backtest/optimization_engine.py` | 新增优化启动/完成结构化日志 |
| `python/services/backtest/service.py` | 新增回测完成结构化日志 |
| `python/tests/test_strategy_alerts.py` | 告警事件创建测试（4 个全部通过） |

### 6.4 提交记录

- `8a243a82` feat(alerts): 策略回测/优化失败自动创建告警事件 + 结构化日志（Phase 5-5）

---

## 七、Phase 5-6：全量测试 + 提交到 master（进行中）
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
| 2026-07-04 | 完成 5-4 性能优化（回测 5 分钟 LRU 缓存 + 3 测试通过） | AI Assistant |
| 2026-07-04 | 完成 5-5 监控告警与日志（告警事件 + 结构化日志，4 测试通过） | AI Assistant |
| | | |
