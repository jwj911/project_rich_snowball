interface TechAnalysisReportCardProps {
  result?: Record<string, unknown> | null
}

export default function TechAnalysisReportCard({ result }: TechAnalysisReportCardProps) {
  if (!result) return null

  const score = typeof result.score === 'number' ? result.score : null
  const rating = typeof result.rating === 'string' ? result.rating : null
  const direction = typeof result.direction === 'string' ? result.direction : null
  const indicators = (result.indicators as Record<string, number> | undefined) || {}
  const trend = (result.trend as Record<string, unknown> | undefined) || {}
  const pattern = (result.pattern as Record<string, unknown> | undefined) || {}
  const divergence = (result.divergence as Record<string, unknown> | undefined) || {}

  const scoreColor =
    score === null
      ? 'text-slate-400'
      : score >= 70
        ? 'text-green-400'
        : score >= 40
          ? 'text-amber-400'
          : 'text-red-400'

  return (
    <div className="mt-3 rounded-xl border border-slate-700 bg-slate-900/50 p-4">
      <div className="mb-4 flex items-center justify-between">
        <div className="text-sm font-medium text-white">技术分析报告</div>
        {score !== null && (
          <div className="text-right">
            <div className={`text-2xl font-bold ${scoreColor}`}>{score}</div>
            <div className="text-xs text-slate-400">综合评分 /100</div>
          </div>
        )}
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {rating && <Badge label={rating} />}
        {direction && <Badge label={direction} />}
        {typeof trend.direction === 'string' && (
          <Badge label={`趋势：${trend.direction}`} />
        )}
        {typeof pattern.pattern === 'string' && pattern.pattern !== '无' && (
          <Badge label={`形态：${pattern.pattern}`} />
        )}
        {typeof divergence.divergence === 'string' && divergence.divergence !== '无' && (
          <Badge label={`背离：${divergence.divergence}`} />
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <Metric label="RSI(24)" value={indicators.rsi24} />
        <Metric label="MACD DIF" value={indicators.macd_dif} />
        <Metric label="MACD DEA" value={indicators.macd_dea} />
        <Metric label="MACD 柱" value={indicators.macd_bar} />
        <Metric label="KDJ K" value={indicators.kdj_k} />
        <Metric label="KDJ D" value={indicators.kdj_d} />
        <Metric label="KDJ J" value={indicators.kdj_j} />
        <Metric label="布林带上轨" value={indicators.boll_upper} />
        <Metric label="布林带中轨" value={indicators.boll_mid} />
        <Metric label="布林带下轨" value={indicators.boll_lower} />
        <Metric label="ADX" value={indicators.adx14} />
        <Metric label="量比" value={indicators.vol_ratio} />
      </div>
    </div>
  )
}

function Badge({ label }: { label: string }) {
  return (
    <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
      {label}
    </span>
  )
}

function Metric({ label, value }: { label: string; value: number | undefined }) {
  const display = value === undefined || Number.isNaN(value) ? '—' : value.toFixed(2)
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-800/50 p-2">
      <div className="text-slate-500">{label}</div>
      <div className="mt-0.5 font-medium text-white">{display}</div>
    </div>
  )
}
