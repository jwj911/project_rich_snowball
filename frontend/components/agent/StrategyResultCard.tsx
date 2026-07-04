'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, Code, FileText, TrendingUp, AlertTriangle } from 'lucide-react'
import type { StrategyCompilerData, StrategyDSL } from './backtest-types'

export default function StrategyResultCard({ result }: { result: Record<string, unknown> | null | undefined }) {
  const [showJson, setShowJson] = useState(false)
  const data = result as StrategyCompilerData | null
  if (!data || !data.dsl) return null

  const dsl = data.dsl

  return (
    <div className="mt-3 rounded-lg border border-slate-700 bg-slate-900/50 p-3">
      <div className="mb-2 flex items-center gap-2">
        <TrendingUp size={14} className="text-amber-400" />
        <span className="text-sm font-medium text-white">策略编译结果</span>
      </div>

      <div className="space-y-2 text-sm text-slate-300">
        <div className="flex items-center justify-between">
          <span className="text-slate-400">名称</span>
          <span className="font-medium text-white">{dsl.name}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-400">品种</span>
          <span className="text-white">{dsl.universe.join(', ')}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-400">方向</span>
          <span className={dsl.direction === 'long' ? 'text-red-400' : 'text-green-400'}>
            {dsl.direction === 'long' ? '做多' : '做空'}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-400">周期</span>
          <span className="text-white">{dsl.timeframe}</span>
        </div>
      </div>

      <div className="mt-3 space-y-2">
        <ConditionBlock title="入场条件" conditions={dsl.entry.conditions} />
        <ConditionBlock title="出场条件" conditions={dsl.exit.conditions} />
        <RiskBlock risk={dsl.risk} />
      </div>

      <div className="mt-3">
        <button
          type="button"
          onClick={() => setShowJson(!showJson)}
          className="inline-flex items-center gap-1 text-xs text-slate-500 transition hover:text-amber-400"
        >
          <Code size={10} />
          {showJson ? '隐藏 JSON' : '查看 JSON'}
          {showJson ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
        </button>
        {showJson && (
          <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-slate-950 p-2 text-xs text-slate-300">
            {data.json || JSON.stringify(dsl, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}

function ConditionBlock({ title, conditions }: { title: string; conditions: Array<{ indicator: string; operator: string; indicator2?: string; value?: number }> }) {
  if (!conditions || conditions.length === 0) return null

  const operatorMap: Record<string, string> = {
    cross_above: '上穿',
    cross_below: '下穿',
    above: '大于',
    below: '小于',
    greater_than: '大于',
    less_than: '小于',
    equal: '等于',
    between: '介于',
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-2">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-amber-400">
        <FileText size={10} />
        {title}
      </div>
      <div className="space-y-1">
        {conditions.map((cond, i) => (
          <div key={i} className="text-xs text-slate-300">
            <span className="font-medium text-white">{cond.indicator}</span>
            {' '}
            <span className="text-slate-400">{operatorMap[cond.operator] || cond.operator}</span>
            {' '}
            {cond.indicator2 ? (
              <span className="font-medium text-white">{cond.indicator2}</span>
            ) : cond.value !== undefined ? (
              <span className="font-medium text-white">{cond.value}</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}

function RiskBlock({ risk }: { risk: StrategyDSL['risk'] }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-2">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-red-400">
        <AlertTriangle size={10} />
        风控参数
      </div>
      <div className="space-y-1 text-xs text-slate-300">
        <div className="flex items-center justify-between">
          <span className="text-slate-400">仓位</span>
          <span>{risk.position_size.type} ({risk.position_size.value})</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-400">止损</span>
          <span>{risk.stop_loss.type} ({risk.stop_loss.value})</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-400">止盈</span>
          <span>{risk.take_profit.type} ({risk.take_profit.value})</span>
        </div>
      </div>
    </div>
  )
}
