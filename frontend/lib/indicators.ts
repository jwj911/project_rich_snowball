import { KlineData } from '@/lib/api'
import { formatNumber } from '@/lib/format'

export type TrendTone = 'up' | 'down' | 'neutral'

export interface TechnicalAnalysis {
  sampleSize: number
  latestClose: number
  ma5: number
  ma20: number
  rangePercent: number
  tone: TrendTone
  trendLabel: string
  volumeLabel: string
  strategyNotes: string[]
  riskNotes: string[]
}

export function buildTechnicalAnalysis(
  data: KlineData[],
  currentPrice: number | null | undefined,
  supportLevels: number[],
  resistanceLevels: number[],
): TechnicalAnalysis | null {
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

export function average(values: number[]) {
  if (values.length === 0) return 0
  return values.reduce((sum, value) => sum + value, 0) / values.length
}
