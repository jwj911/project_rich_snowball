# P0 迭代文档：多条件策略编译 + 多品种组合能力

> **历史归档（2026-07-19）**：本文件记录 2026-07-04 的 P0 迭代结果，不再作为当前迭代入口。当前状态请查看 [`../iteration_plan_20260718_project_audit.md`](../iteration_plan_20260718_project_audit.md)。
>
**迭代日期**：2026-07-04
**关联审计**：[agent_audit.md](agent_audit.md)
**完成项**：GAP-01a、GAP-01b、GAP-02

---

## 概述

本次迭代补齐了审计文档中标注为最高优先级（P0）的三个核心缺口，使 Agent 系统从「单品分析 + 单条件策略研究」升级为「多品种组合 + 多条件策略」的量化投研工作流。

---

## 变更清单

### 1. GAP-01a：`resolve_symbols()` 多品种解析（utils.py）

**文件**：`python/services/agent/utils.py`

**变更内容**：
- 新增 `resolve_symbols()` 函数，返回 `list[str]`，支持：
  - **逗号分隔**：`螺纹钢, 热卷` / `RB, HC, I`
  - **中文连接词**：`螺纹钢和热卷` / `螺纹钢以及铁矿石`
  - **顿号分隔**：`螺纹钢、热卷、铁矿石`
  - **类别关键词**：`黑色系` → 自动加载该类别下所有活跃品种
  - **排除语法**：`除螺纹钢外的黑色系` → 从类别中排除指定品种
- 新增 `_split_variety_parts()` 辅助函数，统一分隔逻辑
- 新增 `_CATEGORY_KEYWORDS` 表，映射中文类别名到数据库 category 字段
- 现有 `resolve_symbol()` 保持不变，向后兼容

### 2. GAP-02：策略编译器多条件 AND/OR 组合（strategy_compiler_agent.py）

**文件**：`python/services/agent/strategy_compiler_agent.py`

**变更内容**：

- `StrategyParser` — 5 个模板方法全部升级：
  - `parse()` 现在返回多品种 `universe`（调用 `resolve_symbols()`）
  - 所有模板方法接收 `symbols: list[str]` 和 `logic: str` 参数
  - 每个模板调用 `_parse_extra_conditions()` 自动从查询中提取额外条件
  - 模板匹配顺序调整：均线 > MACD > 布林带 > 突破 > RSI（避免 RSI 误杀复合查询）

- 新增 3 个多条件解析函数：
  - **`_detect_logic(query)`**：检测 `且/并且/同时/and` → `"and"`，`或/或者/or` → `"or"`
  - **`_parse_extra_conditions(query)`**：从复合查询中提取额外的入场信号
    - RSI 阈值（低于/高于）
    - 成交量（放大/缩小/倍数）
    - 价格在均线上方/下方
    - MACD 柱/bar 正负
    - DIF 在 DEA 上方/下方
    - ADX 强度
    - 突破高低点
    - 额外的均线交叉条件
  - **`_parse_extra_exit_conditions(query)`**：提取额外的出场条件
    - RSI 超买出場
    - 跌破均线出场

- `_format_explanation()`：增加多条件逻辑标签展示（AND/OR）

### 3. GAP-01b：BacktestAgent 多品种回测 + 对比报告（backtest_agent.py）

**文件**：`python/services/agent/backtest_agent.py`

**变更内容**：
- `run()` 检测 DSL 的 `universe` 长度：
  - 单品种 → 调用现有 `run_dsl_backtest()`（向后兼容）
  - 多品种 → 调用新方法 `_run_multi_symbol()`
- 新增 `_run_multi_symbol()`：循环回测所有品种，捕获单品种错误
- 新增 `_format_comparison_report()`：生成 Markdown 对比表格
  - 表格列：品种 / 评分 / 总收益 / 年化收益 / 最大回撤 / 胜率 / 盈亏比 / 夏普 / 交易次数
  - 自动标注最佳表现品种
  - 列出失败的品种及原因

---

## 新增测试

### test_multi_condition_strategy.py（15 个用例）

**文件**：`python/tests/test_multi_condition_strategy.py`

| 测试类 | 用例数 | 覆盖内容 |
|--------|--------|----------|
| `TestMultiConditionAnd` | 4 | MA+RSI / MACD+成交量 / MA+价格位置 / MA+ADX |
| `TestMultiConditionOr` | 2 | RSI或布林带 / 突破或MA交叉 |
| `TestMultiSymbolUniverse` | 5 | 逗号/中文连接词/顿号/英文代码分隔 + 单品回归 |
| `TestMultiConditionValidation` | 4 | 多条件校验通过/失败/cross无indicator2 |

---

## 回归测试

运行完整的 agent 测试套件（41 个用例，全部通过）：

```
tests/test_agents_core.py .......................... 11 passed
tests/test_strategy_compiler.py .................... 13 passed
tests/test_multi_condition_strategy.py ............. 15 passed
tests/test_backtest_agent.py .......................  2 passed
───────────────────────────────────────────────────────
Total: 41 passed, 0 failed
```

---

## 使用示例

### 多条件 AND（均线交叉 + RSI 过滤）
```
用户：螺纹钢5日上穿20日均线且RSI低于40做多
→ 入场条件：[sma5 cross_above sma20, rsi24 < 40]，logic: and
```

### 多条件 OR（RSI 超卖 或 布林带支撑）
```
用户：螺纹钢RSI低于30或者布林带下轨做多
→ 入场条件：[rsi24 < 30, close cross_above boll_lower]，logic: or
```

### 多品种对比
```
用户：螺纹钢、热卷、铁矿石MACD金叉做多回测
→ DSL.universe: [RB, HC, I]
→ 回测结果：对比表 + 最佳表现标注
```
