import { describe, it, expect } from 'vitest'
import {
  formatNumber,
  formatInteger,
  formatPercent,
  formatDateTime,
  getChangeTone,
} from '@/lib/format'

describe('formatNumber', () => {
  it('formats a normal number with default 2 digits', () => {
    expect(formatNumber(1234.5)).toBe('1,234.50')
  })

  it('formats a normal number with custom digits', () => {
    expect(formatNumber(1234.5678, 4)).toBe('1,234.5678')
  })

  it('returns -- for null', () => {
    expect(formatNumber(null)).toBe('--')
  })

  it('returns -- for undefined', () => {
    expect(formatNumber(undefined)).toBe('--')
  })

  it('returns -- for NaN', () => {
    expect(formatNumber(NaN)).toBe('--')
  })

  it('returns -- for Infinity', () => {
    expect(formatNumber(Infinity)).toBe('--')
  })

  it('formats zero correctly', () => {
    expect(formatNumber(0)).toBe('0.00')
  })

  it('formats negative numbers', () => {
    expect(formatNumber(-99.99)).toBe('-99.99')
  })
})

describe('formatInteger', () => {
  it('formats a normal integer', () => {
    expect(formatInteger(1234567)).toBe('1,234,567')
  })

  it('truncates decimals', () => {
    expect(formatInteger(1234.99)).toBe('1,235')
  })

  it('returns -- for null', () => {
    expect(formatInteger(null)).toBe('--')
  })
})

describe('formatPercent', () => {
  it('formats positive value with + sign', () => {
    expect(formatPercent(1.25)).toBe('+1.25%')
  })

  it('formats negative value without extra sign', () => {
    expect(formatPercent(-0.5)).toBe('-0.50%')
  })

  it('formats zero', () => {
    expect(formatPercent(0)).toBe('0.00%')
  })

  it('returns -- for null', () => {
    expect(formatPercent(null)).toBe('--')
  })
})

describe('formatDateTime', () => {
  it('formats ISO string to zh-CN date time', () => {
    const result = formatDateTime('2026-05-14T08:30:00.000Z')
    expect(result).toContain('05/14')
    expect(result).toContain('16:30')
  })

  it('returns -- for null', () => {
    expect(formatDateTime(null)).toBe('--')
  })

  it('returns -- for undefined', () => {
    expect(formatDateTime(undefined)).toBe('--')
  })

  it('returns -- for invalid date string', () => {
    expect(formatDateTime('not-a-date')).toBe('--')
  })
})

describe('getChangeTone', () => {
  it('returns up for positive value', () => {
    expect(getChangeTone(1)).toBe('up')
  })

  it('returns up for zero', () => {
    expect(getChangeTone(0)).toBe('up')
  })

  it('returns down for negative value', () => {
    expect(getChangeTone(-0.01)).toBe('down')
  })

  it('returns up for null (default to 0)', () => {
    expect(getChangeTone(null)).toBe('up')
  })

  it('returns up for undefined (default to 0)', () => {
    expect(getChangeTone(undefined)).toBe('up')
  })
})
