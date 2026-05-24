import { describe, expect, it } from 'vitest'
import { normalizeKlineData, parseTimestamp, maxOf, minOf } from '@/lib/klineData'

describe('parseTimestamp', () => {
  it('parses numeric string as seconds', () => {
    expect(parseTimestamp('1716532800')).toBe(1716532800)
  })

  it('parses millisecond timestamp by dividing by 1000', () => {
    expect(parseTimestamp('1716532800000')).toBe(1716532800)
  })

  it('parses ISO date string', () => {
    expect(parseTimestamp('2024-05-24T08:00:00.000Z')).toBeGreaterThan(1700000000)
  })

  it('returns null for empty string', () => {
    expect(parseTimestamp('')).toBeNull()
  })

  it('returns null for invalid string', () => {
    expect(parseTimestamp('not-a-date')).toBeNull()
  })
})

describe('normalizeKlineData', () => {
  it('normalizes valid kline items', () => {
    const data = [
      { time: '1716532800', open: 100, high: 110, low: 90, close: 105, volume: 1000 },
      { time: '1716532860', open: 105, high: 115, low: 100, close: 110, volume: 2000 },
    ]
    const points = normalizeKlineData(data)
    expect(points).toHaveLength(2)
    expect(points[0].open).toBe(100)
    expect(points[0].high).toBe(110)
    expect(points[0].low).toBe(90)
    expect(points[0].close).toBe(105)
    expect(points[0].volume).toBe(1000)
  })

  it('filters out items with non-finite OHLC values', () => {
    const data = [
      { time: '1716532800', open: 100, high: NaN, low: 90, close: 105, volume: 1000 },
      { time: '1716532860', open: 105, high: 115, low: 100, close: 110, volume: 2000 },
    ]
    const points = normalizeKlineData(data)
    expect(points).toHaveLength(1)
    expect(points[0].close).toBe(110)
  })

  it('filters out items with invalid timestamps', () => {
    const data = [
      { time: 'invalid', open: 100, high: 110, low: 90, close: 105, volume: 1000 },
      { time: '1716532860', open: 105, high: 115, low: 100, close: 110, volume: 2000 },
    ]
    const points = normalizeKlineData(data)
    expect(points).toHaveLength(1)
  })

  it('deduplicates by timestamp and keeps last', () => {
    const data = [
      { time: '1716532800', open: 100, high: 110, low: 90, close: 105, volume: 1000 },
      { time: '1716532800', open: 200, high: 220, low: 180, close: 210, volume: 3000 },
    ]
    const points = normalizeKlineData(data)
    expect(points).toHaveLength(1)
    expect(points[0].close).toBe(210)
  })

  it('sorts by time ascending', () => {
    const data = [
      { time: '1716532860', open: 105, high: 115, low: 100, close: 110, volume: 2000 },
      { time: '1716532800', open: 100, high: 110, low: 90, close: 105, volume: 1000 },
    ]
    const points = normalizeKlineData(data)
    expect(points[0].close).toBe(105)
    expect(points[1].close).toBe(110)
  })

  it('handles negative volume by clamping to 0', () => {
    const data = [
      { time: '1716532800', open: 100, high: 110, low: 90, close: 105, volume: -500 },
    ]
    const points = normalizeKlineData(data)
    expect(points[0].volume).toBe(0)
  })

  it('returns empty array for empty input', () => {
    expect(normalizeKlineData([])).toEqual([])
  })
})

describe('maxOf', () => {
  it('returns maximum high', () => {
    const points = [
      { time: 1 as unknown as import('lightweight-charts').Time, originalTime: '1', open: 1, high: 10, low: 1, close: 1, volume: 1 },
      { time: 2 as unknown as import('lightweight-charts').Time, originalTime: '2', open: 1, high: 20, low: 1, close: 1, volume: 1 },
      { time: 3 as unknown as import('lightweight-charts').Time, originalTime: '3', open: 1, high: 5, low: 1, close: 1, volume: 1 },
    ]
    expect(maxOf(points, 'high')).toBe(20)
  })
})

describe('minOf', () => {
  it('returns minimum low', () => {
    const points = [
      { time: 1 as unknown as import('lightweight-charts').Time, originalTime: '1', open: 1, high: 1, low: 10, close: 1, volume: 1 },
      { time: 2 as unknown as import('lightweight-charts').Time, originalTime: '2', open: 1, high: 1, low: 3, close: 1, volume: 1 },
      { time: 3 as unknown as import('lightweight-charts').Time, originalTime: '3', open: 1, high: 1, low: 5, close: 1, volume: 1 },
    ]
    expect(minOf(points, 'low')).toBe(3)
  })
})
