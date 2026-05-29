import { describe, expect, it } from 'vitest'
import { buildCandleData, buildVolumeData, normalizeKlineData } from '@/lib/klineChart'

describe('klineChart helpers', () => {
  it('normalizes, deduplicates, sorts, and clamps kline rows', () => {
    const rows = normalizeKlineData([
      { time: '2026-05-03', open: 10, high: 11, low: 9, close: 10.5, volume: -20, contract_code: 'RB2609.SHF', contract_id: 1001 },
      { time: 'bad-date', open: 1, high: 2, low: 1, close: 2, volume: 10 },
      { time: '2026-05-01', open: 8, high: 7, low: 9, close: 8.5, volume: 100 },
      { time: '2026-05-01', open: 8.5, high: 9.5, low: 8, close: 9, volume: 120, contract_code: 'RB2608.SHF', contract_id: 1002 },
    ])

    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({
      originalTime: '2026-05-01',
      open: 8.5,
      high: 9.5,
      low: 8,
      close: 9,
      volume: 120,
      contractCode: 'RB2608.SHF',
      contractId: 1002,
    })
    expect(rows[1]).toMatchObject({
      contractCode: 'RB2609.SHF',
      contractId: 1001,
    })
    expect(rows[1].volume).toBe(0)
    expect(Number(rows[0].time)).toBeLessThan(Number(rows[1].time))
  })

  it('preserves contract_id through normalizeKlineData', () => {
    const rows = normalizeKlineData([
      { time: '2026-05-01', open: 1, high: 2, low: 1, close: 2, volume: 10, contract_id: 42 },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].contractId).toBe(42)
    expect(rows[0].contractCode).toBeNull()
  })

  it('builds lightweight chart candle and volume series data', () => {
    const points = normalizeKlineData([
      { time: '2026-05-01', open: 8, high: 9, low: 7, close: 9, volume: 100 },
      { time: '2026-05-02', open: 9, high: 10, low: 8, close: 8, volume: 80 },
    ])

    expect(buildCandleData(points)).toEqual([
      expect.objectContaining({ open: 8, high: 9, low: 7, close: 9 }),
      expect.objectContaining({ open: 9, high: 10, low: 8, close: 8 }),
    ])
    expect(buildVolumeData(points)).toEqual([
      expect.objectContaining({ value: 100, color: 'rgba(255, 107, 107, 0.38)' }),
      expect.objectContaining({ value: 80, color: 'rgba(74, 222, 128, 0.38)' }),
    ])
  })
})
