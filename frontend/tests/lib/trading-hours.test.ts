import { describe, it, expect } from 'vitest'
import { getCurrentSession } from '@/lib/trading-hours'

describe('getCurrentSession', () => {
  it('returns a valid session string', () => {
    const session = getCurrentSession()
    expect(['day', 'night', 'closed']).toContain(session)
  })

  it('returns day for noon time', () => {
    const noon = new Date('2026-05-22T12:00:00+08:00')
    expect(getCurrentSession(undefined, noon)).toBe('day')
  })

  it('returns night for 22:00', () => {
    const late = new Date('2026-05-22T22:00:00+08:00')
    expect(getCurrentSession(undefined, late)).toBe('night')
  })

  it('returns closed for 03:00', () => {
    const early = new Date('2026-05-22T03:00:00+08:00')
    expect(getCurrentSession(undefined, early)).toBe('closed')
  })

  it('returns closed for 17:00 (between day and night)', () => {
    const evening = new Date('2026-05-22T17:00:00+08:00')
    expect(getCurrentSession(undefined, evening)).toBe('closed')
  })

  it('returns night for 01:30 (cross-day night session)', () => {
    const earlyNight = new Date('2026-05-22T01:30:00+08:00')
    expect(getCurrentSession(undefined, earlyNight)).toBe('night')
  })
})
