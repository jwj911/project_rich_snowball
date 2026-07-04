import { Time, UTCTimestamp } from 'lightweight-charts'
import { KlineData } from '@/lib/api'

export const CHART_HEIGHT = 520
export const SUPPORT_COLOR = '#4ade80'
export const RESISTANCE_COLOR = '#ff6b6b'
export const UP_COLOR = '#ff6b6b'
export const DOWN_COLOR = '#4ade80'

export interface AnnotationMenu {
  x: number
  y: number
  price: number
}

export interface CrosshairQuote {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  contractCode: string | null
  contractId: number | null
}

export interface CandlePoint {
  time: Time
  originalTime: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  contractCode: string | null
  contractId: number | null
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
      contractCode: item.contract_code ?? null,
      contractId: item.contract_id ?? null,
    })
  })

  return Array.from(byTime.values()).sort((a, b) => Number(a.time) - Number(b.time))
}

export function buildCandleData(points: CandlePoint[]) {
  return points.map(({ time, open, high, low, close }) => ({ time, open, high, low, close }))
}

export function buildVolumeData(points: CandlePoint[]) {
  return points.map((point) => ({
    time: point.time,
    value: Math.max(point.volume, 0),
    color: point.close >= point.open ? 'rgba(255, 107, 107, 0.38)' : 'rgba(74, 222, 128, 0.38)',
  }))
}

export function maxOf(points: CandlePoint[], key: 'high' | 'low') {
  return Math.max(...points.map((point) => point[key]))
}

export function minOf(points: CandlePoint[], key: 'high' | 'low') {
  return Math.min(...points.map((point) => point[key]))
}

function parseTimestamp(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null

  const numeric = Number(trimmed)
  if (Number.isFinite(numeric) && numeric > 0) {
    return Math.floor(numeric > 10_000_000_000 ? numeric / 1000 : numeric)
  }

  const parsed = Date.parse(trimmed)
  if (!Number.isFinite(parsed)) return null

  // 后端 trade_date 按东八区零点存储，序列化后变成 UTC 前一日 16:00。
  // 这里把 UTC 时刻转回东八区日期，再对齐到 UTC 零点，避免 K 线日期少一天。
  const CN_OFFSET_MS = 8 * 60 * 60 * 1000
  const cnDate = new Date(parsed + CN_OFFSET_MS)
  return Math.floor(
    Date.UTC(cnDate.getUTCFullYear(), cnDate.getUTCMonth(), cnDate.getUTCDate()) / 1000,
  )
}
