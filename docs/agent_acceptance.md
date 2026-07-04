# Agent 系统端到端验收记录

**执行日期**：2026-07-04
**环境**：dev.db (SQLite) + 前端 localhost:3200 + 后端 localhost:8200
**测试结果**：全量 pytest 524 passed, 6 skipped, 0 failed；前端 build 通过 (17/17)

---

### 场景 1：自然语言策略 → 可执行策略

输入：「螺纹钢 5 日均线上穿 20 日均线时做多，跌破 20 日均线时平仓」

Agent：strategy_compiler

状态：completed

DSL 名称：RB 均线交叉策略 (5/20)
品种：['RB']
方向：long
周期：1d

入场条件：
```json
{
  "conditions": [
    {
      "indicator": "sma5",
      "operator": "cross_above",
      "indicator2": "sma20"
    }
  ],
  "logic": "and"
}
```

出场条件：
```json
{
  "conditions": [
    {
      "indicator": "sma5",
      "operator": "cross_below",
      "indicator2": "sma20"
    }
  ],
  "logic": "and"
}
```

风控参数：
```json
{
  "position_size": "fixed_lots 1",
  "stop_loss": "atr_multiple 2.0",
  "take_profit": "risk_reward_ratio 2.0"
}
```

JSON 已生成：True，校验通过：True

---

### 场景 2：品种走势 → 经典技术分析结论

输入：「黄金技术面如何？」

Agent：tech_analysis

状态：completed

- 趋势方向：向上
- 多空倾向：震荡
- 资金流向：缩量上涨，上涨动能减弱（量价背离风险）
- K线走势：近 5 日 3 涨 1 跌，累计变动 +2.35
- 综合评分：53.0/100（中性）
- 关键价位：支撑 448.04 / 阻力 462.39 / MA5 454.48 / MA10 454.09 / MA20 454.32 / MA60 453.24
- 风险提示：ATR 6.64，波动一般；当前评分 53.0/100（中性），建议结合仓位与止损规则。
- 指标数量：23（含 ATR, MA5, MA10, MA20, SMA60, RSI, MACD, 布林带, KDJ, ADX, 量比, 成交量变化等）

---

### 场景 3：复杂分析请求 → 自动多 Agent 串联

输入：「帮我完整分析螺纹钢」

Agent：analysis_pipeline

状态：completed

子任务数：3（data / tech_analysis / risk_management），3 个子任务全部 completed。

汇总报告包含：
- 品种概况（名称、交易所、最新价、涨跌幅）
- 技术分析（评分 30.0/100 中性偏弱、方向向下、多空偏空、资金流向）
- 风控方案（仓位、止损、止盈均生成）

---

### 场景 4：自然语言数据查询（排序）

输入：「有色金属涨幅前 5」

Agent：data

状态：completed

回答：
```
类别：有色金属 品种排名（按 change_percent 降序）：
1. 铜 (CU): 最新价 68450.0，涨跌幅 2.15%，成交量 125680
...
```
LLM fallback 路径（规则化兜底）在无 API key 时正确工作。

---

## 前端浏览器验证

场景 1 策略编译：Chat 选择「策略编译」模式，输入查询后正确显示 DSL 规则卡（名称、品种、方向、入场/出场条件、风控参数、查看 JSON 按钮、去回测提示），执行步骤展开/收起交互正常。

场景 2 技术分析：Chat 选择「技术分析」模式，输入「黄金技术面如何？」后正确显示技术分析报告卡（方向、多空倾向、资金流向、K线走势、关键价位、评分 53/100 中性、风险提示），指标网格含 ATR、MA5、MA10、MA20、RSI、MACD、布林带、KDJ、ADX、成交量变化等 23 个指标。

场景 3 完整分析：Chat 选择「完整分析」模式，输入「帮我完整分析螺纹钢」后显示汇总报告（品种概况、技术面结论含方向/多空/资金流向、风控建议含仓位/止损/止盈），子任务均已记录。

场景 4 数据查询排序：Chat 选择「数据助手」模式，输入「有色金属涨幅前5」后正确返回有色金属品种按涨跌幅降序排列。

## 全量测试

```
524 passed, 6 skipped, 0 failed in 192.48s
```

前端 build：17/17 pages static generated, no errors.
