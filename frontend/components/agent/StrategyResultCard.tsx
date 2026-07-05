'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, Code, FileText, TrendingUp, AlertTriangle, BarChart3 } from 'lucide-react'
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

      <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-200">
        <BarChart3 size={14} className="mt-0.5 shrink-0" />
        <div>
          <div className="font-medium">去回测</div>
          <div className="mt-0.5 text-amber-200/80">
            切换到「策略回测」模式并输入相同策略描述，即可运行历史回测并查看收益、回撤、胜率等指标。
          </div>
        </div>
      </div>
    </div>
  )
}

function ConditionBlock({ title, conditions }: { title: string; conditions: Array<{ indicator: string; operator: string; indicator2?: string; value?: number }> }) {
  if (!conditions || conditions.length === 0) return null

  const operatorMap: Record<string, string> = {
    cross_above: '上穿',
    cross_below: '下穿',
    above: '突破',
    below: '跌破',
    greater_than: '大于',
    less_than: '小于',
    equal: '等于',
    between: '介于',
  }

  // Human-readable indicator labels
  const indicatorMap: Record<string, string> = {
    sma: '均线',
    ema: '指数均线',
    rsi: 'RSI',
    macd_dif: 'MACD快线',
    macd_dea: 'MACD慢线',
    macd: 'MACD',
    macd_bar: 'MACD柱',
    boll_upper: '布林上轨',
    boll_mid: '布林中轨',
    boll_lower: '布林下轨',
    atr: 'ATR',
    kdj_k: 'KDJ-K',
    kdj_d: 'KDJ-D',
    kdj_j: 'KDJ-J',
    cci: 'CCI',
    close: '收盘价',
    volume: '成交量',
  }

  function fmtInd(raw: string): string {
    if (indicatorMap[raw]) return indicatorMap[raw]
    const s = raw.match(/^sma(\d+)$/)
    if (s) return `${s[1]}日均线`
    const e = raw.match(/^ema(\d+)$/)
    if (e) return `${e[1]}日指数均线`
    const r = raw.match(/^rsi(\d+)$/)
    if (r) return `RSI(${r[1]})`
    const c = raw.match(/^cci(\d+)$/)
    if (c) return `CCI(${c[1]})`
    return raw
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
            <span className="font-medium text-white">{fmtInd(cond.indicator)}</span>
            {' '}
            <span className="text-slate-400">{operatorMap[cond.operator] || cond.operator}</span>
            {' '}
            {cond.indicator2 ? (
              <span className="font-medium text-white">{fmtInd(cond.indicator2)}</span>
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
  const typeMap: Record<string, string> = {
    fixed: '固定',
    pct: '百分比',
    atr: 'ATR',
    trailing: '移动',
  }

  function fmtRisk(t: string, v: number): string {
    const label = typeMap[t] || t
    if (t === 'pct') return `${label} (${v}%)`
    return `${label} (${v})`
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-2">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-red-400">
        <AlertTriangle size={10} />
        风控参数
      </div>
      <div className="space-y-1 text-xs text-slate-300">
        <div className="flex items-center justify-between">
          <span className="text-slate-400">仓位</span>
          <span>{fmtRisk(risk.position_size.type, risk.position_size.value)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-400">止损</span>
          <span>{fmtRisk(risk.stop_loss.type, risk.stop_loss.value)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-400">止盈</span>
          <span>{fmtRisk(risk.take_profit.type, risk.take_profit.value)}</span>
        </div>
      </div>
    </div>
  )
}
