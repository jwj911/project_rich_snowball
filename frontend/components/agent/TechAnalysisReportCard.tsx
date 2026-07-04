interface TechAnalysisReportCardProps {
  result?: Record<string, unknown> | null
}

export default function TechAnalysisReportCard({ result }: TechAnalysisReportCardProps) {
  if (!result) return null

  const score = typeof result.score === 'number' ? result.score : null
  const rating = typeof result.rating === 'string' ? result.rating : null
  const direction = typeof result.direction === 'string' ? result.direction : null
  const bias = typeof result.bias === 'string' ? result.bias : null
  const moneyFlow = typeof result.money_flow === 'string' ? result.money_flow : null
  const klineTrend = typeof result.kline_trend === 'string' ? result.kline_trend : null
  const riskNote = typeof result.risk_note === 'string' ? result.risk_note : null
  const keyLevels = (result.key_levels as Record<string, number | null> | undefined) || {}
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
        {direction && <Badge label={`趋势：${direction}`} />}
        {bias && <Badge label={`多空：${bias}`} />}
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

      {(moneyFlow || klineTrend || riskNote) && (
        <div className="mb-4 space-y-1.5 text-xs text-slate-300">
          {moneyFlow && <InfoRow label="资金流向" value={moneyFlow} />}
          {klineTrend && <InfoRow label="K线走势" value={klineTrend} />}
          {riskNote && <InfoRow label="风险提示" value={riskNote} />}
        </div>
      )}

      {(keyLevels.support !== undefined || keyLevels.resistance !== undefined) && (
        <div className="mb-4 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
          <Metric label="支撑位" value={keyLevels.support ?? undefined} />
          <Metric label="阻力位" value={keyLevels.resistance ?? undefined} />
          <Metric label="MA5" value={keyLevels.ma5 ?? undefined} />
          <Metric label="MA20" value={keyLevels.ma20 ?? undefined} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <Metric label="RSI(24)" value={indicators.rsi24} />
        <Metric label="MACD DIF" value={indicators.macd_dif} />
        <Metric label="MACD DEA" value={indicators.macd_dea} />
        <Metric label="MACD 柱" value={indicators.macd_bar} />
        <Metric label="MA5" value={indicators.sma5} />
        <Metric label="MA10" value={indicators.sma10} />
        <Metric label="MA20" value={indicators.sma20} />
        <Metric label="ATR" value={indicators.atr14} />
        <Metric label="KDJ K" value={indicators.kdj_k} />
        <Metric label="KDJ D" value={indicators.kdj_d} />
        <Metric label="KDJ J" value={indicators.kdj_j} />
        <Metric label="ADX" value={indicators.adx14} />
        <Metric label="布林上轨" value={indicators.boll_upper} />
        <Metric label="布林中轨" value={indicators.boll_mid} />
        <Metric label="布林下轨" value={indicators.boll_lower} />
        <Metric label="量比" value={indicators.vol_ratio} />
        <Metric label="成交量变化" value={indicators.volume_change} />
      </div>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="shrink-0 text-slate-500">{label}:</span>
      <span className="text-slate-200">{value}</span>
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
