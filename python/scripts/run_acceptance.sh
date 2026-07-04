#!/usr/bin/env bash
# Acceptance test runner for Agent system (all 4 scenarios)
set -euo pipefail
API="http://127.0.0.1:8200/api"
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1Iiwicm9sZSI6InVzZXIiLCJleHAiOjE3ODMxNTM3MTl9.YgoGPW6_SuJpV-lbbTatSHRsiPBmUy5rg7dk6jzexX4"
TMPFILE=$(mktemp)

call() {
    local agent_type="$1"
    local query="$2"
    echo "{\"agent_type\":\"$agent_type\",\"query\":\"$query\"}" > "$TMPFILE"
    curl -s -X POST "$API/agents/tasks" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d @"$TMPFILE"
}

echo "=== SCENARIO 1: 策略编译 ==="
call "strategy_compiler" "螺纹钢5日上穿20日均线做多" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('Status:', d['status'])
r=d['result']
dsl=r.get('data',{}).get('dsl',{})
print('DSL name:', dsl.get('name'))
print('DSL universe:', dsl.get('universe'))
print('DSL direction:', dsl.get('direction'))
print('DSL entry:', json.dumps(dsl.get('entry',{}), ensure_ascii=False)[:200])
print('DSL exit:', json.dumps(dsl.get('exit',{}), ensure_ascii=False)[:200])
print('DSL risk keys:', list(dsl.get('risk',{}).keys()))
"

echo ""
echo "=== SCENARIO 2: 技术分析 ==="
call "tech_analysis" "黄金技术面如何？" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('Status:', d['status'])
data=d['result'].get('data',{})
print('direction:', data.get('direction'))
print('bias:', data.get('bias'))
print('money_flow:', data.get('money_flow'))
print('kline_trend:', data.get('kline_trend'))
print('score:', data.get('score'))
print('rating:', data.get('rating'))
print('risk_note:', data.get('risk_note'))
print('key_levels:', json.dumps(data.get('key_levels',{}), ensure_ascii=False)[:200])
"

echo ""
echo "=== SCENARIO 3: 完整分析流水线 ==="
call "analysis_pipeline" "帮我完整分析螺纹钢" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('Status:', d['status'])
subs=d.get('sub_tasks',[])
print('sub_tasks:', len(subs))
for s in subs:
    print('  -', s['agent_type'], s['status'])
r=d['result']
data=r.get('data',{})
print('report sections:', list(data.keys()))
tech=data.get('technical',{})
print('tech score:', tech.get('score'))
print('tech rating:', tech.get('rating'))
print('tech direction:', tech.get('direction'))
risk=data.get('risk',{})
print('risk has position:', 'position' in risk)
print('risk has stop_loss:', 'stop_loss' in risk)
"

echo ""
echo "=== SCENARIO 4: 数据查询排序 ==="
call "data" "有色金属涨幅前5" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('Status:', d['status'])
ans=d.get('result',{}).get('answer','')
print('answer:', ans[:300])
"

rm -f "$TMPFILE"
