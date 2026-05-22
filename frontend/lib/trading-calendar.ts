/**
 * 国内期货交易日历（2025-2026）
 * 覆盖六大交易所：上期所、大商所、郑商所、中金所、能源中心、广期所
 *
 * 注意：此为前端静态日历，精确度覆盖主要节假日。
 * 若遇临时休市（如台风、系统故障），需后端动态推送。
 */

export interface TradingDayInfo {
  date: string // YYYY-MM-DD
  isTradingDay: boolean
  isHoliday: boolean
  holidayName?: string
  hasDaySession: boolean
  hasNightSession: boolean
}

// 2025 年节假日
const HOLIDAYS_2025: Record<string, string> = {
  '2025-01-01': '元旦',
  '2025-01-28': '春节',
  '2025-01-29': '春节',
  '2025-01-30': '春节',
  '2025-01-31': '春节',
  '2025-02-01': '春节',
  '2025-02-02': '春节',
  '2025-02-03': '春节',
  '2025-02-04': '春节',
  '2025-04-04': '清明节',
  '2025-04-05': '清明节',
  '2025-04-06': '清明节',
  '2025-05-01': '劳动节',
  '2025-05-02': '劳动节',
  '2025-05-03': '劳动节',
  '2025-05-04': '劳动节',
  '2025-05-05': '劳动节',
  '2025-05-31': '端午节',
  '2025-06-01': '端午节',
  '2025-06-02': '端午节',
  '2025-10-01': '国庆节',
  '2025-10-02': '国庆节',
  '2025-10-03': '国庆节',
  '2025-10-04': '国庆节',
  '2025-10-05': '国庆节',
  '2025-10-06': '国庆节',
  '2025-10-07': '国庆节',
  '2025-10-08': '国庆节',
}

// 2026 年节假日
const HOLIDAYS_2026: Record<string, string> = {
  '2026-01-01': '元旦',
  '2026-01-02': '元旦',
  '2026-02-16': '春节',
  '2026-02-17': '春节',
  '2026-02-18': '春节',
  '2026-02-19': '春节',
  '2026-02-20': '春节',
  '2026-02-21': '春节',
  '2026-02-22': '春节',
  '2026-02-23': '春节',
  '2026-04-04': '清明节',
  '2026-04-05': '清明节',
  '2026-04-06': '清明节',
  '2026-05-01': '劳动节',
  '2026-05-02': '劳动节',
  '2026-05-03': '劳动节',
  '2026-05-04': '劳动节',
  '2026-05-05': '劳动节',
  '2026-06-19': '端午节',
  '2026-06-20': '端午节',
  '2026-06-21': '端午节',
  '2026-10-01': '国庆节',
  '2026-10-02': '国庆节',
  '2026-10-03': '国庆节',
  '2026-10-04': '国庆节',
  '2026-10-05': '国庆节',
  '2026-10-06': '国庆节',
  '2026-10-07': '国庆节',
  '2026-10-08': '国庆节',
}

const ALL_HOLIDAYS: Record<string, string> = { ...HOLIDAYS_2025, ...HOLIDAYS_2026 }

function isWeekend(date: Date): boolean {
  const day = date.getDay()
  return day === 0 || day === 6
}

function formatDate(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function getTradingDayInfo(date?: Date): TradingDayInfo {
  const target = date ?? new Date()
  const dateStr = formatDate(target)
  const holidayName = ALL_HOLIDAYS[dateStr]
  const isHoliday = !!holidayName
  const weekend = isWeekend(target)
  const isTradingDay = !isHoliday && !weekend

  return {
    date: dateStr,
    isTradingDay,
    isHoliday,
    holidayName,
    hasDaySession: isTradingDay,
    hasNightSession: isTradingDay,
  }
}

export function isMarketClosedToday(): boolean {
  return !getTradingDayInfo().isTradingDay
}

export function getMarketStatusMessage(date?: Date): string | null {
  const info = getTradingDayInfo(date)
  if (info.isHoliday) {
    return `今日为${info.holidayName}休市，显示数据为上一交易日收盘数据`
  }
  if (!info.isTradingDay) {
    return '今日周末休市，显示数据为上一交易日收盘数据'
  }
  return null
}
