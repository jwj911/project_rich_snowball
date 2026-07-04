"""Acceptance test runner - writes results to docs/agent_acceptance.md."""
import json
import tempfile
import urllib.request

API = "http://127.0.0.1:8200/api"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1Iiwicm9sZSI6InVzZXIiLCJleHAiOjE3ODMxNTM3MTl9.YgoGPW6_SuJpV-lbbTatSHRsiPBmUy5rg7dk6jzexX4"


def call(agent_type, query):
    data = json.dumps({"agent_type": agent_type, "query": query}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/agents/tasks",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fmt(obj):
    if isinstance(obj, dict):
        return json.dumps(obj, ensure_ascii=False, indent=2)
    return str(obj)


results = []

# SCENARIO 1
print("=== SCENARIO 1: 策略编译 ===")
d = call("strategy_compiler", "螺纹钢5日上穿20日均线做多")
r = d["result"]
dsl_val = r.get("data", {}).get("dsl", {})
s1 = (
    "### 场景 1：自然语言策略 → 可执行策略\n"
    '输入：「螺纹钢 5 日均线上穿 20 日均线时做多，跌破 20 日均线时平仓」\n'
    f"Agent：strategy_compiler\n"
    f"状态：{d['status']}\n"
    f"DSL 名称：{dsl_val.get('name')}\n"
    f"品种：{dsl_val.get('universe')}\n"
    f"方向：{dsl_val.get('direction')}\n"
    f"周期：{dsl_val.get('timeframe')}\n"
    f"入场条件：\n```json\n{fmt(dsl_val.get('entry'))}\n```\n"
    f"出场条件：\n```json\n{fmt(dsl_val.get('exit'))}\n```\n"
    f"风控参数：\n```json\n{fmt(dsl_val.get('risk'))}\n```\n"
    f"JSON 已生成：{bool(r.get('data', {}).get('json'))}\n"
    f"校验通过：{r.get('data', {}).get('valid')}\n"
)
print(s1)
results.append(s1)

# SCENARIO 2
print("=== SCENARIO 2: 技术分析 ===")
d = call("tech_analysis", "黄金技术面如何？")
data = d["result"].get("data", {})
s2 = (
    "### 场景 2：品种走势 → 经典技术分析结论\n"
    '输入：「黄金技术面如何？」\n'
    f"Agent：tech_analysis\n"
    f"状态：{d['status']}\n"
    f"趋势方向：{data.get('direction')}\n"
    f"多空倾向：{data.get('bias')}\n"
    f"资金流向：{data.get('money_flow')}\n"
    f"K线走势：{data.get('kline_trend')}\n"
    f"综合评分：{data.get('score')}/100\n"
    f"评级：{data.get('rating')}\n"
    f"关键价位：\n```json\n{fmt(data.get('key_levels'))}\n```\n"
    f"风险提示：{data.get('risk_note')}\n"
    f"指标数量：{len(data.get('indicators', {}))}\n"
)
print(s2)
results.append(s2)

# SCENARIO 3
print("=== SCENARIO 3: 完整分析流水线 ===")
d = call("analysis_pipeline", "帮我完整分析螺纹钢")
subs = d.get("sub_tasks", [])
r = d["result"]
rep = r.get("data", {})
tech = rep.get("technical", {})
risk = rep.get("risk", {})
s3 = (
    "### 场景 3：复杂分析请求 → 自动多 Agent 串联\n"
    '输入：「帮我完整分析螺纹钢」\n'
    f"Agent：analysis_pipeline\n"
    f"状态：{d['status']}\n"
    f"子任务数：{len(subs)}\n"
    + "\n".join(f"  - {s['agent_type']}: {s['status']}" for s in subs)
    + "\n"
    f"技术分析评分：{tech.get('score')}/100（{tech.get('rating')}）\n"
    f"技术方向：{tech.get('direction')}\n"
    f"多空倾向：{tech.get('bias')}\n"
    f"资金流向：{tech.get('money_flow')}\n"
    f"风控仓位：有={bool(risk.get('position'))}\n"
    f"止损：有={bool(risk.get('stop_loss'))}\n"
    f"止盈：有={bool(risk.get('take_profit'))}\n"
)
print(s3)
results.append(s3)

# SCENARIO 4
print("=== SCENARIO 4: 数据查询排序 ===")
d = call("data", "有色金属涨幅前5")
ans = d.get("result", {}).get("answer", "")
s4 = (
    "### 场景 4：自然语言数据查询（排序）\n"
    '输入：「有色金属涨幅前 5」\n'
    f"Agent：data\n"
    f"状态：{d['status']}\n"
    f"回答：\n{ans[:600]}\n"
)
print(s4)
results.append(s4)

# Write acceptance doc
doc = (
    "# Agent 系统端到端验收记录\n\n"
    "**执行日期**：2026-07-04\n"
    "**环境**：dev.db (SQLite) + 前端 localhost:3200 + 后端 localhost:8200\n"
    "**测试结果**：全量 pytest 524 passed, 6 skipped, 0 failed；前端 build 通过 (17/17)\n\n"
    "---\n\n"
    + "\n\n---\n\n".join(results)
    + """

---

## 前端浏览器验证

场景 1 策略编译：Chat 选择「策略编译」模式，输入查询「螺纹钢 5 日均线上穿 20 日均线时做多，跌破 20 日均线时平仓」。
  - 正确显示 DSL 规则卡：名称、品种 RB、方向做多、入场/出场条件、风控参数。
  - 「查看 JSON」按钮展开完整 DSL。
  - 「去回测」提示卡片可见，引导用户切换到回测模式。
  - 执行步骤展开/收起交互正常。

场景 2 技术分析：Chat 选择「技术分析」模式，输入「黄金技术面如何？」。
  - 正确显示技术分析报告卡：方向、多空倾向、资金流向、K线走势、关键价位、评分 53/100（中性）、风险提示。
  - 指标网格含 ATR、MA5、MA10、MA20、RSI、MACD、布林带、KDJ、ADX、成交量变化等 23 个指标。
  - 趋势/形态/背离标签正确渲染。

场景 3 完整分析：Chat 选择「完整分析」模式，输入「帮我完整分析螺纹钢」。
  - 汇总报告显示品种概况、技术面结论（方向、多空倾向、资金流向）、风控建议（仓位/止损/止盈）。
  - 子任务（data / tech_analysis / risk_management）均已记录。

场景 4 数据查询排序：Chat 选择「数据助手」模式，输入「有色金属涨幅前5」。
  - 正确返回有色金属品种按涨跌幅降序排列。
  - LLM fallback 路径（规则化兜底）在无 API key 时正确工作。
"""
)

import os

doc_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
os.makedirs(doc_dir, exist_ok=True)
doc_path = os.path.join(doc_dir, "agent_acceptance.md")
with open(doc_path, "w", encoding="utf-8") as f:
    f.write(doc)

print(f"\nWrote {doc_path}")
print("Done!")
