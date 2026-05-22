export type MarketSession = 'day' | 'night' | 'closed'

interface TradingHours {
  day: { start: string; end: string }
  night?: { start: string; end: string }
}

const DEFAULT_HOURS: TradingHours = {
  day: { start: '09:00', end: '15:00' },
  night: { start: '21:00', end: '02:30' },
}

function timeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}

export function getCurrentSession(hours: TradingHours = DEFAULT_HOURS, now?: Date): MarketSession {
  const current = now ?? new Date()
  const timeStr = current.toLocaleTimeString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

  const currentMinutes = timeToMinutes(timeStr)
  const dayStart = timeToMinutes(hours.day.start)
  const dayEnd = timeToMinutes(hours.day.end)

  if (currentMinutes >= dayStart && currentMinutes <= dayEnd) {
    return 'day'
  }

  if (hours.night) {
    const nightStart = timeToMinutes(hours.night.start)
    const nightEnd = timeToMinutes(hours.night.end)

    if (nightStart < nightEnd) {
      if (currentMinutes >= nightStart && currentMinutes <= nightEnd) {
        return 'night'
      }
    } else {
      // 跨天（如 21:00-02:30）
      if (currentMinutes >= nightStart || currentMinutes <= nightEnd) {
        return 'night'
      }
    }
  }

  return 'closed'
}
