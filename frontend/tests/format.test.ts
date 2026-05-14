import { describe, expect, it, vi } from 'vitest'
import { formatDateTime, formatNumber, formatPercent, formatRelativeTime } from '@/lib/format'

describe('format helpers', () => {
  it('formats empty or invalid numbers as placeholders', () => {
    expect(formatNumber(null)).toBe('--')
    expect(formatNumber(Number.NaN)).toBe('--')
  })

  it('formats percent with a positive sign', () => {
    expect(formatPercent(1.235)).toBe('+1.24%')
    expect(formatPercent(-1.235)).toBe('-1.24%')
  })

  it('formats date time in Asia/Shanghai', () => {
    expect(formatDateTime('2026-05-14T12:00:00.000Z')).toContain('20:00:00')
  })

  it('formats relative time buckets', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-14T12:00:00.000Z'))

    expect(formatRelativeTime('2026-05-14T11:59:45.000Z')).toBe('15 秒前')
    expect(formatRelativeTime('2026-05-14T11:45:00.000Z')).toBe('15 分钟前')
    expect(formatRelativeTime('2026-05-14T09:00:00.000Z')).toBe('3 小时前')
    expect(formatRelativeTime('2026-05-12T12:00:00.000Z')).toBe('2 天前')

    vi.useRealTimers()
  })
})
