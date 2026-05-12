import { Activity, LineChart, Target, TrendingDown, TrendingUp } from 'lucide-react'
import { KlineData } from '@/lib/api'
import { formatNumber } from '@/lib/format'

interface TechnicalAnalysisPanelProps {
  data: KlineData[]
  currentPrice: number | null | undefined
  supportLevels: number[]
  resistanceLevels: number[]
}

type TrendTone = 'up' | 'down' | 'neutral'

export default function TechnicalAnalysisPanel({
  data,
  currentPrice,
  supportLevels,
  resistanceLevels,
}: TechnicalAnalysisPanelProps) {
  const analysis = buildAnalysis(data, currentPrice, supportLevels, resistanceLevels)

  if (!analysis) {
    return (
      <section className="rounded-lg border border-slate-800 bg-[#10161d] p-4">
        <h2 className="flex items-center gap-2 text-base font-semibold text-slate-200">
          <LineChart size={17} />
          技术分析与策略
        </h2>
        <div className="mt-4 rounded-lg border border-slate-800 bg-black/20 p-4 text-sm text-slate-500">
          K 线数据不足，等待更多行情同步后展示趋势、均线和策略观察。
        </div>
      </section>
    )
  }

  const TrendIcon = analysis.tone === 'up' ? TrendingUp : analysis.tone === 'down' ? TrendingDown : Activity

  return (
    <section className="rounded-lg border border-slate-800 bg-[#10161d] p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-200">
            <LineChart size={17} />
            技术分析与策略
          </h2>
          <p className="mt-1 text-sm text-slate-500">基于最近 {analysis.sampleSize} 根 K 线自动生成</p>
        </div>
        <div className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${toneClass(analysis.tone)}`}>
          <TrendIcon size={15} />
          {analysis.trendLabel}
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="MA5" value={formatNumber(analysis.ma5)} />
        <Metric label="MA20" value={formatNumber(analysis.ma20)} />
        <Metric label="区间振幅" value={`${analysis.rangePercent.toFixed(2)}%`} />
        <Metric label="量能变化" value={analysis.volumeLabel} />
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <StrategyCard
          title="策略观察"
          icon={<Target size={16} className="text-red-300" />}
          items={analysis.strategyNotes}
        />
        <StrategyCard
          title="风险提示"
          icon={<Activity size={16} className="text-amber-300" />}
          items={analysis.riskNotes}
        />
      </div>
    </section>
  )
}

function buildAnalysis(
  data: KlineData[],
  currentPrice: number | null | undefined,
  supportLevels: number[],
  resistanceLevels: number[],
) {
  const validData = data.filter((item) => [item.open, item.high, item.low, item.close, item.volume].every(Number.isFinite))
  if (validData.length < 5) return null

  const closes = validData.map((item) => item.close)
  const volumes = validData.map((item) => item.volume)
  const latestClose = currentPrice ?? closes[closes.length - 1]
  const ma5 = average(closes.slice(-5))
  const ma20 = average(closes.slice(-Math.min(20, closes.length)))
  const recent = validData.slice(-Math.min(20, validData.length))
  const high = Math.max(...recent.map((item) => item.high))
  const low = Math.min(...recent.map((item) => item.low))
  const rangePercent = low > 0 ? ((high - low) / low) * 100 : 0
  const recentVolume = average(volumes.slice(-5))
  const previousVolume = average(volumes.slice(-Math.min(20, volumes.length), -5))
  const volumeRatio = previousVolume > 0 ? recentVolume / previousVolume : 1

  let tone: TrendTone = 'neutral'
  if (latestClose > ma5 && ma5 >= ma20) tone = 'up'
  if (latestClose < ma5 && ma5 <= ma20) tone = 'down'

  const nearestSupport = supportLevels.filter((level) => level < latestClose).sort((a, b) => b - a)[0]
  const nearestResistance = resistanceLevels.filter((level) => level > latestClose).sort((a, b) => a - b)[0]
  const trendLabel = tone === 'up' ? '偏强整理' : tone === 'down' ? '偏弱整理' : '震荡观察'
  const volumeLabel = volumeRatio >= 1.15 ? '放量' : volumeRatio <= 0.85 ? '缩量' : '平稳'

  const strategyNotes = [
    tone === 'up'
      ? '价格位于短期均线上方，优先观察回踩后的承接力度。'
      : tone === 'down'
        ? '价格位于短期均线下方，优先等待企稳信号。'
        : '均线方向暂不明确，适合先观察区间边界。',
    nearestSupport
      ? `下方最近支撑位 ${formatNumber(nearestSupport)}，可作为回撤观察点。`
      : `近 20 根 K 线低点 ${formatNumber(low)} 可作为临时支撑参考。`,
    nearestResistance
      ? `上方最近阻力位 ${formatNumber(nearestResistance)}，突破前不宜追高。`
      : `近 20 根 K 线高点 ${formatNumber(high)} 可作为压力参考。`,
  ]

  const riskNotes = [
    rangePercent >= 6
      ? '近期振幅较大，仓位和止损需要更保守。'
      : '近期振幅相对可控，但仍需关注突发行情。',
    volumeRatio >= 1.15
      ? '量能放大时，价格突破或反转的有效性更需要确认。'
      : '量能未明显放大，突破信号可能需要等待跟进。',
  ]

  return {
    sampleSize: validData.length,
    latestClose,
    ma5,
    ma20,
    rangePercent,
    tone,
    trendLabel,
    volumeLabel,
    strategyNotes,
    riskNotes,
  }
}

function average(values: number[]) {
  if (values.length === 0) return 0
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function toneClass(tone: TrendTone) {
  if (tone === 'up') return 'border-red-900/50 bg-red-500/10 text-red-300'
  if (tone === 'down') return 'border-green-900/50 bg-green-500/10 text-green-300'
  return 'border-slate-700 bg-black/20 text-slate-300'
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-black/30 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 font-mono text-base font-semibold text-slate-200">{value}</div>
    </div>
  )
}

function StrategyCard({ title, icon, items }: { title: string; icon: React.ReactNode; items: string[] }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-black/20 p-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-200">
        {icon}
        {title}
      </h3>
      <div className="mt-3 space-y-2">
        {items.map((item) => (
          <p key={item} className="text-sm leading-6 text-slate-400">{item}</p>
        ))}
      </div>
    </div>
  )
}
