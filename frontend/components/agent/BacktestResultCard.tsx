'use client'

import { useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  BarChart3,
  TrendingUp,
  TrendingDown,
  Activity,
  Target,
  ArrowRight,
  DollarSign,
  AlertTriangle,
} from 'lucide-react'
import type { BacktestResultData } from './backtest-types'

const OPERATOR_LABELS: Record<string, string> = {
  cross_above: '上穿',
  cross_below: '下穿',
  above: '突破',
  below: '跌破',
  greater_than: '大于',
  less_than: '小于',
  equal: '等于',
  between: '介于',
}

const INDICATOR_SHORT_LABELS: Record<string, string> = {
  sma: '均线',
  ema: '指数均线',
  rsi: 'RSI',
  macd_dif: 'MACD DIF',
  macd_dea: 'MACD DEA',
  macd: 'MACD',
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
  high: '最高价',
  low: '最低价',
}

function fmtIndicator(raw: string): string {
  // Handle patterns like sma5, ema20, rsi14, cci20, boll_upper_20_2, atr_upper_14_2, volume_sma20
  const known = INDICATOR_SHORT_LABELS[raw]
  if (known) return known

  // volume_sma<N>
  const vsma = raw.match(/^volume_sma(\d+)$/)
  if (vsma) return `成交量均线(${vsma[1]})`

  // sma<N>
  const s = raw.match(/^sma(\d+)$/)
  if (s) return `${s[1]}日均线`

  // ema<N>
  const e = raw.match(/^ema(\d+)$/)
  if (e) return `${e[1]}日指数均线`

  // rsi<N>
  const r = raw.match(/^rsi(\d+)$/)
  if (r) return `RSI(${r[1]})`

  // cci<N>
  const c = raw.match(/^cci(\d+)$/)
  if (c) return `CCI(${c[1]})`

  // kdj_k<N>, kdj_d<N>, kdj_j<N>
  const k = raw.match(/^kdj_([kdj])(\d+)$/)
  if (k) return `KDJ-${k[1].toUpperCase()}(${k[2]})`

  // boll_upper_N_M etc
  const boll = raw.match(/^boll_(upper|lower|mid)_(\d+)_(\d+)$/)
  if (boll) {
    const part = boll[1] === 'upper' ? '布林上轨' : boll[1] === 'lower' ? '布林下轨' : '布林中轨'
    return `${part}(${boll[2]},${boll[3]})`
  }

  // atr_upper_N_M etc
  const atr = raw.match(/^atr_(upper|lower)_(\d+)_(\d+)$/)
  if (atr) {
    const part = atr[1] === 'upper' ? 'ATR上轨' : 'ATR下轨'
    return `${part}(${atr[2]},${atr[3]})`
  }

  // high_N, low_N
  const hl = raw.match(/^(high|low)_(\d+)$/)
  if (hl) return `${hl[1] === 'high' ? '最高价' : '最低价'}(${hl[2]})`

  return raw
}

function buildStrategyDescription(data: BacktestResultData): string {
  const parts: string[] = []
  const variety = data.variety as Record<string, string> | undefined
  const config = data.config

  // 品种名
  parts.push(variety?.name || config.symbol)

  // 方向
  parts.push(config.direction === 'short' ? '做空' : '做多')

  // 周期
  const periodLabel: Record<string, string> = { '1d': '日线', '1h': '小时线', '15m': '15分钟' }
  if (config.period) {
    parts.push(periodLabel[config.period] || config.period)
  }

  return parts.join(' · ')
}

export default function BacktestResultCard({
  result,
}: {
  result: Record<string, unknown> | null | undefined
}) {
  const [showTrades, setShowTrades] = useState(false)
  const [showEquity, setShowEquity] = useState(false)
  const data = result as BacktestResultData | null
  if (!data || !data.metrics) return null

  const metrics = data.metrics
  const config = data.config
  const trades = data.trades || []
  const equityCurve = data.equity_curve || []
  const variety = data.variety as Record<string, string> | undefined
  const window = data.data_window

  const score = metrics.score || 0
  const noTrades = (metrics.trade_count || 0) === 0
  const scoreColor = noTrades ? 'text-slate-500' : score >= 70 ? 'text-green-400' : score >= 40 ? 'text-amber-400' : 'text-red-400'
  const scoreBg = noTrades ? 'bg-slate-500/10' : score >= 70 ? 'bg-green-500/10' : score >= 40 ? 'bg-amber-500/10' : 'bg-red-500/10'

  // Build human-readable strategy description from conditions
  const strategyDesc = buildStrategyDescription(data)

  return (
    <div className="mt-3 rounded-lg border border-slate-700 bg-slate-900/50 p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 size={14} className="text-amber-400" />
          <span className="text-sm font-medium text-white">策略回测</span>
        </div>
        <div className={`rounded-md px-2 py-0.5 text-xs font-bold ${scoreBg} ${scoreColor}`}>
          {score}/100
        </div>
      </div>

      {/* 策略描述 */}
      <div className="mb-3 text-xs text-slate-400">
        {strategyDesc}
        {window && (
          <span className="ml-2 text-slate-500">
            {window.start?.slice(0, 10)} ~ {window.end?.slice(0, 10)} · {window.bars} 根K线
          </span>
        )}
      </div>

      {/* 未产生交易时的提示 */}
      {noTrades && (
        <div className="mb-3 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-200">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle size={14} />
            未产生交易信号
          </div>
          <p className="mt-1 text-amber-200/80">
            策略条件在所选回测区间内未触发任何买卖信号。可能是参数过于严格、指标组合不匹配当前行情，或需要更长的回测区间。
          </p>
        </div>
      )}

      {/* 核心指标网格 */}
      <div className="mb-3 grid grid-cols-4 gap-2">
        <MetricBox
          label="总收益"
          value={`${metrics.total_return_pct?.toFixed(2) || 0}%`}
          color={metrics.total_return_pct >= 0 ? 'text-red-400' : 'text-green-400'}
          icon={metrics.total_return_pct >= 0 ? TrendingUp : TrendingDown}
        />
        <MetricBox
          label="年化收益"
          value={`${metrics.annualized_return_pct?.toFixed(2) || 0}%`}
          color={metrics.annualized_return_pct >= 0 ? 'text-red-400' : 'text-green-400'}
          icon={Activity}
        />
        <MetricBox
          label="最大回撤"
          value={`${metrics.max_drawdown_pct?.toFixed(2) || 0}%`}
          color="text-green-400"
          icon={Target}
        />
        <MetricBox
          label="胜率"
          value={`${metrics.win_rate_pct?.toFixed(1) || 0}%`}
          color="text-amber-400"
          icon={DollarSign}
        />
      </div>

      <div className="mb-3 grid grid-cols-4 gap-2">
        <MetricBox label="盈亏比" value={metrics.profit_factor?.toFixed(2) || '0'} color="text-slate-300" icon={ArrowRight} />
        <MetricBox label="夏普" value={metrics.sharpe?.toFixed(2) || '0'} color="text-slate-300" icon={Activity} />
        <MetricBox label="交易次数" value={String(metrics.trade_count || 0)} color="text-slate-300" icon={BarChart3} />
        <MetricBox label="总手续费" value={metrics.total_fee?.toFixed(0) || '0'} color="text-slate-300" icon={DollarSign} />
      </div>

      {/* 交易记录 */}
      {trades.length > 0 && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowTrades(!showTrades)}
            className="inline-flex items-center gap-1 text-xs text-slate-500 transition hover:text-amber-400"
          >
            <BarChart3 size={10} />
            {showTrades ? '隐藏交易明细' : `交易明细 (${trades.length}笔)`}
            {showTrades ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
          </button>
          {showTrades && (
            <div className="mt-2 max-h-48 overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-2">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-500">
                    <th className="pb-1 pr-2">方向</th>
                    <th className="pb-1 pr-2">入场</th>
                    <th className="pb-1 pr-2">出场</th>
                    <th className="pb-1 text-right">盈亏</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300">
                  {trades.map((trade, i) => (
                    <tr key={i} className="border-t border-slate-800">
                      <td className="py-1 pr-2">
                        <span className={trade.direction === 'long' ? 'text-red-400' : 'text-green-400'}>
                          {trade.direction === 'long' ? '多' : '空'}
                        </span>
                      </td>
                      <td className="py-1 pr-2">
                        <div className="text-slate-400">{trade.entry_time?.slice(0, 10)}</div>
                        <div>{trade.entry_price}</div>
                      </td>
                      <td className="py-1 pr-2">
                        <div className="text-slate-400">{trade.exit_time?.slice(0, 10)}</div>
                        <div>{trade.exit_price}</div>
                      </td>
                      <td className={`py-1 text-right ${trade.pnl >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                        {trade.pnl >= 0 ? '+' : ''}
                        {trade.pnl.toFixed(0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* 资金曲线 */}
      {equityCurve.length > 0 && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowEquity(!showEquity)}
            className="inline-flex items-center gap-1 text-xs text-slate-500 transition hover:text-amber-400"
          >
            <TrendingUp size={10} />
            {showEquity ? '隐藏资金曲线' : '资金曲线'}
            {showEquity ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
          </button>
          {showEquity && <EquityCurveChart data={equityCurve} />}
        </div>
      )}
    </div>
  )
}

function MetricBox({
  label,
  value,
  color,
  icon: Icon,
}: {
  label: string
  value: string
  color: string
  icon: typeof BarChart3
}) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/50 p-2 text-center">
      <div className="mb-0.5 text-[10px] text-slate-500">{label}</div>
      <div className={`text-sm font-bold ${color}`}>{value}</div>
    </div>
  )
}

function EquityCurveChart({ data }: { data: Array<{ time: string; equity: number; pnl: number; pnl_pct: number }> }) {
  const width = 500
  const height = 120
  const padding = { top: 10, right: 10, bottom: 20, left: 50 }
  const chartWidth = width - padding.left - padding.right
  const chartHeight = height - padding.top - padding.bottom

  const equities = data.map((d) => d.equity)
  const minEquity = Math.min(...equities)
  const maxEquity = Math.max(...equities)
  const equityRange = maxEquity - minEquity || 1

  const points = data.map((d, i) => {
    const x = padding.left + (i / (data.length - 1 || 1)) * chartWidth
    const y = padding.top + chartHeight - ((d.equity - minEquity) / equityRange) * chartHeight
    return `${x},${y}`
  })

  const startEquity = equities[0]
  const endEquity = equities[equities.length - 1]
  const lineColor = endEquity >= startEquity ? '#ef4444' : '#22c55e'

  // Y轴刻度
  const yTicks = 4
  const yTickLabels = Array.from({ length: yTicks + 1 }, (_, i) => {
    const val = minEquity + (equityRange * i) / yTicks
    return (val / 10000).toFixed(1) + '万'
  })

  return (
    <div className="mt-2 overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-2">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" preserveAspectRatio="xMidYMid meet">
        {/* 网格线 */}
        {Array.from({ length: yTicks + 1 }, (_, i) => {
          const y = padding.top + (chartHeight * i) / yTicks
          return (
            <g key={i}>
              <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="#334155" strokeWidth="0.5" />
              <text x={padding.left - 4} y={y + 3} textAnchor="end" fill="#64748b" fontSize="8">
                {yTickLabels[yTicks - i]}
              </text>
            </g>
          )
        })}
        {/* 资金曲线 */}
        <polyline
          fill="none"
          stroke={lineColor}
          strokeWidth="1.5"
          points={points.join(' ')}
        />
        {/* 起点终点 */}
        {data.length > 0 && (
          <>
            <circle cx={points[0].split(',')[0]} cy={points[0].split(',')[1]} r="2" fill={lineColor} />
            <circle
              cx={points[points.length - 1].split(',')[0]}
              cy={points[points.length - 1].split(',')[1]}
              r="2"
              fill={lineColor}
            />
          </>
        )}
      </svg>
      <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500">
        <span>{data[0]?.time?.slice(0, 10)}</span>
        <span>{data[data.length - 1]?.time?.slice(0, 10)}</span>
      </div>
    </div>
  )
}
