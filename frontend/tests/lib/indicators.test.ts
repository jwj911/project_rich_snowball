import { describe, expect, it } from 'vitest'
import { KlineData } from '@/lib/api'
import { average, buildTechnicalAnalysis } from '@/lib/indicators'

function makeKline(closes: number[], volumes: number[] = closes.map(() => 1000)): KlineData[] {
  return closes.map((close, index) => ({
    time: `2026-05-${String(index + 1).padStart(2, '0')}`,
    open: close - 1,
    high: close + 2,
    low: close - 2,
    close,
    volume: volumes[index] ?? 1000,
  }))
}

describe('average', () => {
  it('returns 0 for empty values', () => {
    expect(average([])).toBe(0)
  })

  it('calculates arithmetic mean', () => {
    expect(average([1, 2, 3, 4])).toBe(2.5)
  })
})

describe('buildTechnicalAnalysis', () => {
  it('returns null when fewer than 5 valid bars exist', () => {
    expect(buildTechnicalAnalysis(makeKline([1, 2, 3, 4]), null, [], [])).toBeNull()
  })

  it('filters invalid bars before calculating sample size', () => {
    const data = [
      ...makeKline([10, 11, 12, 13, 14]),
      { time: 'bad', open: Number.NaN, high: 1, low: 1, close: 1, volume: 1 },
    ]

    const analysis = buildTechnicalAnalysis(data, null, [], [])

    expect(analysis?.sampleSize).toBe(5)
  })

  it('classifies a rising series as up and uses nearest support and resistance', () => {
    const analysis = buildTechnicalAnalysis(
      makeKline([10, 11, 12, 13, 14, 15, 16]),
      null,
      [9, 12, 15.5],
      [16.5, 18, 30],
    )

    expect(analysis?.tone).toBe('up')
    expect(analysis?.trendLabel).toBe('偏强整理')
    expect(analysis?.ma5).toBe(14)
    expect(analysis?.strategyNotes[1]).toContain('15.50')
    expect(analysis?.strategyNotes[2]).toContain('16.50')
  })

  it('classifies a falling series as down', () => {
    const analysis = buildTechnicalAnalysis(makeKline([20, 19, 18, 17, 16, 15, 14]), null, [], [])

    expect(analysis?.tone).toBe('down')
    expect(analysis?.trendLabel).toBe('偏弱整理')
  })

  it('uses current price override when judging the latest close', () => {
    const analysis = buildTechnicalAnalysis(makeKline([10, 10, 10, 10, 10]), 12, [], [])

    expect(analysis?.latestClose).toBe(12)
    expect(analysis?.tone).toBe('up')
  })

  it('labels expanded and contracted volume', () => {
    const expanded = buildTechnicalAnalysis(
      makeKline([10, 11, 12, 13, 14, 15, 16, 17, 18, 19], [100, 100, 100, 100, 100, 200, 200, 200, 200, 200]),
      null,
      [],
      [],
    )
    const contracted = buildTechnicalAnalysis(
      makeKline([10, 11, 12, 13, 14, 15, 16, 17, 18, 19], [200, 200, 200, 200, 200, 100, 100, 100, 100, 100]),
      null,
      [],
      [],
    )

    expect(expanded?.volumeLabel).toBe('放量')
    expect(contracted?.volumeLabel).toBe('缩量')
  })

  it('falls back to recent high and low when no levels surround price', () => {
    const analysis = buildTechnicalAnalysis(makeKline([10, 11, 12, 13, 14]), null, [], [])

    expect(analysis?.strategyNotes[1]).toContain('近 20 根 K 线低点')
    expect(analysis?.strategyNotes[2]).toContain('近 20 根 K 线高点')
  })
})
