import type { AgentTaskStepResponse } from '@/lib/api'

interface FactorResultCardProps {
  result?: Record<string, unknown> | null
  steps?: AgentTaskStepResponse[]
}

export default function FactorResultCard({ result }: FactorResultCardProps) {
  if (!result) return null

  const fmtPct = (v: unknown) => {
    if (v === null || v === undefined) return '—'
    const n = typeof v === 'number' ? v : Number(v)
    if (Number.isNaN(n)) return '—'
    return `${(n * 100).toFixed(2)}%`
  }

  const fmtNum = (v: unknown, digits = 3) => {
    if (v === null || v === undefined) return '—'
    const n = typeof v === 'number' ? v : Number(v)
    if (Number.isNaN(n)) return '—'
    return n.toFixed(digits)
  }

  const quantileReturns = (result.quantile_returns as number[] | undefined) || []

  return (
    <div className="mt-3 rounded-xl border border-slate-700 bg-slate-900/50 p-4">
      <div className="mb-3 text-sm font-medium text-white">因子评估结果</div>

      <div className="mb-4 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <Metric label="IC 均值" value={fmtNum(result.ic_mean)} />
        <Metric label="ICIR" value={fmtNum(result.icir)} />
        <Metric label="Rank IC" value={fmtNum(result.rank_ic_mean)} />
        <Metric label="Rank ICIR" value={fmtNum(result.rank_icir)} />
        <Metric label="多空收益" value={fmtPct(result.long_short_return)} />
        <Metric label="年化收益" value={fmtPct(result.long_short_annual_return)} />
        <Metric label="最大回撤" value={fmtPct(result.long_short_max_drawdown)} />
        <Metric label="Sharpe" value={fmtNum(result.long_short_sharpe)} />
        <Metric label="换手率" value={fmtPct(result.turnover)} />
        <Metric label="覆盖率" value={fmtPct(result.coverage)} />
      </div>

      {quantileReturns.length > 0 && (
        <div>
          <div className="mb-2 text-xs text-slate-400">分层累计收益（最低 → 最高）</div>
          <div className="flex h-24 items-end gap-2">
            {quantileReturns.map((ret, idx) => {
              const n = typeof ret === 'number' ? ret : Number(ret)
              const height = Number.isNaN(n) ? 0 : Math.min(Math.max(n * 100, -50), 50) + 50
              const color = idx < quantileReturns.length / 2 ? 'bg-red-400' : 'bg-green-400'
              return (
                <div
                  key={idx}
                  className="flex flex-1 flex-col items-center justify-end gap-1"
                >
                  <div
                    className={`w-full rounded-t ${color} opacity-80`}
                    style={{ height: `${height}%` }}
                  />
                  <span className="text-[10px] text-slate-400">Q{idx + 1}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {typeof result.formula === 'string' && (
        <div className="mt-3 text-xs text-slate-400">
          公式：
          <code className="rounded bg-slate-800 px-1 py-0.5 text-amber-400">{result.formula}</code>
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-800/50 p-2">
      <div className="text-slate-500">{label}</div>
      <div className="mt-0.5 font-medium text-white">{value}</div>
    </div>
  )
}
