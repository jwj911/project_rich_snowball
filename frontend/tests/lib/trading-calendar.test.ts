import { describe, it, expect } from 'vitest'
import { getTradingDayInfo, isMarketClosedToday, getMarketStatusMessage } from '@/lib/trading-calendar'

describe('getTradingDayInfo', () => {
  it('marks weekend as non-trading', () => {
    const saturday = new Date('2026-05-23') // Saturday
    const info = getTradingDayInfo(saturday)
    expect(info.isTradingDay).toBe(false)
    expect(info.isHoliday).toBe(false)
  })

  it('marks holiday as non-trading with name', () => {
    const nationalDay = new Date('2025-10-01')
    const info = getTradingDayInfo(nationalDay)
    expect(info.isTradingDay).toBe(false)
    expect(info.isHoliday).toBe(true)
    expect(info.holidayName).toBe('国庆节')
  })

  it('marks weekday as trading day', () => {
    const weekday = new Date('2026-05-22') // Friday
    const info = getTradingDayInfo(weekday)
    expect(info.isTradingDay).toBe(true)
    expect(info.isHoliday).toBe(false)
    expect(info.hasDaySession).toBe(true)
    expect(info.hasNightSession).toBe(true)
  })
})

describe('isMarketClosedToday', () => {
  it('returns boolean', () => {
    expect(typeof isMarketClosedToday()).toBe('boolean')
  })
})

describe('getMarketStatusMessage', () => {
  it('returns null on trading day', () => {
    const weekday = new Date('2026-05-22')
    expect(getMarketStatusMessage(weekday)).toBeNull()
  })

  it('returns holiday message on holiday', () => {
    const holiday = new Date('2025-10-01')
    const msg = getMarketStatusMessage(holiday)
    expect(msg).toContain('国庆节')
    expect(msg).toContain('休市')
  })

  it('returns weekend message on weekend', () => {
    const weekend = new Date('2026-05-23')
    const msg = getMarketStatusMessage(weekend)
    expect(msg).toContain('周末')
    expect(msg).toContain('休市')
  })
})
