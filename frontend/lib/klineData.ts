import { KlineData } from '@/lib/api'
import { Time, UTCTimestamp } from 'lightweight-charts'

export type CandlePoint = {
  time: Time
  originalTime: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export function normalizeKlineData(data: KlineData[]): CandlePoint[] {
  const byTime = new Map<number, CandlePoint>()

  data.forEach((item) => {
    const timestamp = parseTimestamp(item.time)
    if (timestamp === null) return

    const open = Number(item.open)
    const high = Number(item.high)
    const low = Number(item.low)
    const close = Number(item.close)
    const volume = Number(item.volume)

    if (![open, high, low, close].every(Number.isFinite)) return

    const safeHigh = Math.max(high, open, close, low)
    const safeLow = Math.min(low, open, close, high)

    byTime.set(timestamp, {
      time: timestamp as UTCTimestamp,
      originalTime: item.time,
      open,
      high: safeHigh,
      low: safeLow,
      close,
      volume: Number.isFinite(volume) ? Math.max(volume, 0) : 0,
    })
  })

  return Array.from(byTime.values()).sort((a, b) => Number(a.time) - Number(b.time))
}

export function parseTimestamp(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null

  const numeric = Number(trimmed)
  if (Number.isFinite(numeric) && numeric > 0) {
    return Math.floor(numeric > 10_000_000_000 ? numeric / 1000 : numeric)
  }

  const parsed = Date.parse(trimmed)
  if (!Number.isFinite(parsed)) return null

  return Math.floor(parsed / 1000)
}

export function maxOf(points: CandlePoint[], key: 'high' | 'low') {
  return Math.max(...points.map((point) => point[key]))
}

export function minOf(points: CandlePoint[], key: 'high' | 'low') {
  return Math.min(...points.map((point) => point[key]))
}
