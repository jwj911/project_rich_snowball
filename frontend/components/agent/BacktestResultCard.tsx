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
} from 'lucide-react'
import type { BacktestResultData } from './backtest-types'

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
  const scoreColor = score >= 70 ? 'text-green-400' : score >= 40 ? 'text-amber-400' : 'text-red-400'
  const scoreBg = score >= 70 ? 'bg-green-500/10' : score >= 40 ? 'bg-amber-500/10' : 'bg-red-500/10'

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

      {/* 品种与参数 */}
      <div className="mb-3 text-xs text-slate-400">
        {variety?.name || config.symbol} · {config.short_window}/{config.long_window} 均线 · {config.direction === 'short' ? '做空' : '做多'} · {config.period}
        {window && (
          <span className="ml-2 text-slate-500">
            {window.start?.slice(0, 10)} ~ {window.end?.slice(0, 10)} · {window.bars} 根
          </span>
        )}
      </div>

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
        <MetricBox
          label="初始资金"
          value={`${(config.initial_cash / 10000).toFixed(1)}万`}
          color="text-slate-300"
          icon={DollarSign}
        />
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
